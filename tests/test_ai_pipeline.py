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


def test_elderly_explanation_is_warm_and_actionable(monkeypatch):
    monkeypatch.delenv('ECG_EXPLANATION_PROVIDER', raising=False)
    result = generate_explanation({
        'classification': {'label': 'normal'},
        'measurements': {'heart_rate': {'bpm': 77}},
        'concepts': [{'label': 'RR间期相对规则'}],
        'quality': {'status': 'basic_checks_passed'},
        'decision': {
            'state': 'assistive_classification',
            'can_present_classification': True,
        },
    })
    summary = result['elderly_summary']
    assert '每分钟 77 次' in summary
    assert '保存记录' in summary
    assert '医生' in summary
    assert '完全正常' not in summary
    assert '身体整体是否健康' in summary
    assert '身体健康' not in summary
    assert '窦性节律' not in summary


def test_uncertain_elderly_explanation_reassures_without_guarantees():
    from ai_model.explanation.generator import _template

    result = _template({
        'classification': {'label': None},
        'decision': {'state': 'model_uncertain'},
        'quality': {'status': 'degraded'},
        'measurement_coach': {'actions': ['坐稳并保持安静，再测一次。']},
    })
    assert '不等于身体一定有问题' in result['reassurance']
    assert result['measurement_guidance'] == ['坐稳并保持安静，再测一次。']


def test_template_asks_about_symptoms_when_ectopy_evidence_exists():
    from ai_model.explanation.generator import _template

    result = _template({
        'classification': {'label': 'other_abnormality'},
        'concepts': [{'name': 'ventricular_ectopy', 'label': '室性心拍相关特征'}],
        'measurements': {'beats': {'vpc_count': 1}},
        'quality': {'status': 'basic_checks_passed'},
    })
    assert any('漏跳' in question for question in result['symptom_questions'])
    assert any('头晕' in question for question in result['symptom_questions'])


def test_elderly_summary_mentions_early_beat_only_with_vpc_evidence():
    from ai_model.explanation.generator import _template

    result = _template({
        'classification': {'label': 'other_abnormality'},
        'concepts': [{'name': 'ventricular_ectopy', 'label': '室性心拍相关特征', 'evidence': {'vpc_count': 1}}],
        'measurements': {'beats': {'vpc_count': 1}},
        'quality': {'status': 'basic_checks_passed'},
    })
    assert '1 次心跳比前后稍早出现' in result['elderly_summary']
    assert '有没有心慌' in result['elderly_summary']


def test_baseline_drift_explanation_gives_safe_retake_guidance():
    from ai_model.explanation.generator import _template

    result = _template({
        'classification': {'label': None},
        'decision': {'state': 'model_uncertain'},
        'quality': {
            'status': 'degraded',
            'issues': [{'code': 'baseline_drift', 'label': '基线漂移'}],
            'reasons': ['基线漂移'],
        },
        'measurement_coach': {'actions': ['保持姿势稳定。']},
    })
    assert '基准线' in result['elderly_summary']
    assert any('电极' in item for item in result['measurement_guidance'])
    assert any('不必屏气' in item for item in result['measurement_guidance'])


def test_barely_acceptable_external_quality_caps_score_at_70(monkeypatch):
    from ai_model.quality import coach
    from ai_model.quality.external import _quality_score

    monkeypatch.setattr(coach, 'assess_external_quality', lambda *args: {
        'available': True,
        'provider': 'neurokit2',
        'label': 'barely acceptable',
    })
    quality = coach.merge_external_quality(
        {'score': 90, 'status': 'basic_checks_passed', 'grade': 'good', 'issues': [], 'reason_codes': [], 'reasons': [], 'classification_eligible': True},
        [float(index % 10) for index in range(100)],
        100,
    )
    assert _quality_score('barely acceptable') == 70.0
    assert quality['score'] == 70.0
    assert quality['classification_eligible'] is True
    assert quality['status'] == 'basic_checks_passed'


def test_neurokit_quality_is_disabled_by_default(monkeypatch):
    from ai_model.quality import coach

    monkeypatch.delenv('ECG_QUALITY_PROVIDER', raising=False)
    captured = {}

    def assess_external(samples, sample_rate_hz, provider):
        captured['provider'] = provider
        return {'available': False, 'provider': 'none', 'status': 'disabled'}

    monkeypatch.setattr(coach, 'assess_external_quality', assess_external)
    quality = coach.merge_external_quality(
        {'score': 100, 'status': 'basic_checks_passed'},
        [float(index % 7) for index in range(100)],
        100,
    )
    assert captured['provider'] == 'none'
    assert quality['external_quality']['status'] == 'disabled'


def test_hardware_csv_uses_filtered_ecg_column():
    text = (
        'timestamp(s),resp_raw,ecg_raw,resp_filtered,ecg_filtered\n'
        '0.0,1,10,2,-1.5\n'
        '0.002,1,11,2.1,-1.2\n'
    )
    result = parse_csv(text, 500)
    assert result['source'] == 'hardware_csv'
    assert result['unit'] == 'mV'
    assert result['input_unit'] == 'adc_count'
    assert result['samples'] == [
        -1.5 * 2420 / (6 * 2**23),
        -1.2 * 2420 / (6 * 2**23),
    ]
    assert result['calibration']['raw_offset_removed'] is False


def test_single_column_csv_is_not_adc_scaled():
    result = parse_csv('value\n-1.5\n', 500)
    assert result['samples'] == [-1.5]
    assert result['source'] == 'csv_import'
    assert 'calibration' not in result


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
