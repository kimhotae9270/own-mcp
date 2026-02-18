# app/core/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from apscheduler.triggers.cron import CronTrigger

from app.core.db import db_conn

async def cleanup_expired_refresh_tokens() -> None:
    # 만료된 refresh 토큰 삭제
    async with db_conn() as conn:
        res = await conn.execute(
            """
            DELETE FROM refresh_tokens
            WHERE expires_at < now() - interval '7 days';
            """
        )

    # asyncpg execute 결과: "DELETE 123" 이런 문자열
    try:
        deleted = int(res.split()[-1])
    except Exception:
        deleted = 0

    print(f"[Scheduler] Deleted {deleted} expired refresh tokens")
def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        cleanup_expired_refresh_tokens,
        trigger=CronTrigger(hour=4, minute=5),
        id="cleanup_refresh_tokens",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    scheduler.start()
    return scheduler

def shutdown_scheduler(scheduler: AsyncIOScheduler) -> None:
    if scheduler:
        scheduler.shutdown(wait=False)