"""王书阁：记录、任务状态、趋势与持久化。"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ai_model.pipeline import analyze
from app.core.config import settings
from app.core.errors import (
    InputUnavailable, RecordNotFound, TaskFinished, TaskNotFound, ValidationError,
)
from app.services import signals
from app.services.storage import connect

PROCESSING_VERSION = "records-v2"
TERMINAL = {"completed", "failed", "cancelled"}
QUALITY_VALUES = {"basic_checks_passed", "insufficient", "unknown"}
SORTS = {"created_at_desc", "created_at_asc"}
ACCESS_ACTIONS = {"view", "waveform", "raw", "export", "note", "reanalyze", "delete"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _canonical(signal) -> str:
    return json.dumps(signal, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _duration_ms(started, finished):
    start, end = _parse_iso(started), _parse_iso(finished)
    if not start or not end:
        return None
    return int((end - start).total_seconds() * 1000)


def _task_dict(row) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "stage": row["stage"],
        "outcome": row["outcome"],
        "error": row["error"],
        "error_code": row["error_code"],
        "record_id": row["record_id"],
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "cancel_requested": bool(row["cancel_requested"]),
        "processing_version": row["processing_version"],
        "source_record_id": row["source_record_id"],
        "duration_ms": _duration_ms(row["started_at"], row["finished_at"]),
    }


def _event(db, task_id: str, status: str, stage: str | None, error_code: str | None, detail: str) -> None:
    db.execute(
        "INSERT INTO task_events(task_id, status, stage, error_code, detail, created_at) VALUES (?,?,?,?,?,?)",
        (task_id, status, stage, error_code, detail, _now()),
    )


def _audit(db, record_id: str | None, actor_id: str | None, action: str,
           detail: str | None = None) -> None:
    db.execute(
        "INSERT INTO record_access_log(record_id, actor_id, action, detail, created_at) VALUES (?,?,?,?,?)",
        (record_id, actor_id, action, detail, _now()),
    )


def _task_row(task_id: str, user: str):
    with connect() as db:
        row = db.execute("SELECT * FROM analysis_tasks WHERE id=? AND owner_id=?", (task_id, user)).fetchone()
    if not row:
        raise TaskNotFound("任务不存在或没有查看权限")
    return row


def submit_task(user: str, signal: dict, *, idempotency_key: str | None = None,
                source_record_id: str | None = None):
    """写入任务与标准输入，返回 (task, created)。重复的幂等键返回原任务。"""
    key = (idempotency_key or "").strip() or None
    if key and len(key) > 64:
        raise ValidationError("Idempotency-Key 最长 64 字符")
    digest = hashlib.sha256(_canonical(signal).encode("utf-8")).hexdigest()
    task_id = secrets.token_hex(12)
    created_at = _now()
    with connect() as db:
        if key:
            existing = db.execute(
                "SELECT * FROM analysis_tasks WHERE owner_id=? AND idempotency_key=?", (user, key)
            ).fetchone()
            if existing:
                return _task_dict(existing), False
        try:
            db.execute(
                """INSERT INTO analysis_tasks(
                    id, owner_id, status, stage, created_at, updated_at, processing_version,
                    source, input_sha256, idempotency_key, source_record_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, user, "pending", "queued", created_at, created_at, PROCESSING_VERSION,
                 signal.get("source"), digest, key, source_record_id),
            )
        except sqlite3.IntegrityError:
            if key:
                existing = db.execute(
                    "SELECT * FROM analysis_tasks WHERE owner_id=? AND idempotency_key=?", (user, key)
                ).fetchone()
                if existing:
                    return _task_dict(existing), False
            raise
        db.execute("INSERT INTO task_inputs(task_id, payload) VALUES (?,?)", (task_id, json.dumps(signal)))
        _event(db, task_id, "pending", "queued", None, "任务已提交")
    return task_status(user, task_id), True


def submit(user: str, signal: dict, *, idempotency_key: str | None = None,
           source_record_id: str | None = None) -> dict:
    return submit_task(user, signal, idempotency_key=idempotency_key,
                       source_record_id=source_record_id)[0]


