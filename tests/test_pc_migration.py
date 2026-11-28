import csv
import io
import struct
import time
from math import pi, sin
from pathlib import Path

import pytest

from ai_model.inference.edge_adapter import EdgeClassifier
from hardware.realtime import Acquisition, Frames, Session
from signal_processing.python.ecg_preprocessing import parse_csv
from test_api_flow import account, wait_task


def frame(format='document_34', code=1234):
    count = 4 if format == 'document_34' else 1
    return b'\xaa\xbb' + b''.join(struct.pack('>II', 8388608 - i, 8388608 + code + i) for i in range(count))


@pytest.mark.parametrize('format,count', [('document_34', 4), ('source_10', 1)])
def test_fragmented_bluetooth_alignment_and_strict_error(format, count):
    parser = Frames(format)
    data = b'noise' + frame(format) * 6
    rows = []
    for i in range(0, len(data), 7):
        rows.extend(parser.feed(data[i:i + 7]))
    assert len(rows) == count * 6
    assert rows[0] == (0, 1234)
    assert parser.skipped == 5
    with pytest.raises(ValueError):
        parser.feed(b'\x00' + frame(format))


def test_bluetooth_capture_ownership_and_persistence(tmp_path):
    class Serial:
        def __init__(self, *_):
            self.count = 0
            self.closed = False
        def read(self, _):
            self.count += 1
            return frame() * 4 if self.count == 1 else b''
        def close(self):
            self.closed = True
    manager = Acquisition()
    capture = manager.start('owner', 'COM9', 115200, 'document_34', 'hgb', tmp_path, serial_factory=Serial)
    session = manager.get('owner', capture['id'])
    deadline = time.monotonic() + 2
    while not session.values and time.monotonic() < deadline:
        time.sleep(.01)
    with pytest.raises(LookupError):
        manager.get('other', capture['id'])
    with pytest.raises(ValueError):
        manager.start('other', 'COM8', 115200, 'document_34', 'cnn', tmp_path, serial_factory=Serial)
    manager.shutdown()
    assert session.reader.closed
    assert [point['respiration'] for point in session.snapshot()['points'][:4]] == [0, -1, -2, -3]
    signal = session.signal()
    assert len(signal['samples']) == 16
    assert signal['samples'][0] == pytest.approx(1234 * 2420 / (6 * 8388608))
    assert signal['respiration_waveform'] == [1.5, 0.5, -0.5, -1.5] * 4
    assert signal['respiration_sample_rate_hz'] == 500
    assert signal['acquisition']['source_dropped_samples'] is None
    assert (session.directory / 'capture.bin').read_bytes() == frame() * 4
    assert '8389842' in (session.directory / 'samples.csv').read_text()


def test_explicit_models_keep_input_contract():
    for kind in ('cnn', 'hgb'):
        result = EdgeClassifier(kind).predict(dict(waveform=[0.] * 1000, unit='mV', sample_rate_hz=250))
        assert result['status'] == 'model_unavailable'
        assert result['label'] is None


def test_csv_model_selection_and_reanalysis_persist(client, monkeypatch):
    import ai_model.pipeline as pipeline
    class Model:
        def __init__(self, kind):
            self.kind = kind
        def predict(self, _):
            return dict(status='classified', label=self.kind, confidence=None, model_version=self.kind)
    monkeypatch.setattr(pipeline, 'load_classifier', Model)
    headers = account(client, 'pc-course')
    text = 'value\n' + '\n'.join(str((i % 20) * .01) for i in range(1500))
    response = client.post('/api/v1/analyze/ecg', headers=headers,
        files={'file': ('synthetic.csv', text)}, data={'sample_rate_hz': 500, 'model_type': 'cnn'})
    assert response.status_code == 202
    task = wait_task(client, headers, response.json()['id'])
    record = task['record']
    assert record['result']['prediction']['label'] == 'cnn'
    response = client.post(f"/api/v1/records/{record['id']}/reanalyze", headers=headers, json={'model_type': 'hgb'})
    assert response.status_code == 202
    assert wait_task(client, headers, response.json()['id'])['record']['result']['prediction']['label'] == 'hgb'
    assert client.post('/api/v1/analyze/ecg', headers=headers,
        files={'file': ('synthetic.csv', text)}, data={'sample_rate_hz': 500, 'model_type': 'bad'}).status_code == 400
    assert client.get('/api/v1/acquisition/ports').status_code == 401


