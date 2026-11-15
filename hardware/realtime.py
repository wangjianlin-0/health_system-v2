"""ADS1292R蓝牙串口会话：只接收、保留原始数据、错误后不跨段续接。"""
from collections import deque
from pathlib import Path
import csv
import json
import os
import threading
import time
import uuid

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

from hardware.vendor.ads1292 import decode_vendor_frame, VENDOR_FORMATS
from hardware.vendor.windows_serial import WindowsSerial
from signal_processing.python.ecg_preprocessing import ADS_LSB_MV


def ports():
    if os.name != 'nt':
        return []
    import winreg
    result = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DEVICEMAP\SERIALCOMM') as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                label, port, _ = winreg.EnumValue(key, i)
                result.append(dict(port=port, label=label))
    except FileNotFoundError:
        pass
    return sorted(result, key=lambda row: row['port'])


class Frames:
    """初始三帧对齐；锁定后严格检查，不静默重同步或填补丢样。"""
    def __init__(self, format='document_34'):
        if format not in VENDOR_FORMATS:
            raise ValueError('必须选择document_34或source_10')
        self.format = format
        self.size = 2 + 8 * VENDOR_FORMATS[format]
        self.buffer = bytearray()
        self.locked = False
        self.skipped = 0

    def feed(self, data):
        self.buffer.extend(data)
        if not self.locked:
            candidates = []
            for start in range(len(self.buffer) - self.size * 3 + 1):
                if self.buffer[start:start + 2] != b'\xaa\xbb':
                    continue
                try:
                    for k in range(3):
                        at = start + k * self.size
                        decode_vendor_frame(bytes(self.buffer[at:at + self.size]), format=self.format)
                    candidates.append(start)
                except ValueError:
                    continue
            if len({p % self.size for p in candidates}) > 1:
                raise ValueError('初始帧边界不唯一，请核对协议')
            if not candidates:
                if len(self.buffer) >= 4096:
                    raise ValueError('找不到连续三帧，请核对蓝牙端口、波特率和10/34字节格式')
                return []
            self.skipped = candidates[0]
            del self.buffer[:self.skipped]
            self.locked = True
        rows = []
        while len(self.buffer) >= self.size:
            rows.extend(decode_vendor_frame(bytes(self.buffer[:self.size]), format=self.format))
            del self.buffer[:self.size]
        return rows