def execute(task_id: str) -> bool:
    with connect() as db:
        claimed = db.execute(
            """UPDATE analysis_tasks SET status='running', stage='validating',
                   started_at=COALESCE(started_at, ?), heartbeat_at=?, updated_at=?,
                   worker_id=?, attempt=attempt+1
               WHERE id=? AND status='pending'""",
            (_now(), _now(), _now(), f"worker-{threading.get_ident()}", task_id),
        )
        if claimed.rowcount != 1:
            return False
        row = db.execute(
            "SELECT t.owner_id, t.source_record_id, t.input_path, t.input_sha256, i.payload "
            "FROM analysis_tasks t LEFT JOIN task_inputs i ON i.task_id=t.id WHERE t.id=?",
            (task_id,),
        ).fetchone()
        _event(db, task_id, "running", "validating", None, "开始执行")
    if not row or not row["payload"]:
        _fail(task_id, RuntimeError("任务输入缺失"))
        return False
    heartbeat = _start_heartbeat(task_id)
    try:
        signal = json.loads(row["payload"])
        result = analyze(signal)
        result.setdefault("lead", signal.get("lead"))
        if _cancel_requested(task_id):
            _finish_cancelled(task_id)
            return False
        return _save_result(task_id, row["owner_id"], result, row["source_record_id"],
                            row["input_path"], row["input_sha256"]) is not None
    except Exception as exc:
        _fail(task_id, exc)
        return False
    finally:
        heartbeat.set()


def _start_heartbeat(task_id: str) -> threading.Event:
    stop = threading.Event()

    def beat():
        while not stop.wait(settings.heartbeat_seconds):
            try:
                with connect() as db:
                    db.execute(
                        "UPDATE analysis_tasks SET heartbeat_at=? WHERE id=? AND status='running'",
                        (_now(), task_id),
                    )
            except Exception:
                continue

    threading.Thread(target=beat, name=f"heartbeat-{task_id[:6]}", daemon=True).start()
    return stop


def _cancel_requested(task_id: str) -> bool:
    with connect() as db:
        row = db.execute("SELECT cancel_requested FROM analysis_tasks WHERE id=?", (task_id,)).fetchone()
    return bool(row and row["cancel_requested"])


def _summary_from_result(result: dict) -> dict:
    prediction = result.get("prediction") or {}
    quality = result.get("quality") or {}
    heart_rate = prediction.get("heart_rate") or {}
    bpm = heart_rate.get("bpm")
    if not isinstance(bpm, (int, float)):
        bpm = result.get("heart_rate_bpm")
    waveform = result.get("waveform") or []
    outcome = prediction.get("status") or "unknown"
    return {
        "source": result.get("source"),
        "lead": result.get("lead"),
        "unit": result.get("unit"),
        "sample_rate_hz": result.get("sample_rate_hz"),
        "duration_sec": result.get("duration_sec"),
        "n_samples": len(waveform),
        "quality_status": quality.get("status"),
        "quality_score": quality.get("score"),
        "label": prediction.get("label"),
        "confidence": prediction.get("confidence"),
        "heart_rate_bpm": bpm if isinstance(bpm, (int, float)) else None,
        "model_version": prediction.get("model_version"),
        "processing_version": result.get("processing_version"),
        "outcome": outcome,
    }


def _record_columns():
    return (
        "id, owner_id, created_at, payload, task_id, source, lead, unit, sample_rate_hz, "
        "duration_sec, n_samples, quality_status, quality_score, label, confidence, "
        "heart_rate_bpm, model_version, processing_version, note, input_path, input_sha256, "
        "supersedes_record_id, updated_at"
    )