def test_no_empty_session_blocks_reconnection(tmp_path):
    manager = Acquisition()
    class EmptySerial:
        def __init__(self, *_): pass
        def read(self, _): return b''
        def close(self): pass
    capture = manager.start('owner', 'COM9', 115200, 'source_10', 'cnn', tmp_path, serial_factory=EmptySerial)
    manager.get('owner', capture['id']).stop()
    manager.start('owner', 'COM9', 115200, 'source_10', 'cnn', tmp_path, serial_factory=EmptySerial)
    manager.shutdown()


def test_capture_api_save_once_and_raw_file(client, monkeypatch, tmp_path):
    from ai_model import pipeline
    from app.api import acquisition as api
    from app.services.storage import connect

    manager = Acquisition()
    monkeypatch.setattr(api, 'acquisition', manager)
    monkeypatch.setattr(Session, '_analyze', lambda self: None)
    model_result = dict(status='classified', label='normal', model_version='test',
                        heart_rate={'bpm': 75.0})
    monkeypatch.setattr(pipeline, '_rhythm_prediction', lambda _: dict(model_result))
    monkeypatch.setattr(pipeline, '_beat_prediction', lambda *_: dict(model_result))
    sample_count = 15000
    fixture = (Path(__file__).resolve().parents[1] / 'ai_model' / 'vendor' / 'ecg_edge' /
               'model' / 'inference' / 'examples' / 'synthetic500.csv')
    ecg = [float(line) for line in fixture.read_text().splitlines()[:sample_count]]
    codes = b''.join(
        struct.pack('>II', 8388608 + round(5000 * sin(2 * pi * index / 2000)),
                    8388608 + round(value * 6 * 8388608 / 2420))
        for index, value in enumerate(ecg)
    )
    frames = b''.join(b'\xaa\xbb' + codes[i:i + 32] for i in range(0, len(codes), 32))

    class Serial(io.BytesIO):
        def __init__(self, *_):
            super().__init__(frames)

    owner, other = account(client, 'capture-owner'), account(client, 'capture-other')
    # Obtain the real owner ID through the existing identity service.
    from app.services.family import authenticate
    owner_id = authenticate(owner['Authorization'].split(' ')[1])
    capture = manager.start(owner_id, 'COM9', 115200, 'document_34', 'hgb', tmp_path, serial_factory=Serial)
    sid = capture['id']
    session = manager.get(owner_id, sid)
    deadline = time.monotonic() + 5
    while len(session.values) < sample_count and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(session.values) == sample_count
    assert client.get('/api/v1/acquisition/sessions/' + sid, headers=other).status_code == 404
    assert client.post('/api/v1/acquisition/sessions/' + sid + '/save', headers=owner).status_code == 400
    assert client.post('/api/v1/acquisition/sessions/' + sid + '/stop', headers=owner).status_code == 200
    saved = client.post('/api/v1/acquisition/sessions/' + sid + '/save', headers=owner)
    assert saved.status_code == 202
    saved_again = client.post('/api/v1/acquisition/sessions/' + sid + '/save', headers=owner)
    assert saved_again.json()['id'] == saved.json()['id']
    task = wait_task(client, owner, saved.json()['id'])
    record = task['record']
    assert record['source'] == 'ads1292r_bluetooth'
    assert record['result']['acquisition']['continuity_verified'] is False
    assert record['result']['respiration_analysis']['rate_bpm'] == pytest.approx(15.0, abs=0.5)
    assert record['result']['respiration_waveform'] == session.signal()['respiration_waveform']
    path = '/api/v1/records/' + record['id']
    raw = client.get(path + '/raw', headers=owner)
    assert raw.status_code == 200
    assert 'resp_raw,ecg_raw' in raw.text

    exported = client.get(path + '/export', headers=owner)
    assert exported.status_code == 200
    row = next(csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))
    assert float(row['heart_rate_bpm']) == 75
    assert float(row['respiration_rate_bpm']) == record['result']['respiration_analysis']['rate_bpm']
    assert parse_csv(exported.text, 500)['respiration_waveform'] == record['result']['respiration_waveform']
    assert row['respiration_unit'] == 'adc_counts_relative'

    # Simulate a saved task from before the respiratory channel was forwarded.
    with connect() as db:
        db.execute("UPDATE task_inputs SET payload=json_remove(payload, '$.respiration_waveform', "
                   "'$.respiration_sample_rate_hz', '$.respiration_unit') WHERE task_id=?", (task['id'],))
    reanalysis = client.post(path + '/reanalyze', headers=owner, json={})
    assert reanalysis.status_code == 202
    updated = wait_task(client, owner, reanalysis.json()['id'])['record']
    assert updated['result']['respiration_analysis'] == record['result']['respiration_analysis']
    manager.shutdown()
