from ai_model.inference.factory import load_classifier, predict


def test_ecgfounder_requires_published_weights():
    model = load_classifier('ecgfounder')
    result = predict(model, {'waveform': [0.0], 'sample_rate_hz': 500})
    assert result['status'] == 'model_unavailable'
    assert result['label'] is None
    assert '导联' in result['explanation'] or '权重' in result['explanation']
