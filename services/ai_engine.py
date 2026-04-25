"""
╔══════════════════════════════════════════════════════════════╗
║               AI ERROR FIX ENGINE                            ║
║    Analyze logs, suggest fixes, auto-apply simple fixes      ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import os
import sys
import subprocess
from typing import Tuple, List, Optional

from core.executor import install_pip_packages, PACKAGE_MAP
from database.db_manager import get_process_by_id


# ══════════════════════════════════════════════════════════════
#  ERROR PATTERNS
# ══════════════════════════════════════════════════════════════

ERROR_PATTERNS = [
    {
        "pattern": r"ModuleNotFoundError: No module named '(\w+)'",
        "type": "missing_module",
        "fix": "auto_install",
        "label": "মডিউল পাওয়া যায়নি",
    },
    {
        "pattern": r"ImportError: cannot import name '(\w+)'",
        "type": "import_error",
        "fix": "suggest",
        "label": "ইম্পোর্ট এরর",
    },
    {
        "pattern": r"SyntaxError: (.+)",
        "type": "syntax_error",
        "fix": "suggest",
        "label": "সিনট্যাক্স এরর",
    },
    {
        "pattern": r"PermissionError: (.+)",
        "type": "permission_error",
        "fix": "suggest",
        "label": "পারমিশন এরর",
    },
    {
        "pattern": r"FileNotFoundError: (.+)",
        "type": "file_not_found",
        "fix": "suggest",
        "label": "ফাইল পাওয়া যায়নি",
    },
    {
        "pattern": r"ConnectionRefusedError",
        "type": "connection_error",
        "fix": "suggest",
        "label": "কানেকশন এরর",
    },
    {
        "pattern": r"RecursionError",
        "type": "recursion_error",
        "fix": "suggest",
        "label": "রিকার্সন এরর",
    },
    {
        "pattern": r"MemoryError",
        "type": "memory_error",
        "fix": "suggest",
        "label": "মেমোরি এরর",
    },
    {
        "pattern": r"TimeoutError",
        "type": "timeout_error",
        "fix": "suggest",
        "label": "টাইমআউট এরর",
    },
    {
        "pattern": r"JSONDecodeError",
        "type": "json_error",
        "fix": "suggest",
        "label": "JSON পার্স এরর",
    },
    {
        "pattern": r"KeyError: '(\w+)'",
        "type": "key_error",
        "fix": "suggest",
        "label": "কী এরর",
    },
    {
        "pattern": r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
        "type": "attribute_error",
        "fix": "suggest",
        "label": "অ্যাট্রিবিউট এরর",
    },
    {
        "pattern": r"TypeError: (.+)",
        "type": "type_error",
        "fix": "suggest",
        "label": "টাইপ এরর",
    },
    {
        "pattern": r"ValueError: (.+)",
        "type": "value_error",
        "fix": "suggest",
        "label": "ভ্যালু এরর",
    },
    {
        "pattern": r"ZeroDivisionError",
        "type": "zero_division",
        "fix": "suggest",
        "label": "শূন্য দিয়ে ভাগ এরর",
    },
    {
        "pattern": r"IndentationError: (.+)",
        "type": "indent_error",
        "fix": "suggest",
        "label": "ইনডেন্টেশন এরর",
    },
]

FIX_SUGGESTIONS = {
    "missing_module": (
        "🔧 **সমাধান:** মডিউলটি ইনস্টল নেই।\n"
        "➡️ `pip install {match}` কমান্ড চালান অথবা 'অটো ফিক্স' চাপুন।"
    ),
    "import_error": (
        "🔧 **সমাধান:** নাম ভুল বা ভার্সন মিসমেচ।\n"
        "➡️ ইম্পোর্ট স্টেটমেন্ট এবং প্যাকেজ ভার্সন চেক করুন।"
    ),
    "syntax_error": (
        "🔧 **সমাধান:** কোডে সিনট্যাক্স ভুল আছে।\n"
        "➡️ উল্লেখিত লাইনে ব্র্যাকেট, কোলন বা কোটেশন চেক করুন।"
    ),
    "permission_error": (
        "🔧 **সমাধান:** ফাইল/ফোল্ডার পারমিশন নেই।\n"
        "➡️ chmod বা ফাইল পাথ চেক করুন।"
    ),
    "file_not_found": (
        "🔧 **সমাধান:** উল্লেখিত ফাইল বিদ্যমান নেই।\n"
        "➡️ ফাইল পাথ এবং নাম সঠিক কিনা যাচাই করুন।"
    ),
    "connection_error": (
        "🔧 **সমাধান:** সার্ভারে সংযোগ করা যাচ্ছে না।\n"
        "➡️ হোস্ট/পোর্ট সঠিক কিনা এবং নেটওয়ার্ক চেক করুন।"
    ),
    "recursion_error": (
        "🔧 **সমাধান:** অসীম রিকার্সন লুপ।\n"
        "➡️ বেস কেস যোগ করুন বা sys.setrecursionlimit() ব্যবহার করুন।"
    ),
    "memory_error": (
        "🔧 **সমাধান:** মেমোরি শেষ হয়ে গেছে।\n"
        "➡️ বড় ডেটা জেনারেটর দিয়ে প্রসেস করুন বা RAM আপগ্রেড করুন।"
    ),
    "timeout_error": (
        "🔧 **সমাধান:** অপারেশন টাইমআউট।\n"
        "➡️ timeout মান বাড়ান বা async ব্যবহার করুন।"
    ),
    "json_error": (
        "🔧 **সমাধান:** JSON ফরম্যাট ভুল।\n"
        "➡️ JSON validator দিয়ে ডেটা চেক করুন।"
    ),
    "key_error": (
        "🔧 **সমাধান:** Dictionary-তে key নেই।\n"
        "➡️ `.get()` মেথড ব্যবহার করুন: `d.get('key', default)`"
    ),
    "attribute_error": (
        "🔧 **সমাধান:** অবজেক্টে এই attribute নেই।\n"
        "➡️ `hasattr()` দিয়ে চেক করুন বা ডকুমেন্টেশন দেখুন।"
    ),
    "type_error": (
        "🔧 **সমাধান:** ভুল ডেটা টাইপ ব্যবহার।\n"
        "➡️ `type()` বা `isinstance()` দিয়ে টাইপ চেক করুন।"
    ),
    "value_error": (
        "🔧 **সমাধান:** ভুল মান পাস করা হয়েছে।\n"
        "➡️ ইনপুট ভ্যালিডেশন যোগ করুন।"
    ),
    "zero_division": (
        "🔧 **সমাধান:** শূন্য দিয়ে ভাগ।\n"
        "➡️ ভাগ করার আগে `if divisor != 0:` চেক করুন।"
    ),
    "indent_error": (
        "🔧 **সমাধান:** ইনডেন্টেশন ভুল।\n"
        "➡️ ট্যাব এবং স্পেস মিক্স করবেন না। সবখানে ৪ স্পেস ব্যবহার করুন।"
    ),
}


# ══════════════════════════════════════════════════════════════
#  ERROR ANALYZER
# ══════════════════════════════════════════════════════════════

class AIErrorEngine:

    def analyze_log(self, log_content: str) -> str:
        """
        Analyze log content, detect errors, and provide fixes.
        """
        if not log_content.strip():
            return "✅ লগে কোনো এরর পাওয়া যায়নি।"

        detected = []
        auto_fixable = []

        for pattern_info in ERROR_PATTERNS:
            match = re.search(pattern_info["pattern"], log_content, re.IGNORECASE)
            if match:
                err_type = pattern_info["type"]
                label = pattern_info["label"]
                matched_val = match.group(1) if match.lastindex else ""
                suggestion = FIX_SUGGESTIONS.get(err_type, "সাধারণ ডিবাগিং করুন।")
                suggestion = suggestion.replace("{match}", matched_val)

                detected.append(f"🚨 **{label}**\n{suggestion}")

                if pattern_info["fix"] == "auto_install" and matched_val:
                    auto_fixable.append(matched_val)

        if not detected:
            # Check for general crash
            if "Traceback" in log_content or "Error" in log_content:
                return (
                    "⚠️ **এরর শনাক্ত হয়েছে** (নির্দিষ্ট টাইপ অজানা)\n\n"
                    "📋 সম্পূর্ণ Traceback পড়ুন এবং শেষ লাইনটি মনোযোগ দিন।"
                )
            return "✅ লগে কোনো পরিচিত এরর পাওয়া যায়নি।"

        result = ["🤖 **AI এরর বিশ্লেষণ**\n"]
        result.extend(detected)

        if auto_fixable:
            result.append(
                f"\n⚡ **অটো-ফিক্সযোগ্য মডিউল:** `{', '.join(auto_fixable)}`\n"
                "➡️ নিচের 'অটো ফিক্স' বাটনে চাপুন।"
            )

        return "\n\n".join(result)

    def auto_fix(self, log_content: str, script_path: str) -> Tuple[bool, str]:
        """
        Attempt to auto-fix detected issues (missing modules).
        """
        results = []
        fixed = False

        # Fix missing modules
        for pattern_info in ERROR_PATTERNS:
            if pattern_info["fix"] != "auto_install":
                continue
            for match in re.finditer(pattern_info["pattern"], log_content, re.IGNORECASE):
                module = match.group(1)
                package = PACKAGE_MAP.get(module, module)
                ok, msg = install_pip_packages([package], os.path.dirname(script_path))
                results.append(f"📦 `{package}`: {'✅' if ok else '❌'} {msg}")
                if ok:
                    fixed = True

        if not results:
            return False, "❌ অটো-ফিক্সযোগ্য কোনো সমস্যা পাওয়া যায়নি।"

        summary = "\n".join(results)
        if fixed:
            return True, f"🔧 **অটো ফিক্স সম্পন্ন:**\n\n{summary}"
        else:
            return False, f"❌ **অটো ফিক্স ব্যর্থ:**\n\n{summary}"

    def analyze_process_log(self, proc_id: int, user_id: int) -> str:
        proc = get_process_by_id(proc_id, user_id)
        if not proc:
            return "❌ প্রসেস পাওয়া যায়নি।"
        log_file = proc.get("log_file", "")
        if not log_file or not os.path.exists(log_file):
            return "📭 লগ ফাইল নেই।"
        with open(log_file, "r", errors="replace") as f:
            content = f.read()
        return self.analyze_log(content[-5000:])  # Last 5KB


# Global AI engine
ai_engine = AIErrorEngine()