class Session:
    def __init__(self, owner, port, baud, format, model, directory, *, serial_factory=WindowsSerial):
        self.id = uuid.uuid4().hex
        self.owner, self.port, self.baud = owner, port, baud
        self.model, self.format = model, format
        self.directory = Path(directory) / owner / self.id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.changed = threading.Event()
        self.done = threading.Event()
        self.values = []
        self.display = deque(maxlen=2500)
        self.status, self.error = 'starting', None
        self.prediction, self.analysis_samples = None, 0
        self.task = None
        self.received_bytes = 0
        self.parser = Frames(format)
        self.sos = butter(2, [0.5, 40], btype='bandpass', fs=500, output='sos')
        self.zi = None
        self.created_at = time.time()
        self.reader = None
        try:
            self.reader = serial_factory(port, baud)
            self.raw = (self.directory / 'capture.bin').open('xb')
            self.csv_file = (self.directory / 'samples.csv').open('x', encoding='utf-8', newline='')
            self.writer = csv.writer(self.csv_file)
            self.writer.writerow(['timestamp(s)', 'resp_raw', 'ecg_raw'])
        except Exception:
            if self.reader:
                self.reader.close()
            if hasattr(self, 'raw'):
                self.raw.close()
            raise
        self.status = 'running'
        self.capture_thread = threading.Thread(target=self._capture, daemon=True, name='ecg-capture')
        self.analysis_thread = threading.Thread(target=self._analyze, daemon=True, name='ecg-preview')

    def start(self):
        self.capture_thread.start()
        self.analysis_thread.start()

    def _capture(self):
        last_data = time.monotonic()
        try:
            while not self.stop_event.is_set():
                data = self.reader.read(4096)
                if not data:
                    if time.monotonic() - last_data > 5:
                        raise TimeoutError('5秒未收到数据，请检查蓝牙连接；重新连接需新建会话')
                    self.stop_event.wait(.01)
                    continue
                last_data = time.monotonic()
                self.raw.write(data)
                self.raw.flush()
                self.received_bytes += len(data)
                pairs = self.parser.feed(data)
                if not pairs:
                    continue
                converted = [ecg * ADS_LSB_MV for _, ecg in pairs]
                if self.zi is None:
                    self.zi = sosfilt_zi(self.sos) * converted[0]
                filtered, self.zi = sosfilt(self.sos, converted, zi=self.zi)
                with self.lock:
                    if len(self.values) + len(converted) > 200000:
                        self.status = 'limit_reached'
                        break
                    for (resp, ecg), value, view in zip(pairs, converted, filtered):
                        index = len(self.values)
                        self.writer.writerow([index / 500, resp + 8388608, ecg + 8388608])
                        self.values.append(value)
                        self.display.append(dict(t=index / 500, v=float(view), raw=value))
                    self.csv_file.flush()
                self.changed.set()
        except Exception as exc:
            self.status, self.error = 'error', str(exc)
        finally:
            try:
                self.reader.close()
            except OSError as exc:
                self.status, self.error = 'error', str(exc)
            self.raw.close()
            self.csv_file.close()
            if self.status == 'running':
                self.status = 'stopped'
            self.done.set()
            self.changed.set()
            self._metadata()

    def _analyze(self):
        from ai_model.inference.edge_adapter import EdgeClassifier
        classifier = EdgeClassifier(self.model)
        previous, last_run = 0, 0.
        while True:
            self.changed.wait(.5)
            self.changed.clear()
            final = self.done.is_set()
            with self.lock:
                count = len(self.values)
                if count < 2000 or (count == previous and not (final and self.prediction and self.prediction.get('preview'))):
                    if final:
                        return
                    continue
                if not final and (count - previous < 2000 or time.monotonic() - last_run < 4):
                    continue
                values = list(self.values)
            previous, last_run = count, time.monotonic()
            prediction = classifier.predict(dict(waveform_raw_mV=values, sample_rate_hz=500, unit='mV'))
            # 每次重算从会话起点到当前的全部前缀；不把独立分块当连续推理。
            # 在线仅显示至少滞后2.5秒的稳定事件，末尾未完成心拍留到停止后整段复算。
            if not final and prediction.get('beats'):
                items = [b for b in prediction['beats']['items']
                         if b.get('decision_sample500', b['waveform_ready_sample500']) < count - 1250]
                counts = {label: sum(b['valid'] and b['label'] == label for b in items)
                          for label in prediction['classes']}
                prediction['beats'] = dict(items=items, count=len(items), by_type=counts,
                    classified_count=sum(counts.values()), unclassified_count=len(items) - sum(counts.values()))
                positions = [b['r_sample500'] for b in items]
                rr = np.diff(positions) / 500
                prediction['heart_rate'] = dict(bpm=round(float(60 / np.median(rr)), 2)) if len(rr) else None
                prediction['label'] = '；'.join(f'{k}类{v}拍' for k, v in counts.items()) if sum(counts.values()) else None
                prediction['status'] = 'classified' if sum(counts.values()) else 'no_valid_beats'
            prediction['preview'] = not final
            with self.lock:
                self.prediction, self.analysis_samples = prediction, count
            if final:
                self._metadata()
                return

    def _metadata(self):
        try:
            (self.directory / 'session.json').write_text(json.dumps(self.snapshot(), ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass

    def snapshot(self):
        with self.lock:
            prediction = None
            if self.prediction:
                prediction = dict(self.prediction)
                if prediction.get('beats'):
                    prediction['beats'] = dict(prediction['beats'], items=prediction['beats']['items'][-100:])
            return dict(id=self.id, status=self.status, error=self.error, port=self.port,
                baud=self.baud, format=self.format, model=self.model, sample_rate_hz=500,
                sample_count=len(self.values), duration_sec=len(self.values) / 500,
                received_bytes=self.received_bytes, skipped_initial_bytes=self.parser.skipped,
                pending_bytes=len(self.parser.buffer), source_dropped_samples=None,
                continuity_verified=False, created_at=self.created_at, points=list(self.display),
                prediction=prediction, analysis_samples=self.analysis_samples,
                analysis_pending=self.analysis_thread.is_alive(), task=self.task)

    def stop(self):
        self.stop_event.set()
        self.capture_thread.join(timeout=3)
        if self.capture_thread.is_alive():
            raise RuntimeError('采集线程尚未结束')
        return self.snapshot()

    def signal(self):
        if not self.done.is_set():
            raise ValueError('请先停止采集')
        if not self.values:
            raise ValueError('本次没有收到完整样本')
        return dict(samples=list(self.values), sample_rate_hz=500, unit='mV',
            lead='ads1292r_ch2', source='ads1292r_bluetooth', model_type=self.model,
            acquisition=dict(session_id=self.id, format=self.format, port=self.port, baud=self.baud,
                source_dropped_samples=None, continuity_verified=False, error=self.error,
                pending_bytes=len(self.parser.buffer), skipped_initial_bytes=self.parser.skipped,
                conversion=dict(vref_v=2.42, gain=6, adc_denominator=8388608, calibrated=False),
                display_filter='causal_0.5_40Hz_not_model_input'))


class Acquisition:
    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = {}

    def start(self, owner, port, baud, format, model, directory, *, serial_factory=WindowsSerial):
        if model not in ('cnn', 'hgb'):
            raise ValueError('实时采集请选择CNN或HGB')
        with self.lock:
            if any(not s.done.is_set() for s in self.sessions.values()):
                raise ValueError('采集端口正被使用，请先结束当前会话')
            if any(s.owner == owner and s.values and s.task is None for s in self.sessions.values()):
                raise ValueError('请先保存上一轮采集再开始新会话')
            if len(self.sessions) >= 32:
                for sid, session in list(self.sessions.items()):
                    if session.done.is_set() and (session.task or not session.values) and not session.analysis_thread.is_alive():
                        del self.sessions[sid]
                        break
                else:
                    raise ValueError('会话数量达到上限，请保存后重启服务')
            session = Session(owner, port, baud, format, model, directory, serial_factory=serial_factory)
            self.sessions[session.id] = session
            session.start()
            return session.snapshot()

    def get(self, owner, sid):
        with self.lock:
            session = self.sessions.get(sid)
            if not session or session.owner != owner:
                raise LookupError('采集会话不存在或无权访问')
            return session

    def shutdown(self):
        with self.lock:
            for session in self.sessions.values():
                session.stop()


acquisition = Acquisition()
