from ai_model import config
from ai_model.inference import factory


def _reload_project_env(tmp_path, monkeypatch, content):
    module = tmp_path / 'ai_model' / 'config.py'
    if content is not None:
        (tmp_path / '.env').write_text(content, encoding='utf-8')
    monkeypatch.setattr(config, 'Path', lambda _: module)
    monkeypatch.setattr(config, '_LOADED', False)
    config.load_project_env()


def test_model_type_from_project_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv('ECG_MODEL_TYPE', raising=False)
    _reload_project_env(tmp_path, monkeypatch, 'ECG_MODEL_TYPE="openecg"\n')
    monkeypatch.setattr(factory, 'load_classifier', lambda model_type: model_type)
    assert factory.configured_classifier() == 'openecg'


def test_project_dotenv_overrides_stale_process_ai_setting(tmp_path, monkeypatch):
    monkeypatch.setenv('ECG_MODEL_TYPE', 'none')
    _reload_project_env(tmp_path, monkeypatch, 'ECG_MODEL_TYPE=openecg\n')
    monkeypatch.setattr(factory, 'load_classifier', lambda model_type: model_type)
    assert factory.configured_classifier() == 'openecg'


def test_no_config_defaults_to_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv('ECG_MODEL_TYPE', raising=False)
    _reload_project_env(tmp_path, monkeypatch, None)
    assert factory.configured_classifier() is None
