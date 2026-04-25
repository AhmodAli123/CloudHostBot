"""
╔══════════════════════════════════════════════════════════════╗
║               ADMIN HANDLERS                                 ║
║    Full admin panel: users, broadcast, shell, stats, etc.    ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import shutil
import subprocess
from telebot import TeleBot
from telebot.types import Message, CallbackQuery

from database.db_manager import (
    get_all_users, get_user, ban_user, unban_user,
    set_maintenance, is_maintenance, get_global_stats,
    get_recent_logs, log_action, get_processes
)
from services.file_service import file_service
from services.subscription_service import subscription_service
from services.security import get_user_plan
from core.executor import executor
from utils.keyboards import (
    kb_admin_panel, kb_main_menu, kb_cancel,
    ikb_plan_selector, ikb_confirm, fmt_system_stats,
    fmt_user_info, fmt_size, fmt_time, fmt_duration
)
from config.settings import ADMIN_IDS, PLANS


# ══════════════════════════════════════════════════════════════
#  ADMIN STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════

_admin_states: dict = {}


def set_admin_state(user_id: int, state: str, **data):
    _admin_states[user_id] = {"state": state, "data": data}


def get_admin_state(user_id: int) -> dict:
    return _admin_states.get(user_id, {"state": None, "data": {}})


def clear_admin_state(user_id: int):
    _admin_states.pop(user_id, None)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ══════════════════════════════════════════════════════════════
#  REGISTER ADMIN HANDLERS
# ══════════════════════════════════════════════════════════════

def register_admin_handlers(bot: TeleBot):

    # ─── ADMIN PANEL ENTRY ──────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🛡️ এডমিন প্যানেল")
    def admin_panel(message: Message):
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "🚫 অ্যাক্সেস নেই।")
            return
        stats = get_global_stats()
        maint = "🔴 চালু" if is_maintenance() else "🟢 বন্ধ"
        text = (
            f"🛡️ **এডমিন কন্ট্রোল প্যানেল**\n\n"
            f"👥 মোট ইউজার: `{stats['total_users']}`\n"
            f"📁 মোট ফাইল: `{stats['total_files']}`\n"
            f"⚙️ চলমান প্রসেস: `{stats['running_processes']}`\n"
            f"⏱️ আপটাইম: `{fmt_duration(stats['uptime_seconds'])}`\n"
            f"🔧 মেইনটেন্যান্স: {maint}\n\n"
            "নিচের বাটন থেকে যেকোনো কাজ করুন 👇"
        )
        bot.send_message(
            message.chat.id, text,
            parse_mode="Markdown",
            reply_markup=kb_admin_panel()
        )

    # ─── USER LIST ──────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "👥 ব্যবহারকারী তালিকা")
    def admin_user_list(message: Message):
        if not is_admin(message.from_user.id):
            return
        users = get_all_users()
        if not users:
            bot.send_message(message.chat.id, "📭 কোনো ইউজার নেই।", reply_markup=kb_admin_panel())
            return

        # Send in pages of 10
        per_page = 10
        for i in range(0, min(len(users), 50), per_page):
            chunk = users[i:i + per_page]
            lines = [f"👥 **ইউজার তালিকা** ({i+1}–{i+len(chunk)}/{len(users)}):\n"]
            for u in chunk:
                plan = PLANS.get(u["plan"])
                plan_label = plan.emoji if plan else "?"
                banned = "🚫" if u.get("is_banned") else "✅"
                lines.append(
                    f"{banned} `{u['user_id']}` | {plan_label} | "
                    f"@{u.get('username') or 'N/A'} — {u.get('full_name', '')}"
                )
            bot.send_message(message.chat.id, "\n".join(lines),
                             parse_mode="Markdown", reply_markup=kb_admin_panel())

    # ─── GLOBAL STATS ───────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🌐 গ্লোবাল স্ট্যাটস")
    def admin_global_stats(message: Message):
        if not is_admin(message.from_user.id):
            return
        stats = get_global_stats()
        system = fmt_system_stats()
        text = (
            f"🌐 **গ্লোবাল স্ট্যাটিস্টিক্স**\n\n"
            f"👥 মোট ইউজার: `{stats['total_users']}`\n"
            f"📁 মোট ফাইল: `{stats['total_files']}`\n"
            f"⚙️ চলমান প্রসেস: `{stats['running_processes']}`\n"
            f"⏱️ বট আপটাইম: `{fmt_duration(stats['uptime_seconds'])}`\n\n"
            f"{system}"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_admin_panel())

    # ─── BAN MANAGEMENT ─────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🚫 ব্যান ম্যানেজ")
    def admin_ban_menu(message: Message):
        if not is_admin(message.from_user.id):
            return
        set_admin_state(message.from_user.id, "awaiting_ban_input")
        bot.send_message(
            message.chat.id,
            "🚫 **ব্যান / আনব্যান**\n\n"
            "ফরম্যাট: `ban <user_id>` বা `unban <user_id>`\n\n"
            "উদাহরণ: `ban 123456789`",
            parse_mode="Markdown",
            reply_markup=kb_cancel()
        )

    # ─── PLAN MANAGEMENT ────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "👑 প্ল্যান দিন")
    def admin_plan_menu(message: Message):
        if not is_admin(message.from_user.id):
            return
        set_admin_state(message.from_user.id, "awaiting_plan_user_id")
        bot.send_message(
            message.chat.id,
            "👑 **প্ল্যান অ্যাসাইন করুন**\n\n"
            "ইউজারের Telegram ID টাইপ করুন:",
            parse_mode="Markdown",
            reply_markup=kb_cancel()
        )

    # ─── BROADCAST ──────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "📢 ব্রডকাস্ট")
    def admin_broadcast_prompt(message: Message):
        if not is_admin(message.from_user.id):
            return
        set_admin_state(message.from_user.id, "awaiting_broadcast_msg")
        bot.send_message(
            message.chat.id,
            "📢 **ব্রডকাস্ট মেসেজ**\n\n"
            "সব ইউজারকে পাঠাতে চান এমন মেসেজ লিখুন:",
            parse_mode="Markdown",
            reply_markup=kb_cancel()
        )

    # ─── MAINTENANCE ────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🔒 মেইনটেন্যান্স")
    def admin_maintenance_toggle(message: Message):
        if not is_admin(message.from_user.id):
            return
        current = is_maintenance()
        set_maintenance(not current)
        status = "🔴 **চালু** হয়েছে" if not current else "🟢 **বন্ধ** হয়েছে"
        bot.send_message(
            message.chat.id,
            f"🔧 মেইনটেন্যান্স মোড {status}\n\n"
            f"{'এখন সাধারণ ইউজাররা বট ব্যবহার করতে পারবে না।' if not current else 'এখন সব ইউজার বট ব্যবহার করতে পারবে।'}",
            parse_mode="Markdown",
            reply_markup=kb_admin_panel()
        )
        log_action(message.from_user.id, "maintenance_toggle", str(not current))

    # ─── CLEAR LOGS ─────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🗑️ লগ ক্লিয়ার")
    def admin_clear_logs(message: Message):
        if not is_admin(message.from_user.id):
            return
        try:
            log_dir = "logs"
            count = 0
            if os.path.exists(log_dir):
                for root, dirs, files in os.walk(log_dir):
                    for f in files:
                        if f.endswith(".log"):
                            os.remove(os.path.join(root, f))
                            count += 1
            log_action(message.from_user.id, "clear_logs", f"{count} files")
            bot.send_message(message.chat.id, f"🗑️ `{count}` টি লগ ফাইল মুছে ফেলা হয়েছে।",
                             parse_mode="Markdown", reply_markup=kb_admin_panel())
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ ব্যর্থ: {e}", reply_markup=kb_admin_panel())

    # ─── BOT RESTART ────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🔄 বট রিস্টার্ট")
    def admin_restart_bot(message: Message):
        if not is_admin(message.from_user.id):
            return
        bot.send_message(message.chat.id, "🔄 বট রিস্টার্ট হচ্ছে...", reply_markup=kb_admin_panel())
        log_action(message.from_user.id, "bot_restart", "")
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ─── STOP ALL PROCESSES ─────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "💥 সকল প্রসেস বন্ধ")
    def admin_stop_all(message: Message):
        if not is_admin(message.from_user.id):
            return
        count = executor.stop_all_processes_admin()
        log_action(message.from_user.id, "stop_all_processes", f"{count} stopped")
        bot.send_message(message.chat.id, f"💥 `{count}` টি প্রসেস বন্ধ করা হয়েছে।",
                         parse_mode="Markdown", reply_markup=kb_admin_panel())

    # ─── RESET USER FILES ───────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "🗂️ ফাইল রিসেট (ইউজার)")
    def admin_reset_files_prompt(message: Message):
        if not is_admin(message.from_user.id):
            return
        set_admin_state(message.from_user.id, "awaiting_reset_user_id")
        bot.send_message(
            message.chat.id,
            "🗂️ **ইউজার ফাইল রিসেট**\n\n"
            "যে ইউজারের ফাইল মুছবেন তার Telegram ID দিন:",
            parse_mode="Markdown",
            reply_markup=kb_cancel()
        )

    # ─── SHELL COMMAND ──────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "⚡ শেল কমান্ড")
    def admin_shell_prompt(message: Message):
        if not is_admin(message.from_user.id):
            return
        set_admin_state(message.from_user.id, "awaiting_shell_cmd")
        bot.send_message(
            message.chat.id,
            "⚡ **শেল কমান্ড এক্সিকিউট করুন**\n\n"
            "⚠️ সতর্কতার সাথে ব্যবহার করুন!\n\n"
            "কমান্ড টাইপ করুন (যেমন: `ls -la`, `df -h`, `free -m`):",
            parse_mode="Markdown",
            reply_markup=kb_cancel()
        )

    # ─── SYSTEM MONITOR ─────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text == "📊 সিস্টেম মনিটর")
    def admin_system_monitor(message: Message):
        if not is_admin(message.from_user.id):
            return
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot_time = psutil.boot_time()
        uptime = int(time.time() - boot_time)

        # Process count
        all_procs = len(psutil.pids())

        text = (
            f"📊 **সিস্টেম মনিটর**\n\n"
            f"⚡ **CPU:**\n"
            f"  ব্যবহার: `{cpu}%`\n"
            f"  কোর: `{psutil.cpu_count()}`\n\n"
            f"💾 **RAM:**\n"
            f"  ব্যবহৃত: `{fmt_size(ram.used)}` / `{fmt_size(ram.total)}`\n"
            f"  ফ্রি: `{fmt_size(ram.available)}`\n"
            f"  শতাংশ: `{ram.percent}%`\n\n"
            f"💿 **ডিস্ক:**\n"
            f"  ব্যবহৃত: `{fmt_size(disk.used)}` / `{fmt_size(disk.total)}`\n"
            f"  ফ্রি: `{fmt_size(disk.free)}`\n"
            f"  শতাংশ: `{disk.percent}%`\n\n"
            f"🌐 **নেটওয়ার্ক:**\n"
            f"  পাঠানো: `{fmt_size(net.bytes_sent)}`\n"
            f"  প্রাপ্ত: `{fmt_size(net.bytes_recv)}`\n\n"
            f"🔢 মোট প্রসেস: `{all_procs}`\n"
            f"⏱️ সিস্টেম আপটাইম: `{fmt_duration(uptime)}`"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=kb_admin_panel())

    # ═══════════════════════════════════════════════════════
    #  ADMIN TEXT INPUT STATE MACHINE
    # ═══════════════════════════════════════════════════════

    @bot.message_handler(
        func=lambda m: (
            m.from_user.id in ADMIN_IDS
            and get_admin_state(m.from_user.id)["state"] is not None
            and m.text != "❌ বাতিল করুন"
            and m.text != "🔙 মূল মেনু"
        )
    )
    def admin_state_handler(message: Message):
        user_id = message.from_user.id
        state_info = get_admin_state(user_id)
        state = state_info["state"]
        data = state_info["data"]
        text = message.text.strip()

        # ── Ban / Unban ───────────────────────────────────
        if state == "awaiting_ban_input":
            clear_admin_state(user_id)
            parts = text.lower().split()
            if len(parts) != 2 or parts[0] not in ("ban", "unban"):
                bot.send_message(message.chat.id,
                                 "❌ ফরম্যাট ভুল। উদাহরণ: `ban 123456789`",
                                 parse_mode="Markdown", reply_markup=kb_admin_panel())
                return
            action, target_id_str = parts
            try:
                target_id = int(target_id_str)
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_admin_panel())
                return
            if action == "ban":
                ban_user(target_id)
                log_action(user_id, "ban_user", str(target_id))
                bot.send_message(message.chat.id, f"🚫 User `{target_id}` ব্যান হয়েছে।",
                                 parse_mode="Markdown", reply_markup=kb_admin_panel())
            else:
                unban_user(target_id)
                log_action(user_id, "unban_user", str(target_id))
                bot.send_message(message.chat.id, f"✅ User `{target_id}` আনব্যান হয়েছে।",
                                 parse_mode="Markdown", reply_markup=kb_admin_panel())

        # ── Plan: get user ID ─────────────────────────────
        elif state == "awaiting_plan_user_id":
            try:
                target_id = int(text)
                target_user = get_user(target_id)
                if not target_user:
                    bot.send_message(message.chat.id, f"❌ User `{target_id}` পাওয়া যায়নি।",
                                     parse_mode="Markdown", reply_markup=kb_admin_panel())
                    clear_admin_state(user_id)
                    return
                set_admin_state(user_id, "awaiting_plan_select", target_id=target_id)
                bot.send_message(
                    message.chat.id,
                    f"👑 **{target_user.get('full_name', 'User')}** (`{target_id}`) এর জন্য প্ল্যান বেছে নিন:",
                    parse_mode="Markdown",
                    reply_markup=ikb_plan_selector(target_id)
                )
            except ValueError:
                clear_admin_state(user_id)
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_admin_panel())

        # ── Broadcast: send message ───────────────────────
        elif state == "awaiting_broadcast_msg":
            clear_admin_state(user_id)
            users = get_all_users()
            sent = 0
            failed = 0
            broadcast_text = f"📢 **এডমিন বার্তা:**\n\n{text}"
            for u in users:
                try:
                    bot.send_message(u["user_id"], broadcast_text, parse_mode="Markdown")
                    sent += 1
                    time.sleep(0.05)  # Rate limit safety
                except Exception:
                    failed += 1
            log_action(user_id, "broadcast", f"sent:{sent} failed:{failed}")
            bot.send_message(
                message.chat.id,
                f"📢 **ব্রডকাস্ট সম্পন্ন!**\n\n✅ পাঠানো: `{sent}`\n❌ ব্যর্থ: `{failed}`",
                parse_mode="Markdown",
                reply_markup=kb_admin_panel()
            )

        # ── Reset user files ──────────────────────────────
        elif state == "awaiting_reset_user_id":
            clear_admin_state(user_id)
            try:
                target_id = int(text)
                ok, msg = file_service.reset_user_files(target_id)
                bot.send_message(message.chat.id, msg, reply_markup=kb_admin_panel())
            except ValueError:
                bot.send_message(message.chat.id, "❌ বৈধ ID দিন।", reply_markup=kb_admin_panel())

        # ── Shell command ─────────────────────────────────
        elif state == "awaiting_shell_cmd":
            clear_admin_state(user_id)

            # Blocked dangerous commands
            BLOCKED = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb", "shutdown", "reboot"]
            if any(b in text.lower() for b in BLOCKED):
                bot.send_message(message.chat.id,
                                 "🚫 এই কমান্ড নিরাপত্তার কারণে ব্লক করা আছে।",
                                 reply_markup=kb_admin_panel())
                return

            try:
                result = subprocess.run(
                    text, shell=True,
                    capture_output=True, text=True,
                    timeout=30
                )
                output = result.stdout + result.stderr
                if not output.strip():
                    output = "(কোনো আউটপুট নেই)"
                if len(output) > 3800:
                    output = output[:3800] + "\n...(কাটা হয়েছে)"

                log_action(user_id, "shell_cmd", text[:100])
                bot.send_message(
                    message.chat.id,
                    f"⚡ **কমান্ড:** `{text}`\n\n"
                    f"📤 **আউটপুট:**\n```\n{output}\n```",
                    parse_mode="Markdown",
                    reply_markup=kb_admin_panel()
                )
            except subprocess.TimeoutExpired:
                bot.send_message(message.chat.id, "⏱️ কমান্ড টাইমআউট (৩০ সেকেন্ড)।",
                                 reply_markup=kb_admin_panel())
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ এরর: {e}", reply_markup=kb_admin_panel())

    # ═══════════════════════════════════════════════════════
    #  ADMIN CALLBACK QUERIES
    # ═══════════════════════════════════════════════════════

    @bot.callback_query_handler(func=lambda c: c.data.startswith("setplan_") and c.from_user.id in ADMIN_IDS)
    def cb_set_plan(call: CallbackQuery):
        # Format: setplan_{user_id}_{plan}_{days}
        parts = call.data.split("_")
        if len(parts) != 4:
            bot.answer_callback_query(call.id, "❌ ভুল ফরম্যাট")
            return
        _, target_id, plan, days = parts
        target_id = int(target_id)
        days = int(days)

        ok, msg = subscription_service.assign_plan(call.from_user.id, target_id, plan, days)
        bot.answer_callback_query(call.id, "✅ আপডেট হয়েছে!")
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        clear_admin_state(call.from_user.id)

        # Notify the user if possible
        try:
            plan_info = PLANS.get(plan)
            if plan_info:
                bot.send_message(
                    target_id,
                    f"🎉 **আপনার প্ল্যান আপগ্রেড হয়েছে!**\n\n"
                    f"{plan_info.emoji} **{plan_info.label}** প্ল্যান অ্যাক্টিভ হয়েছে।\n"
                    f"📅 {days} দিনের জন্য।",
                    parse_mode="Markdown"
                )
        except Exception:
            pass  # User may have blocked the bot
