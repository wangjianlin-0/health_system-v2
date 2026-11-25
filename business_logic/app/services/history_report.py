"""Build a longitudinal report from explicit self-reports and measured values."""
import json
import math
import os
import re
from collections import defaultdict
from statistics import median
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SYSTEM_PROMPT = """你为长辈整理心电历史观察报告。输入是后端已审核的中文段落。
请选择最值得先读的 section_id，并为它选择一个语气：direct 或 gentle。
不修改事实、不生成新文案、不推断诊断或原因。只返回 JSON 对象，
字段 first_section_id 和 tone。first_section_id 必须来自输入候选项。"""


def build_report(rows):
    if not rows:
        return None
    recent, baseline = defaultdict(list), defaultdict(list)
    recent_ids, baseline_ids = set(), set()
    symptoms = {}
    for row in rows:
        if row["feeling"] == "palpitations":
            symptoms.setdefault(row["date"], row["id"])
        bpm = row["heart_rate_bpm"]
        if (row["scene"] == "rest" and row["feeling"] == "none"
                and row["quality_status"] == "basic_checks_passed"
                and isinstance(bpm, (int, float)) and math.isfinite(bpm) and bpm > 0):
            values, identifiers = (recent, recent_ids) if row["recent"] else (baseline, baseline_ids)
            values[row["date"]].append(bpm)
            identifiers.add(row["id"])

    evidence = [row["id"] for row in rows if row["id"] in recent_ids | baseline_ids]
    heart_rate = {"recent_days": len(recent), "baseline_days": len(baseline)}
    if len(recent) >= 3 and len(baseline) >= 5:
        current = round(median(map(median, recent.values())), 1)
        old = round(median(map(median, baseline.values())), 1)
        change = round(current - old, 1)
        heart_rate.update(recent_bpm=current, baseline_bpm=old, difference_bpm=change)
        comparison = f"较此前{'高' if change > 0 else '低'} {abs(change):g} 次/分" if change else "与此前相同"
        trend = (f"最近 7 天，平时静坐且没有不适时测得的心率中间值为 {current:g} 次/分，"
                 f"{comparison}。近期和此前分别有 {len(recent)} 天和 {len(baseline)} 天可比较。")
    else:
        trend = (f"最近 7 天有 {len(recent)} 天、此前 28 天有 {len(baseline)} 天可比较的静坐记录，"
                 "暂时不能判断长期心率变化。")

    sections = [{
        "id": "trend", "title": "和平时相比，心率有什么变化",
        "text": trend,
        "action": "在相近时段补充静坐、没有不适时的记录。活动后或不舒服时，可单独标记。",
        "record_ids": evidence,
    }]
    if symptoms:
        recent_symptoms = sum(row["recent"] and row["id"] in symptoms.values() for row in rows)
        symptom_section = {
            "id": "symptoms", "title": "把心慌时的情况记下来",
            "text": f"近 35 天有 {len(symptoms)} 天的测量记录填写了心慌，其中 {recent_symptoms} 天在最近一周。",
            "action": ("可预约门诊咨询，带上相关波形、当时的感受和用药清单。"
                       if len(symptoms) >= 2 else "下次方便记录时，可以补上发生场景和持续时间。"),
            "record_ids": list(symptoms.values()),
        }
        sections.insert(0, symptom_section)

    return {
        "headline": "这段时间的心电记录",
        "sections": sections,
        "heart_rate": heart_rate,
        "possible_factors": [{
            "text": "可回想心慌前是否睡得少、喝过浓茶或咖啡，或近期是否调整过用药。"
                    "心律等其他身体原因需要结合就诊评估。目前记录不足以确定原因。",
            "title": "英国 NHS · 心慌",
            "url": "https://www.nhs.uk/symptoms/heart-palpitations/",
        }] if symptoms else [],
        "safety_notice": (
            "如果现在心慌并伴有胸痛、呼吸困难、快要晕倒或已经晕倒，请立即联系当地急救服务。"
            if symptoms else None
        ),
        "presentation": "local",
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def config():
    endpoint = os.getenv("ECG_REPORT_QWEN_URL", "").strip()
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ""
        port = url.port
    except ValueError:
        return None
    if (key and url.scheme == "https" and not url.username and not url.password
            and port in (None, 443)
            and re.fullmatch(r"(?:dashscope(?:-intl|-us)?|[a-z0-9-]+\.[a-z0-9-]+\.maas)\.aliyuncs\.com", host)
            and url.path == "/compatible-mode/v1/chat/completions"
            and not url.query and not url.fragment):
        return endpoint, key
    return None


def polish_report(report):
    provider = config()
    if not provider or not report:
        return report
    endpoint, key = provider
    candidates = [{"id": item["id"], "text": item["text"]} for item in report["sections"]]
    data = {
        "model": "qwen-plus", "max_tokens": 120, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(candidates, ensure_ascii=False)},
        ],
    }
    request = Request(endpoint, data=json.dumps(data).encode(),
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=6) as response:
            answer = json.loads(response.read(32768))["choices"][0]["message"]["content"]
        picked = json.loads(answer)
        if not isinstance(picked, dict) or set(picked) != {"first_section_id", "tone"} or picked["tone"] not in ("direct", "gentle"):
            return report
        first = next(section for section in report["sections"] if section["id"] == picked["first_section_id"])
    except (URLError, OSError, ValueError, TypeError, KeyError, IndexError, StopIteration):
        return report
    return {**report, "presentation": "qwen",
            "headline": "我们一起来看看这段时间的记录" if picked["tone"] == "gentle" else report["headline"],
            "sections": [first, *(item for item in report["sections"] if item is not first)]}
