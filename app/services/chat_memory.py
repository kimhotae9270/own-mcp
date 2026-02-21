import json
import os
import logging

from app.core.redis_client import r

# Redis는 "LLM 컨텍스트용 숏텀 메모리"로만 쓰는 것을 권장합니다.
# 원본 메시지 로그는 DB(messages 테이블)에 남기고,
# Redis에는 요약(summary) + 최근 메시지(recent)만 유지하면 토큰/비용/지연을 안정적으로 관리할 수 있습니다.

SHORT_TTL = 60 * 60 * 6

# recent 리스트에 유지할 최대 메시지 수(메시지 단위: user/assistant 각각 1개)
CHAT_MAX_MESSAGES = int(os.getenv("CHAT_MAX_MESSAGES", "30"))

# 요약이 트리거되었을 때, recent 리스트에 남겨둘 메시지 수
# - CHAT_MAX_MESSAGES보다 작게 두면 요약 호출 빈도가 줄어듭니다.
CHAT_KEEP_MESSAGES = int(os.getenv("CHAT_KEEP_MESSAGES", "20"))

# 요약 생성에 사용할 모델
SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))

logger = logging.getLogger(__name__)


def k_recent(uid, cid):
    return f"conv:{uid}:{cid}:recent"


def k_summary(uid, cid):
    return f"conv:{uid}:{cid}:summary"


def k_state(uid, cid):
    return f"conv:{uid}:{cid}:state"


def _safe_json_loads(x):
    try:
        if isinstance(x, (bytes, bytearray)):
            x = x.decode("utf-8")
        return json.loads(x)
    except Exception:
        return None


def _fmt_for_summary(msgs: list[dict]) -> str:
    lines: list[str] = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if not role or not content:
            continue
        if role not in ("user", "assistant"):
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def _update_summary(prev_summary: str, old_msgs: list[dict]) -> str:
    """prev_summary에 old_msgs(원문)를 누적 반영한 요약을 생성합니다."""
    transcript = _fmt_for_summary(old_msgs)
    if not transcript:
        return prev_summary or ""

    # 순환 import 방지를 위해 lazy import
    try:
        from agent.llm.client import get_llm
    except Exception:
        logger.exception("Failed to import get_llm for summarization")
        return prev_summary or ""

    llm = get_llm()
    sys = (
        "You are a conversation summarizer. "
        "Update the running summary with new dialogue. "
        "Write the updated summary in Korean. "
        "Keep it concise and factual. "
        "Preserve: user preferences, decisions, constraints, TODOs, IDs/dates, and tool outcomes. "
        "Do NOT invent details. "
        "Target length: <= 1200 Korean characters."
    )
    usr = (
        "[기존 요약]\n"
        f"{(prev_summary or '(없음)').strip()}\n\n"
        "[새로 반영할 대화(원문)]\n"
        f"{transcript}\n\n"
        "위 내용을 반영해서 '업데이트된 요약'만 출력해줘."
    )

    try:
        resp = await llm.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": usr},
            ],
            temperature=0.0,
        )
        return (resp.choices[0].message.content or "").strip() or (prev_summary or "")
    except Exception:
        logger.exception("Summarization LLM call failed")
        return prev_summary or ""


async def load_mem(user_id: int, conversation_id: str):
    recent_raw = await r.lrange(k_recent(user_id, conversation_id), 0, -1)
    recent = [m for m in (_safe_json_loads(x) for x in (recent_raw or [])) if m]

    summary = await r.get(k_summary(user_id, conversation_id)) or ""
    if isinstance(summary, (bytes, bytearray)):
        summary = summary.decode("utf-8")

    state_raw = await r.get(k_state(user_id, conversation_id))
    state = json.loads(state_raw) if state_raw else {}
    return {"recent": recent, "summary": summary, "state": state}


async def save_mem(
    user_id: int,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
    summary=None,
    state=None,
):
    rk = k_recent(user_id, conversation_id)
    summary_key = k_summary(user_id, conversation_id)
    state_key = k_state(user_id, conversation_id)

    # 안전장치
    max_msgs = max(1, int(CHAT_MAX_MESSAGES))
    keep_msgs = min(max(1, int(CHAT_KEEP_MESSAGES)), max_msgs)

    # 1) recent에 이번 턴 추가
    await r.rpush(rk, json.dumps({"role": "user", "content": user_text}, ensure_ascii=False))
    await r.rpush(rk, json.dumps({"role": "assistant", "content": assistant_text}, ensure_ascii=False))

    # 2) 외부에서 summary/state를 넘겨주면 먼저 반영
    if summary is not None:
        await r.set(summary_key, summary)
    if state is not None:
        await r.set(state_key, json.dumps(state, ensure_ascii=False))

    # 3) 메시지 길이 관리: max_msgs 초과 시 오래된 메시지를 summary로 누적하고 삭제
    try:
        llen = await r.llen(rk)
    except Exception:
        llen = len(await r.lrange(rk, 0, -1))

    if llen > max_msgs:
        # 앞에서 cut개를 summary에 누적하고, recent에는 keep_msgs만 남김
        cut = max(0, llen - keep_msgs)
        if cut > 0:
            old_raw = await r.lrange(rk, 0, cut - 1)
            old_msgs = [m for m in (_safe_json_loads(x) for x in (old_raw or [])) if m]

            prev_summary = summary if summary is not None else (await r.get(summary_key) or "")
            if isinstance(prev_summary, (bytes, bytearray)):
                prev_summary = prev_summary.decode("utf-8")

            new_summary = await _update_summary(prev_summary, old_msgs)
            await r.set(summary_key, new_summary)

            # 앞부분 삭제(= keep_msgs만 남김)
            await r.ltrim(rk, cut, -1)

    # 혹시 모를 runaway 방지: 그래도 max_msgs 넘으면 마지막 max_msgs만 유지
    await r.ltrim(rk, -max_msgs, -1)

    # 4) TTL 연장
    await r.expire(rk, SHORT_TTL)
    await r.expire(summary_key, SHORT_TTL)
    await r.expire(state_key, SHORT_TTL)