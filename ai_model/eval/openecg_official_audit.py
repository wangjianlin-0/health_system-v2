"""Audit the installed OpenECG release and its published codec-v6 claims.

This verifies artifacts and extracts model-card claims. It deliberately does
not present published numbers as locally reproduced dataset measurements.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    import openecg

    root = Path(openecg.__file__).resolve().parent
    models = root / 'models'
    artifacts = []
    for name in ('codec_v6.pt', 'codec_v6_int8.onnx', 'codec_v6_MODEL_CARD.md'):
        path = models / name
        artifacts.append({
            'name': name,
            'exists': path.is_file(),
            'bytes': path.stat().st_size if path.is_file() else None,
            'sha256': sha256(path) if path.is_file() else None,
        })
    report = {
        'audit_type': 'artifact_and_documentation_audit_not_dataset_reproduction',
        'openecg_version': openecg.__version__,
        'distribution_version': importlib.metadata.version('openecg'),
        'official_repository': 'https://github.com/vitaldb/openecg',
        'release': 'v0.11.0',
        'artifacts': artifacts,
        'published_codec_v6_claims': {
            'frame_boundary_macro_f1_ludb_val': 0.855,
            'frame_boundary_macro_f1_ludb_val_clean': 0.867,
            'frame_median_timing_ms': 11.1,
            'beat_vpc_f1_mit_bih_ds2': 0.929,
            'rhythm_macro_f1_lydus_test': 0.797,
            'code_test': {
                'records': 827,
                'single_label_exams': 818,
                'f1': {'sinus': 0.931, 'avb': 0.778, 'afib': 0.846, 'bbb': 0.513,
                       'macro': 0.767},
                'auroc': {'sinus': 0.944, 'avb': 0.994, 'afib': 0.999, 'bbb': 0.946},
            },
        },
        'reproduction_status': {
            'artifact_identity': 'verified_locally',
            'inference_smoke_test': 'available',
            'ludb_metric': 'requires exact official split/cleaning and evaluation runner',
            'mit_bih_ds2_metric': 'requires exact DS1/DS2 protocol and official codec-v6 beat scorer',
            'lydus_metric': 'not independently reproducible without non-public Lydus data',
            'code_test_metric': 'data cited publicly, but v0.11.0 does not ship the end-to-end audit runner',
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
