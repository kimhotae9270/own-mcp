import uuid
import json

async def ensure_conversation(db, *, user_id: int, conversation_id: str) -> uuid.UUID:
    conv_id = uuid.UUID(conversation_id)

    row = await db.fetchrow(
        "SELECT id FROM conversations WHERE id=$1 AND user_id=$2",
        conv_id, user_id
    )
    if row is None:
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES ($1, $2, $3)",
            conv_id, user_id, None
        )

    # 활동 갱신
    await db.execute(
        "UPDATE conversations SET last_active_at=now() WHERE id=$1 AND user_id=$2",
        conv_id, user_id
    )
    return conv_id


async def append_message(db, *, user_id: int, conversation_id: uuid.UUID, role: str, content: str, trace=None):
    if trace is None:
        trace_json = None
    elif isinstance(trace, str):
        trace_json = trace
    else:
        trace_json = json.dumps(trace, ensure_ascii=False, default=str)

    await db.execute(
        "INSERT INTO messages (conversation_id, user_id, role, content, trace) VALUES ($1,$2,$3,$4,$5)",
        conversation_id, user_id, role, content, trace_json
    )
