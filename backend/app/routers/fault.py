"""故障处置接口：维护故障记录，覆盖派单处置、确认恢复、挂起故障等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.fault import STATUS_ORDER, FaultService

router = APIRouter(prefix="/api/fault", tags=["故障处置"])

service = FaultService()

LIST_FIELDS = ["故障编号", "涉及站点", "站点区域", "故障现象", "发生时刻", "影响要素", "处置人员", "派单时刻", "挂起时刻", "挂起原因", "恢复时刻", "恢复说明", "处置时长", "故障状态"]


@router.get("/board")
def board(region: str | None = Query(default=None, description="按站点区域过滤看板")) -> dict[str, Any]:
    """处置看板：状态量、异常量、平均处置时长与列表共用同一套计算口径。"""
    payload = service.board(region=region)
    payload["regions"] = service.all_regions()
    return payload


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按故障编号 / 涉及站点 / 站点区域检索"),
    status: str | None = Query(default=None, description="待派单、处置中、已挂起、已恢复"),
    region: str | None = Query(default=None, description="按站点区域过滤"),
    sort: str | None = Query(default=None, description="region 表示按站点区域排列"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按故障编号、状态、区域过滤故障处置列表；没有数据时返回空页，不报错。"""
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"故障状态「{status}」不支持，可选：{'、'.join(STATUS_ORDER)}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, region=region, sort=sort, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/regions")
def list_regions() -> dict[str, Any]:
    """列出当前故障记录覆盖的站点区域，供看板与列表筛选、排列使用。"""
    return {"regions": service.all_regions()}


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    status: str | None = None,
    region: str | None = None,
    sort: str | None = None,
) -> dict[str, Any]:
    """导出故障处置清单：沿用列表的过滤条件与序列化口径，导出的状态/时长与页面一致。"""
    items, total = service.list_entries(
        keyword=keyword, status=status, region=region, sort=sort, page=1, size=10000
    )
    return {"module": "fault", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条故障记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"故障记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条故障记录，缺字段或重复报障合并时都会说明原因而不是静默丢弃。"""
    entry, message, _merged = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条故障记录执行派单处置、确认恢复、挂起故障。

    挂起需带挂起原因、恢复可带恢复说明；状态机不允许的动作（含点错记录）会被拦下。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
