"""Generate history advice from record summaries and local, reviewed templates."""

import json
from collections import defaultdict
from pathlib import Path

MODEL_LABELS = {
    "CNN-H27-fold0": {"pac": "S", "vpc": "V", "fusion": "F"},
    "HGB-v92-fold0": {"pac": "S", "vpc": "VF（合并类）"},
}

KNOWLEDGE = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


def _item(rule_id, observation, records):
    return {
        "rule_id": rule_id,
        "observation": observation,
        "evidence_records": [
            {"id": row["id"], "date": row["date"]} for row in records
        ],
        **KNOWLEDGE[rule_id],
    }


def build_advice(rows):
    """Rows are distinct original measurements, latest first, with local dates."""
    items = []
    recent_poor = [
        row for row in rows if row["recent"] and row["quality_status"] == "insufficient"
    ]
    recent_count = sum(row["recent"] for row in rows)
    if len(recent_poor) >= 2:
        items.append(_item(
            "poor_signal_repeat",
            f"最近 7 天的 {recent_count} 次记录中，有 {len(recent_poor)} 次信号质量不足。",
            recent_poor,
        ))

    groups = defaultdict(dict)
    for row in rows:
        labels = MODEL_LABELS.get(row["model_version"])
        if (not labels or row["status"] != "classified"
                or row["quality_status"] != "basic_checks_passed"):
            continue
        counts = json.loads(row["beat_counts"] or "{}")
        if not isinstance(counts, dict):
            continue
        for field, label in labels.items():
            count = counts.get(field)
            if type(count) is int and count > 0:
                key = (row["model_version"], row["model_hash"], label)
                groups[key].setdefault(row["date"], row)

    for (version, _, label), dates in sorted(groups.items(), key=lambda group: -len(group[1])):
        if len(dates) >= 2:
            items.append(_item(
                "repeat_model_label",
                f"最近 35 天有 {len(dates)} 个不同日期的已分析片段出现 {version} 模型的 {label} 类标记。",
                dates.values(),
            ))

    if rows and not items:
        items.append(_item(
            "track_measurement_context",
            "已记录的测量可用于回顾波形和当时的测量情况。",
            rows[:1],
        ))
    return {"measurement_count": len(rows), "items": items}
