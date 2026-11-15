"""CNN-H27 / HGB-v92电脑适配；固定fold0，保留逐拍概率与未知状态。"""
from pathlib import Path
import importlib.util
import json
import math
import os
import statistics
import subprocess
import sys
import time


class EdgeClassifier:
    def __init__(self, kind='cnn'):
        if kind not in ('cnn', 'hgb'):
            raise ValueError('模型须为cnn或hgb')
        self.kind = kind
        self.model_version = 'CNN-H27-fold0' if kind == 'cnn' else 'HGB-v92-fold0'

    def predict(self, processed):
        base = dict(model_version=self.model_version, task_type='beat_level',
                    execution_location='host_pc', qualified=False, confidence=None,
                    preprocess='hp05', fold=0)

        def unavailable(message):
            return dict(base, status='model_unavailable', label=None, explanation=message)

        values = processed.get('waveform_raw_mV', processed.get('waveform'))
        if processed.get('sample_rate_hz') != 500 or processed.get('unit') != 'mV':
            return unavailable('CNN/HGB要求500 Hz单导联原始mV，不自动修改采样率或单位。')
        if not isinstance(values, list) or not 1000 <= len(values) <= 200000:
            return unavailable('模型输入要求2秒以上的完整记录，最多200000点。')
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            return unavailable('模型输入存在非有限值。')
        if self.kind == 'cnn' and importlib.util.find_spec('torch') is None:
            return unavailable('CNN 推理依赖 PyTorch，当前 Python 环境未安装 torch。')
        env = dict(os.environ)
        env.update({name: '4' for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')})
        started = time.perf_counter()
        try:
            response = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-B',
                str(Path(__file__).with_name('edge_worker.py'))],
                input=json.dumps(dict(model=self.kind, samples=values), allow_nan=False).encode('utf-8'),
                capture_output=True, timeout=180, env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if response.returncode:
                import logging
                logging.getLogger(__name__).error('本地模型失败: %s', response.stderr.decode('utf-8', errors='replace')[-2000:])
                return unavailable('模型依赖或资产校验失败。请运行 scripts/check_pc_models.py 查看检查结果。')
            raw = json.loads(response.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return unavailable('电脑模型进程失败或超时，未生成分类。')
        beats = raw['beats']
        classes = raw['classes']
        counts = {label: sum(b['valid'] and b['label'] == label for b in beats) for label in classes}
        valid = sum(counts.values())
        positions = [b['r_sample500'] for b in beats]
        rr = [(b - a) / 500 for a, b in zip(positions, positions[1:]) if b > a]
        rates = [60 / interval for interval in rr]
        heart_rate = (dict(bpm=round(60 / statistics.median(rr), 2),
            min_bpm=round(min(rates), 2), max_bpm=round(max(rates), 2)) if rates else None)
        for beat in beats:
            beat['confidence'] = max(beat['probabilities']) if beat['probabilities'] else None
        text = '；'.join(f'{name}类{count}拍' for name, count in counts.items()) if valid else None
        return dict(base, status='classified' if valid else 'no_valid_beats', label=text,
            model_sha256=raw['model_sha256'], classes=classes, heart_rate=heart_rate,
            clipped_samples=raw['clipped_samples'], inference_ms=round((time.perf_counter() - started) * 1000, 1),
            timing_scope='电脑子进程启动、资产校验、整段检测/特征与分类总耗时',
            beats=dict(count=len(beats), classified_count=valid, unclassified_count=len(beats) - valid,
                       by_type=counts, items=beats),
            explanation='研究模型逐拍结果。N不表示健康；HGB的VF为V/E/F合并，非心室颤动。概率不等于临床可靠度。')
