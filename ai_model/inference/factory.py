"""Classifier factory with an explicit unavailable default."""
import os
from typing import Protocol

from ai_model.config import load_project_env

load_project_env()


class Classifier(Protocol):
    def predict(self, processed: dict) -> dict: ...

def load_classifier(model_type: str = 'none', model_path: str = '') -> Classifier | None:
    if model_type in ('', 'none', 'unavailable'):
        return None
    if model_type == 'openecg':
        from ai_model.inference.openecg_adapter import OpenEcgClassifier
        return OpenEcgClassifier()
    if model_type in ('ecgfounder', 'ecg_founder'):
        from ai_model.inference.ecgfounder_adapter import ECGFounderClassifier
        return ECGFounderClassifier(model_path)
    raise ValueError(f'不支持的分类器: {model_type}')


def configured_classifier() -> Classifier | None:
    model_type = os.environ.get('ECG_MODEL_TYPE', 'none')
    try:
        return load_classifier(
            model_type,
            os.environ.get('ECGFOUNDER_WEIGHTS', ''),
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        if model_type in ('ecgfounder', 'ecg_founder'):
            return UnavailableClassifier(str(exc))
        raise


class UnavailableClassifier:
    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.model_version = 'ecgfounder-unavailable'

    def predict(self, processed: dict) -> dict:
        del processed
        return {
            'status': 'model_unavailable',
            'label': None,
            'confidence': None,
            'model_version': self.model_version,
            'explanation': self.reason,
        }

def predict(model: Classifier | None, signal_data: dict) -> dict:
    if model is None:
        return {'status': 'model_unavailable', 'label': None, 'confidence': None,
                'model_version': None, 'explanation': '真实模型尚未接入，不输出正常或异常分类'}
    return model.predict(signal_data)
