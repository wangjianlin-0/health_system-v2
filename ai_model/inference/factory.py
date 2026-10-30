"""Classifier factory with an explicit unavailable default."""
import os
from pathlib import Path
from typing import Protocol

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
    model_type = os.environ.get('ECG_MODEL_TYPE')
    if model_type is None:
        env_file = Path(__file__).resolve().parents[2] / '.env'
        try:
            for line in env_file.read_text(encoding='utf-8').splitlines():
                key, separator, value = line.partition('=')
                if separator and key.strip() == 'ECG_MODEL_TYPE':
                    model_type = value.strip().strip('"').strip("'")
                    break
        except OSError:
            pass
    return load_classifier(model_type or 'none')

def predict(model: Classifier | None, signal_data: dict) -> dict:
    if model is None:
        return {'status': 'model_unavailable', 'label': None, 'confidence': None,
                'model_version': None, 'explanation': '真实模型尚未接入，不输出正常或异常分类'}
    return model.predict(signal_data)