def _save_result(task_id: str, owner: str, result: dict, source_record_id: str | None,
                 input_path: str | None = None, input_sha256: str | None = None):
    summary = _summary_from_result(result)
    record_id = secrets.token_hex(12)
    created_at = _now()
    stored_result = dict(result)
    waveform = stored_result.pop("waveform", []) or []
    payload = {
        "id": record_id,
        "task_id": task_id,
        "created_at": created_at,
        "task_status": "completed",
        "result": stored_result,
    }
    with connect() as db:
        current = db.execute("SELECT status, cancel_requested FROM analysis_tasks WHERE id=?", (task_id,)).fetchone()
        if not current or current["status"] != "running":
            return None
        if current["cancel_requested"]:
            _finish_cancelled(task_id)
            return None
        db.execute(
            f"INSERT INTO records({_record_columns()}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record_id, owner, created_at, json.dumps(payload, ensure_ascii=False), task_id,
                summary["source"], summary["lead"], summary["unit"], summary["sample_rate_hz"],
                summary["duration_sec"], summary["n_samples"], summary["quality_status"],
                summary["quality_score"], summary["label"], summary["confidence"],
                summary["heart_rate_bpm"], summary["model_version"], summary["processing_version"],
                None, input_path, input_sha256, source_record_id, created_at,
            ),
        )
        if waveform:
            db.execute(
                "INSERT OR REPLACE INTO record_signals(record_id, sample_rate_hz, unit, n_samples, encoding, data) "
                "VALUES (?,?,?,?,?,?)",
                (record_id, float(summary["sample_rate_hz"] or 0), summary["unit"] or "mV",
                 len(waveform), signals.ENCODING, signals.encode(waveform)),
            )
        db.execute(
            """UPDATE analysis_tasks SET status='completed', stage='finished', outcome=?,
                   updated_at=?, finished_at=?, heartbeat_at=?, record_id=?
               WHERE id=?""",
            (summary["outcome"], _now(), _now(), _now(), record_id, task_id),
        )
        _event(db, task_id, "completed", "finished", None, "分析完成")
    return record_id


def _finish_cancelled(task_id: str) -> None:
    with connect() as db:
        db.execute(
            """UPDATE analysis_tasks SET status='cancelled', stage='finished', error_code='cancelled',
                   error='用户已取消', updated_at=?, finished_at=?, heartbeat_at=?
               WHERE id=? AND status='running'""",
            (_now(), _now(), _now(), task_id),
        )
        _event(db, task_id, "cancelled", "finished", "cancelled", "用户取消")


def _fail(task_id: str, exc: Exception) -> None:
    message = f"{type(exc).__name__}: {exc}"
    code = "input_invalid" if isinstance(exc, ValueError) else "analysis_failed"
    with connect() as db:
        db.execute(
            """UPDATE analysis_tasks SET status='failed', stage='finished', error=?, error_code=?,
                   updated_at=?, finished_at=?, heartbeat_at=?
               WHERE id=? AND status NOT IN ('completed','failed','cancelled')""",
            (message, code, _now(), _now(), _now(), task_id),
        )
        _event(db, task_id, "failed", "finished", code, message)


def recover_tasks() -> dict:
    """启动恢复：pending 重新入队；单进程前提下所有 running 标为中断。"""
    interrupted = []
    with connect() as db:
        stale = db.execute("SELECT id FROM analysis_tasks WHERE status='running'").fetchall()
        for row in stale:
            db.execute(
                """UPDATE analysis_tasks SET status='failed', stage='finished', error_code='interrupted',
                       error='服务重启时任务未完成，请重新提交', updated_at=?, finished_at=?, heartbeat_at=?
                   WHERE id=?""",
                (_now(), _now(), _now(), row["id"]),
            )
            _event(db, row["id"], "failed", "finished", "interrupted", "服务重启时任务未完成")
            interrupted.append(row["id"])
        pending = []
        for row in db.execute(
            "SELECT t.id FROM analysis_tasks t JOIN task_inputs i ON i.task_id=t.id "
            "WHERE t.status='pending' ORDER BY t.created_at"
        ).fetchall():
            pending.append(row["id"])
    return {"pending": pending, "interrupted": interrupted}


