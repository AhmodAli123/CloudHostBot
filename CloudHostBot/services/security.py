"""
╔══════════════════════════════════════════════════════════════╗
║               SECURITY MIDDLEWARE                            ║
╚══════════════════════════════════════════════════════════════╝
"""

import functools
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from database.db_manager import get_user, upsert_user, is_maintenance, log_action
from config.settings import ADMIN_IDS
from services.subscription_service import subscription_service


def register_user(message: Message):
    """Auto-register user on first contact."""
    u = message.from_user
    upsert_user(u.id, u.username or "", u.full_name or "")
    subscription_service.check_and_downgrade(u.id)


def check_access(message: Message) -> tuple:
    """
    Returns (allowed: bool, reason: str)
    Checks: maintenance mode, ban status.
    """
    user_id = message.from_user.id

    # Admins bypass maintenance
    if user_id in ADMIN_IDS:
        return True, ""

    # Maintenance mode
    if is_maintenance():
        return False, (
            "🔧 **মেইনটেন্যান্স মোড সক্রিয়**\n\n"
            "বটটি সাময়িকভাবে বন্ধ আছে। অনুগ্রহ করে পরে চেষ্টা করুন।"
        )

    # Ban check
    user = get_user(user_id)
    if user and user.get("is_banned"):
        return False, "🚫 আপনি এই বট থেকে ব্যান করা হয়েছেন।"

    return True, ""


def require_access(bot: TeleBot):
    """Decorator for message handlers: enforce access control."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(message: Message, *args, **kwargs):
            register_user(message)
            allowed, reason = check_access(message)
            if not allowed:
                bot.send_message(message.chat.id, reason, parse_mode="Markdown")
                return
            return func(message, *args, **kwargs)
        return wrapper
    return decorator


def require_admin(bot: TeleBot):
    """Decorator: admin-only handlers."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(message: Message, *args, **kwargs):
            if message.from_user.id not in ADMIN_IDS:
                bot.send_message(
                    message.chat.id,
                    "🚫 এই কমান্ড শুধুমাত্র অ্যাডমিনের জন্য।"
                )
                return
            return func(message, *args, **kwargs)
        return wrapper
    return decorator


def get_user_plan(user_id: int) -> str:
    user = get_user(user_id)
    return user.get("plan", "free") if user else "free"
