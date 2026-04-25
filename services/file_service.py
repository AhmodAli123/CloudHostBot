"""
╔══════════════════════════════════════════════════════════════╗
║               FILE MANAGEMENT SERVICE                        ║
║    Upload, list, delete, edit, extract files per user        ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import shutil
import zipfile
import time
from typing import Tuple, List, Optional, Dict

from database.db_manager import (
    add_file, get_files, delete_file_record,
    get_file_by_name, get_total_storage, log_action, get_user
)
from utils.keyboards import get_user_storage_dir, fmt_size, safe_filename
from config.settings import PLANS, ALLOWED_EXTENSIONS


# ══════════════════════════════════════════════════════════════
#  FILE SERVICE
# ══════════════════════════════════════════════════════════════

class FileService:

    # ─── UPLOAD ────────────────────────────────────────────

    def save_uploaded_file(
        self,
        user_id: int,
        filename: str,
        file_bytes: bytes,
        plan: str = "free"
    ) -> Tuple[bool, str]:
        """
        Save a file uploaded via Telegram.
        Returns (success, message).
        """
        filename = safe_filename(filename)
        ext = os.path.splitext(filename)[1].lower()

        # Extension check
        if ext not in ALLOWED_EXTENSIONS:
            return False, (
                f"❌ অনুমোদিত নয়: `{ext}`\n"
                f"✅ অনুমোদিত: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        limits = PLANS.get(plan)
        if not limits:
            return False, "❌ অজানা প্ল্যান।"

        # File size check
        size_bytes = len(file_bytes)
        if size_bytes > limits.max_file_size_mb * 1024 * 1024:
            return False, f"❌ ফাইল অনেক বড়। সর্বোচ্চ: {limits.max_file_size_mb} MB"

        # File count check
        existing = get_files(user_id)
        if len(existing) >= limits.max_files:
            return False, f"❌ ফাইল সীমা পূর্ণ। সর্বোচ্চ: {limits.max_files} টি"

        # Storage check
        current_storage = get_total_storage(user_id)
        if (current_storage + size_bytes) > limits.max_storage_mb * 1024 * 1024:
            used = fmt_size(current_storage)
            total = f"{limits.max_storage_mb} MB"
            return False, f"❌ স্টোরেজ পূর্ণ। ব্যবহৃত: {used} / {total}"

        # Save file
        storage_dir = get_user_storage_dir(user_id)
        filepath = os.path.join(storage_dir, filename)

        # Avoid overwriting — append timestamp if exists
        if os.path.exists(filepath):
            base, ext2 = os.path.splitext(filename)
            filename = f"{base}_{int(time.time())}{ext2}"
            filepath = os.path.join(storage_dir, filename)

        with open(filepath, "wb") as f:
            f.write(file_bytes)

        file_id = add_file(user_id, filename, filepath, size_bytes)
        log_action(user_id, "upload_file", filename)

        msg = f"✅ **{filename}** আপলোড সফল!\n📦 সাইজ: `{fmt_size(size_bytes)}`"

        # Auto-extract ZIP
        if ext == ".zip":
            ok, extract_msg = self.extract_zip(user_id, filename, plan)
            msg += f"\n\n{extract_msg}"

        return True, msg

    # ─── EXTRACT ZIP ───────────────────────────────────────

    def extract_zip(
        self,
        user_id: int,
        zip_filename: str,
        plan: str = "free"
    ) -> Tuple[bool, str]:
        """Extract a ZIP file into user's storage directory."""
        storage_dir = get_user_storage_dir(user_id)
        zip_path = os.path.join(storage_dir, safe_filename(zip_filename))

        if not os.path.exists(zip_path):
            return False, "❌ ZIP ফাইল পাওয়া যায়নি।"

        if not zipfile.is_zipfile(zip_path):
            return False, "❌ বৈধ ZIP ফাইল নয়।"

        limits = PLANS.get(plan)
        extracted_files = []

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Security: check for path traversal in zip entries
                for member in zf.namelist():
                    member_path = os.path.realpath(
                        os.path.join(storage_dir, member)
                    )
                    if not member_path.startswith(os.path.realpath(storage_dir)):
                        return False, "❌ নিরাপত্তা লঙ্ঘন: ZIP-এ অনুপযুক্ত পাথ।"

                zf.extractall(storage_dir)
                extracted_files = zf.namelist()

            # Register extracted files in DB
            for fname in extracted_files:
                fpath = os.path.join(storage_dir, fname)
                if os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    existing = get_files(user_id)
                    if len(existing) < (limits.max_files if limits else 100):
                        add_file(user_id, fname, fpath, size)

            log_action(user_id, "extract_zip", zip_filename)
            return True, f"📦 ZIP এক্সট্র্যাক্ট সফল! {len(extracted_files)} টি ফাইল।"

        except zipfile.BadZipFile:
            return False, "❌ ZIP ফাইল নষ্ট।"
        except Exception as e:
            return False, f"❌ এক্সট্র্যাক্ট ব্যর্থ: {str(e)}"

    # ─── LIST ──────────────────────────────────────────────

    def list_files(self, user_id: int) -> List[Dict]:
        """Return all files for a user."""
        files = get_files(user_id)
        # Verify files still exist on disk
        valid = []
        for f in files:
            if os.path.exists(f["filepath"]):
                valid.append(f)
            else:
                # Cleanup stale DB record
                delete_file_record(f["id"], user_id)
        return valid

    def format_file_list(self, files: List[Dict]) -> str:
        if not files:
            return "📭 কোনো ফাইল নেই। /upload দিয়ে আপলোড করুন।"
        lines = ["📁 **আপনার ফাইলসমূহ:**\n"]
        for i, f in enumerate(files, 1):
            size = fmt_size(f.get("size_bytes", 0))
            ext = os.path.splitext(f["filename"])[1]
            icon = "🐍" if ext == ".py" else "🟨" if ext == ".js" else "📄"
            lines.append(f"{i}. {icon} `{f['filename']}` — {size}")
        return "\n".join(lines)

    # ─── DELETE ────────────────────────────────────────────

    def delete_file(self, user_id: int, filename: str) -> Tuple[bool, str]:
        filename = safe_filename(filename)
        record = get_file_by_name(user_id, filename)
        if not record:
            return False, f"❌ ফাইল পাওয়া যায়নি: `{filename}`"

        filepath = record["filepath"]
        if os.path.exists(filepath):
            os.remove(filepath)

        delete_file_record(record["id"], user_id)
        log_action(user_id, "delete_file", filename)
        return True, f"🗑️ **{filename}** মুছে ফেলা হয়েছে।"

    def delete_file_by_id(self, user_id: int, file_id: int) -> Tuple[bool, str]:
        files = get_files(user_id)
        record = next((f for f in files if f["id"] == file_id), None)
        if not record:
            return False, "❌ ফাইল পাওয়া যায়নি।"
        return self.delete_file(user_id, record["filename"])

    # ─── READ / EDIT ───────────────────────────────────────

    def read_file(self, user_id: int, filename: str) -> Tuple[bool, str]:
        filename = safe_filename(filename)
        storage_dir = get_user_storage_dir(user_id)
        filepath = os.path.join(storage_dir, filename)

        if not os.path.exists(filepath):
            return False, "❌ ফাইল পাওয়া যায়নি।"

        try:
            with open(filepath, "r", errors="replace") as f:
                content = f.read()
            if len(content) > 3800:
                content = content[:3800] + "\n\n... (বাকি অংশ কাটা হয়েছে)"
            return True, content
        except Exception as e:
            return False, f"❌ ফাইল পড়তে ব্যর্থ: {e}"

    def write_file(self, user_id: int, filename: str, content: str) -> Tuple[bool, str]:
        filename = safe_filename(filename)
        storage_dir = get_user_storage_dir(user_id)
        filepath = os.path.join(storage_dir, filename)

        if not os.path.exists(filepath):
            return False, "❌ ফাইল পাওয়া যায়নি।"

        try:
            with open(filepath, "w") as f:
                f.write(content)
            log_action(user_id, "edit_file", filename)
            return True, f"✅ **{filename}** সেভ হয়েছে।"
        except Exception as e:
            return False, f"❌ সেভ ব্যর্থ: {e}"

    def create_new_file(
        self,
        user_id: int,
        filename: str,
        content: str,
        plan: str = "free"
    ) -> Tuple[bool, str]:
        filename = safe_filename(filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"❌ অনুমোদিত নয়: {ext}"

        limits = PLANS.get(plan)
        existing = get_files(user_id)
        if limits and len(existing) >= limits.max_files:
            return False, f"❌ ফাইল সীমা পূর্ণ।"

        storage_dir = get_user_storage_dir(user_id)
        filepath = os.path.join(storage_dir, filename)

        with open(filepath, "w") as f:
            f.write(content)

        size = len(content.encode())
        add_file(user_id, filename, filepath, size)
        log_action(user_id, "create_file", filename)
        return True, f"✅ **{filename}** তৈরি হয়েছে।"

    # ─── RESET USER FILES (Admin) ───────────────────────────

    def reset_user_files(self, user_id: int) -> Tuple[bool, str]:
        """Admin: delete all files for a user."""
        storage_dir = get_user_storage_dir(user_id)
        try:
            shutil.rmtree(storage_dir, ignore_errors=True)
            os.makedirs(storage_dir, exist_ok=True)
            # Clear DB
            files = get_files(user_id)
            for f in files:
                delete_file_record(f["id"], user_id)
            log_action(0, "admin_reset_files", f"user:{user_id}")
            return True, f"✅ User {user_id} এর সমস্ত ফাইল মুছে ফেলা হয়েছে।"
        except Exception as e:
            return False, f"❌ রিসেট ব্যর্থ: {e}"

    # ─── STORAGE INFO ──────────────────────────────────────

    def get_storage_info(self, user_id: int, plan: str = "free") -> str:
        used = get_total_storage(user_id)
        limits = PLANS.get(plan)
        max_mb = limits.max_storage_mb if limits else 100
        max_bytes = max_mb * 1024 * 1024
        pct = (used / max_bytes * 100) if max_bytes else 0
        bar_filled = int(pct / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        return (
            f"💾 **স্টোরেজ ব্যবহার**\n"
            f"[{bar}] {pct:.1f}%\n"
            f"ব্যবহৃত: `{fmt_size(used)}` / `{fmt_size(max_bytes)}`"
        )


# Global file service instance
file_service = FileService()
