"""模型模块：统一分析入口、证据链和解释生成。"""
from typing import Any

from signal_processing.python.ecg_preprocessing import process
from ai_model.explanation.concepts import build_evidence_payload
from ai_model.explanation.generator import generate_explanation
from ai_model.inference.factory import configured_classifier, load_classifier, predict


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

def analyze(signal):
    result = process(signal)
    if result['quality']['status'] == 'insufficient':
        prediction = {'status': 'skipped_quality', 'label': None, 'confidence': None, 'model_version': None, 'explanation': '数据不足，请重新记录'}
    elif signal.get('model_type') in ('cnn', 'hgb', 'openecg', 'none'):
        try:
            prediction = predict(load_classifier(signal['model_type']), result)
        except (ImportError, RuntimeError):
            prediction = {'status': 'model_unavailable', 'label': None, 'confidence': None,
                          'model_version': signal['model_type'],
                          'explanation': '所选模型依赖未就绪，请检查运行环境。'}
    else:
        prediction = classify(result)
    evidence = build_evidence_payload(prediction, result['quality'])
    prediction['evidence'] = evidence
    explanation = generate_explanation(evidence)
    prediction['explanation_detail'] = explanation
    prediction['explanation'] = (prediction.get('explanation') if prediction['status'] == 'model_unavailable'
                               else explanation.get('summary', ''))
    result['prediction'] = prediction
    result['source'] = signal.get('source', 'unknown')
    result['mode'] = 'pc-model-evidence-pipeline' if prediction['status'] == 'classified' else 'framework_demo'
    result['model_type'] = signal.get('model_type')
    if 'acquisition' in signal:
        result['acquisition'] = signal['acquisition']
    return result
