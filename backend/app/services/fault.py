"""故障处置业务规则：状态流转、字段校验、合并口径与看板统计都收在这里。

状态机：待派单 --派单处置--> 处置中 --挂起故障--> 已挂起 --确认恢复--> 已恢复
                                  └──确认恢复──────┘
- 挂起只允许从「处置中」发起，且必须填写挂起原因，挂起时刻随之落库；
- 恢复只允许从「处置中 / 已挂起」发起，恢复时刻落库，挂起原因与挂起时刻保留不丢；
- 同一站点 + 同一故障现象且尚未恢复的记录视为重复报障，合并到原记录上；
- 列表、详情、看板的「故障状态 / 处置时长 / 异常量」统一由 serialize_entry 计算。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "fault"
REQUIRED_FIELDS = ["故障编号", "涉及站点", "站点区域", "故障现象", "影响要素"]
OPEN_STATUSES = ["待派单", "处置中", "已挂起"]
STATUS_ORDER = ["待派单", "处置中", "已挂起", "已恢复"]
# 已派单但未恢复（处置中、已挂起）的故障计入异常量；待派单单列，已恢复不计。
ABNORMAL_STATUSES = ["处置中", "已挂起"]
ACTIONS = ["派单处置", "挂起故障", "确认恢复"]

_TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    return datetime.now().strftime(_TIME_FMT)


def _parse_time(value: Any) -> datetime | None:
    """兼容「YYYY-MM-DD HH:MM:SS」与 ISO 格式；解析不了的视为缺时间。"""
    if not value:
        return None
    text = str(value).strip().replace("/", "-")
    for parser in (
        lambda v: datetime.strptime(v, _TIME_FMT),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M"),
        lambda v: datetime.strptime(v, "%Y-%m-%d"),
        datetime.fromisoformat,
    ):
        try:
            return parser(text)
        except ValueError:
            continue
    return None


def format_duration(minutes: float | None) -> str:
    """处置时长的唯一展示口径：分钟向上取整后按天/小时/分钟拼中文。"""
    if minutes is None:
        return "未派单"
    total = max(int(minutes), 0)
    if total < 1:
        return "不足1分钟"
    days, remain = divmod(total, 60 * 24)
    hours, mins = divmod(remain, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if mins or not parts:
        parts.append(f"{mins}分钟")
    return "".join(parts)


def _duration_text(entry: dict[str, Any], *, at: datetime | None = None) -> str:
    """派单时刻 → 恢复时刻；还没恢复的按当前时刻滚动计算；待派单显示「未派单」。"""
    start = _parse_time(entry.get("派单时刻"))
    if start is None:
        return "未派单"
    end = _parse_time(entry.get("恢复时刻")) or at or datetime.now()
    return format_duration((end - start).total_seconds() / 60)


def _is_open(entry: dict[str, Any]) -> bool:
    return entry.get("status") != "已恢复"


def serialize_entry(entry: dict[str, Any], *, at: datetime | None = None) -> dict[str, Any]:
    """对外字段统一在这里投影，保证列表、详情、看板、导出看到的口径一致。"""
    status = str(entry.get("status") or "待派单")
    abnormal = status in ABNORMAL_STATUSES
    missing = [field for field in ("涉及站点", "故障现象", "影响要素") if not str(entry.get(field) or "").strip()]
    data = dict(entry)
    data["status"] = status
    data["pending"] = status != "已恢复"
    data["abnormal"] = abnormal
    data["故障状态"] = status
    data["处置时长"] = _duration_text(entry, at=at)
    data["异常标识"] = "异常" if abnormal else "正常"
    data["信息完整"] = not missing
    data["待补字段"] = "、".join(missing)
    data.setdefault("报障次数", 1)
    data.setdefault("重复报障", [])
    data.setdefault("挂起原因", "")
    data.setdefault("挂起时刻", "")
    data.setdefault("恢复说明", "")
    return data


class FaultService:
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
        rows = self._filter(store.rows(MODULE), keyword=keyword, status=status, region=region)
        if sort == "region":
            # 按站点区域排列：同一区域聚到一起，区域内再按报障先后。
            rows = sorted(rows, key=lambda row: (str(row.get("站点区域") or ""), int(row.get("id", 0))))
        total = len(rows)
        start = max(page - 1, 0) * size
        return [serialize_entry(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return serialize_entry(entry) if entry is not None else None

    def all_regions(self) -> list[str]:
        names = {str(row.get("站点区域") or "").strip() for row in store.rows(MODULE)}
        return sorted(name for name in names if name)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """登记故障。

        返回 (记录, 提示信息, 是否合并到了已有记录)；必填缺失时记录为 None。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，请补全后再登记", False

        station = str(values["涉及站点"]).strip()
        phenomenon = str(values["故障现象"]).strip()
        merged = self._merge_duplicate(station, phenomenon, values)
        if merged is not None:
            return serialize_entry(merged), (
                f"站点「{station}」的故障现象「{phenomenon}」已有未恢复记录"
                f"（{merged['故障编号']}），本次按重复报障合并，累计报障 {merged['报障次数']} 次"
            ), True

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ("故障编号", "涉及站点", "站点区域", "故障现象", "影响要素"):
            entry[field] = str(values[field]).strip()
        entry["发生时刻"] = str(values.get("发生时刻") or _now()).strip() or _now()
        entry["处置人员"] = str(values.get("处置人员") or "").strip()
        entry["报障次数"] = 1
        entry["重复报障"] = []
        entry["挂起原因"] = ""
        entry["挂起时刻"] = ""
        entry["恢复时刻"] = ""
        entry["恢复说明"] = ""
        entry["派单时刻"] = ""
        entry["status"] = "待派单"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return serialize_entry(entry), "故障记录已登记", False

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"故障记录 {entry_id} 不存在或已归档"
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于故障处置可执行范围"

        status = entry.get("status")
        if action == "派单处置":
            if status != "待派单":
                return None, f"故障记录「{entry.get('故障编号')}」当前为{status}，无需重复派单"
            operator = str(values.get("处置人员") or entry.get("处置人员") or "").strip()
            if not operator:
                return None, "派单处置需填写处置人员"
            entry["处置人员"] = operator
            entry["派单时刻"] = _now()
            entry["status"] = "处置中"
        elif action == "挂起故障":
            if status == "待派单":
                return None, f"故障记录「{entry.get('故障编号')}」尚未派单，不能直接挂起，请先派单处置"
            if status == "已挂起":
                return None, f"故障记录「{entry.get('故障编号')}」已是挂起状态，请勿重复挂起"
            if status == "已恢复":
                return None, f"故障记录「{entry.get('故障编号')}」已恢复，不能再挂起"
            reason = str(values.get("挂起原因") or "").strip()
            if not reason:
                return None, "挂起故障必须填写挂起原因，便于恢复时追溯"
            entry["挂起原因"] = reason
            entry["挂起时刻"] = _now()
            entry["status"] = "已挂起"
        else:  # 确认恢复
            if status not in ("处置中", "已挂起"):
                return None, (
                    f"故障记录「{entry.get('故障编号')}」当前为{status}，"
                    "只有处置中或已挂起的记录才能确认恢复，请勿误操作其他记录"
                )
            entry["恢复时刻"] = _now()
            note = str(values.get("恢复说明") or "").strip()
            if note:
                entry["恢复说明"] = note
            entry["status"] = "已恢复"

        # 待处理 / 异常标记只由状态推导，避免各动作各写一套口径。
        entry["pending"] = entry["status"] != "已恢复"
        entry["abnormal"] = entry["status"] in ABNORMAL_STATUSES
        return serialize_entry(entry), f"故障记录已{action}"

    def board(self, *, region: str | None = None) -> dict[str, Any]:
        """处置看板：各状态量、异常量与平均处置时长全部来自同一份序列化结果。"""
        snapshot = datetime.now()
        rows = [
            serialize_entry(row, at=snapshot)
            for row in self._filter(store.rows(MODULE), region=region)
        ]
        counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            counts[row["故障状态"]] += 1
        recovered = [row for row in rows if row["故障状态"] == "已恢复"]
        durations = [
            (_parse_time(row.get("恢复时刻")) - _parse_time(row.get("派单时刻"))).total_seconds() / 60
            for row in recovered
            if _parse_time(row.get("恢复时刻")) and _parse_time(row.get("派单时刻"))
        ]
        avg = format_duration(sum(durations) / len(durations)) if durations else "暂无已恢复记录"
        incomplete = sum(1 for row in rows if not row["信息完整"])
        abnormal_total = sum(1 for row in rows if row["异常标识"] == "异常")
        return {
            "cards": [
                {"label": "待派单故障", "value": counts["待派单"]},
                {"label": "处置中故障", "value": counts["处置中"]},
                {"label": "已挂起故障", "value": counts["已挂起"]},
                {"label": "异常量（处置中+已挂起）", "value": abnormal_total},
                {"label": "已恢复故障", "value": counts["已恢复"]},
                {"label": "资料未齐", "value": incomplete},
                {"label": "平均处置时长", "value": avg},
            ],
            "statusCounts": counts,
            "abnormal": abnormal_total,
            "total": len(rows),
        }

    # ---- 内部辅助 -------------------------------------------------
    def _filter(
        self,
        rows: list[dict[str, Any]],
        *,
        keyword: str | None = None,
        status: str | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        result = rows
        if keyword:
            key = keyword.strip()
            result = [
                row
                for row in result
                if key in str(row.get("故障编号", ""))
                or key in str(row.get("涉及站点", ""))
                or key in str(row.get("站点区域", ""))
            ]
        if status:
            result = [row for row in result if row.get("status") == status]
        if region:
            result = [row for row in result if str(row.get("站点区域") or "").strip() == region.strip()]
        return result

    def _merge_duplicate(
        self, station: str, phenomenon: str, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        """同一站点 + 同一故障现象且尚未恢复时合并报障，已恢复的不再并单。"""
        for row in store.rows(MODULE):
            if not _is_open(row):
                continue
            if str(row.get("涉及站点") or "").strip() != station:
                continue
            if str(row.get("故障现象") or "").strip() != phenomenon:
                continue
            row["报障次数"] = int(row.get("报障次数") or 1) + 1
            row.setdefault("重复报障", []).append(
                {"报障时刻": str(values.get("发生时刻") or _now()), "报障说明": str(values.get("报障说明") or "").strip()}
            )
            # 重复报障刷新发生时刻，影响要素若原记录缺失可借本次补全。
            row["发生时刻"] = str(values.get("发生时刻") or row.get("发生时刻") or _now())
            if not str(row.get("影响要素") or "").strip() and str(values.get("影响要素") or "").strip():
                row["影响要素"] = str(values["影响要素"]).strip()
            return row
        return None
