"""
╔══════════════════════════════════════════════════════════════╗
║          CLOUD HOST BOT — CONFIGURATION SETTINGS            ║
║          Production-Ready Telegram Cloud Platform            ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict

# ─────────────────────────────────────────────
#  BOT CREDENTIALS
# ─────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS: List[int] = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
DB_PATH: str = "database/cloudhost.db"
CACHE_PATH: str = "database/cache.json"

# ─────────────────────────────────────────────
#  STORAGE
# ─────────────────────────────────────────────
BASE_STORAGE: str = "storage"
LOG_DIR: str = "logs"
MAX_UPLOAD_SIZE_MB: int = 50  # MB

# ─────────────────────────────────────────────
#  SUBSCRIPTION PLANS
# ─────────────────────────────────────────────
@dataclass
class PlanLimits:
    max_files: int
    max_processes: int
    max_storage_mb: int
    max_file_size_mb: int
    label: str
    emoji: str

PLANS: Dict[str, PlanLimits] = {
    "free": PlanLimits(
        max_files=5,
        max_processes=2,
        max_storage_mb=100,
        max_file_size_mb=10,
        label="Free",
        emoji="🆓"
    ),
    "premium": PlanLimits(
        max_files=30,
        max_processes=10,
        max_storage_mb=1024,
        max_file_size_mb=50,
        label="Premium",
        emoji="⭐"
    ),
    "pro": PlanLimits(
        max_files=100,
        max_processes=50,
        max_storage_mb=10240,
        max_file_size_mb=100,
        label="Pro",
        emoji="💎"
    ),
}

# ─────────────────────────────────────────────
#  PROCESS SETTINGS
# ─────────────────────────────────────────────
PROCESS_TIMEOUT_SEC: int = 3600        # 1 hour max run time
LOG_TAIL_LINES: int = 50
PROCESS_CHECK_INTERVAL: int = 30       # seconds

# ─────────────────────────────────────────────
#  FLASK KEEP-ALIVE
# ─────────────────────────────────────────────
FLASK_PORT: int = int(os.getenv("PORT", 8080))
FLASK_HOST: str = "0.0.0.0"

# ─────────────────────────────────────────────
#  ALLOWED FILE EXTENSIONS
# ─────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".py", ".js", ".zip", ".txt", ".json", ".env", ".sh"}
RUNNABLE_EXTENSIONS = {".py", ".js"}

# ─────────────────────────────────────────────
#  MESSAGES & TEXT
# ─────────────────────────────────────────────
BOT_NAME = "☁️ CloudHost Bot"
VERSION = "2.0.0"
