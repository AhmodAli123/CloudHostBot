"""
╔══════════════════════════════════════════════════════════════╗
║               SUBSCRIPTION SERVICE                           ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
from typing import Tuple
from database.db_manager import get_user, set_plan, update_user, log_action
from config.settings import PLANS
from utils.keyboards import fmt_time, fmt_plan_info


class SubscriptionService:

    def get_plan_status(self, user_id: int) -> str:
        user = get_user(user_id)
        if not user:
            return "❌ ব্যবহারকারী পাওয়া যায়নি।"
        plan = user.get("plan", "free")
        limits = PLANS.get(plan)
        expiry = user.get("plan_expiry", 0)

        if plan != "free" and expiry > 0:
            remaining = int(expiry - time.time())
            if remaining <= 0:
                update_user(user_id, plan="free", plan_expiry=0)
                plan = "free"
                expiry_str = "মেয়াদ শেষ (ডাউনগ্রেড হয়েছে)"
            else:
                days = remaining // 86400
                expiry_str = f"✅ {days} দিন বাকি (শেষ: {fmt_time(expiry)})"
        else:
            expiry_str = "—"

        return (
            f"💳 **আপনার প্ল্যান**\n\n"
            f"{fmt_plan_info(plan)}\n\n"
            f"📅 মেয়াদ: {expiry_str}"
        )

    def assign_plan(self, admin_id: int, target_user_id: int, plan: str, days: int) -> Tuple[bool, str]:
        if plan not in PLANS:
            return False, f"❌ অজানা প্ল্যান: {plan}"
        set_plan(target_user_id, plan, days)
        log_action(admin_id, "assign_plan", f"user:{target_user_id} plan:{plan} days:{days}")
        expiry = time.time() + days * 86400 if plan != "free" else 0
        expiry_str = fmt_time(expiry) if expiry else "—"
        limits = PLANS[plan]
        return True, (
            f"✅ প্ল্যান আপডেট হয়েছে!\n\n"
            f"👤 User: `{target_user_id}`\n"
            f"{limits.emoji} প্ল্যান: **{limits.label}**\n"
            f"📅 মেয়াদ: {expiry_str}"
        )

    def check_and_downgrade(self, user_id: int):
        user = get_user(user_id)
        if not user:
            return
        if user["plan"] != "free" and user.get("plan_expiry", 0) > 0:
            if time.time() > user["plan_expiry"]:
                update_user(user_id, plan="free", plan_expiry=0)


subscription_service = SubscriptionService()
