import json
from unittest.mock import MagicMock

from app.services import history_report


def test_report_compares_daily_medians_and_excludes_ineligible_records():
    def row(date, bpm, *, recent, suffix="", scene="rest", feeling="none",
            quality="basic_checks_passed"):
        return {"id": date + suffix, "date": date, "heart_rate_bpm": bpm, "recent": recent,
                "scene": scene, "feeling": feeling, "quality_status": quality}

    rows = [row(f"2026-11-{day:02}", 70, recent=False) for day in range(1, 6)]
    rows += [row(f"2026-11-{day}", bpm, recent=True) for day, bpm in [(21, 72), (22, 74), (23, 76)]]
    rows += [
        row("2026-11-21", 84, recent=True, suffix="-repeat"),
        row("2026-11-24", 130, recent=True, scene="after_activity"),
        row("2026-11-24", 115, recent=True, suffix="-symptom", feeling="palpitations"),
        row("2026-11-25", 110, recent=True, quality="insufficient"),
        row("2026-11-25", 100, recent=True, suffix="-unknown", feeling=None),
    ]
    report = history_report.build_report(rows)
    assert report["heart_rate"] == {"recent_days": 3, "baseline_days": 5,
                                   "recent_bpm": 76.0, "baseline_bpm": 70.0, "difference_bpm": 6.0}
    assert report["sections"][0]["record_ids"] == ["2026-11-24-symptom"]
    assert report["safety_notice"]


def test_qwen_can_only_select_an_existing_section_and_tone(monkeypatch):
    monkeypatch.setenv("ECG_REPORT_QWEN_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    opener = MagicMock()
    monkeypatch.setattr(history_report, "build_opener", lambda *args: opener)
    response = opener.open.return_value.__enter__.return_value
    report = {"headline": "本地", "sections": [{"id": "trend", "text": "统计", "record_ids": ["private-id"]}],
              "presentation": "local", "safety_notice": "保留提示"}
    for section_id in ("fabricated", "trend"):
        content = json.dumps({"first_section_id": section_id, "tone": "gentle"})
        response.read.return_value = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        actual = history_report.polish_report(report)
        assert actual["presentation"] == ("qwen" if section_id == "trend" else "local")
        assert actual["safety_notice"] == report["safety_notice"]
        assert actual["sections"] == report["sections"]
        assert b"private-id" not in opener.open.call_args.args[0].data


def test_context_is_saved_and_included_in_the_owner_report(client):
    from test_records_api import account, create_record

    owner = account(client, "report-owner")
    other = account(client, "report-other")
    identifier = create_record(client, owner)["id"]
    url = f"/api/v1/records/{identifier}"
    body = {"scene": "rest", "feeling": "palpitations"}
    assert client.patch(url + "/body-context", headers=other, json=body).status_code == 404
    assert client.patch(url + "/body-context", headers=owner, json=body).json() == body
    assert client.patch(url, headers=owner, json={"note": "test"}).status_code == 200
    assert client.get(url, headers=owner).json()["body_context"] == body
    assert client.get("/api/v1/records/advice", headers=owner).json()["report"]["sections"][0]["id"] == "symptoms"
    assert client.get("/api/v1/records/advice", headers=other).json()["report"] is None
