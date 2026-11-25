"""Unified ECG pipeline: OpenECG rhythm plus CNN/HGB beat analysis."""

from __future__ import annotations

import os
from typing import Any

from signal_processing.python.ecg_preprocessing import process
from ai_model.analysis import beat_analysis, legacy_beats, rate_analysis, rhythm_analysis
from ai_model.beat_detection.detector import RPeakDetector
from ai_model.explanation.concepts import build_evidence_payload
from ai_model.explanation.generator import generate_explanation
from ai_model.inference.factory import load_classifier, predict
from ai_model.quality.coach import QualityCoach
from ai_model.respiration.analyzer import RespirationAnalyzer
from ai_model.safety.rules import evaluate_safety


_RESPIRATION_ANALYZER = RespirationAnalyzer()
_R_PEAK_DETECTOR = RPeakDetector()
_QUALITY_COACH = QualityCoach()
# Compatibility hooks retained for existing tests and callers that reset model state.
_CLASSIFIER = None
_CLASSIFIER_READY = False


def _unavailable(model_version: str, message: str) -> dict[str, Any]:
    return {
        'status': 'model_unavailable',
        'label': None,
        'confidence': None,
        'model_version': model_version,
        'explanation': message,
    }


def _run_model(model_type: str, processed: dict[str, Any]) -> dict[str, Any]:
    try:
        return predict(load_classifier(model_type), processed)
    except (ImportError, RuntimeError, ValueError) as exc:
        return _unavailable(model_type, f'{type(exc).__name__}: {exc}')


def _rhythm_prediction(processed: dict[str, Any]) -> dict[str, Any]:
    return _run_model('openecg', processed)


def _beat_prediction(model_type: str, processed: dict[str, Any]) -> dict[str, Any]:
    if model_type not in {'cnn', 'hgb', 'ensemble'}:
        return _unavailable(model_type or 'none', '未选择 CNN 或 HGB 逐拍模型。')
    return _run_model(model_type, processed)


def _edge_r_peaks(prediction: dict[str, Any]) -> dict[str, Any] | None:
    items = (prediction.get('beats') or {}).get('items') or []
    events = [
        {
            'sample': int(item['r_sample500']),
            'time_sec': float(item['r_seconds']),
            't_s': float(item['r_seconds']),
            'type': str(item.get('label') or 'untyped').lower(),
            'source': 'edge_model',
        }
        for item in items
        if isinstance(item.get('r_sample500'), (int, float))
        and isinstance(item.get('r_seconds'), (int, float))
    ]
    if not events:
        return None
    return _R_PEAK_DETECTOR._result(events, 500, 'edge_model')


