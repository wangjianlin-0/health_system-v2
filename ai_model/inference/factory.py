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
    raise ValueError(f'不支持的分类器: {model_type}')


def configured_classifier() -> Classifier | None:
    return load_classifier(os.environ.get('ECG_MODEL_TYPE', 'none'))

def predict(model: Classifier | None, signal_data: dict) -> dict:
    if model is None:
        return {'status': 'model_unavailable', 'label': None, 'confidence': None,
                'model_version': None, 'explanation': '真实模型尚未接入，不输出正常或异常分类'}
    return model.predict(signal_data)
