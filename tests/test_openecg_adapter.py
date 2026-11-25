from ai_model.inference.openecg_adapter import OpenEcgClassifier


def _adapter(reports):
    adapter = OpenEcgClassifier.__new__(OpenEcgClassifier)
    adapter.model_asset = {'backend': 'onnxruntime', 'sha256': 'frozen'}
    codec = object()
    adapter._codec = lambda: codec
    class Api:
        def __init__(self):
            self.reports = iter(reports)
        def report(self, signal, fs, model):
            assert len(signal) == 5000 and fs == 500 and model is codec
            return next(self.reports)
    adapter.openecg = Api()
    return adapter


def _report(label, bpm, confidence=.9):
    return {
        'rhythm': {'label': label, 'confidence': confidence, 'distribution': {label: confidence}},
        'heart_rate': {'bpm': bpm}, 'beats': {'events': []}, 'intervals_ms': {}, 'flags': [],
    }


def test_long_record_is_fully_windowed_and_dimensions_are_split(monkeypatch):
    monkeypatch.setenv('ECG_RHYTHM_STEP_SECONDS', '5')
    adapter = _adapter([_report('sinus', 70), _report('bbb', 72), _report('afib', 90),
                        _report('afib', 88), _report('sinus', 75)])
    result = adapter.predict({'waveform': [0.0] * 15000, 'sample_rate_hz': 500})
    assert result['analysis_scope'] == {
        'duration_seconds': 30.0, 'window_seconds': 10, 'step_seconds': 5,
        'windows_analyzed': 5, 'full_record_covered': True,
    }
    assert result['rhythm_dimensions']['rhythm']['primary'] == 'afib'
    assert result['rhythm_dimensions']['conduction']['flags'] == ['bbb']
    assert result['heart_rate']['bpm'] == 75.0
    assert result['rhythm_events'][2]['label'] == 'afib'
    assert result['rhythm_events'][2]['start_sec'] == 10.0
    assert result['rhythm_events'][2]['end_sec'] == 25.0
    assert result['rhythm_events'][2]['window_count'] == 2
    assert result['model_asset']['backend'] == 'onnxruntime'


def test_tail_window_covers_non_aligned_record(monkeypatch):
    monkeypatch.setenv('ECG_RHYTHM_STEP_SECONDS', '5')
    adapter = _adapter([_report('sinus', 70), _report('sinus', 70), _report('sinus', 70)])
    result = adapter.predict({'waveform': [0.0] * 6250, 'sample_rate_hz': 500})
    assert [(x['start_sec'], x['end_sec']) for x in result['rhythm_windows']] == [
        (0.0, 10.0), (2.5, 12.5), (2.5, 12.5)
    ][:len(result['rhythm_windows'])]
    assert result['rhythm_windows'][-1]['end_sec'] == 12.5


def test_short_record_does_not_initialize_onnx():
    adapter = OpenEcgClassifier.__new__(OpenEcgClassifier)
    adapter.model_asset = {'backend': 'onnxruntime'}
    adapter._codec = lambda: (_ for _ in ()).throw(AssertionError('must stay lazy'))
    result = adapter.predict({'waveform': [0.0] * 1200, 'sample_rate_hz': 500})
    assert result['status'] == 'skipped_quality'
