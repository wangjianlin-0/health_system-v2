import shutil
import sys
import uuid
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'business_logic'))

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import records, storage


@pytest.fixture(autouse=True)
def isolated_model_configuration(monkeypatch):
    """Run tests without local models, secrets or external LLM calls."""
    import ai_model.pipeline as pipeline
    monkeypatch.setenv('ECG_MODEL_TYPE', 'none')
    monkeypatch.setenv('ECG_EXPLANATION_PROVIDER', 'template')
    monkeypatch.setattr(pipeline, '_CLASSIFIER', None)
    monkeypatch.setattr(pipeline, '_CLASSIFIER_READY', False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(records, 'settings', replace(settings, upload_dir=tmp_path / 'uploads'))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def tmp_path():
    """Some Windows sandboxes deny pytest's default temp root; use a provisioned dir."""
    temp_root = ROOT / 'tests' / '.tmp'
    temp_root.mkdir(parents=True, exist_ok=True)
    directory = temp_root / uuid.uuid4().hex
    directory.mkdir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)