def _events_for(task_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT id, status, stage, error_code, detail, created_at "
            "FROM task_events WHERE task_id=? ORDER BY id",
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def task_events(user: str, task_id: str) -> dict:
    _task_row(task_id, user)
    return {"task_id": task_id, "events": _events_for(task_id)}


def task_status(user: str, task_id: str, include_events: bool = False) -> dict:
    data = _task_dict(_task_row(task_id, user))
    if data["record_id"]:
        try:
            data["record"] = detail(user, data["record_id"])
        except LookupError:
            data["record"] = None
    if include_events:
        data["events"] = _events_for(task_id)
    return data


def list_tasks(user: str, status: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    statuses = None
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        invalid = [item for item in statuses if item not in {"pending", "running", "completed", "failed", "cancelled"}]
        if invalid:
            raise ValidationError("status 仅支持 pending/running/completed/failed/cancelled")
    where = ["owner_id=?"]
    params: list = [user]
    if statuses:
        where.append(f"status IN ({','.join('?' for _ in statuses)})")
        params.extend(statuses)
    clause = " WHERE " + " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM analysis_tasks{clause}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM analysis_tasks{clause} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "items": [_task_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


def cancel_task(user: str, task_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM analysis_tasks WHERE id=? AND owner_id=?", (task_id, user)).fetchone()
        if not row:
            raise TaskNotFound("任务不存在或没有查看权限")
        if row["status"] == "pending":
            db.execute(
                """UPDATE analysis_tasks SET status='cancelled', stage='finished', error_code='cancelled',
                       error='用户已取消', updated_at=?, finished_at=?, heartbeat_at=?
                   WHERE id=?""",
                (_now(), _now(), _now(), task_id),
            )
            _event(db, task_id, "cancelled", "finished", "cancelled", "用户取消")
        elif row["status"] == "running":
            db.execute("UPDATE analysis_tasks SET cancel_requested=1, updated_at=? WHERE id=?", (_now(), task_id))
            _event(db, task_id, "running", row["stage"], "cancel_requested", "用户请求取消")
        else:
            raise TaskFinished("任务已结束，不能取消")
    return task_status(user, task_id)


def create(user: str, signal: dict):
    task = submit(user, signal)
    execute(task["id"])
    status = task_status(user, task["id"])
    if status["status"] == "failed":
        raise ValueError(status["error"])
    return status["record"]


def _record_summary(row, payload: dict | None = None) -> dict:
    payload = payload or {}
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"] or row["created_at"],
        "task_id": row["task_id"] or payload.get("task_id"),
        "source": row["source"],
        "lead": row["lead"],
        "unit": row["unit"],
        "sample_rate_hz": row["sample_rate_hz"],
        "duration_sec": row["duration_sec"],
        "n_samples": row["n_samples"],
        "quality_status": row["quality_status"],
        "quality_score": row["quality_score"],
        "label": row["label"],
        "confidence": row["confidence"],
        "heart_rate_bpm": row["heart_rate_bpm"],
        "model_version": row["model_version"],
        "processing_version": row["processing_version"],
        "note": row["note"],
        "supersedes_record_id": row["supersedes_record_id"],
        "owner_username": row["owner_username"] if "owner_username" in row.keys() else None,
    }


def _query_parts(user: str, shared: bool, from_date=None, to_date=None, quality=None,
                 label=None, q=None):
    joins = " JOIN users u ON u.id=r.owner_id"
    conditions: list[str] = []
    params: list = []
    if shared:
        joins += " JOIN grants g ON g.owner_id=r.owner_id AND g.active=1 AND g.relative_id=?"
        params.append(user)
    else:
        conditions.append("r.owner_id=?")
        params.append(user)
    if from_date:
        conditions.append("r.created_at>=?")
        params.append(_date_param(from_date, end=False))
    if to_date:
        conditions.append("r.created_at<=?")
        params.append(_date_param(to_date, end=True))
    if quality:
        if quality not in QUALITY_VALUES:
            raise ValidationError("quality 仅支持 basic_checks_passed/insufficient/unknown")
        conditions.append("r.quality_status=?")
        params.append(quality)
    if label:
        conditions.append("r.label=?")
        params.append(label)
    if q:
        if len(q) > 80:
            raise ValidationError("关键词过长")
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("(r.id LIKE ? ESCAPE '\\' OR COALESCE(r.note,'') LIKE ? ESCAPE '\\')")
        params.extend([f"{escaped}%", f"%{escaped}%"])
    clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    return joins, clause, params


def _date_param(value: str, *, end: bool) -> str:
    text = (value or "").strip()
    if not text:
        raise ValidationError("日期不能为空")
    if len(text) == 10:
        try:
            day = datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValidationError("日期格式应为 YYYY-MM-DD") from exc
        suffix = "T23:59:59.999999+00:00" if end else "T00:00:00+00:00"
        return day.strftime("%Y-%m-%d") + suffix
    parsed = _parse_iso(text)
    if not parsed:
        raise ValidationError("日期格式应为 YYYY-MM-DD 或 ISO 时间")
    return parsed.astimezone(timezone.utc).isoformat()


def _visible_rows(user: str, shared: bool, date_from=None, date_to=None, quality=None,
                  label=None, q=None, sort="created_at_desc", limit=None, offset=0):
    if sort not in SORTS:
        raise ValidationError("sort 仅支持 created_at_desc/created_at_asc")
    joins, clause, params = _query_parts(user, shared, date_from, date_to, quality, label, q)
    order = "r.created_at DESC, r.id DESC" if sort == "created_at_desc" else "r.created_at ASC, r.id ASC"
    distinct = "DISTINCT " if shared else ""
    sql = f"SELECT {distinct}r.*, u.username AS owner_username FROM records r{joins}{clause} ORDER BY {order}"
    count_sql = f"SELECT COUNT({'DISTINCT ' if shared else ''}r.id) FROM records r{joins}{clause}"
    with connect() as db:
        total = db.execute(count_sql, params).fetchone()[0]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            rows = db.execute(sql, (*params, limit, offset)).fetchall()
        else:
            rows = db.execute(sql, params).fetchall()
    return rows, total


def list_records(user: str, shared: bool = False, page: int | None = None, page_size: int = 20,
                 date_from=None, date_to=None, quality=None, label=None, q=None,
                 sort: str = "created_at_desc"):
    if page is None:
        rows, _ = _visible_rows(user, shared, date_from, date_to, quality, label, q, sort)
        return [_record_summary(row) for row in rows]
    rows, total = _visible_rows(
        user, shared, date_from, date_to, quality, label, q, sort,
        limit=page_size, offset=(page - 1) * page_size,
    )
    return {
        "items": [_record_summary(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size if total else 0,
        "shared": shared,
    }


FALLBACK_ZONES = {
    "Asia/Shanghai": 8,
    "Asia/Chongqing": 8,
    "Asia/Harbin": 8,
    "Asia/Hong_Kong": 8,
    "Asia/Macau": 8,
    "Asia/Taipei": 8,
    "PRC": 8,
}
_OFFSET_ZONE = re.compile(r'^(Etc/)?(?:GMT|UTC)([+-])(\d{1,2})(?::?(\d{2}))?$', re.IGNORECASE)


def _zone(name: str):
    key = (name or "UTC").strip()
    if key.upper() in {"UTC", "ETC/UTC", "GMT", "Z"}:
        return timezone.utc
    match = _OFFSET_ZONE.match(key)
    if match:
        etc, sign, hours, minutes = match.groups()
        total = int(hours) * 60 + int(minutes or 0)
        if total > 14 * 60:
            raise ValidationError("时区偏移超出范围")
        value = 1 if sign == "+" else -1
        if etc:
            # POSIX Etc/GMT-8 表示 UTC+8，符号与常见写法相反
            value = -value
        return timezone(value * timedelta(minutes=total))
    try:
        return ZoneInfo(key)
    except Exception:
        offset = FALLBACK_ZONES.get(key)
        if offset is not None:
            return timezone(timedelta(hours=offset))
        raise ValidationError("时区无效，请使用 IANA 名称，如 Asia/Shanghai")


def trend(user: str, shared: bool = False, days: int = 30, timezone_name: str = "UTC",
          fill: bool = True) -> dict:
    zone = _zone(timezone_name)
    now_local = datetime.now(zone)
    first_date = (now_local - timedelta(days=days - 1)).date()
    start_local = datetime.combine(first_date, datetime.min.time(), tzinfo=zone)
    cutoff = start_local.astimezone(timezone.utc).isoformat()
    joins, clause, params = _query_parts(user, shared)
    if clause:
        joins_clause = f"{clause} AND r.created_at>=?"
    else:
        joins_clause = " WHERE r.created_at>=?"
    with connect() as db:
        rows = db.execute(
            f"SELECT r.created_at, r.quality_status, r.label, r.heart_rate_bpm "
            f"FROM records r{joins}{joins_clause}",
            (*params, cutoff),
        ).fetchall()
    buckets: dict[str, dict] = {}
    rates_all: list[float] = []
    last_record = None
    for row in rows:
        created = _parse_iso(row["created_at"])
        if not created:
            continue
        date_text = created.astimezone(zone).date().isoformat()
        bucket = buckets.setdefault(date_text, {
            "date": date_text, "records": 0, "quality": {}, "classified": 0,
            "rates": [], "heart_rate_bpm": None,
            "heart_rate_min_bpm": None, "heart_rate_max_bpm": None,
        })
        bucket["records"] += 1
        status = row["quality_status"] or "unknown"
        bucket["quality"][status] = bucket["quality"].get(status, 0) + 1
        if row["label"] is not None:
            bucket["classified"] += 1
        bpm = row["heart_rate_bpm"]
        if isinstance(bpm, (int, float)):
            bucket["rates"].append(float(bpm))
            rates_all.append(float(bpm))
        if not last_record or row["created_at"] > last_record:
            last_record = row["created_at"]
    if fill:
        dates = [(first_date + timedelta(days=index)).isoformat() for index in range(days)]
    else:
        dates = sorted(buckets)
    points = []
    for date_text in dates:
        bucket = buckets.get(date_text)
        if not bucket:
            points.append({
                "date": date_text, "records": 0, "quality": {}, "classified": 0,
                "heart_rate_bpm": None, "heart_rate_min_bpm": None, "heart_rate_max_bpm": None,
            })
            continue
        rates = bucket["rates"]
        bucket["heart_rate_bpm"] = round(sum(rates) / len(rates), 1) if rates else None
        bucket["heart_rate_min_bpm"] = round(min(rates), 1) if rates else None
        bucket["heart_rate_max_bpm"] = round(max(rates), 1) if rates else None
        bucket.pop("rates")
        points.append(bucket)
    total = sum(point["records"] for point in points)
    insufficient = sum(point["quality"].get("insufficient", 0) for point in points)
    classified = sum(point["classified"] for point in points)
    heart_rate_days = sum(1 for point in points if point["heart_rate_bpm"] is not None)
    return {
        "days_requested": days,
        "timezone": timezone_name or "UTC",
        "shared": shared,
        "summary": {
            "total": total,
            "classified": classified,
            "insufficient": insufficient,
            "heart_rate_days": heart_rate_days,
            "avg_heart_rate_bpm": round(sum(rates_all) / len(rates_all), 1) if rates_all else None,
            "last_record_at": last_record,
        },
        "days": points,
    }


def _visible_record_row(user: str, identifier: str, *, owner_only: bool = False):
    sql = ("SELECT r.*, u.username AS owner_username FROM records r JOIN users u ON u.id=r.owner_id "
           "WHERE r.id=?")
    params: list = [identifier]
    if owner_only:
        sql += " AND r.owner_id=?"
        params.append(user)
    else:
        sql += (" AND (r.owner_id=? OR EXISTS (SELECT 1 FROM grants g "
                "WHERE g.owner_id=r.owner_id AND g.relative_id=? AND g.active=1))")
        params.extend([user, user])
    with connect() as db:
        return db.execute(sql, params).fetchone()


def _signal_row(record_id: str):
    with connect() as db:
        return db.execute("SELECT * FROM record_signals WHERE record_id=?", (record_id,)).fetchone()


def store_raw_input(user: str, task_id: str, content: bytes) -> str | None:
    """保存上传原件；失败不阻塞分析，原件是可选的追溯材料。"""
    path = (settings.upload_dir / user / f"{task_id}.csv").resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except OSError:
        return None
    with connect() as db:
        db.execute("UPDATE analysis_tasks SET input_path=? WHERE id=?", (str(path), task_id))
    return str(path)


def raw_file(user: str, identifier: str):
    row = _visible_record_row(user, identifier, owner_only=True)
    if not row:
        raise RecordNotFound("记录不存在或没有下载权限")
    if not row["input_path"]:
        raise InputUnavailable("该记录没有保存原始文件")
    path = Path(row["input_path"])
    try:
        path.resolve().relative_to(settings.upload_dir.resolve())
    except (ValueError, OSError) as exc:
        raise InputUnavailable("原始文件路径无效") from exc
    if not path.is_file():
        raise InputUnavailable("原始文件已清理")
    with connect() as db:
        _audit(db, identifier, user, "raw")
    return path, f"ecg-record-{identifier}-raw.csv"


def waveform_window(user: str, identifier: str, start_sec: float | None = None,
                    end_sec: float | None = None, max_points: int = 2000,
                    mode: str = "envelope") -> dict:
    if mode not in {"envelope", "mean"}:
        raise ValidationError("mode 仅支持 envelope/mean")
    row = _visible_record_row(user, identifier)
    if not row:
        raise RecordNotFound("记录不存在或没有查看权限")
    signal_row = _signal_row(identifier)
    payload = json.loads(row["payload"])
    result = payload.get("result") or {}
    if settings.signal_source != "payload" and signal_row:
        values = signals.decode(signal_row["data"], signal_row["encoding"], signal_row["n_samples"])
        rate = float(signal_row["sample_rate_hz"])
        unit = signal_row["unit"]
    else:
        values = result.get("waveform") or []
        rate = float(result.get("sample_rate_hz") or 0)
        unit = result.get("unit") or "mV"
    if not values or rate <= 0:
        raise InputUnavailable("记录没有可用的波形数据")
    duration = len(values) / rate
    start = 0.0 if start_sec is None else max(0.0, min(float(start_sec), duration))
    end = duration if end_sec is None else max(0.0, min(float(end_sec), duration))
    if end <= start:
        raise ValidationError("时间窗无效：end_sec 必须大于 start_sec")
    start_index = min(len(values), int(start * rate))
    end_index = min(len(values), max(start_index + 1, int(round(end * rate))))
    segment = values[start_index:end_index]
    points = signals.window_points(segment, start_index, rate, max_points, mode)
    with connect() as db:
        _audit(db, identifier, user, "waveform")
    return {
        "record_id": identifier,
        "sample_rate_hz": rate,
        "unit": unit,
        "total_samples": len(values),
        "start_sec": round(start_index / rate, 6),
        "end_sec": round(end_index / rate, 6),
        "returned_points": len(points),
        "mode": mode,
        "points": points,
    }


def update_note(user: str, identifier: str, note: str):
    text = (note or "").strip()
    if len(text) > 500:
        raise ValidationError("备注最多 500 字符")
    row = _visible_record_row(user, identifier, owner_only=True)
    if not row:
        raise RecordNotFound("记录不存在或没有编辑权限")
    with connect() as db:
        payload = json.loads(row["payload"])
        payload["note"] = text
        db.execute(
            "UPDATE records SET note=?, updated_at=?, payload=? WHERE id=?",
            (text, _now(), json.dumps(payload, ensure_ascii=False), identifier),
        )
        _audit(db, identifier, user, "note")
    return detail(user, identifier)


def reanalyze(user: str, identifier: str) -> dict:
    row = _visible_record_row(user, identifier, owner_only=True)
    if not row:
        raise RecordNotFound("记录不存在或没有重分析权限")
    with connect() as db:
        task = db.execute(
            "SELECT t.id, t.input_path, i.payload FROM analysis_tasks t "
            "LEFT JOIN task_inputs i ON i.task_id=t.id WHERE t.record_id=? "
            "ORDER BY t.created_at DESC LIMIT 1",
            (identifier,),
        ).fetchone()
        _audit(db, identifier, user, "reanalyze")
    if not task or not task["payload"]:
        raise InputUnavailable("原始输入已清理，无法重分析")
    new_task = submit(user, json.loads(task["payload"]), source_record_id=identifier)
    source_path = task["input_path"]
    if source_path and Path(source_path).is_file():
        target = (settings.upload_dir / user / f"{new_task['id']}.csv").resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(source_path).read_bytes())
            with connect() as db:
                db.execute("UPDATE analysis_tasks SET input_path=? WHERE id=?", (str(target), new_task["id"]))
        except OSError:
            pass
    return new_task


def export_record(user: str, identifier: str, format: str = "csv"):
    row = _visible_record_row(user, identifier, owner_only=True)
    if not row:
        raise RecordNotFound("记录不存在或没有导出权限")
    record = detail(user, identifier)
    with connect() as db:
        _audit(db, identifier, user, "export", format)
    if format == "json":
        return json.dumps(record, ensure_ascii=False, indent=2), "application/json; charset=utf-8"
    if format != "csv":
        raise ValueError("导出格式仅支持 csv 或 json")
    result = record.get("result", {})
    prediction = result.get("prediction", {})
    heart_rate = prediction.get("heart_rate") or {}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[
        "timestamp_sec", "value", "sample_rate_hz", "unit", "source",
        "quality_status", "quality_reasons", "heart_rate_bpm", "record_id", "created_at",
    ])
    writer.writeheader()
    values = result.get("waveform") or []
    rate = float(result.get("sample_rate_hz") or 1)
    for index, value in enumerate(values):
        writer.writerow({
            "timestamp_sec": index / rate,
            "value": value,
            "sample_rate_hz": result.get("sample_rate_hz"),
            "unit": result.get("unit"),
            "source": result.get("source"),
            "quality_status": result.get("quality", {}).get("status"),
            "quality_reasons": ";".join(result.get("quality", {}).get("reasons", [])),
            "heart_rate_bpm": heart_rate.get("bpm", result.get("heart_rate_bpm")),
            "record_id": record.get("id"),
            "created_at": record.get("created_at"),
        })
    return "\ufeff" + output.getvalue(), "text/csv; charset=utf-8"


def delete_record(user: str, identifier: str):
    path = None
    with connect() as db:
        row = db.execute("SELECT id, input_path FROM records WHERE id=? AND owner_id=?",
                         (identifier, user)).fetchone()
        if not row:
            raise RecordNotFound("记录不存在或没有删除权限")
        path = row["input_path"]
        _audit(db, identifier, user, "delete")
        db.execute("UPDATE records SET supersedes_record_id=NULL WHERE supersedes_record_id=?",
                   (identifier,))
        db.execute("UPDATE analysis_tasks SET source_record_id=NULL WHERE source_record_id=?",
                   (identifier,))
        task_rows = db.execute("SELECT id FROM analysis_tasks WHERE record_id=?", (identifier,)).fetchall()
        task_ids = [task["id"] for task in task_rows]
        if task_ids:
            db.executemany("DELETE FROM task_inputs WHERE task_id=?", [(task_id,) for task_id in task_ids])
            db.executemany("DELETE FROM analysis_tasks WHERE id=?", [(task_id,) for task_id in task_ids])
        db.execute("DELETE FROM record_signals WHERE record_id=?", (identifier,))
        db.execute("DELETE FROM records WHERE id=? AND owner_id=?", (identifier, user))
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return {"id": identifier, "message": "记录已删除"}


def detail(user: str, identifier: str):
    row = _visible_record_row(user, identifier)
    if not row:
        raise RecordNotFound("记录不存在或没有查看权限")
    payload = json.loads(row["payload"])
    signal_row = _signal_row(identifier)
    result = payload.setdefault("result", {})
    if settings.signal_source != "payload" and signal_row:
        result["waveform"] = signals.decode(
            signal_row["data"], signal_row["encoding"], signal_row["n_samples"])
    elif "waveform" not in result:
        result["waveform"] = []
    for key, value in _record_summary(row, payload).items():
        if value is not None:
            payload[key] = value
        else:
            payload.setdefault(key, value)
    payload["owner_username"] = row["owner_username"]
    payload["owned"] = row["owner_id"] == user
    payload["has_raw_file"] = bool(row["input_path"] and Path(row["input_path"]).is_file())
    with connect() as db:
        _audit(db, identifier, user, "view")
    return payload


def access_log(user: str, identifier: str, action: str | None = None,
               page: int = 1, page_size: int = 20) -> dict:
    if action and action not in ACCESS_ACTIONS:
        raise ValidationError(f"action 仅支持 {'/'.join(sorted(ACCESS_ACTIONS))}")
    row = _visible_record_row(user, identifier, owner_only=True)
    if not row:
        raise RecordNotFound("记录不存在或没有审计查看权限")
    where = ["l.record_id=?"]
    params: list = [identifier]
    if action:
        where.append("l.action=?")
        params.append(action)
    clause = " WHERE " + " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM record_access_log l{clause}", params).fetchone()[0]
        rows = db.execute(
            f"""SELECT l.id, l.action, l.detail, l.created_at, l.actor_id, u.username AS actor_username
                FROM record_access_log l LEFT JOIN users u ON u.id=l.actor_id{clause}
                ORDER BY l.id DESC LIMIT ? OFFSET ?""",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "record_id": identifier,
        "items": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


def purge_audit_log(days: int | None = None) -> int:
    days = settings.audit_retention_days if days is None else int(days)
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connect() as db:
        cursor = db.execute("DELETE FROM record_access_log WHERE created_at < ?", (cutoff,))
    return cursor.rowcount
