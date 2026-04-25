"""
╔══════════════════════════════════════════════════════════════╗
║               EXECUTION ENGINE                               ║
║    Run Python/Node scripts, manage processes, kill trees     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import re
import ast
import sys
import time
import signal
import shutil
import asyncio
import subprocess
import threading
import psutil
from typing import Optional, Tuple, Dict, List

from database.db_manager import (
    add_process, update_process_status, get_processes,
    get_process_by_id, log_action, get_all_running_processes
)
from utils.keyboards import get_user_storage_dir, get_user_log_dir
from config.settings import PROCESS_TIMEOUT_SEC, PLANS


# ══════════════════════════════════════════════════════════════
#  DEPENDENCY AUTO-INSTALLER
# ══════════════════════════════════════════════════════════════

# Map of common import names → pip package names
PACKAGE_MAP = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "telegram": "pyTelegramBotAPI",
    "aiogram": "aiogram",
    "aiohttp": "aiohttp",
    "requests": "requests",
    "flask": "flask",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "SQLAlchemy",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "selenium": "selenium",
    "httpx": "httpx",
    "pydantic": "pydantic",
    "cryptography": "cryptography",
    "paramiko": "paramiko",
    "pymongo": "pymongo",
    "redis": "redis",
    "celery": "celery",
    "jwt": "PyJWT",
    "stripe": "stripe",
    "twilio": "twilio",
    "discord": "discord.py",
}


def extract_python_imports(code: str) -> List[str]:
    """Extract all top-level imports from Python source."""
    packages = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    packages.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    packages.append(node.module.split(".")[0])
    except SyntaxError:
        # Fallback: regex
        for match in re.finditer(r'^(?:import|from)\s+(\w+)', code, re.MULTILINE):
            packages.append(match.group(1))
    return list(set(packages))


def extract_node_requires(code: str) -> List[str]:
    """Extract require() calls from Node.js source."""
    pattern = r"require\(['\"]([^'\"./][^'\"]*)['\"]"
    return list(set(re.findall(pattern, code)))


def install_pip_packages(packages: List[str], user_storage: str) -> Tuple[bool, str]:
    """Install missing pip packages."""
    stdlib_modules = set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else set()
    to_install = []
    for pkg in packages:
        if pkg in stdlib_modules:
            continue
        mapped = PACKAGE_MAP.get(pkg, pkg)
        to_install.append(mapped)

    if not to_install:
        return True, "কোনো ডিপেন্ডেন্সি ইনস্টল প্রয়োজন নেই।"

    cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + to_install
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True, f"✅ ইনস্টল হয়েছে: {', '.join(to_install)}"
        else:
            return False, f"❌ ইনস্টল ব্যর্থ:\n{result.stderr[:500]}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


def install_requirements_txt(req_path: str) -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", "pip", "install", "-r", req_path, "--quiet"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True, "✅ requirements.txt থেকে প্যাকেজ ইনস্টল হয়েছে।"
        return False, f"❌ ইনস্টল ব্যর্থ:\n{result.stderr[:500]}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


def install_package_json(dir_path: str) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            ["npm", "install", "--silent"],
            cwd=dir_path, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return True, "✅ npm প্যাকেজ ইনস্টল হয়েছে।"
        return False, f"❌ npm ইনস্টল ব্যর্থ:\n{result.stderr[:500]}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


# ══════════════════════════════════════════════════════════════
#  SCRIPT EXECUTOR
# ══════════════════════════════════════════════════════════════

class ScriptExecutor:
    """Manages script execution, process lifecycle, and logs."""

    def __init__(self):
        self._processes: Dict[int, subprocess.Popen] = {}  # proc_db_id → Popen
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    # ─── PREPARE & RUN ─────────────────────────────────────

    def run_script(
        self,
        user_id: int,
        script_path: str,
        script_name: str,
        plan: str = "free",
        auto_install: bool = True
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Launch a script in the background.
        Returns (success, message, proc_db_id)
        """
        # Check process limit
        running = get_processes(user_id, "running")
        plan_limits = PLANS.get(plan)
        if plan_limits and len(running) >= plan_limits.max_processes:
            return False, f"❌ প্রসেস লিমিট ({plan_limits.max_processes}) পূর্ণ হয়েছে।", None

        if not os.path.exists(script_path):
            return False, "❌ স্ক্রিপ্ট ফাইল পাওয়া যায়নি।", None

        ext = os.path.splitext(script_name)[1].lower()
        if ext == ".py":
            cmd = [sys.executable, script_path]
            install_msg = self._auto_install_python(script_path, auto_install)
        elif ext == ".js":
            if not shutil.which("node"):
                return False, "❌ Node.js ইনস্টল নেই।", None
            cmd = ["node", script_path]
            install_msg = self._auto_install_node(script_path, auto_install)
        else:
            return False, "❌ অসমর্থিত ফাইল টাইপ।", None

        # Set up log file
        log_dir = get_user_log_dir(user_id)
        log_file = os.path.join(log_dir, f"{script_name}_{int(time.time())}.log")

        try:
            with open(log_file, "w") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Starting: {script_name}\n")
                if install_msg:
                    lf.write(f"[DEPS] {install_msg}\n")
                lf.write("─" * 50 + "\n")

            proc = subprocess.Popen(
                cmd,
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(script_path),
                preexec_fn=os.setsid  # Create new process group
            )

            proc_id = add_process(user_id, proc.pid, script_name, script_path, log_file)
            self._processes[proc_id] = proc
            log_action(user_id, "run_script", script_name)

            return True, f"✅ **{script_name}** শুরু হয়েছে!\n🆔 প্রসেস ID: `{proc_id}`\n📜 লগ ট্র্যাক হচ্ছে...", proc_id

        except Exception as e:
            return False, f"❌ শুরু করতে ব্যর্থ: {str(e)}", None

    def _auto_install_python(self, script_path: str, enabled: bool) -> str:
        if not enabled:
            return ""
        try:
            with open(script_path) as f:
                code = f.read()
            imports = extract_python_imports(code)
            ok, msg = install_pip_packages(imports, os.path.dirname(script_path))

            # Check for requirements.txt in same dir
            req = os.path.join(os.path.dirname(script_path), "requirements.txt")
            if os.path.exists(req):
                install_requirements_txt(req)
            return msg
        except Exception as e:
            return f"ডিপেন্ডেন্সি চেক ব্যর্থ: {e}"

    def _auto_install_node(self, script_path: str, enabled: bool) -> str:
        if not enabled:
            return ""
        dir_path = os.path.dirname(script_path)
        pkg_json = os.path.join(dir_path, "package.json")
        if os.path.exists(pkg_json):
            ok, msg = install_package_json(dir_path)
            return msg
        return ""

    # ─── STOP / KILL ───────────────────────────────────────

    def stop_process(self, proc_id: int, user_id: int, force: bool = False) -> Tuple[bool, str]:
        """Stop a process gracefully or forcefully."""
        proc_info = get_process_by_id(proc_id, user_id)
        if not proc_info:
            return False, "❌ প্রসেস পাওয়া যায়নি।"

        pid = proc_info.get("pid")
        popen = self._processes.get(proc_id)

        if popen:
            try:
                if force:
                    os.killpg(os.getpgid(popen.pid), signal.SIGKILL)
                else:
                    os.killpg(os.getpgid(popen.pid), signal.SIGTERM)
                popen.wait(timeout=5)
            except Exception:
                pass
        else:
            # Try via PID directly
            self._kill_pid(pid, force)

        update_process_status(proc_id, "stopped")
        self._processes.pop(proc_id, None)
        log_action(user_id, "stop_process", f"ID:{proc_id}")
        action = "ফোর্স কিল" if force else "বন্ধ"
        return True, f"✅ প্রসেস {action} করা হয়েছে।"

    def _kill_pid(self, pid: int, force: bool = False):
        try:
            proc = psutil.Process(pid)
            children = proc.children(recursive=True)
            for child in children:
                child.kill() if force else child.terminate()
            proc.kill() if force else proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def restart_process(self, proc_id: int, user_id: int) -> Tuple[bool, str, Optional[int]]:
        """Stop and restart a process."""
        proc_info = get_process_by_id(proc_id, user_id)
        if not proc_info:
            return False, "❌ প্রসেস পাওয়া যায়নি।", None

        self.stop_process(proc_id, user_id, force=True)
        time.sleep(1)

        from database.db_manager import get_user
        user = get_user(user_id)
        plan = user["plan"] if user else "free"

        return self.run_script(
            user_id,
            proc_info["script_path"],
            proc_info["script_name"],
            plan
        )

    def stop_all_user_processes(self, user_id: int) -> int:
        """Stop all processes for a user. Returns count stopped."""
        procs = get_processes(user_id, "running")
        count = 0
        for p in procs:
            ok, _ = self.stop_process(p["id"], user_id, force=True)
            if ok:
                count += 1
        return count

    def stop_all_processes_admin(self) -> int:
        """Admin: stop ALL running processes."""
        procs = get_all_running_processes()
        count = 0
        for p in procs:
            self._kill_pid(p.get("pid", 0), force=True)
            update_process_status(p["id"], "stopped")
            count += 1
        self._processes.clear()
        return count

    # ─── LOGS ──────────────────────────────────────────────

    def get_log_tail(self, proc_id: int, user_id: int, lines: int = 50) -> str:
        proc_info = get_process_by_id(proc_id, user_id)
        if not proc_info:
            return "❌ প্রসেস পাওয়া যায়নি।"
        log_file = proc_info.get("log_file", "")
        return self._tail_file(log_file, lines)

    def get_log_by_filename(self, log_path: str, lines: int = 50) -> str:
        return self._tail_file(log_path, lines)

    def _tail_file(self, filepath: str, lines: int) -> str:
        if not filepath or not os.path.exists(filepath):
            return "📭 লগ ফাইল নেই বা খালি।"
        try:
            with open(filepath, "r", errors="replace") as f:
                content = f.readlines()
            tail = content[-lines:]
            return "".join(tail) or "📭 লগ ফাইল খালি।"
        except Exception as e:
            return f"❌ লগ পড়তে ব্যর্থ: {e}"

    # ─── MONITOR ───────────────────────────────────────────

    def _monitor_loop(self):
        """Background thread: clean up finished processes."""
        while True:
            try:
                for proc_id, popen in list(self._processes.items()):
                    if popen.poll() is not None:  # Process finished
                        update_process_status(proc_id, "finished")
                        self._processes.pop(proc_id, None)
            except Exception:
                pass
            time.sleep(30)

    # ─── RESOURCE INFO ─────────────────────────────────────

    def get_process_resource_info(self, proc_id: int, user_id: int) -> str:
        proc_info = get_process_by_id(proc_id, user_id)
        if not proc_info:
            return "❌ প্রসেস পাওয়া যায়নি।"

        pid = proc_info.get("pid")
        try:
            p = psutil.Process(pid)
            cpu = p.cpu_percent(interval=0.5)
            mem = p.memory_info().rss
            status = p.status()
            started = proc_info.get("started_at", 0)
            duration = int(time.time() - started) if started else 0
            from utils.keyboards import fmt_size, fmt_duration
            return (
                f"📊 **{proc_info['script_name']} রিসোর্স**\n\n"
                f"⚡ CPU: `{cpu}%`\n"
                f"💾 RAM: `{fmt_size(mem)}`\n"
                f"📊 স্ট্যাটাস: `{status}`\n"
                f"⏱️ চলছে: `{fmt_duration(duration)}`\n"
                f"🔢 PID: `{pid}`"
            )
        except psutil.NoSuchProcess:
            update_process_status(proc_id, "finished")
            return "⚠️ প্রসেসটি আর চলছে না।"
        except Exception as e:
            return f"❌ তথ্য পেতে ব্যর্থ: {e}"


# Global executor instance
executor = ScriptExecutor()
