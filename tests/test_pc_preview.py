"""在线完整前缀预览与停止后重算，使用实际CNN及合成串口原码。"""
from pathlib import Path
import importlib.util
import time

import numpy as np
import pytest

from hardware.realtime import Acquisition, Session

pytestmark = pytest.mark.skipif(importlib.util.find_spec('torch') is None,
                               reason='真实CNN在线预览需要PyTorch CPU环境')


def test_real_preview_then_final_on_stop(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / 'ai_model/vendor/ecg_edge/model/inference/examples/synthetic500.csv'
    values = np.loadtxt(source, delimiter=',')[:5000]
    codes = np.rint(values / (2420 / (6 * 8388608))).astype(np.int64) + 8388608
    body = b''.join(b'\xaa\xbb' + b''.join((8388608).to_bytes(4, 'big') + int(v).to_bytes(4, 'big')
                    for v in codes[i:i + 4]) for i in range(0, len(codes), 4))
    class Serial:
        def __init__(self, *_): self.offset = 0
        def read(self, count):
            block = body[self.offset:self.offset + count]
            self.offset += len(block)
            return block
        def close(self): pass
    # Drain the synthetic burst before starting inference so this test checks the
    # 10-second prefix rather than a scheduler-dependent initial 4-second prefix.
    def start_after_capture(self):
        self.capture_thread.start()
        deadline = time.monotonic() + 3
        while len(self.values) < 5000 and time.monotonic() < deadline:
            time.sleep(.01)
        self.analysis_thread.start()
    monkeypatch.setattr(Session, 'start', start_after_capture)
    manager = Acquisition()
    capture = manager.start('preview', 'COM9', 115200, 'document_34', 'cnn', tmp_path, serial_factory=Serial)
    session = manager.get('preview', capture['id'])
    try:
        deadline = time.monotonic() + 25
        while session.prediction is None and time.monotonic() < deadline:
            time.sleep(.02)
        preview = session.snapshot()
        assert preview['prediction']['preview'] is True
        assert preview['prediction']['status'] == 'classified'
        assert all(b['decision_sample500'] < preview['analysis_samples'] - 1250
                   for b in preview['prediction']['beats']['items'])
        session.stop()
        session.analysis_thread.join(timeout=25)
        final = session.snapshot()
        assert final['prediction']['preview'] is False
        assert final['analysis_samples'] == 5000
        assert final['prediction']['beats']['count'] >= preview['prediction']['beats']['count']
    finally:
        manager.shutdown()
