import json
from app.core.redis_client import r
SHORT_TTL = 60 * 60 * 6
RECENT_MAX_TURNS = 12  # recent: 12턴

def k_recent(uid, cid): return f"conv:{uid}:{cid}:recent"
def k_summary(uid, cid): return f"conv:{uid}:{cid}:summary"
def k_state(uid, cid): return f"conv:{uid}:{cid}:state"

async def load_mem(user_id: int, conversation_id: str):
    recent_raw = await r.lrange(k_recent(user_id, conversation_id), 0, -1)
    recent = [json.loads(x) for x in recent_raw] if recent_raw else []
    summary = await r.get(k_summary(user_id, conversation_id)) or ""
    state_raw = await r.get(k_state(user_id, conversation_id))
    state = json.loads(state_raw) if state_raw else {}
    return {"recent": recent, "summary": summary, "state": state}

async def save_mem(user_id: int, conversation_id: str, user_text: str, assistant_text: str, summary=None, state=None):
    rk = k_recent(user_id, conversation_id)

    await r.rpush(rk, json.dumps({"role":"user","content": user_text}, ensure_ascii=False))
    await r.rpush(rk, json.dumps({"role":"assistant","content": assistant_text}, ensure_ascii=False))

    # 최근만 유지 (메시지 기준이라 2*턴)
    await r.ltrim(rk, -2 * RECENT_MAX_TURNS, -1)

    if summary is not None:
        await r.set(k_summary(user_id, conversation_id), summary)
    if state is not None:
        await r.set(k_state(user_id, conversation_id), json.dumps(state, ensure_ascii=False))

    # TTL 연장
    await r.expire(rk, SHORT_TTL)
    await r.expire(k_summary(user_id, conversation_id), SHORT_TTL)
    await r.expire(k_state(user_id, conversation_id), SHORT_TTL)
