"""Verify lightweight model manifests and write an auditable report."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_model.registry.model_registry import verify_model_manifests

report = verify_model_manifests()
target = ROOT / 'runtime' / 'verification' / 'model_registry.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report['passed'] else 1)
