import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'business_logic'))


@pytest.fixture(autouse=True)
def isolate_external_ai(monkeypatch):
    """Keep tests deterministic and prevent accidental external API calls."""
    monkeypatch.setenv('ECG_EXPLANATION_PROVIDER', 'template')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setenv('ECG_MODEL_TYPE', 'none')

    import ai_model.pipeline as pipeline
    pipeline._CLASSIFIER = None
    pipeline._CLASSIFIER_READY = False
    yield
    pipeline._CLASSIFIER = None
    pipeline._CLASSIFIER_READY = False
