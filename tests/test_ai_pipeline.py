from ai_model.explanation.concepts import build_concepts
from ai_model.explanation.generator import generate_explanation
from signal_processing.python.ecg_preprocessing import parse_csv


def test_concepts_are_traceable():
    prediction = {
        'label': 'atrial_fibrillation',
        'confidence': 0.8,
        'heart_rate': {'bpm': 78, 'rr_cv': 0.2},
        'beats': {'vpc_count': 0},
        'flags': [],
    }
    concepts = build_concepts(prediction, {'status': 'basic_checks_passed'})
    names = {item['name'] for item in concepts}
    assert 'irregular_rr' in names
    assert all(item['evidence'] for item in concepts)


def test_noisy_signal_template_explanation():
    payload = {
        'classification': {'label': 'too_noisy'},
        'concepts': [{'label': '信号质量不足'}],
        'quality': {'status': 'insufficient', 'reasons': ['平直信号']},
    }
    result = generate_explanation(payload)
    assert result['diagnosis_status'] == 'not_a_diagnosis'
    assert result['risk_level'] == 'repeat_measurement'
    assert result['provider'] == 'template'
    assert result['api_called'] is False


def test_hardware_csv_uses_filtered_ecg_column():
    text = (
        'timestamp(s),resp_raw,ecg_raw,resp_filtered,ecg_filtered\n'
        '0.0,1,10,2,-1.5\n'
        '0.002,1,11,2.1,-1.2\n'
    )
    result = parse_csv(text, 500)
    assert result['source'] == 'hardware_csv'
    assert result['samples'] == [-1.5, -1.2]


def test_deepseek_defaults(monkeypatch):
    import ai_model.explanation.generator as generator

    monkeypatch.setenv('ECG_EXPLANATION_PROVIDER', 'deepseek')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.delenv('ECG_LLM_ENDPOINT', raising=False)
    monkeypatch.delenv('ECG_LLM_MODEL', raising=False)

    captured = {}

    def fake_urlopen(request, timeout):
        captured['url'] = request.full_url
        captured['body'] = request.data.decode('utf-8')
        raise RuntimeError('stop after request construction')

    monkeypatch.setattr(generator.request, 'urlopen', fake_urlopen)
    result = generator.generate_explanation({
        'classification': {'label': 'normal'},
        'concepts': [],
        'quality': {'status': 'basic_checks_passed'},
    })
    assert captured['url'] == 'https://api.deepseek.com/chat/completions'
    assert '"model": "deepseek-chat"' in captured['body']
    assert result['provider'] == 'template'
    assert result['api_called'] is False


def test_llm_technical_elderly_summary_is_replaced(monkeypatch):
    import ai_model.explanation.generator as generator

    monkeypatch.setenv('ECG_EXPLANATION_PROVIDER', 'deepseek')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')

    class FakeResponse:
        def read(self):
            import json
            return json.dumps({
                'choices': [{
                    'message': {
                        'content': json.dumps({
                            'elderly_summary': '本次单导联短时记录呈正常窦性节律特征，RR间期规则，未见室性早搏。',
                            'professional_interpretation': '专业解释',
                            'evidence': [],
                            'uncertainty': ['单导联短时记录'],
                            'reassurance': '请放心',
                            'next_steps': [],
                            'measurement_guidance': [],
                            'urgent_warning': '出现不适及时就医',
                            'risk_level': 'reference_only',
                            'diagnosis_status': 'not_a_diagnosis',
                        })
                    }
                }]
            }).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(generator.request, 'urlopen', lambda request, timeout: FakeResponse())
    result = generator.generate_explanation({
        'classification': {'label': 'normal'},
        'concepts': [{'label': 'RR 间期相对规则'}],
        'measurements': {'heart_rate': {'bpm': 77}},
        'quality': {'status': 'basic_checks_passed'},
    })
    assert result['api_called'] is True
    assert '单导联' not in result['elderly_summary']
    assert '窦性节律' not in result['elderly_summary']
    assert 'RR' not in result['elderly_summary']
