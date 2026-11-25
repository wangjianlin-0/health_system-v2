"""实际CPU模型通过上传、队列、存储、重分析的集成回归；仅用公开合成输入。"""
from pathlib import Path
import importlib.util
import pytest

from test_api_flow import account, wait_task

pytestmark = pytest.mark.skipif(importlib.util.find_spec('torch') is None,
                               reason='实际CNN集成需要requirements-pc.txt；基础CI保留无模型测试')


def test_real_cnn_hgb_upload_and_reanalysis(client):
    headers = account(client, 'actual-pc-models')
    path = Path(__file__).resolve().parents[1] / 'ai_model/vendor/ecg_edge/model/inference/examples/synthetic500.csv'
    response = client.post('/api/v1/analyze/ecg', headers=headers,
        files={'file': ('synthetic500.csv', path.read_bytes())},
        data={'sample_rate_hz': 500, 'model_type': 'cnn'})
    assert response.status_code == 202
    result = wait_task(client, headers, response.json()['id'], timeout=40)['record']
    prediction = result['result']['prediction']
    assert prediction['status'] == 'classified', prediction
    assert prediction['execution_location'] == 'host_pc'
    assert {key: prediction['beats']['by_type'][key] for key in ('normal', 'pac', 'vpc', 'fusion')} == dict(
        normal=55, pac=1, vpc=16, fusion=0)
    assert result['heart_rate_bpm'] > 0
    assert result['result']['prediction']['explanation_detail']['risk_level'] == 'needs_review'
    assert 'H27' in result['model_version']
    response = client.post(f"/api/v1/records/{result['id']}/reanalyze", headers=headers, json={'model_type': 'hgb'})
    next_result = wait_task(client, headers, response.json()['id'], timeout=40)['record']
    # The multimodel API normalizes HGB N/S/VF into the shared beat schema;
    # the detector's one boundary event remains explicitly unclassified.
    assert next_result['result']['prediction']['beats']['by_type'] == dict(
        normal=57, pac=8, vpc=7, fusion=0, paced=0, unknown=1)
    assert next_result['supersedes_record_id'] == result['id']
    detail = client.get('/api/v1/records/' + next_result['id'], headers=headers).json()
    assert len(detail['result']['waveform']) == 30000
    events = detail['result']['beat_analysis']['events']
    classified = [event for event in events if event['label'] != 'unknown']
    assert len(events) == 73 and len(classified) == 72
    assert all(event['source'] == 'edge_hgb' for event in classified)
    assert all(event['raw_label'] in ('N', 'S', 'VF') for event in classified)
    assert all(0 <= event['confidence'] <= 1 for event in classified)
    assert events == next_result['result']['beat_analysis']['events']
