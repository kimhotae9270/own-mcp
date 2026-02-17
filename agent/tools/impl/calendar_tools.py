# tools/impl/calendar_tools.py

from __future__ import annotations

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import requests

from agent.tool_registry.registry import register_tool
from app.services.google_token_manager import get_valid_google_access_token

GOOGLE_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


# =========================================================
# 공통 유틸
# =========================================================

def _calendar_request(
    access_token: str,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    url = f"{GOOGLE_CALENDAR_BASE}{path}"

    resp = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=json_body,
        timeout=10,
    )

    if resp.status_code >= 400:

        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text,
        }

    if resp.status_code == 204:

        return {"ok": True}

    return {"ok": True, "data": resp.json()}


# =========================================================
# 1️⃣ 이벤트 생성
# =========================================================

class CalendarCreateEventArgs(BaseModel):
    title: str = Field(..., description="Event title.")
    start: str = Field(..., description="Start datetime (ISO 8601 with timezone).")
    end: str = Field(..., description="End datetime (ISO 8601 with timezone).")
    all_day: bool = Field(False,
                          description="If true, treat start/end as dates (YYYY-MM-DD) and create an all-day event.")
    location: Optional[str] = Field(None, description="Optional location.")
    description: Optional[str] = Field(None, description="Optional description.")
    calendar_id: str = Field("primary", description="Calendar ID (default: primary).")
    timezone: Optional[str] = Field(None, description="Optional timezone (e.g., Asia/Seoul).")


@register_tool(
    name="calendar_create_event",
    description="Create a Google Calendar event for the current authenticated user.",
    input_model=CalendarCreateEventArgs,
    tags=["calendar", "write"],
)
async def calendar_create_event(args: CalendarCreateEventArgs, ctx: dict) -> dict:
    user_id = ctx["user_id"]

    # 🔐 항상 유효한 토큰 보장
    access_token = get_valid_google_access_token(user_id)
    print("캘린더 실행",user_id)
    body = {
        "summary": args.title,
        "location": args.location,
        "description": args.description,
        "start": {"dateTime": args.start},
        "end": {"dateTime": args.end},
    }

    if args.all_day:
        body["start"] = {"date": args.start}
        body["end"] = {"date": args.end}  # all-day는 end가 '다음날'이어야 함
    else:
        body["start"] = {"dateTime": args.start}
        body["end"] = {"dateTime": args.end}
        if args.timezone:
            body["start"]["timeZone"] = args.timezone
            body["end"]["timeZone"] = args.timezone

    return _calendar_request(
        access_token=access_token,
        method="POST",
        path=f"/calendars/{args.calendar_id}/events",
        json_body=body,
    )


# =========================================================
# 2️⃣ 이벤트 조회
# =========================================================

class CalendarListEventsArgs(BaseModel):
    calendar_id: str = Field("primary", description="Calendar ID (default: primary).")
    time_min: Optional[str] = Field(None, description="Lower bound ISO datetime.")
    time_max: Optional[str] = Field(None, description="Upper bound ISO datetime.")
    max_results: int = Field(10, ge=1, le=50, description="Max results (1-50).")
    query: Optional[str] = Field(None, description="Free text search.")
    single_events: bool = Field(True, description="Expand recurring events.")


@register_tool(
    name="calendar_list_events",
    description="List events from the user's Google Calendar.",
    input_model=CalendarListEventsArgs,
    tags=["calendar", "read"],
)
async def calendar_list_events(args: CalendarListEventsArgs, ctx: dict) -> dict:
    user_id = ctx["user_id"]
    access_token = get_valid_google_access_token(user_id)

    params = {
        "maxResults": args.max_results,
        "singleEvents": str(args.single_events).lower(),
        "orderBy": "startTime",
    }

    if args.time_min:
        params["timeMin"] = args.time_min
    if args.time_max:
        params["timeMax"] = args.time_max
    if args.query:
        params["q"] = args.query

    return _calendar_request(
        access_token=access_token,
        method="GET",
        path=f"/calendars/{args.calendar_id}/events",
        params=params,
    )


# =========================================================
# 3️⃣ 이벤트 삭제
# =========================================================

class CalendarDeleteEventArgs(BaseModel):
    event_id: str = Field(..., description="Google eventId to delete.")
    calendar_id: str = Field("primary", description="Calendar ID (default: primary).")


@register_tool(
    name="calendar_delete_event",
    description="Delete an event from the user's Google Calendar.",
    input_model=CalendarDeleteEventArgs,
    tags=["calendar", "write"],
)
async def calendar_delete_event(args: CalendarDeleteEventArgs, ctx: dict) -> dict:
    user_id = ctx["user_id"]
    access_token = get_valid_google_access_token(user_id)

    return _calendar_request(
        access_token=access_token,
        method="DELETE",
        path=f"/calendars/{args.calendar_id}/events/{args.event_id}",
    )
