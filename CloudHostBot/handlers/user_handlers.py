"""
╔══════════════════════════════════════════════════════════════╗
║               USER HANDLERS                                  ║
║    /start, file manager, process manager, stats, help        ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import time
from telebot import TeleBot
from telebot.types import Message, CallbackQuery

from database.db_manager import (
    get_user, get_files, get_processes, log_action,
    get_global_stats, upsert_user
)
from services.file_service import file_service
from services.security import get_user_plan
from services.subscription_service import subscription_service
from services.cron_service import cron_service
from services.ai_engine import ai_engine
from core.executor import executor
from utils.keyboards import (
    kb_main_menu, kb_file_manager, kb_process_manager,
    kb_cron_menu, kb_marketplace_menu, kb_cancel, kb_back,
    ikb_file_actions, ikb_process_actions, ikb_confirm, ikb_pagination,
    fmt_system_stats, fmt_user_info, fmt_size, fmt_time, paginate
)
from config.settings import PLANS, BOT_NAME, VERSION, ADMIN_IDS
from database.db_manager import get_marketplace_items


# ══════════════════════════════════════════════════════════════
#  STATE MANAGEMENT (simple in-memory)
# ══════════════════════════════════════════════════════════════

_user_states: dict = {}   # user_id → {"state": str, "data": dict}


def set_state(user_id: int, state: str, **data):
    _user_states[user_id] = {"state": state, "data": data}


def get_state(user_id: int) -> dict:
    return _user_states.get(user_id, {"state": None, "data": {}})


def clear_state(user_id: int):
    _user_states.pop(user_id, None)


# ══════════════════════════════════════════════════════════════
#  REGISTER HANDLERS
# ══════════════════════════════════════════════════════════════

def register_user_handlers(bot: TeleBot):

    # ─── /START ────────────────────────────────────────────

    @bot.message_handler(commands=["start"])
    def cmd_start(message: Message):
        u = message.from_user
        upsert_user(u.id, u.username or "", u.full_name or "")
        subscription_service.check_and_downgrade(u.id)
        is_admin = u.id in ADMIN_IDS

        text = (
            f"☁️ **{BOT_NAME}** এ স্বাগতম!\n\n"
            f"👋 হ্যালো, **{u.full_name}**!\n\n"
            f"এই বটটি একটি সম্পূর্ণ **ক্লাউড কোড হোস্টিং প্ল্যাটফর্ম**।\n\n"
            f"🐍 Python ও 🟨 Node.js স্ক্রিপ্ট রান করুন\n"
            f"📁 ফাইল আপলোড ও ম্যানেজ করুন\n"
            f"⚙️ প্রসেস মনিটর করুন\n"
            f"⏰ ক্রোন জব সেট করুন\n\n"
            f"নিচের মেনু থেকে শুরু করুন 👇"
        )
        bot.send_message(
            message.chat.id, text,
            parse_mode="Markdown",
            reply_markup=kb_main_menu(is_admin)
        )

    # ─── MAIN MENU NAVIGATION ──────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "📁 ফাইল ম্যানেজার")
    def menu_files(message: Message):
        clear_state(message.from_user.id)
        user = get_user(message.from_user.id)
        plan = user.get("plan", "free") if user else "free"
        storage_info = file_service.get_storage_info(message.from_user.id, plan)
        files = file_service.list_files(message.from_user.id)
        limits = PLANS.get(plan)
        text = (
            f"📁 **ফাইল ম্যানেজার**\n\n"
            f"{storage_info}\n\n"
            f"📂 মোট ফাইল: `{len(files)}/{limits.max_files if limits else '?'}`"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_file_manager())

    @bot.message_handler(func=lambda m: m.text == "⚙️ প্রসেস ম্যানেজার")
    def menu_processes(message: Message):
        clear_state(message.from_user.id)
        user = get_user(message.from_user.id)
        plan = user.get("plan", "free") if user else "free"
        procs = get_processes(message.from_user.id, "running")
        limits = PLANS.get(plan)
        text = (
            f"⚙️ **প্রসেস ম্যানেজার**\n\n"
            f"🔄 চলমান প্রসেস: `{len(procs)}/{limits.max_processes if limits else '?'}`\n\n"
            "নিচের বাটন থেকে প্রসেস ম্যানেজ করুন 👇"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_process_manager())

    @bot.message_handler(func=lambda m: m.text == "📊 স্ট্যাটিস্টিক্স")
    def menu_stats(message: Message):
        user_id = message.from_user.id
        user = get_user(user_id)
        plan = user.get("plan", "free") if user else "free"
        files = file_service.list_files(user_id)
        procs = get_processes(user_id, "running")
        storage = file_service.get_storage_info(user_id, plan)
        system = fmt_system_stats()
        limits = PLANS.get(plan)
        text = (
            f"📊 **আপনার স্ট্যাটিস্টিক্স**\n\n"
            f"💳 প্ল্যান: `{limits.emoji} {limits.label}` \n"
            f"📁 ফাইল: `{len(files)}`\n"
            f"⚙️ প্রসেস: `{len(procs)}`\n\n"
            f"{storage}\n\n"
            f"{system}"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_main_menu(user_id in ADMIN_IDS))

    @bot.message_handler(func=lambda m: m.text == "💳 সাবস্ক্রিপশন")
    def menu_subscription(message: Message):
        text = subscription_service.get_plan_status(message.from_user.id)
        plans_info = "\n\n".join([
            f"{p.emoji} **{p.label}**\n"
            f"  📁 {p.max_files} ফাইল | ⚙️ {p.max_processes} প্রসেস | 💾 {p.max_storage_mb} MB"
            for p in PLANS.values()
        ])
        full_text = f"{text}\n\n━━━━━━━━━━━━━\n\n📋 **সব প্ল্যান:**\n\n{plans_info}"
        bot.send_message(message.chat.id, full_text, parse_mode="Markdown",
                         reply_markup=kb_main_menu(message.from_user.id in ADMIN_IDS))

    @bot.message_handler(func=lambda m: m.text == "⏰ ক্রোন জব")
    def menu_cron(message: Message):
        text = cron_service.list_jobs(message.from_user.id)
        bot.send_message(message.chat.id, f"⏰ **ক্রোন জব ম্যানেজার**\n\n{text}",
                         parse_mode="Markdown", reply_markup=kb_cron_menu())

    @bot.message_handler(func=lambda m: m.text == "🛒 মার্কেটপ্লেস")
    def menu_marketplace(message: Message):
        items = get_marketplace_items()
        if not items:
            text = "🛒 **মার্কেটপ্লেস**\n\n📭 এখনো কোনো স্ক্রিপ্ট শেয়ার হয়নি।"
        else:
            lines = ["🛒 **মার্কেটপ্লেস স্ক্রিপ্ট:**\n"]
            for item in items[:10]:
                price = f"💰 {item['price']} TK" if item['price'] > 0 else "🆓 ফ্রি"
                lines.append(
                    f"📝 **{item['title']}**\n"
                    f"👤 @{item.get('username','?')} | {price} | ⬇️ {item['downloads']}\n"
                    f"📄 {item.get('description','')[:50]}"
                )
            text = "\n\n".join(lines)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_marketplace_menu())

    @bot.message_handler(func=lambda m: m.text == "❓ সাহায্য")
    def menu_help(message: Message):
        text = (
            f"❓ **{BOT_NAME} সাহায্য**\n\n"
            f"🔢 ভার্সন: `{VERSION}`\n\n"
            "**📁 ফাইল ম্যানেজার:**\n"
            "• ফাইল আপলোড করুন (.py, .js, .zip)\n"
            "• ফাইল রান, এডিট, ডিলিট করুন\n\n"
            "**⚙️ প্রসেস ম্যানেজার:**\n"
            "• চলমান স্ক্রিপ্ট দেখুন\n"
            "• প্রসেস স্টপ / রিস্টার্ট করুন\n\n"
            "**⏰ ক্রোন জব:**\n"
            "• `every_5m` → প্রতি ৫ মিনিটে\n"
            "• `every_2h` → প্রতি ২ ঘন্টায়\n"
            "• `08:30` → প্রতিদিন নির্দিষ্ট সময়ে\n\n"
            "**💳 প্ল্যান আপগ্রেড:**\n"
            "• এডমিনের সাথে যোগাযোগ করুন\n\n"
            "**🤖 AI এরর ফিক্স:**\n"
            "• প্রসেস লগ বিশ্লেষণ করে স্বয়ংক্রিয়ভাবে সমস্যা সমাধান"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown",
                         reply_markup=kb_main_menu(message.from_user.id in ADMIN_IDS))

    @bot.message_handler(func=lambda m: m.text == "🔙 মূল মেনু")
    def menu_back(message: Message):
        clear_state(message.from_user.id)
        bot.send_message(
            message.chat.id, "🏠 মূল মেনুতে ফিরে এলেন।",
            reply_markup=kb_main_menu(message.from_user.id in ADMIN_IDS)
        )

    @bot.message_handler(func=lambda m: m.text == "❌ বাতিল করুন")
    def cancel_action(message: Message):
        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "❌ বাতিল করা হয়েছে।",
                         reply_markup=kb_main_menu(message.from_user.id in ADMIN_IDS))

    # ═══════════════════════════════════════════════════════
    #  FILE MANAGER ACTIONS
    # ═══════════════════════════════════════════════════════

    @bot.message_handler(func=lambda m: m.text == "📤 ফাইল আপলোড")
    def file_upload_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_file_upload")
        bot.send_message(
            message.chat.id,
            "📤 **ফাইল আপলোড করুন**\n\n"
            "এখন ফাইলটি পাঠান (.py, .js, .zip, .txt, .json)\n\n"
            "❌ বাতিল করতে নিচের বাটন চাপুন।",
            parse_mode="Markdown",
            reply_markup=kb_cancel()
        )

    @bot.message_handler(content_types=["document"])
    def handle_document_upload(message: Message):
        state = get_state(message.from_user.id)
        if state["state"] != "awaiting_file_upload":
            return

        user_id = message.from_user.id
        user = get_user(user_id)
        plan = user.get("plan", "free") if user else "free"

        doc = message.document
        filename = doc.file_name or f"file_{int(time.time())}"

        try:
            file_info = bot.get_file(doc.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            ok, msg = file_service.save_uploaded_file(user_id, filename, file_bytes, plan)
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_file_manager())
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ আপলোড ব্যর্থ: {e}", reply_markup=kb_file_manager())

        clear_state(user_id)

    @bot.message_handler(func=lambda m: m.text == "📋 ফাইল তালিকা")
    def file_list(message: Message):
        files = file_service.list_files(message.from_user.id)
        text = file_service.format_file_list(files)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_file_manager())

        # Show inline action buttons per file
        for f in files[:10]:
            bot.send_message(
                message.chat.id,
                f"📄 `{f['filename']}` ({fmt_size(f.get('size_bytes', 0))})",
                parse_mode="Markdown",
                reply_markup=ikb_file_actions(f["id"], f["filename"])
            )

    @bot.message_handler(func=lambda m: m.text == "▶️ স্ক্রিপ্ট রান করুন")
    def script_run_prompt(message: Message):
        files = file_service.list_files(message.from_user.id)
        runnable = [f for f in files if os.path.splitext(f["filename"])[1].lower() in {".py", ".js"}]
        if not runnable:
            bot.send_message(message.chat.id, "📭 কোনো রানযোগ্য স্ক্রিপ্ট নেই।\n(.py বা .js আপলোড করুন)",
                             reply_markup=kb_file_manager())
            return
        set_state(message.from_user.id, "awaiting_script_select")
        text = "▶️ **কোন স্ক্রিপ্ট রান করবেন?**\n\nফাইলের নাম টাইপ করুন:\n\n"
        text += "\n".join([f"• `{f['filename']}`" for f in runnable])
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "🗑️ ফাইল মুছুন")
    def file_delete_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_delete_filename")
        files = file_service.list_files(message.from_user.id)
        if not files:
            bot.send_message(message.chat.id, "📭 কোনো ফাইল নেই।", reply_markup=kb_file_manager())
            return
        text = "🗑️ **কোন ফাইল মুছবেন?**\n\nফাইলের নাম টাইপ করুন:\n\n"
        text += "\n".join([f"• `{f['filename']}`" for f in files])
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "📝 ফাইল এডিট করুন")
    def file_edit_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_edit_filename")
        files = file_service.list_files(message.from_user.id)
        if not files:
            bot.send_message(message.chat.id, "📭 কোনো ফাইল নেই।", reply_markup=kb_file_manager())
            return
        text = "📝 **কোন ফাইল এডিট করবেন?**\n\nফাইলের নাম টাইপ করুন:\n\n"
        text += "\n".join([f"• `{f['filename']}`" for f in files])
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "📦 ZIP এক্সট্র্যাক্ট")
    def zip_extract_prompt(message: Message):
        files = file_service.list_files(message.from_user.id)
        zips = [f for f in files if f["filename"].endswith(".zip")]
        if not zips:
            bot.send_message(message.chat.id, "📭 কোনো ZIP ফাইল নেই।", reply_markup=kb_file_manager())
            return
        set_state(message.from_user.id, "awaiting_zip_extract")
        text = "📦 **কোন ZIP এক্সট্র্যাক্ট করবেন?**\n\nZIP ফাইলের নাম টাইপ করুন:\n\n"
        text += "\n".join([f"• `{f['filename']}`" for f in zips])
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cancel())

    # ═══════════════════════════════════════════════════════
    #  PROCESS MANAGER ACTIONS
    # ═══════════════════════════════════════════════════════

    @bot.message_handler(func=lambda m: m.text == "📊 চলমান প্রসেস")
    def running_processes(message: Message):
        user_id = message.from_user.id
        procs = get_processes(user_id, "running")
        if not procs:
            bot.send_message(message.chat.id, "📭 কোনো প্রসেস চলছে না।", reply_markup=kb_process_manager())
            return
        bot.send_message(message.chat.id, f"⚙️ **{len(procs)}টি প্রসেস চলছে:**", parse_mode="Markdown",
                         reply_markup=kb_process_manager())
        for p in procs:
            bot.send_message(
                message.chat.id,
                f"🆔 `{p['id']}` | 📝 `{p['script_name']}` | 🔢 PID: `{p['pid']}`\n"
                f"⏰ শুরু: {fmt_time(p['started_at'])}",
                parse_mode="Markdown",
                reply_markup=ikb_process_actions(p["id"])
            )

    @bot.message_handler(func=lambda m: m.text == "⏹️ প্রসেস থামান")
    def stop_process_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_stop_proc_id")
        bot.send_message(message.chat.id, "⏹️ প্রসেস ID টাইপ করুন (📊 থেকে ID দেখুন):",
                         reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "🔄 প্রসেস রিস্টার্ট")
    def restart_process_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_restart_proc_id")
        bot.send_message(message.chat.id, "🔄 রিস্টার্ট করতে প্রসেস ID টাইপ করুন:",
                         reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "📜 প্রসেস লগ")
    def proc_log_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_log_proc_id")
        bot.send_message(message.chat.id, "📜 লগ দেখতে প্রসেস ID টাইপ করুন:",
                         reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "💀 ফোর্স কিল")
    def force_kill_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_kill_proc_id")
        bot.send_message(message.chat.id, "💀 **ফোর্স কিল** করতে প্রসেস ID দিন (সতর্ক থাকুন!):",
                         reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "📈 রিসোর্স ব্যবহার")
    def resource_usage_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_resource_proc_id")
        bot.send_message(message.chat.id, "📈 রিসোর্স দেখতে প্রসেস ID টাইপ করুন:",
                         reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "📜 লগ দেখুন")
    def view_logs(message: Message):
        user_id = message.from_user.id
        procs = get_processes(user_id, "running") + get_processes(user_id, "finished")
        if not procs:
            bot.send_message(message.chat.id, "📭 কোনো লগ নেই।",
                             reply_markup=kb_main_menu(user_id in ADMIN_IDS))
            return
        text = "📜 **লগ তালিকা:**\n\n"
        text += "\n".join([
            f"🆔 `{p['id']}` | `{p['script_name']}` | {p['status']}"
            for p in procs[:10]
        ])
        text += "\n\nID দিয়ে লগ দেখতে ⚙️ প্রসেস ম্যানেজার → 📜 প্রসেস লগ"
        bot.send_message(message.chat.id, text, parse_mode="Markdown",
                         reply_markup=kb_main_menu(user_id in ADMIN_IDS))

    # ═══════════════════════════════════════════════════════
    #  CRON JOB ACTIONS
    # ═══════════════════════════════════════════════════════

    @bot.message_handler(func=lambda m: m.text == "➕ নতুন ক্রোন জব")
    def cron_add_prompt(message: Message):
        files = file_service.list_files(message.from_user.id)
        if not files:
            bot.send_message(message.chat.id, "📭 প্রথমে একটি স্ক্রিপ্ট আপলোড করুন।",
                             reply_markup=kb_cron_menu())
            return
        set_state(message.from_user.id, "awaiting_cron_filename")
        text = (
            "➕ **নতুন ক্রোন জব**\n\n"
            "স্ক্রিপ্টের নাম টাইপ করুন:\n\n" +
            "\n".join([f"• `{f['filename']}`" for f in files])
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "📋 ক্রোন জব তালিকা")
    def cron_list(message: Message):
        text = cron_service.list_jobs(message.from_user.id)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cron_menu())

    @bot.message_handler(func=lambda m: m.text == "❌ ক্রোন জব মুছুন")
    def cron_delete_prompt(message: Message):
        set_state(message.from_user.id, "awaiting_cron_delete_id")
        bot.send_message(message.chat.id, "❌ মুছতে ক্রোন জব ID টাইপ করুন:",
                         reply_markup=kb_cancel())

    # ═══════════════════════════════════════════════════════
    #  MARKETPLACE ACTIONS
    # ═══════════════════════════════════════════════════════

    @bot.message_handler(func=lambda m: m.text == "📤 স্ক্রিপ্ট শেয়ার করুন")
    def marketplace_share_prompt(message: Message):
        files = file_service.list_files(message.from_user.id)
        if not files:
            bot.send_message(message.chat.id, "📭 শেয়ার করার জন্য ফাইল নেই।",
                             reply_markup=kb_marketplace_menu())
            return
        set_state(message.from_user.id, "awaiting_marketplace_filename")
        text = "📤 কোন স্ক্রিপ্ট শেয়ার করবেন? ফাইলের নাম দিন:\n\n"
        text += "\n".join([f"• `{f['filename']}`" for f in files])
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_cancel())

    @bot.message_handler(func=lambda m: m.text == "🛒 স্ক্রিপ্ট ব্রাউজ করুন")
    def marketplace_browse(message: Message):
        from database.db_manager import get_marketplace_items
        items = get_marketplace_items()
        if not items:
            bot.send_message(message.chat.id, "📭 মার্কেটপ্লেস খালি।", reply_markup=kb_marketplace_menu())
            return
        for item in items[:5]:
            price = f"💰 {item['price']} TK" if item['price'] > 0 else "🆓 ফ্রি"
            bot.send_message(
                message.chat.id,
                f"📝 **{item['title']}**\n"
                f"👤 @{item.get('username', '?')}\n"
                f"{price} | ⬇️ {item['downloads']}\n"
                f"📄 {item.get('description', '')}",
                parse_mode="Markdown",
                reply_markup=kb_marketplace_menu()
            )

    # ═══════════════════════════════════════════════════════
    #  UNIVERSAL TEXT INPUT HANDLER (State Machine)
    # ═══════════════════════════════════════════════════════

    @bot.message_handler(func=lambda m: m.content_type == "text" and not m.text.startswith("/"))
    def handle_text_input(message: Message):
        user_id = message.from_user.id
        state_info = get_state(user_id)
        state = state_info["state"]
        data = state_info["data"]
        text = message.text.strip()

        if not state:
            return  # Ignore unrecognized text

        user = get_user(user_id)
        plan = user.get("plan", "free") if user else "free"

        # ── Script selection to run ──────────────────────
        if state == "awaiting_script_select":
            clear_state(user_id)
            rec = file_service.list_files(user_id)
            match = next((f for f in rec if f["filename"] == text), None)
            if not match:
                bot.send_message(message.chat.id, f"❌ ফাইল পাওয়া যায়নি: `{text}`",
                                 parse_mode="Markdown", reply_markup=kb_file_manager())
                return
            bot.send_message(message.chat.id, "⏳ স্ক্রিপ্ট শুরু হচ্ছে...", reply_markup=kb_process_manager())
            ok, msg, proc_id = executor.run_script(user_id, match["filepath"], match["filename"], plan)
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_process_manager())

        # ── Delete file ──────────────────────────────────
        elif state == "awaiting_delete_filename":
            clear_state(user_id)
            ok, msg = file_service.delete_file(user_id, text)
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_file_manager())

        # ── Edit file (step 1: filename) ─────────────────
        elif state == "awaiting_edit_filename":
            ok, content = file_service.read_file(user_id, text)
            if not ok:
                bot.send_message(message.chat.id, content, reply_markup=kb_file_manager())
                clear_state(user_id)
                return
            set_state(user_id, "awaiting_edit_content", filename=text)
            bot.send_message(
                message.chat.id,
                f"📝 **{text}** এর বর্তমান কন্টেন্ট:\n\n```\n{content[:3000]}\n```\n\n"
                "➡️ নতুন কন্টেন্ট পাঠান (সম্পূর্ণ ফাইল রিপ্লেস হবে):",
                parse_mode="Markdown",
                reply_markup=kb_cancel()
            )

        # ── Edit file (step 2: new content) ──────────────
        elif state == "awaiting_edit_content":
            filename = data.get("filename", "")
            clear_state(user_id)
            ok, msg = file_service.write_file(user_id, filename, text)
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_file_manager())

        # ── ZIP extract ──────────────────────────────────
        elif state == "awaiting_zip_extract":
            clear_state(user_id)
            ok, msg = file_service.extract_zip(user_id, text, plan)
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_file_manager())

        # ── Stop process ─────────────────────────────────
        elif state == "awaiting_stop_proc_id":
            clear_state(user_id)
            try:
                proc_id = int(text)
                ok, msg = executor.stop_process(proc_id, user_id)
                bot.send_message(message.chat.id, msg, reply_markup=kb_process_manager())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_process_manager())

        # ── Restart process ──────────────────────────────
        elif state == "awaiting_restart_proc_id":
            clear_state(user_id)
            try:
                proc_id = int(text)
                ok, msg, _ = executor.restart_process(proc_id, user_id)
                bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_process_manager())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_process_manager())

        # ── View log ─────────────────────────────────────
        elif state == "awaiting_log_proc_id":
            clear_state(user_id)
            try:
                proc_id = int(text)
                log = executor.get_log_tail(proc_id, user_id)
                analysis = ai_engine.analyze_process_log(proc_id, user_id)
                if len(log) > 3800:
                    log = "..." + log[-3800:]
                bot.send_message(message.chat.id, f"📜 **লগ (শেষ ৫০ লাইন):**\n```\n{log}\n```",
                                 parse_mode="Markdown", reply_markup=kb_process_manager())
                bot.send_message(message.chat.id, analysis, parse_mode="Markdown",
                                 reply_markup=kb_process_manager())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_process_manager())

        # ── Force kill ───────────────────────────────────
        elif state == "awaiting_kill_proc_id":
            clear_state(user_id)
            try:
                proc_id = int(text)
                ok, msg = executor.stop_process(proc_id, user_id, force=True)
                bot.send_message(message.chat.id, msg, reply_markup=kb_process_manager())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_process_manager())

        # ── Resource usage ───────────────────────────────
        elif state == "awaiting_resource_proc_id":
            clear_state(user_id)
            try:
                proc_id = int(text)
                info = executor.get_process_resource_info(proc_id, user_id)
                bot.send_message(message.chat.id, info, parse_mode="Markdown", reply_markup=kb_process_manager())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_process_manager())

        # ── Cron: filename step ──────────────────────────
        elif state == "awaiting_cron_filename":
            rec = file_service.list_files(user_id)
            match = next((f for f in rec if f["filename"] == text), None)
            if not match:
                bot.send_message(message.chat.id, f"❌ ফাইল পাওয়া যায়নি: `{text}`",
                                 parse_mode="Markdown", reply_markup=kb_cron_menu())
                clear_state(user_id)
                return
            set_state(user_id, "awaiting_cron_expr", filename=text)
            bot.send_message(
                message.chat.id,
                "⏰ **সময়সূচি লিখুন:**\n\n"
                "• `every_5m` → প্রতি ৫ মিনিট\n"
                "• `every_2h` → প্রতি ২ ঘন্টা\n"
                "• `08:30` → প্রতিদিন সকাল ৮:৩০",
                parse_mode="Markdown",
                reply_markup=kb_cancel()
            )

        # ── Cron: expression step ────────────────────────
        elif state == "awaiting_cron_expr":
            filename = data.get("filename", "")
            clear_state(user_id)
            ok, msg = cron_service.add_job(user_id, filename, text, plan)
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_cron_menu())

        # ── Cron delete ──────────────────────────────────
        elif state == "awaiting_cron_delete_id":
            clear_state(user_id)
            try:
                job_id = int(text)
                ok, msg = cron_service.remove_job(user_id, job_id)
                bot.send_message(message.chat.id, msg, reply_markup=kb_cron_menu())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_cron_menu())

        # ── Marketplace share: filename ──────────────────
        elif state == "awaiting_marketplace_filename":
            rec = file_service.list_files(user_id)
            match = next((f for f in rec if f["filename"] == text), None)
            if not match:
                bot.send_message(message.chat.id, f"❌ ফাইল পাওয়া যায়নি।", reply_markup=kb_marketplace_menu())
                clear_state(user_id)
                return
            set_state(user_id, "awaiting_marketplace_title", filename=text)
            bot.send_message(message.chat.id, "📝 স্ক্রিপ্টের শিরোনাম লিখুন:", reply_markup=kb_cancel())

        elif state == "awaiting_marketplace_title":
            set_state(user_id, "awaiting_marketplace_desc",
                      filename=data.get("filename"), title=text)
            bot.send_message(message.chat.id, "📄 সংক্ষিপ্ত বিবরণ লিখুন:", reply_markup=kb_cancel())

        elif state == "awaiting_marketplace_desc":
            from database.db_manager import add_marketplace_item
            filename = data.get("filename")
            title = data.get("title")
            clear_state(user_id)
            add_marketplace_item(user_id, title, text, filename, price=0)
            bot.send_message(message.chat.id, f"✅ **{title}** মার্কেটপ্লেসে যোগ হয়েছে!",
                             parse_mode="Markdown", reply_markup=kb_marketplace_menu())

    # ═══════════════════════════════════════════════════════
    #  CALLBACK QUERY HANDLER (Inline Buttons)
    # ═══════════════════════════════════════════════════════

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call: CallbackQuery):
        user_id = call.from_user.id
        data = call.data
        user = get_user(user_id)
        plan = user.get("plan", "free") if user else "free"

        try:
            # ── File actions ──────────────────────────────
            if data.startswith("run_"):
                file_id = int(data.split("_")[1])
                files = get_files(user_id)
                rec = next((f for f in files if f["id"] == file_id), None)
                if rec:
                    ok, msg, _ = executor.run_script(user_id, rec["filepath"], rec["filename"], plan)
                    bot.answer_callback_query(call.id, "▶️ রান করা হচ্ছে...")
                    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown",
                                     reply_markup=kb_process_manager())

            elif data.startswith("del_"):
                file_id = int(data.split("_")[1])
                ok, msg = file_service.delete_file_by_id(user_id, file_id)
                bot.answer_callback_query(call.id, "🗑️")
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id)

            elif data.startswith("edit_"):
                file_id = int(data.split("_")[1])
                files = get_files(user_id)
                rec = next((f for f in files if f["id"] == file_id), None)
                if rec:
                    set_state(user_id, "awaiting_edit_content", filename=rec["filename"])
                    ok, content = file_service.read_file(user_id, rec["filename"])
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        f"📝 **{rec['filename']}** এর কন্টেন্ট:\n\n```\n{content[:2500]}\n```\n\n➡️ নতুন কন্টেন্ট পাঠান:",
                        parse_mode="Markdown", reply_markup=kb_cancel()
                    )

            # ── Process actions ───────────────────────────
            elif data.startswith("stop_"):
                proc_id = int(data.split("_")[1])
                ok, msg = executor.stop_process(proc_id, user_id)
                bot.answer_callback_query(call.id, "⏹️")
                bot.send_message(call.message.chat.id, msg, reply_markup=kb_process_manager())

            elif data.startswith("restart_"):
                proc_id = int(data.split("_")[1])
                ok, msg, _ = executor.restart_process(proc_id, user_id)
                bot.answer_callback_query(call.id, "🔄")
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown",
                                 reply_markup=kb_process_manager())

            elif data.startswith("kill_"):
                proc_id = int(data.split("_")[1])
                ok, msg = executor.stop_process(proc_id, user_id, force=True)
                bot.answer_callback_query(call.id, "💀")
                bot.send_message(call.message.chat.id, msg, reply_markup=kb_process_manager())

            elif data.startswith("log_"):
                proc_id = int(data.split("_")[1])
                log = executor.get_log_tail(proc_id, user_id)
                if len(log) > 3800:
                    log = "..." + log[-3800:]
                bot.answer_callback_query(call.id)
                bot.send_message(call.message.chat.id,
                                 f"📜 **লগ:**\n```\n{log}\n```",
                                 parse_mode="Markdown", reply_markup=kb_process_manager())

            elif data == "cancel_confirm":
                bot.answer_callback_query(call.id, "❌ বাতিল")
                bot.edit_message_text("❌ বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

            elif data == "noop":
                bot.answer_callback_query(call.id)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Error: {str(e)[:50]}")
