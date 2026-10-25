"""唐一可：统一分析入口、证据链和解释生成。"""
from typing import Any

from signal_processing.python.ecg_preprocessing import process
from ai_model.explanation.concepts import build_evidence_payload
from ai_model.explanation.generator import generate_explanation
from ai_model.inference.factory import configured_classifier, predict
from ai_model.quality.coach import (
    assess_signal_quality,
    build_measurement_coach,
    merge_external_quality,
)


_CLASSIFIER = None
_CLASSIFIER_READY = False


def classify(processed: dict[str, Any]) -> dict[str, Any]:
    global _CLASSIFIER, _CLASSIFIER_READY
    if not _CLASSIFIER_READY:
        try:
            _CLASSIFIER = configured_classifier()
        except (ImportError, RuntimeError, ValueError):
            _CLASSIFIER = None
        _CLASSIFIER_READY = True
    return predict(_CLASSIFIER, processed)

def _decision(prediction: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    if not quality.get('classification_eligible', True):
        return {
            'state': 'signal_invalid',
            'label': '信号不合格',
            'can_present_classification': False,
            'reason': '信号质量未达到分类要求',
        }
    if prediction.get('status') != 'classified':
        return {
            'state': 'model_uncertain',
            'label': '模型不确定',
            'can_present_classification': False,
            'reason': prediction.get('explanation', '模型未完成可靠分类'),
        }
    confidence = prediction.get('confidence')
    if isinstance(confidence, (int, float)) and confidence < 0.55:
        return {
            'state': 'model_uncertain',
            'label': '模型不确定',
            'can_present_classification': False,
            'reason': '模型置信度低于辅助展示阈值',
        }
    if quality.get('score', 100) < 70:
        return {
            'state': 'model_uncertain',
            'label': '模型不确定',
            'can_present_classification': False,
            'reason': '信号存在干扰，分类结果需要复测确认',
        }
    return {
        'state': 'assistive_classification',
        'label': '可提供辅助分类',
        'can_present_classification': True,
        'reason': '信号质量和模型输出达到辅助展示要求',
    }


def analyze(signal):
    result = process(signal)
    measured_quality = assess_signal_quality(result['waveform'], result['sample_rate_hz'])
    measured_quality = merge_external_quality(
        measured_quality,
        result['waveform'],
        result['sample_rate_hz'],
    )
    result['quality'].update(measured_quality)
    coach = build_measurement_coach(
        result['quality'],
        signal.get('previous_quality'),
    )
    result['measurement_coach'] = coach
    if not result['quality'].get('classification_eligible', False):
        prediction = {'status': 'skipped_quality', 'label': None, 'confidence': None, 'model_version': None, 'explanation': '数据不足，请重新记录'}
    else:
        prediction = classify(result)
    prediction['decision'] = _decision(prediction, result['quality'])
    evidence = build_evidence_payload(prediction, result['quality'], coach)
    prediction['evidence'] = evidence
    explanation = generate_explanation(evidence)
    prediction['explanation_detail'] = explanation
    prediction['explanation'] = explanation.get('summary', '')
    result['prediction'] = prediction
    result['source'] = signal.get('source', 'unknown')
    result['mode'] = 'openecg-evidence-pipeline' if prediction['status'] == 'classified' else 'framework_demo'
    return result
