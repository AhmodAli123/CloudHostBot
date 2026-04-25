"""
╔══════════════════════════════════════════════════════════════╗
║           CLOUDHOST BOT — MAIN ENTRY POINT                   ║
║                                                              ║
║   Production-Ready Telegram Cloud Hosting Platform           ║
║   Version: 2.0.0                                             ║
║                                                              ║
║   Features:                                                  ║
║   ✅ File Management (Python/JS/ZIP)                         ║
║   ✅ Script Execution Engine                                 ║
║   ✅ Process Manager (PM2-like)                              ║
║   ✅ Subscription System (Free/Premium/Pro)                  ║
║   ✅ Cron Job Scheduler                                      ║
║   ✅ AI Error Fix Engine                                     ║
║   ✅ Admin Panel (Full Control)                              ║
║   ✅ Flask Keep-Alive Dashboard                              ║
║   ✅ Auto Dependency Installer                               ║
║   ✅ Marketplace System                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import logging
import threading

import telebot
from telebot import TeleBot

# ─────────────────────────────────────────────
#  SETUP LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("CloudHostBot")

# ─────────────────────────────────────────────
#  ENSURE DIRECTORIES EXIST
# ─────────────────────────────────────────────
for directory in ["storage", "logs", "database", "config"]:
    os.makedirs(directory, exist_ok=True)

# ─────────────────────────────────────────────
#  IMPORTS (after dirs created)
# ─────────────────────────────────────────────
from config.settings import BOT_TOKEN, ADMIN_IDS, BOT_NAME, VERSION
from database.db_manager import init_db, set_setting
from core.keep_alive import start_keep_alive
from handlers.user_handlers import register_user_handlers
from handlers.admin_handlers import register_admin_handlers
from services.security import register_user, check_access


# ══════════════════════════════════════════════════════════════
#  BOT INITIALIZATION
# ══════════════════════════════════════════════════════════════

def create_bot() -> TeleBot:
    """Create and configure the Telegram bot."""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.critical("❌ BOT_TOKEN সেট করা হয়নি! config/settings.py বা .env ফাইল চেক করুন।")
        sys.exit(1)

    bot = TeleBot(
        BOT_TOKEN,
        parse_mode=None,
        threaded=True,
        num_threads=4
    )

    # ─── Middleware: access control for ALL messages ──────
    @bot.middleware_handler(update_types=["message"])
    def middleware_check(bot_instance, message):
        if message.from_user:
            register_user(message)
            # Update last_activity
            from database.db_manager import update_user
            update_user(message.from_user.id, last_activity=int(time.time()))

    # ─── Global error handler ────────────────────────────
    @bot.message_handler(func=lambda m: False)
    def fallback(message):
        pass  # Catch-all, never triggers

    return bot


def register_all_handlers(bot: TeleBot):
    """Register all message and callback handlers."""
    register_user_handlers(bot)
    register_admin_handlers(bot)
    logger.info("✅ সব হ্যান্ডলার রেজিস্টার হয়েছে।")


# ══════════════════════════════════════════════════════════════
#  STARTUP NOTIFICATIONS
# ══════════════════════════════════════════════════════════════

def notify_admins(bot: TeleBot):
    """Send startup notification to all admins."""
    from database.db_manager import get_global_stats
    from utils.keyboards import fmt_duration
    import psutil

    stats = get_global_stats()
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()

    msg = (
        f"🚀 **{BOT_NAME}** চালু হয়েছে!\n\n"
        f"🔢 ভার্সন: `{VERSION}`\n"
        f"👥 ইউজার: `{stats['total_users']}`\n"
        f"📁 ফাইল: `{stats['total_files']}`\n"
        f"⚡ CPU: `{cpu}%`\n"
        f"💾 RAM: `{ram.percent}%`\n"
        f"⏱️ সময়: `{time.strftime('%d/%m/%Y %H:%M:%S')}`"
    )
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Admin {admin_id} তে নোটিফিকেশন পাঠানো যায়নি: {e}")


# ══════════════════════════════════════════════════════════════
#  POLLING WITH AUTO-RESTART
# ══════════════════════════════════════════════════════════════

def start_polling(bot: TeleBot):
    """Start bot polling with automatic restart on failure."""
    retry_count = 0
    max_retries = 10

    while retry_count < max_retries:
        try:
            logger.info(f"🤖 Polling শুরু হচ্ছে... (attempt {retry_count + 1})")
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=15,
                logger_level=logging.WARNING,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
        except telebot.apihelper.ApiException as e:
            logger.error(f"❌ Telegram API এরর: {e}")
            retry_count += 1
            time.sleep(5)
        except Exception as e:
            logger.error(f"❌ অপ্রত্যাশিত এরর: {e}")
            retry_count += 1
            time.sleep(3)
        else:
            break  # Clean exit

    logger.critical("❌ সর্বোচ্চ রিট্রাই শেষ। বট বন্ধ হচ্ছে।")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print(f"  ☁️  {BOT_NAME} v{VERSION}")
    print("  Telegram Cloud Hosting Platform")
    print("=" * 60)

    # 1. Initialize database
    logger.info("📦 ডেটাবেস ইনিশিয়ালাইজ হচ্ছে...")
    init_db()
    set_setting("bot_start_time", str(time.time()))

    # 2. Start Flask keep-alive
    logger.info("🌐 Keep-alive সার্ভার শুরু হচ্ছে...")
    start_keep_alive()

    # 3. Create bot
    logger.info("🤖 বট তৈরি হচ্ছে...")
    bot = create_bot()

    # 4. Register handlers
    register_all_handlers(bot)

    # 5. Notify admins
    try:
        notify_admins(bot)
    except Exception as e:
        logger.warning(f"এডমিন নোটিফিকেশন ব্যর্থ: {e}")

    # 6. Start cron service (already auto-started as daemon thread)
    from services.cron_service import cron_service
    logger.info("⏰ ক্রোন সার্ভিস চালু আছে।")

    # 7. Start polling
    logger.info(f"✅ বট সফলভাবে চালু! @{bot.get_me().username}")
    start_polling(bot)


if __name__ == "__main__":
    main()
