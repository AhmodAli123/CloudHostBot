"""
╔══════════════════════════════════════════════════════════════╗
║               UTILITIES — KEYBOARDS & FORMATTERS             ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import time
import psutil
import shutil
from datetime import datetime
from typing import List, Optional
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config.settings import PLANS, ADMIN_IDS


# ══════════════════════════════════════════════════════════════
#  REPLY KEYBOARDS (Main Navigation)
# ══════════════════════════════════════════════════════════════

def kb_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Main menu keyboard for all users."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📁 ফাইল ম্যানেজার"),
        KeyboardButton("⚙️ প্রসেস ম্যানেজার"),
    )
    kb.add(
        KeyboardButton("📊 স্ট্যাটিস্টিক্স"),
        KeyboardButton("💳 সাবস্ক্রিপশন"),
    )
    kb.add(
        KeyboardButton("📜 লগ দেখুন"),
        KeyboardButton("⏰ ক্রোন জব"),
    )
    kb.add(
        KeyboardButton("🛒 মার্কেটপ্লেস"),
        KeyboardButton("❓ সাহায্য"),
    )
    if is_admin:
        kb.add(KeyboardButton("🛡️ এডমিন প্যানেল"))
    return kb


def kb_file_manager() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📤 ফাইল আপলোড"),
        KeyboardButton("📋 ফাইল তালিকা"),
    )
    kb.add(
        KeyboardButton("▶️ স্ক্রিপ্ট রান করুন"),
        KeyboardButton("🗑️ ফাইল মুছুন"),
    )
    kb.add(
        KeyboardButton("📝 ফাইল এডিট করুন"),
        KeyboardButton("📦 ZIP এক্সট্র্যাক্ট"),
    )
    kb.add(KeyboardButton("🔙 মূল মেনু"))
    return kb


def kb_process_manager() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📊 চলমান প্রসেস"),
        KeyboardButton("⏹️ প্রসেস থামান"),
    )
    kb.add(
        KeyboardButton("🔄 প্রসেস রিস্টার্ট"),
        KeyboardButton("📜 প্রসেস লগ"),
    )
    kb.add(
        KeyboardButton("💀 ফোর্স কিল"),
        KeyboardButton("📈 রিসোর্স ব্যবহার"),
    )
    kb.add(KeyboardButton("🔙 মূল মেনু"))
    return kb


def kb_admin_panel() -> ReplyKeyboardMarkup:
    """Admin panel with full control buttons."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("👥 ব্যবহারকারী তালিকা"),
        KeyboardButton("🌐 গ্লোবাল স্ট্যাটস"),
    )
    kb.add(
        KeyboardButton("🚫 ব্যান ম্যানেজ"),
        KeyboardButton("👑 প্ল্যান দিন"),
    )
    kb.add(
        KeyboardButton("📢 ব্রডকাস্ট"),
        KeyboardButton("🔒 মেইনটেন্যান্স"),
    )
    kb.add(
        KeyboardButton("🗑️ লগ ক্লিয়ার"),
        KeyboardButton("🔄 বট রিস্টার্ট"),
    )
    kb.add(
        KeyboardButton("⚡ শেল কমান্ড"),
        KeyboardButton("💥 সকল প্রসেস বন্ধ"),
    )
    kb.add(
        KeyboardButton("🗂️ ফাইল রিসেট (ইউজার)"),
        KeyboardButton("📊 সিস্টেম মনিটর"),
    )
    kb.add(KeyboardButton("🔙 মূল মেনু"))
    return kb


def kb_cron_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("➕ নতুন ক্রোন জব"),
        KeyboardButton("📋 ক্রোন জব তালিকা"),
    )
    kb.add(
        KeyboardButton("❌ ক্রোন জব মুছুন"),
    )
    kb.add(KeyboardButton("🔙 মূল মেনু"))
    return kb


def kb_marketplace_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🛒 স্ক্রিপ্ট ব্রাউজ করুন"),
        KeyboardButton("📤 স্ক্রিপ্ট শেয়ার করুন"),
    )
    kb.add(KeyboardButton("🔙 মূল মেনু"))
    return kb


def kb_cancel() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ বাতিল করুন"))
    return kb


def kb_back() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔙 মূল মেনু"))
    return kb


# ══════════════════════════════════════════════════════════════
#  INLINE KEYBOARDS (Special cases only)
# ══════════════════════════════════════════════════════════════

def ikb_file_actions(file_id: int, filename: str) -> InlineKeyboardMarkup:
    """Inline actions for a specific file."""
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("▶️ রান", callback_data=f"run_{file_id}"),
        InlineKeyboardButton("📝 এডিট", callback_data=f"edit_{file_id}"),
        InlineKeyboardButton("🗑️ ডিলিট", callback_data=f"del_{file_id}"),
    )
    return kb


