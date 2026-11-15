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


def test_hardware_csv_converts_raw_ecg_column():
    text = (
        'timestamp(s),resp_raw,ecg_raw,resp_filtered,ecg_filtered\n'
        '0.0,1,8388608,2,-1.5\n'
        '0.002,1,8388609,2.1,-1.2\n'
    )
    result = parse_csv(text, 500)
    assert result['source'] == 'ads1292r_csv'
    assert result['samples'] == [0.0, 2420 / (6 * 8388608)]


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


def test_llm_json_is_validated_and_audited(monkeypatch):
    import json
    import ai_model.explanation.generator as generator

    monkeypatch.setenv('ECG_EXPLANATION_PROVIDER', 'openai_compatible')
    monkeypatch.setenv('ECG_LLM_ENDPOINT', 'https://example.invalid/v1')
    monkeypatch.setenv('ECG_LLM_MODEL', 'medical-explainer')
    monkeypatch.setenv('ECG_LLM_API_KEY', 'test-key')
    answer = {
        'elderly_summary': '本次结果仅供参考。',
        'professional_interpretation': '已有JSON显示信号可分析。',
        'condition_education': [],
        'evidence': ['质量检查通过'],
        'uncertainty': ['单导联短时记录'],
        'reassurance': '请结合后续复核。',
        'next_steps': ['保存记录'],
        'measurement_guidance': [],
        'urgent_warning': '出现胸痛或晕厥时及时就医。',
        'risk_level': 'reference_only',
        'diagnosis_status': 'not_a_diagnosis',
    }

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({'choices': [{'message': {'content': json.dumps(answer, ensure_ascii=False)}}]}).encode()

    monkeypatch.setattr(generator.request, 'urlopen', lambda req, timeout: Response())
    result = generator.generate_explanation({
        'classification': {'label': 'normal'}, 'concepts': [],
        'measurements': {}, 'quality': {'status': 'basic_checks_passed'},
    })
    assert result['provider'] == 'openai_compatible'
    assert result['model'] == 'medical-explainer'
    assert result['api_called'] is True
    assert result['diagnosis_status'] == 'not_a_diagnosis'
    assert result['latency_ms'] >= 0


def test_template_adds_pvc_education_without_claiming_patient_symptoms():
    result = generate_explanation({
        'classification': {'label': 'N类55拍；V类16拍', 'task_type': 'beat_level'},
        'concepts': [], 'measurements': {}, 'quality': {'status': 'basic_checks_passed'},
        'beat_analysis': {'counts': {'normal': 55, 'pac': 0, 'pvc': 16, 'fusion': 0}},
        'rate_analysis': {'result': 'in_range', 'average_bpm': 74, 'regularity': 'regular'},
    })
    item = next(value for value in result['condition_education'] if '室性早搏' in value['condition'])
    assert item['not_patient_facts'] is True
    assert item['possible_symptoms']
    assert item['common_associations']
    assert result['elderly_summary']
    assert '本次记录' in result['elderly_summary']
    assert '室性提前心拍候选 16 拍' in result['elderly_summary']
    assert '干扰' not in result['elderly_summary']


def test_invalid_llm_json_falls_back_to_template(monkeypatch):
    import json
    import ai_model.explanation.generator as generator

    monkeypatch.setenv('ECG_EXPLANATION_PROVIDER', 'openai_compatible')
    monkeypatch.setenv('ECG_LLM_ENDPOINT', 'https://example.invalid/v1')

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({'choices': [{'message': {'content': '{"diagnosis_status":"diagnosed"}'}}]}).encode()

    monkeypatch.setattr(generator.request, 'urlopen', lambda req, timeout: Response())
    result = generator.generate_explanation({
        'classification': {'label': 'normal'}, 'concepts': [],
        'measurements': {}, 'quality': {'status': 'basic_checks_passed'},
    })
    assert result['provider'] == 'template'
    assert result['api_called'] is False
    assert 'fallback_reason' in result
