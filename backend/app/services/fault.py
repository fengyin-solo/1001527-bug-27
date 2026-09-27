"""故障处置业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "fault"
REQUIRED_FIELDS = ["涉及站点", "故障现象"]
OPTIONAL_FIELDS = ["站点区域", "发生时刻", "影响要素", "处置人员"]
STATUS_ORDER = ["待派单", "处置中", "已挂起", "已恢复", "已作废"]
OPEN_STATUSES = {"待派单", "处置中", "已挂起"}
ABNORMAL_STATUSES = {"已挂起"}
ACTION_RULES = {"派单处置": "处置中", "挂起故障": "已挂起", "确认恢复": "已恢复", "标记误报": "已作废"}
ACTION_ALLOWED_FROM = {
    "派单处置": {"待派单", "已挂起"},
    "挂起故障": {"待派单", "处置中"},
    "确认恢复": {"处置中", "已挂起"},
    "标记误报": {"待派单", "处置中", "已挂起"},
}
TIME_FORMAT = "%Y-%m-%d %H:%M"
TIME_FORMATS = (TIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _now_text(moment: datetime) -> str:
    return moment.strftime(TIME_FORMAT)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_duration(minutes: float) -> str:
    total = max(int(round(minutes)), 0)
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}小时{mins}分"
    if hours:
        return f"{hours}小时"
    return f"{mins}分"


class FaultService:
    def _decorate(self, row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        """补齐派生字段：故障状态、处置时长、资料待补，保证列表/详情/看板同一口径。"""
        moment = now or datetime.now()
        entry = dict(row)
        status = str(entry.get("status") or "")
        entry["故障状态"] = status
        entry["pending"] = status in OPEN_STATUSES
        entry["abnormal"] = status in ABNORMAL_STATUSES
        entry["资料待补"] = status != "已作废" and not str(entry.get("影响要素") or "").strip()
        entry["处置时长"] = ""
        start = _parse_time(entry.get("发生时刻"))
        if status != "已作废" and start is not None:
            end = _parse_time(entry.get("恢复时刻")) or moment
            entry["处置时长"] = _format_duration((end - start).total_seconds() / 60)
        return entry

    def _sync_flags(self, entry: dict[str, Any]) -> None:
        """状态变更后同步看板计数字段，异常量只看「已挂起」。"""
        status = str(entry.get("status") or "")
        entry["pending"] = status in OPEN_STATUSES
        entry["abnormal"] = status in ABNORMAL_STATUSES

    def _append_trace(self, entry: dict[str, Any], action: str, note: str = "") -> None:
        trace = entry.setdefault("处置轨迹", [])
        trace.append({"时刻": _now_text(datetime.now()), "动作": action, "说明": note})

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        region: str | None = None,
        sort: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        now = datetime.now()
        rows = [self._decorate(row, now=now) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("故障编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if region:
            rows = [row for row in rows if str(row.get("站点区域", "")) == region]
        if sort == "站点区域":
            rows.sort(key=lambda row: (str(row.get("站点区域") or ""), str(row.get("发生时刻") or "")))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return self._decorate(row)

    def stats(self) -> dict[str, Any]:
        """处置看板口径：异常量、待处理、平均处置时长，与列表/详情同源。"""
        now = datetime.now()
        rows = [self._decorate(row, now=now) for row in store.rows(MODULE)]
        durations: list[float] = []
        for row in rows:
            if row.get("status") != "已恢复":
                continue
            start = _parse_time(row.get("发生时刻"))
            end = _parse_time(row.get("恢复时刻"))
            if start is not None and end is not None:
                durations.append(max(0.0, (end - start).total_seconds() / 60))
        average = sum(durations) / len(durations) if durations else 0.0
        return {
            "总数": len(rows),
            "待派单": sum(1 for row in rows if row.get("status") == "待派单"),
            "处置中": sum(1 for row in rows if row.get("status") == "处置中"),
            "已挂起": sum(1 for row in rows if row.get("status") == "已挂起"),
            "已恢复": sum(1 for row in rows if row.get("status") == "已恢复"),
            "已作废": sum(1 for row in rows if row.get("status") == "已作废"),
            "待处理": sum(1 for row in rows if row.get("pending")),
            "异常量": sum(1 for row in rows if row.get("abnormal")),
            "资料待补": sum(1 for row in rows if row.get("资料待补")),
            "平均处置时长": _format_duration(average) if durations else "—",
            "平均处置时长分钟": round(average, 1),
            "站点区域列表": sorted({str(row.get("站点区域") or "") for row in rows if str(row.get("站点区域") or "").strip()}),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, False
        station = str(values.get("涉及站点") or "").strip()
        phenomenon = str(values.get("故障现象") or "").strip()
        for row in store.rows(MODULE):
            same_fault = (
                str(row.get("涉及站点", "")).strip() == station
                and str(row.get("故障现象", "")).strip() == phenomenon
            )
            if same_fault and row.get("status") in OPEN_STATUSES:
                row["报障次数"] = int(row.get("报障次数", 1)) + 1
                row["最近报障时刻"] = _now_text(datetime.now())
                self._append_trace(row, "重复报障", f"同一站点同一故障现象再次报障，合并到本记录（第 {row['报障次数']} 次）")
                return self._decorate(row), [], True
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["故障编号"] = str(values.get("故障编号") or "").strip() or f"FAUL-{entry['id']:04d}"
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        if not entry["发生时刻"]:
            entry["发生时刻"] = _now_text(datetime.now())
        entry["status"] = STATUS_ORDER[0]
        entry["报障次数"] = 1
        entry["最近报障时刻"] = entry["发生时刻"]
        entry["挂起原因"] = ""
        entry["挂起时刻"] = ""
        entry["恢复时刻"] = ""
        entry["误报原因"] = ""
        entry["处置轨迹"] = []
        self._sync_flags(entry)
        self._append_trace(entry, "登记故障", "故障记录登记")
        rows.append(entry)
        return self._decorate(entry), [], False

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"故障记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于故障处置可执行范围"
        current = str(entry.get("status") or "")
        allowed_from = ACTION_ALLOWED_FROM[action]
        if current not in allowed_from:
            return None, f"当前状态「{current}」不能执行「{action}」，仅「{'、'.join(sorted(allowed_from))}」状态可执行"
        values = values or {}
        reason = str(values.get("挂起原因") or values.get("原因") or "").strip()
        operator = str(values.get("处置人员") or "").strip()
        now_text = _now_text(datetime.now())
        note = reason
        if action == "挂起故障":
            if not reason:
                return None, "挂起故障必须填写挂起原因，否则无法留痕"
            entry["挂起原因"] = reason
            entry["挂起时刻"] = now_text
        elif action == "确认恢复":
            entry["恢复时刻"] = now_text
            if not str(entry.get("影响要素") or "").strip():
                note = "影响要素未填写，记录标记为资料待补"
        elif action == "标记误报":
            entry["误报原因"] = reason or "登记时选错故障记录"
            note = entry["误报原因"]
        if operator:
            entry["处置人员"] = operator
        entry["status"] = ACTION_RULES[action]
        self._sync_flags(entry)
        self._append_trace(entry, action, note)
        return self._decorate(entry), f"故障记录已{action}"