def analyze(signal: dict[str, Any]) -> dict[str, Any]:
    result = process(signal)
    quality = _QUALITY_COACH.assess(result, signal)
    result['quality'] = quality
    eligible = quality.get('status') != 'insufficient'
    selected_beat_model = str(
        signal.get('model_type') or os.environ.get('ECG_MODEL_TYPE') or 'none'
    ).lower()

    if eligible:
        rhythm_prediction = _rhythm_prediction(result)
        edge_prediction = _beat_prediction(selected_beat_model, result)
    else:
        skipped = {
            'status': 'skipped_quality',
            'label': None,
            'confidence': None,
            'model_version': None,
            'explanation': '信号质量不足，未执行模型分类。',
        }
        rhythm_prediction = dict(skipped)
        edge_prediction = dict(skipped)

    openecg_events = (rhythm_prediction.get('beats') or {}).get('events') or []
    edge_r_peak_result = _edge_r_peaks(edge_prediction)
    if edge_r_peak_result is not None:
        r_peak_result = edge_r_peak_result
    elif (
        eligible
        and selected_beat_model in {'cnn', 'hgb', 'ensemble'}
        and edge_prediction.get('status') != 'classified'
    ):
        r_peak_result = _R_PEAK_DETECTOR.detect(
            result['waveform'],
            result['sample_rate_hz'],
            openecg_events,
        )
    elif not eligible:
        r_peak_result = {
            'status': 'skipped_quality',
            'provider': 'quality_gate',
            'reason': '信号质量不足',
            'count': 0,
            'events': [],
            'heart_rate': {},
            'scope': '信号质量不足，未执行 R 峰检测',
        }
    elif selected_beat_model in {'cnn', 'hgb', 'ensemble'}:
        r_peak_result = {
            'status': 'insufficient',
            'provider': 'edge_model',
            'reason': '模型未返回逐拍事件',
            'count': 0,
            'events': [],
            'heart_rate': edge_prediction.get('heart_rate') or {},
            'scope': '所选逐拍模型未返回可标准化的心拍位置',
        }
    else:
        r_peak_result = {
            'status': 'not_requested',
            'provider': 'none',
            'reason': '未选择 CNN 或 HGB 逐拍模型',
            'count': 0,
            'events': [],
            'heart_rate': {},
            'scope': '未请求逐拍模型时不执行独立 R 峰回退',
        }

    beat_result = beat_analysis(edge_prediction, edge_prediction, r_peak_result)
    if beat_result.get('status') == 'model_unavailable' and rhythm_prediction.get('beats'):
        beat_result = beat_analysis(rhythm_prediction, edge_prediction, r_peak_result)
    edge_prediction['beats'] = legacy_beats(beat_result)

    rhythm_result = rhythm_analysis(rhythm_prediction)
    rate_source = dict(edge_prediction)
    rate_source['heart_rate'] = (
        edge_prediction.get('heart_rate')
        or r_peak_result.get('heart_rate')
        or rhythm_prediction.get('heart_rate')
    )
    rate_peaks = r_peak_result
    if not r_peak_result.get('events') and openecg_events:
        rate_peaks = _R_PEAK_DETECTOR.from_openecg(openecg_events, result['sample_rate_hz'])
    rate_result = rate_analysis(rate_source, rate_peaks)
    respiration_result = _RESPIRATION_ANALYZER.analyze(result)
    safety = evaluate_safety(
        quality,
        beat_result,
        rhythm_result,
        rate_result,
        respiration_result,
        signal.get('symptoms') if isinstance(signal.get('symptoms'), list) else None,
    )

    # OpenECG is a record-level rhythm model, not a beat classifier.  When it is
    # explicitly selected, expose its classified state at the compatibility
    # top level instead of letting the intentionally absent beat model make the
    # whole analysis look unavailable.
    prediction = dict(
        rhythm_prediction if selected_beat_model == 'openecg' else edge_prediction
    )
    prediction['rhythm'] = rhythm_prediction.get('rhythm') or {}
    prediction['rhythm_model'] = {
        'status': rhythm_prediction.get('status'),
        'model_version': rhythm_prediction.get('model_version'),
        'model_asset': rhythm_prediction.get('model_asset'),
        'analysis_scope': rhythm_prediction.get('analysis_scope'),
    }
    prediction['rhythm_dimensions'] = rhythm_prediction.get('rhythm_dimensions') or {}
    prediction['rhythm_windows'] = rhythm_prediction.get('rhythm_windows') or []
    prediction['rhythm_events'] = rhythm_prediction.get('rhythm_events') or []
    prediction['beats'] = legacy_beats(beat_result)
    prediction['heart_rate'] = rate_source.get('heart_rate')
    prediction['beat_model'] = {
        'requested': (
            selected_beat_model
            if selected_beat_model in {'cnn', 'hgb', 'ensemble'}
            else 'none'
        ),
        'status': edge_prediction.get('status'),
        'model_version': edge_prediction.get('model_version'),
    }
    if edge_prediction.get('agreement'):
        prediction['beat_model']['agreement'] = edge_prediction['agreement']
        prediction['beat_model']['review_model'] = edge_prediction.get('review_model')
    evidence = build_evidence_payload(prediction, quality)
    evidence.update({
        'beat_analysis': beat_result,
        'r_peak_analysis': r_peak_result,
        'rhythm_analysis': rhythm_result,
        'rate_analysis': rate_result,
        'respiration_analysis': respiration_result,
        'safety': safety,
    })
    prediction['evidence'] = evidence
    explanation = generate_explanation(evidence)
    prediction['explanation_detail'] = explanation
    prediction['explanation'] = (
        explanation.get('summary', '')
        if rhythm_prediction.get('status') == 'classified'
        else edge_prediction.get('explanation')
        if edge_prediction.get('status') == 'model_unavailable'
        else explanation.get('summary', '')
    )

    result.update({
        'prediction': prediction,
        'beat_analysis': beat_result,
        'r_peak_analysis': r_peak_result,
        'rhythm_analysis': rhythm_result,
        'rate_analysis': rate_result,
        'respiration_analysis': respiration_result,
        'safety': safety,
        'source': signal.get('source', 'unknown'),
        'mode': 'openecg-rhythm-edge-beat-pipeline',
        'model_type': selected_beat_model,
    })
    if 'acquisition' in signal:
        result['acquisition'] = signal['acquisition']
    return result
