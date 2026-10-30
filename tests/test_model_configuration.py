from ai_model.inference import factory


def test_model_type_from_project_dotenv(tmp_path, monkeypatch):
    module = tmp_path / 'ai_model' / 'inference' / 'factory.py'
    (tmp_path / '.env').write_text('ECG_MODEL_TYPE="openecg"' + chr(10), encoding='utf-8')
    monkeypatch.delenv('ECG_MODEL_TYPE', raising=False)
    monkeypatch.setattr(factory, 'Path', lambda _: module)
    monkeypatch.setattr(factory, 'load_classifier', lambda model_type: model_type)
    assert factory.configured_classifier() == 'openecg'


def test_process_environment_overrides_dotenv(tmp_path, monkeypatch):
    module = tmp_path / 'ai_model' / 'inference' / 'factory.py'
    (tmp_path / '.env').write_text('ECG_MODEL_TYPE=openecg' + chr(10), encoding='utf-8')
    monkeypatch.setenv('ECG_MODEL_TYPE', 'none')
    monkeypatch.setattr(factory, 'Path', lambda _: module)
    monkeypatch.setattr(factory, 'load_classifier', lambda model_type: model_type)
    assert factory.configured_classifier() == 'none'


def test_no_config_defaults_to_unavailable(tmp_path, monkeypatch):
    module = tmp_path / 'ai_model' / 'inference' / 'factory.py'
    monkeypatch.delenv('ECG_MODEL_TYPE', raising=False)
    monkeypatch.setattr(factory, 'Path', lambda _: module)
    assert factory.configured_classifier() is None
