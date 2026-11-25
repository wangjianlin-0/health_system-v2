import json
import unittest

from app.services.history_advice import build_advice


def measurement(identifier, date, *, quality="basic_checks_passed", bpm_labels=None,
                version="CNN-H27-fold0", model_hash="hash", recent=True):
    return {
        "id": identifier,
        "date": date,
        "recent": recent,
        "quality_status": quality,
        "status": "classified",
        "model_version": version,
        "model_hash": model_hash,
        "beat_counts": json.dumps(bpm_labels or {}),
    }


class HistoryAdviceTests(unittest.TestCase):
    def test_empty_history(self):
        self.assertEqual(build_advice([]), {"measurement_count": 0, "items": []})

    def test_quality_counts_only_recent_measurements(self):
        rows = [
            measurement("new", "2026-11-25", quality="insufficient"),
            measurement("good", "2026-11-24"),
            measurement("poor", "2026-11-23", quality="insufficient"),
            measurement("old", "2026-11-01", quality="insufficient", recent=False),
        ]
        item, = build_advice(rows)["items"]
        self.assertEqual(item["rule_id"], "poor_signal_repeat")
        self.assertIn("3 次记录中，有 2 次", item["observation"])
        self.assertEqual([r["id"] for r in item["evidence_records"]], ["new", "poor"])

    def test_label_requires_multiple_days_with_same_model_and_weights(self):
        rows = [
            measurement("latest", "2026-11-25", bpm_labels={"vpc": 2}),
            measurement("same_day", "2026-11-25", bpm_labels={"vpc": 1}),
            measurement("other_weights", "2026-11-24", bpm_labels={"vpc": 1}, model_hash="other"),
            measurement("other_model", "2026-11-23", bpm_labels={"vpc": 1}, version="HGB-v92-fold0"),
            measurement("normal", "2026-11-22", bpm_labels={"normal": 4, "unknown": 2}),
        ]
        item, = build_advice(rows)["items"]
        self.assertEqual(item["rule_id"], "track_measurement_context")
        rows.append(measurement("earlier", "2026-11-21", bpm_labels={"vpc": 3}))
        item, = build_advice(rows)["items"]
        self.assertEqual(item["rule_id"], "repeat_model_label")
        self.assertEqual([r["id"] for r in item["evidence_records"]], ["latest", "earlier"])


def test_advice_endpoint_only_uses_the_current_users_records(client):
    from test_records_api import account, upload_flat

    owner = account(client, "advice-owner")
    other = account(client, "advice-other")
    first = upload_flat(client, owner)
    second = upload_flat(client, owner)
    upload_flat(client, other)
    url = "/api/v1/records/advice?timezone=Asia%2FShanghai"
    response = client.get(url, headers=owner)
    assert response.status_code == 200
    assert response.json()["measurement_count"] == 2
    item, = response.json()["items"]
    assert item["rule_id"] == "poor_signal_repeat"
    assert {record["id"] for record in item["evidence_records"]} == {first["id"], second["id"]}
    assert client.get(url, headers=other).json()["measurement_count"] == 1
    assert client.get(url).status_code == 401
