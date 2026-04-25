"""
╔══════════════════════════════════════════════════════════════╗
║               CRON JOB SERVICE                               ║
║     Schedule scripts to run at intervals or specific times   ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import threading
import re
from typing import Tuple, List, Dict, Optional
from database.db_manager import (
    add_cron_job, get_cron_jobs, delete_cron_job,
    get_file_by_name, get_conn, log_action
)
from core.executor import executor
from database.db_manager import get_user


# ══════════════════════════════════════════════════════════════
#  CRON EXPRESSION PARSER
# ══════════════════════════════════════════════════════════════

def parse_cron_expr(expr: str) -> Optional[int]:
    """
    Supported formats:
      - every_Xm  → every X minutes
      - every_Xh  → every X hours
      - HH:MM     → daily at specific time (returns next timestamp)
    Returns interval in seconds, or None if invalid.
    """
    expr = expr.strip().lower()

    m = re.match(r'^every[_\s](\d+)m$', expr)
    if m:
        return int(m.group(1)) * 60

    m = re.match(r'^every[_\s](\d+)h$', expr)
    if m:
        return int(m.group(1)) * 3600

    m = re.match(r'^(\d{1,2}):(\d{2})$', expr)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60  # daily interval

    return None


def next_run_time(interval_sec: int, last_run: float) -> float:
    if last_run == 0:
        return time.time()
    return last_run + interval_sec


# ══════════════════════════════════════════════════════════════
#  CRON SERVICE
# ══════════════════════════════════════════════════════════════

class CronService:

    def __init__(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def add_job(
        self,
        user_id: int,
        script_name: str,
        cron_expr: str,
        plan: str = "free"
    ) -> Tuple[bool, str]:
        # Validate file exists
        file_rec = get_file_by_name(user_id, script_name)
        if not file_rec:
            return False, f"❌ ফাইল পাওয়া যায়নি: `{script_name}`"

        interval = parse_cron_expr(cron_expr)
        if not interval:
            return False, (
                "❌ ভুল ক্রোন ফরম্যাট।\n\n"
                "✅ সঠিক ফরম্যট:\n"
                "• `every_5m` → প্রতি ৫ মিনিটে\n"
                "• `every_2h` → প্রতি ২ ঘন্টায়\n"
                "• `08:30` → প্রতিদিন সকাল ৮:৩০"
            )

        # Limit: max 5 cron jobs per user
        existing = get_cron_jobs(user_id)
        if len(existing) >= 5:
            return False, "❌ সর্বোচ্চ ৫টি ক্রোন জব রাখা যাবে।"

        job_id = add_cron_job(user_id, script_name, cron_expr)
        log_action(user_id, "add_cron", f"{script_name} @ {cron_expr}")
        return True, (
            f"⏰ **ক্রোন জব তৈরি হয়েছে!**\n\n"
            f"📝 স্ক্রিপ্ট: `{script_name}`\n"
            f"🕐 সময়সূচি: `{cron_expr}`\n"
            f"🆔 জব ID: `{job_id}`"
        )

    def remove_job(self, user_id: int, job_id: int) -> Tuple[bool, str]:
        delete_cron_job(job_id, user_id)
        log_action(user_id, "del_cron", f"job:{job_id}")
        return True, f"✅ ক্রোন জব `{job_id}` মুছে ফেলা হয়েছে।"

    def list_jobs(self, user_id: int) -> str:
        jobs = get_cron_jobs(user_id)
        if not jobs:
            return "📭 কোনো ক্রোন জব নেই।"
        lines = ["⏰ **আপনার ক্রোন জবসমূহ:**\n"]
        for j in jobs:
            lines.append(
                f"🆔 `{j['id']}` | 📝 `{j['script_name']}` | 🕐 `{j['cron_expr']}`"
            )
        return "\n".join(lines)

    def _loop(self):
        """Background scheduler thread."""
        while True:
            try:
                with get_conn() as conn:
                    jobs = conn.execute(
                        "SELECT * FROM cron_jobs WHERE enabled = 1"
                    ).fetchall()

                now = time.time()
                for job in jobs:
                    job = dict(job)
                    interval = parse_cron_expr(job["cron_expr"])
                    if not interval:
                        continue
                    last = job.get("last_run", 0)
                    if now >= last + interval:
                        # Run the script
                        file_rec = get_file_by_name(job["user_id"], job["script_name"])
                        if file_rec:
                            user = get_user(job["user_id"])
                            plan = user["plan"] if user else "free"
                            executor.run_script(
                                job["user_id"],
                                file_rec["filepath"],
                                job["script_name"],
                                plan
                            )
                        # Update last_run
                        with get_conn() as conn2:
                            conn2.execute(
                                "UPDATE cron_jobs SET last_run = ? WHERE id = ?",
                                (now, job["id"])
                            )
                            conn2.commit()
            except Exception as e:
                pass  # Silent fail in background
            time.sleep(30)


cron_service = CronService()