def ikb_process_actions(proc_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("⏹️ স্টপ", callback_data=f"stop_{proc_id}"),
        InlineKeyboardButton("🔄 রিস্টার্ট", callback_data=f"restart_{proc_id}"),
        InlineKeyboardButton("📜 লগ", callback_data=f"log_{proc_id}"),
    )
    kb.add(InlineKeyboardButton("💀 ফোর্স কিল", callback_data=f"kill_{proc_id}"))
    return kb


def ikb_confirm(action: str, data: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ হ্যাঁ", callback_data=f"confirm_{action}_{data}"),
        InlineKeyboardButton("❌ না", callback_data="cancel_confirm"),
    )
    return kb


def ikb_plan_selector(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("⭐ Premium (30 দিন)", callback_data=f"setplan_{user_id}_premium_30"),
        InlineKeyboardButton("💎 Pro (30 দিন)", callback_data=f"setplan_{user_id}_pro_30"),
        InlineKeyboardButton("⭐ Premium (90 দিন)", callback_data=f"setplan_{user_id}_premium_90"),
        InlineKeyboardButton("💎 Pro (90 দিন)", callback_data=f"setplan_{user_id}_pro_90"),
        InlineKeyboardButton("🆓 Free তে ফেরত", callback_data=f"setplan_{user_id}_free_0"),
    )
    return kb


def ikb_pagination(current: int, total: int, prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []
    if current > 0:
        buttons.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_page_{current - 1}"))
    buttons.append(InlineKeyboardButton(f"📄 {current + 1}/{total}", callback_data="noop"))
    if current < total - 1:
        buttons.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_page_{current + 1}"))
    if buttons:
        kb.add(*buttons)
    return kb


# ══════════════════════════════════════════════════════════════
#  FORMATTERS
# ══════════════════════════════════════════════════════════════

def fmt_size(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def fmt_time(ts: float) -> str:
    if not ts:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")


def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"


def fmt_user_info(user: dict) -> str:
    plan = PLANS.get(user.get("plan", "free"))
    plan_label = f"{plan.emoji} {plan.label}" if plan else "Unknown"
    expiry = fmt_time(user.get("plan_expiry", 0)) if user.get("plan") != "free" else "—"
    banned = "🚫 ব্যান" if user.get("is_banned") else "✅ সক্রিয়"
    return (
        f"👤 **{user.get('full_name', 'Unknown')}**\n"
        f"🆔 ID: `{user.get('user_id')}`\n"
        f"📛 @{user.get('username', 'N/A')}\n"
        f"💳 প্ল্যান: {plan_label}\n"
        f"📅 মেয়াদ: {expiry}\n"
        f"🗓️ যোগদান: {fmt_time(user.get('join_date', 0))}\n"
        f"⏰ শেষ সক্রিয়: {fmt_time(user.get('last_activity', 0))}\n"
        f"স্ট্যাটাস: {banned}"
    )


def fmt_system_stats() -> str:
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"🖥️ **সিস্টেম স্ট্যাটাস**\n\n"
        f"⚡ CPU: `{cpu}%`\n"
        f"💾 RAM: `{ram.percent}%` ({fmt_size(ram.used)} / {fmt_size(ram.total)})\n"
        f"💿 Disk: `{disk.percent}%` ({fmt_size(disk.used)} / {fmt_size(disk.total)})\n"
    )


def fmt_plan_info(plan_name: str) -> str:
    plan = PLANS.get(plan_name)
    if not plan:
        return "❌ অজানা প্ল্যান"
    return (
        f"{plan.emoji} **{plan.label} প্ল্যান**\n\n"
        f"📁 সর্বোচ্চ ফাইল: `{plan.max_files}`\n"
        f"⚙️ সর্বোচ্চ প্রসেস: `{plan.max_processes}`\n"
        f"💾 স্টোরেজ: `{plan.max_storage_mb} MB`\n"
        f"📦 সর্বোচ্চ ফাইল সাইজ: `{plan.max_file_size_mb} MB`"
    )


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def get_user_storage_dir(user_id: int) -> str:
    path = os.path.join("storage", str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def get_user_log_dir(user_id: int) -> str:
    path = os.path.join("logs", str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def is_admin(user_id: int) -> bool:
    from config.settings import ADMIN_IDS
    return user_id in ADMIN_IDS


def paginate(items: list, page: int, per_page: int = 5):
    start = page * per_page
    end = start + per_page
    return items[start:end], len(items) // per_page + (1 if len(items) % per_page else 0)


def safe_filename(name: str) -> str:
    """Sanitize filename to prevent path traversal."""
    return os.path.basename(name).replace("..", "").replace("/", "").replace("\\", "")
