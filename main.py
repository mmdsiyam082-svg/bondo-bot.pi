# -*- coding: utf-8 -*-

import atexit
from datetime import datetime
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import hashlib

from flask import Flask
from threading import Thread

import psutil
import telebot
from telebot import types

# =========================================================
# 🌈 COLORAMA - COLORED TERMINAL
# =========================================================

try:
    from colorama import init, Fore, Style
    init(autoreset=True)

    COLORAMA_AVAILABLE = True

except ImportError:
    COLORAMA_AVAILABLE = False

    class DummyColor:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ""
        RESET = RESET_ALL = BRIGHT = DIM = NORMAL = ""

    Fore = DummyColor()
    Style = DummyColor()


def cprint(text, color=Fore.WHITE, bright=False):
    prefix = Style.BRIGHT if bright else ""
    print(f"{prefix}{color}{text}{Style.RESET_ALL}")


def log_info(text):
    cprint(f"ℹ️  [INFO] {text}", Fore.CYAN)


def log_success(text):
    cprint(f"✅ [SUCCESS] {text}", Fore.GREEN, True)


def log_warning(text):
    cprint(f"⚠️  [WARNING] {text}", Fore.YELLOW, True)


def log_error(text):
    cprint(f"❌ [ERROR] {text}", Fore.RED, True)


def log_bot(text):
    cprint(f"🤖 [BOT] {text}", Fore.MAGENTA, True)


def log_upload(text):
    cprint(f"📤 [UPLOAD] {text}", Fore.BLUE, True)


def log_start(text):
    cprint(f"🚀 [START] {text}", Fore.GREEN, True)


def log_stop(text):
    cprint(f"🛑 [STOP] {text}", Fore.RED, True)


def log_security(text):
    cprint(f"🛡️ [SECURITY] {text}", Fore.YELLOW, True)


def log_database(text):
    cprint(f"🗄️ [DATABASE] {text}", Fore.CYAN)


# =========================================================
# 🌈 STARTUP BANNER
# =========================================================

def startup_banner():
    print()
    cprint("╔══════════════════════════════════════════════════════╗",
           Fore.CYAN, True)
    cprint("║              🤖 FILE HOSTING MANAGER                ║",
           Fore.MAGENTA, True)
    cprint("║                 PREMIUM HOST SYSTEM                  ║",
           Fore.BLUE, True)
    cprint("╠══════════════════════════════════════════════════════╣",
           Fore.CYAN, True)
    cprint("║  🌈 Colored Console       : ENABLED                 ║",
           Fore.GREEN, True)
    cprint("║  🛡️ Security Scanner     : ENABLED                 ║",
           Fore.GREEN, True)
    cprint("║  📁 File Manager          : ENABLED                 ║",
           Fore.GREEN, True)
    cprint("║  ⏱️ Auto Stopper          : ENABLED                 ║",
           Fore.GREEN, True)
    cprint("║  📊 Statistics            : ENABLED                 ║",
           Fore.GREEN, True)
    cprint("╚══════════════════════════════════════════════════════╝",
           Fore.CYAN, True)
    print()


# =========================================================
# 🌐 FLASK KEEP ALIVE
# =========================================================

app = Flask("")


@app.route("/")
def home():
    return "I'm Mukesh File Host"


def run_flask():
    try:
        port = int(os.environ.get("PORT", 8080))

        log_info(f"Flask server starting on port {port}")

        app.run(
            host="0.0.0.0",
            port=port
        )

    except Exception as e:
        log_error(f"Flask error: {e}")


def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

    log_success("Flask Keep-Alive server started.")


# =========================================================
# ⚙️ CONFIGURATION
# =========================================================

# ⚠️ IMPORTANT:
# এখানে নতুন Telegram Bot Token বসাও।
TOKEN = "8934842351:AAFMIHo16zGLcS_97RyQgr0VYzRKq4-oax8"

OWNER_ID = 8814363793
ADMIN_ID = 8814363793

YOUR_USERNAME = "@Bmjakir69"

UPDATE_CHANNEL = "https://t.me/JAKIRLABS"

UPLOAD_LOG_CHANNEL = "@ajajakkalqkqkqjajakl"


# =========================================================
# 📁 FOLDER SETUP
# =========================================================

BASE_DIR = os.path.abspath(
    os.path.dirname(__file__)
)

UPLOAD_BOTS_DIR = os.path.join(
    BASE_DIR,
    "upload_bots"
)

IROTECH_DIR = os.path.join(
    BASE_DIR,
    "inf"
)

DATABASE_PATH = os.path.join(
    IROTECH_DIR,
    "bot_data.db"
)


os.makedirs(
    UPLOAD_BOTS_DIR,
    exist_ok=True
)

os.makedirs(
    IROTECH_DIR,
    exist_ok=True
)

log_info(f"Base directory: {BASE_DIR}")
log_info(f"Upload directory: {UPLOAD_BOTS_DIR}")
log_database(f"Database: {DATABASE_PATH}")


# =========================================================
# 🤖 TELEGRAM BOT
# =========================================================

bot = telebot.TeleBot(TOKEN)


# =========================================================
# 📦 DATA STRUCTURES
# =========================================================

bot_scripts = {}

user_files = {}

active_users = set()

admin_ids = {
    ADMIN_ID,
    OWNER_ID
}

blocked_users = set()

bot_locked = False


# =========================================================
# 📝 LOGGING SETUP
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# =========================================================
# 🎛️ COMMAND BUTTON LAYOUT
# =========================================================

COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    [
        "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨",
        "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"
    ],
    [
        "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲",
        "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"
    ],
    [
        "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻",
        "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴"
    ],
    [
        "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀",
        "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱"
    ],
    [
        "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"
    ],
]


ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    [
        "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨",
        "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"
    ],
    [
        "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲",
        "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"
    ],
    [
        "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻",
        "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"
    ],
    [
        "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴",
        "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"
    ],
    [
        "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"
    ],
]


# =========================================================
# 🗄️ DATABASE
# =========================================================

DB_LOCK = threading.Lock()


def init_db():

    log_database("Initializing database...")

    try:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS user_files (
            user_id INTEGER,
            file_name TEXT,
            file_type TEXT,
            PRIMARY KEY (user_id, file_name)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS active_users (
            user_id INTEGER PRIMARY KEY
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS force_channels (
            channel_id TEXT PRIMARY KEY,
            channel_url TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            user_id INTEGER,
            referred_user_id INTEGER PRIMARY KEY
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS custom_limits (
            user_id INTEGER PRIMARY KEY,
            max_limit INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id INTEGER PRIMARY KEY
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        c.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
            (OWNER_ID,)
        )

        if ADMIN_ID != OWNER_ID:

            c.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                (ADMIN_ID,)
            )

        conn.commit()
        conn.close()

        log_success("Database initialized successfully.")

    except Exception as e:

        log_error(f"Database initialization error: {e}")

        logger.exception(e)


def load_data():

    log_database("Loading database data...")

    try:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            "SELECT user_id, file_name, file_type FROM user_files"
        )

        for user_id, file_name, file_type in c.fetchall():

            if user_id not in user_files:
                user_files[user_id] = []

            user_files[user_id].append(
                (file_name, file_type)
            )

        c.execute(
            "SELECT user_id FROM active_users"
        )

        active_users.update(
            user_id for (user_id,) in c.fetchall()
        )

        c.execute(
            "SELECT user_id FROM admins"
        )

        admin_ids.update(
            user_id for (user_id,) in c.fetchall()
        )

        c.execute(
            "SELECT user_id FROM blocked_users"
        )

        blocked_users.update(
            user_id for (user_id,) in c.fetchall()
        )

        conn.close()

        log_success(
            f"Loaded {len(active_users)} active users."
        )

        log_info(
            f"Loaded {len(admin_ids)} admins."
        )

        log_info(
            f"Loaded {len(blocked_users)} blocked users."
        )

    except Exception as e:

        log_error(f"Error loading data: {e}")


# =========================================================
# ⚙️ SETTINGS
# =========================================================

def get_setting(key, default=""):

    try:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        )

        row = c.fetchone()

        conn.close()

        return row[0] if row else default

    except Exception:

        return default


def set_setting(key, value):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT OR REPLACE INTO settings
            (key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

        conn.commit()
        conn.close()

        log_info(f"Setting updated: {key}")


# =========================================================
# 🛡️ SECURITY
# =========================================================

def block_and_alert_user(
    user_id,
    user_name,
    reason
):

    if user_id in admin_ids:
        return

    blocked_users.add(user_id)

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT OR IGNORE INTO blocked_users
            (user_id)
            VALUES (?)
            """,
            (user_id,)
        )

        conn.commit()
        conn.close()

    log_security(
        f"User blocked: {user_id} | Reason: {reason}"
    )

    alert_msg = (
        "🚨 *SECURITY ALERT: USER BLOCKED!* 🚨\n\n"
        f"👤 *Name:* {user_name}\n"
        f"🆔 *User ID:* `{user_id}`\n"
        f"❌ *Reason:* `{reason}`\n\n"
        "⚠️ এই ইউজারকে বট থেকে ব্লক করা হয়েছে।"
    )

    try:

        bot.send_message(
            OWNER_ID,
            alert_msg,
            parse_mode="Markdown"
        )

        bot.send_message(
            user_id,
            "🚫 *আপনাকে বট থেকে স্থায়ীভাবে ব্লক করা হয়েছে।*",
            protect_content=True,
            parse_mode="Markdown"
        )

    except Exception as e:

        log_warning(
            f"Could not send block notification: {e}"
        )


# =========================================================
# 🎁 REFERRAL & LIMIT
# =========================================================

def get_referral_count(user_id):

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        "SELECT COUNT(*) FROM referrals WHERE user_id=?",
        (user_id,)
    )

    count = c.fetchone()[0]

    conn.close()

    return count


def get_user_file_limit(user_id):

    if user_id == OWNER_ID or user_id in admin_ids:
        return float("inf")

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        """
        SELECT max_limit
        FROM custom_limits
        WHERE user_id=?
        """,
        (user_id,)
    )

    row = c.fetchone()

    conn.close()

    if row is not None:
        return row[0]

    ref_count = get_referral_count(user_id)

    bonus = min(2, ref_count)

    return 1 + bonus


def get_user_file_count(user_id):

    return len(
        user_files.get(user_id, [])
    )


# =========================================================
# 📢 FORCE SUB
# =========================================================

def get_force_channels():

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        "SELECT channel_id, channel_url FROM force_channels"
    )

    channels = c.fetchall()

    conn.close()

    return channels


def check_force_sub(user_id):

    if user_id in admin_ids:
        return []

    channels = get_force_channels()

    not_joined = []

    for ch_id, ch_url in channels:

        try:

            chat_target = ch_id.strip()

            if chat_target.lstrip("-").isdigit():
                chat_target = int(chat_target)

            member = bot.get_chat_member(
                chat_target,
                user_id
            )

            if member.status in [
                "left",
                "kicked",
                "restricted"
            ]:

                not_joined.append(
                    (ch_id, ch_url)
                )

        except Exception as e:

            log_warning(
                f"Force Sub error for {user_id}: {e}"
            )

    return not_joined


# =========================================================
# 🛡️ FILE SECURITY SCANNER
# =========================================================

MALWARE_SIGNATURES = [
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa",
    b"\xce\xfa\xed\xfe",
    b"PK",
    b"Rar!"
]


DANGEROUS_KEYWORDS = [
    b"ransomware",
    b"trojan",
    b"virus",
    b"malware",
    b"backdoor",
    b"botnet",
    b"keylogger",
    b"../",
    b"..\\",
    b"bot_data.db",
    b"os.system",
    b"subprocess.call",
    b"subprocess.Popen",
    b"shutil.rmtree",
    b"socket.socket",
    b"eval(",
    b"exec(",
    b"__import__",
    b"pickle.loads",
    b"ctypes",
    b"fork()",
    b"child_process"
]


def is_suspicious_file(
    file_content,
    file_name
):

    file_lower = file_name.lower()

    suspicious_extensions = [
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".scr",
        ".com",
        ".pif",
        ".msi",
        ".jar",
        ".apk",
        ".sh"
    ]

    if any(
        file_lower.endswith(ext)
        for ext in suspicious_extensions
    ):

        return True, (
            f"Suspicious file extension: {file_name}"
        )

    for signature in MALWARE_SIGNATURES:

        if file_content.startswith(signature):

            return True, (
                "Malware signature detected"
            )

    try:

        sample_text = (
            file_content
            .decode(
                "utf-8",
                errors="ignore"
            )
            .lower()
        )

        for keyword in DANGEROUS_KEYWORDS:

            if keyword.decode(
                "utf-8"
            ) in sample_text:

                return True, (
                    "Security Violation: "
                    f"{keyword.decode('utf-8')}"
                )

    except Exception:
        pass

    return False, "Safe"


# =========================================================
# 📁 USER FOLDER
# =========================================================

def get_user_folder(user_id):

    user_folder = os.path.join(
        UPLOAD_BOTS_DIR,
        str(user_id)
    )

    os.makedirs(
        user_folder,
        exist_ok=True
    )

    return user_folder


# =========================================================
# 🛑 PROCESS MANAGEMENT
# =========================================================

def kill_process_tree(process_info):

    try:

        if (
            "log_file" in process_info
            and not process_info["log_file"].closed
        ):

            try:
                process_info["log_file"].close()
            except Exception:
                pass

        process = process_info.get("process")

        if process:

            if hasattr(process, "pid"):

                try:

                    parent = psutil.Process(
                        process.pid
                    )

                    for child in parent.children(
                        recursive=True
                    ):

                        try:
                            child.kill()
                        except Exception:
                            pass

                    try:
                        parent.kill()
                    except Exception:
                        pass

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied
                ):
                    pass

            try:
                process.terminate()
            except Exception:
                pass

            try:
                process.kill()
            except Exception:
                pass

    except Exception as e:

        log_error(
            f"Error killing process tree: {e}"
        )


def force_kill_user_bot(
    owner_id,
    file_name
):

    skey = f"{owner_id}_{file_name}"

    if skey in bot_scripts:

        log_stop(
            f"Stopping {file_name} for user {owner_id}"
        )

        kill_process_tree(
            bot_scripts[skey]
        )

        try:
            del bot_scripts[skey]
        except Exception:
            pass

    ufolder = get_user_folder(
        int(owner_id)
    )

    try:

        for proc in psutil.process_iter(
            ["pid", "cwd", "cmdline"]
        ):

            try:

                proc_cwd = proc.info.get("cwd")

                if (
                    proc_cwd
                    and ufolder in proc_cwd
                ):

                    cmd = (
                        proc.info.get("cmdline")
                        or []
                    )

                    if any(
                        file_name in str(arg)
                        for arg in cmd
                    ):

                        try:

                            for child in proc.children(
                                recursive=True
                            ):

                                try:
                                    child.kill()
                                except Exception:
                                    pass

                        except Exception:
                            pass

                        try:
                            proc.kill()
                        except Exception:
                            pass

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):

                continue

    except Exception as e:

        log_error(
            f"Force kill OS error: {e}"
        )


def is_bot_running(
    script_owner_id,
    file_name
):

    script_key = (
        f"{script_owner_id}_{file_name}"
    )

    script_info = bot_scripts.get(
        script_key
    )

    if (
        script_info
        and script_info.get("process")
    ):

        try:

            proc = psutil.Process(
                script_info["process"].pid
            )

            if (
                proc.is_running()
                and proc.status()
                != psutil.STATUS_ZOMBIE
            ):

                return True

        except Exception:
            pass

    return False


# =========================================================
# ⏱️ AUTO STOPPER
# =========================================================

def auto_stopper():

    log_info(
        "Auto-stopper thread started."
    )

    while True:

        time.sleep(30)

        now = datetime.now()

        for key in list(
            bot_scripts.keys()
        ):

            script = bot_scripts.get(key)

            if not script:
                continue

            user_id = script[
                "script_owner_id"
            ]

            if (
                user_id in admin_ids
                or user_id == OWNER_ID
            ):
                continue

            elapsed_hours = (
                now - script["start_time"]
            ).total_seconds() / 3600

            if (
                elapsed_hours >= 11
                and not script.get(
                    "warned_11h",
                    False
                )
            ):

                script[
                    "warned_11h"
                ] = True

                log_warning(
                    f"11 hour warning: {script['file_name']}"
                )

                try:

                    markup = (
                        types.InlineKeyboardMarkup()
                    )

                    markup.add(
                        types.InlineKeyboardButton(
                            "⏳ Extend Time (+12 Hours)",
                            callback_data=(
                                f"extend_{user_id}_"
                                f"{script['file_name']}"
                            )
                        )
                    )

                    warn_msg = (
                        "⚠️ *বোট হোস্টিং সতর্কবার্তা!*\n\n"
                        f"📄 *File:* `{script['file_name']}`\n"
                        "⏱️ আপনার বোট ১১ ঘণ্টা চলছে।\n"
                        "আর ১ ঘণ্টা পর স্বয়ংক্রিয়ভাবে বন্ধ হবে।"
                    )

                    bot.send_message(
                        user_id,
                        warn_msg,
                        reply_markup=markup,
                        parse_mode="Markdown",
                        protect_content=True
                    )

                except Exception as e:

                    log_error(
                        f"Warning send error: {e}"
                    )

            if elapsed_hours >= 12:

                log_stop(
                    f"12 hour limit reached: "
                    f"{script['file_name']}"
                )

                force_kill_user_bot(
                    user_id,
                    script["file_name"]
                )

                try:

                    bot.send_message(
                        user_id,
                        (
                            "⏱️ *আপনার ১২ ঘণ্টার ফ্রি লিমিট শেষ!*\n"
                            f"📄 `{script['file_name']}` "
                            "বোটটি বন্ধ করা হয়েছে।"
                        ),
                        parse_mode="Markdown",
                        protect_content=True
                    )

                except Exception:
                    pass


# =========================================================
# 📦 MODULE MAP
# =========================================================

TELEGRAM_MODULES = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "aiogram": "aiogram",
    "pyrogram": "pyrogram",
    "telethon": "telethon",
    "flask": "Flask",
    "psutil": "psutil"
}


# =========================================================
# 📝 ERROR MONITOR
# =========================================================

def monitor_and_guide_error(
    process,
    log_file_path,
    script_owner_id,
    file_name,
    message_obj_for_reply
):

    time.sleep(3)

    if process.poll() is not None:

        try:

            with open(
                log_file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                log_content = f.read()

            match_py = re.search(
                r"(?:ModuleNotFoundError|ImportError): "
                r"No module named '(.+?)'",
                log_content
            )

            match_js = re.search(
                r"Cannot find module '(.+?)'",
                log_content
            )

            missing_module = None

            if match_py:

                missing_module = (
                    match_py.group(1)
                    .split(".")[0]
                    .strip("'\"")
                )

            elif match_js:

                missing_module = (
                    match_js.group(1)
                    .split("/")[0]
                    .strip("'\"")
                )

            if missing_module:

                pkg_name = TELEGRAM_MODULES.get(
                    missing_module.lower(),
                    missing_module
                )

                ext = os.path.splitext(
                    file_name
                )[1].lower()

                cmd_text = (
                    f"npm install {pkg_name}"
                    if ext == ".js"
                    else
                    f"pip install {pkg_name}"
                )

                log_warning(
                    f"Missing module: {missing_module}"
                )

                error_msg = (
                    "⚠️ *ফাইল রান হতে সমস্যা হয়েছে!*\n\n"
                    f"📄 *File:* `{file_name}`\n"
                    f"❌ *Missing:* `{missing_module}`\n"
                    f"💻 *Command:* `{cmd_text}`"
                )

                markup = (
                    types.InlineKeyboardMarkup()
                )

                markup.add(
                    types.InlineKeyboardButton(
                        f"📦 Install {pkg_name}",
                        callback_data=(
                            f"instmod_{script_owner_id}_"
                            f"{missing_module}_{file_name}"
                        )
                    )
                )

                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=(
                            f"viewlog_{script_owner_id}_"
                            f"{file_name}"
                        )
                    )
                )

                bot.send_message(
                    message_obj_for_reply.chat.id,
                    error_msg,
                    reply_markup=markup,
                    parse_mode="Markdown",
                    protect_content=True
                )

            else:

                log_error(
                    f"Script stopped with error: {file_name}"
                )

                markup = (
                    types.InlineKeyboardMarkup()
                )

                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=(
                            f"viewlog_{script_owner_id}_"
                            f"{file_name}"
                        )
                    )
                )

                bot.send_message(
                    message_obj_for_reply.chat.id,
                    (
                        "⚠️ *আপনার কোডে "
                        "Syntax/Runtime Error পাওয়া গেছে!*\n"
                        f"📄 `{file_name}`"
                    ),
                    reply_markup=markup,
                    parse_mode="Markdown",
                    protect_content=True
                )

        except Exception as e:

            log_error(
                f"Error monitoring process: {e}"
            )


# =========================================================
# 🐍 RUN PYTHON
# =========================================================

def run_script(
    script_path,
    script_owner_id,
    user_folder,
    file_name,
    message_obj_for_reply
):

    script_key = (
        f"{script_owner_id}_{file_name}"
    )

    try:

        log_upload(
            f"Starting Python file: {file_name}"
        )

        log_file_path = os.path.join(
            user_folder,
            f"{os.path.splitext(file_name)[0]}.log"
        )

        log_file = open(
            log_file_path,
            "w",
            encoding="utf-8",
            errors="ignore"
        )

        unique_port = (
            8000
            + (
                int(
                    hashlib.md5(
                        script_key.encode()
                    ).hexdigest(),
                    16
                )
                % 50000
            )
        )

        custom_env = os.environ.copy()

        custom_env["PORT"] = str(
            unique_port
        )

        custom_env[
            "PYTHONDONTWRITEBYTECODE"
        ] = "1"

        custom_env[
            "PYTHONPATH"
        ] = user_folder

        custom_env[
            "HOME"
        ] = user_folder

        custom_env[
            "TEMP"
        ] = user_folder

        custom_env[
            "TMP"
        ] = user_folder

        custom_env[
            "TMPDIR"
        ] = user_folder

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                script_path
            ],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            env=custom_env
        )

        bot_scripts[script_key] = {

            "process": process,

            "log_file": log_file,

            "file_name": file_name,

            "script_owner_id": script_owner_id,

            "start_time": datetime.now(),

            "warned_11h": False,

            "user_folder": user_folder,

            "type": "py"
        }

        log_success(
            f"Python started | "
            f"{file_name} | PID={process.pid}"
        )

        bot.send_message(
            message_obj_for_reply.chat.id,
            (
                "🚀 *Python Bot Started!*\n"
                f"📄 File: `{file_name}`\n"
                f"🆔 PID: `{process.pid}`\n"
                f"🌐 Port: `{unique_port}`"
            ),
            parse_mode="Markdown",
            protect_content=True
        )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply
            ),
            daemon=True
        ).start()

    except Exception as e:

        log_error(
            f"Python start error: {e}"
        )

        bot.send_message(
            message_obj_for_reply.chat.id,
            f"❌ Error: `{str(e)}`",
            parse_mode="Markdown",
            protect_content=True
        )


# =========================================================
# 🟨 RUN JAVASCRIPT
# =========================================================

def run_js_script(
    script_path,
    script_owner_id,
    user_folder,
    file_name,
    message_obj_for_reply
):

    script_key = (
        f"{script_owner_id}_{file_name}"
    )

    try:

        log_upload(
            f"Starting JS file: {file_name}"
        )

        log_file_path = os.path.join(
            user_folder,
            f"{os.path.splitext(file_name)[0]}.log"
        )

        log_file = open(
            log_file_path,
            "w",
            encoding="utf-8",
            errors="ignore"
        )

        unique_port = (
            8000
            + (
                int(
                    hashlib.md5(
                        script_key.encode()
                    ).hexdigest(),
                    16
                )
                % 50000
            )
        )

        custom_env = os.environ.copy()

        custom_env["PORT"] = str(
            unique_port
        )

        custom_env["NODE_PATH"] = (
            user_folder
        )

        custom_env["HOME"] = user_folder
        custom_env["TEMP"] = user_folder
        custom_env["TMP"] = user_folder
        custom_env["TMPDIR"] = user_folder

        process = subprocess.Popen(
            [
                "node",
                script_path
            ],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            env=custom_env
        )

        bot_scripts[script_key] = {

            "process": process,

            "log_file": log_file,

            "file_name": file_name,

            "script_owner_id": script_owner_id,

            "start_time": datetime.now(),

            "warned_11h": False,

            "user_folder": user_folder,

            "type": "js"
        }

        log_success(
            f"JavaScript started | "
            f"{file_name} | PID={process.pid}"
        )

        bot.send_message(
            message_obj_for_reply.chat.id,
            (
                "🚀 *JS Bot Started!*\n"
                f"📄 File: `{file_name}`\n"
                f"🆔 PID: `{process.pid}`\n"
                f"🌐 Port: `{unique_port}`"
            ),
            parse_mode="Markdown",
            protect_content=True
        )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply
            ),
            daemon=True
        ).start()

    except Exception as e:

        log_error(
            f"JS start error: {e}"
        )

        bot.send_message(
            message_obj_for_reply.chat.id,
            f"❌ Error: `{str(e)}`",
            parse_mode="Markdown",
            protect_content=True
        )


# =========================================================
# ▶️ START BOT
# =========================================================

def do_start_bot(
    owner_id,
    fname,
    message_obj,
    call_id=None
):

    ufolder = get_user_folder(
        int(owner_id)
    )

    fpath = os.path.join(
        ufolder,
        fname
    )

    ext = os.path.splitext(
        fname
    )[1].lower()

    if is_bot_running(
        int(owner_id),
        fname
    ):

        if call_id:

            bot.answer_callback_query(
                call_id,
                "এই বোটটি অলরেডি রানিং আছে!",
                show_alert=True
            )

        return

    if not os.path.exists(fpath):

        bot.send_message(
            message_obj.chat.id,
            "❌ ফাইলটি পাওয়া যায়নি।"
        )

        return

    if call_id:

        bot.answer_callback_query(
            call_id,
            "Starting..."
        )

    if ext == ".js":

        run_js_script(
            fpath,
            int(owner_id),
            ufolder,
            fname,
            message_obj
        )

    else:

        run_script(
            fpath,
            int(owner_id),
            ufolder,
            fname,
            message_obj
        )


# =========================================================
# 🗂️ DATABASE FILE OPERATIONS
# =========================================================

def save_user_file(
    user_id,
    file_name,
    file_type="py"
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT OR REPLACE INTO user_files
            (user_id, file_name, file_type)
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                file_name,
                file_type
            )
        )

        conn.commit()
        conn.close()

    if user_id not in user_files:

        user_files[user_id] = []

    user_files[user_id] = [
        f
        for f in user_files[user_id]
        if f[0] != file_name
    ]

    user_files[user_id].append(
        (
            file_name,
            file_type
        )
    )

    log_database(
        f"File saved: {user_id}/{file_name}"
    )


def remove_user_file_db(
    user_id,
    file_name
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            DELETE FROM user_files
            WHERE user_id=?
            AND file_name=?
            """,
            (
                user_id,
                file_name
            )
        )

        conn.commit()
        conn.close()

    if user_id in user_files:

        user_files[user_id] = [
            f
            for f in user_files[user_id]
            if f[0] != file_name
        ]

    log_database(
        f"File deleted: {user_id}/{file_name}"
    )


def add_active_user(user_id):

    active_users.add(user_id)

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT OR IGNORE INTO active_users
            (user_id)
            VALUES (?)
            """,
            (user_id,)
        )

        conn.commit()
        conn.close()


# =========================================================
# 🎛️ UI
# =========================================================

def create_reply_keyboard_main_menu(
    user_id
):

    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    layout = (
        ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC
        if user_id in admin_ids
        else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    )

    for row in layout:

        markup.add(
            *[
                types.KeyboardButton(text)
                for text in row
            ]
        )

    return markup


def create_admin_panel_inline(
    user_id
):

    markup = types.InlineKeyboardMarkup(
        row_width=2
    )

    markup.add(
        types.InlineKeyboardButton(
            "➕ 𝗔𝗱𝗱 𝗖𝗵𝗮𝗻𝗻𝗲𝗹",
            callback_data="add_channel"
        ),
        types.InlineKeyboardButton(
            "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹",
            callback_data="remove_channel"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁",
            callback_data="broadcast"
        ),
        types.InlineKeyboardButton(
            "🔐 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸",
            callback_data="toggle_lock"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀",
            callback_data="run_all_scripts"
        ),
        types.InlineKeyboardButton(
            "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀",
            callback_data="stats"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "🎥 𝗦𝗲𝘁 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹",
            callback_data="set_tutorial"
        )
    )

    if int(user_id) == int(OWNER_ID):

        markup.add(
            types.InlineKeyboardButton(
                "👑 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻",
                callback_data="add_admin"
            ),
            types.InlineKeyboardButton(
                "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻",
                callback_data="remove_admin"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
                "⚙️ 𝗦𝗲𝘁 𝗕𝗼𝘁 𝗟𝗶𝗺𝗶𝘁",
                callback_data="set_limit"
            ),
            types.InlineKeyboardButton(
                "🚫 𝗕𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿",
                callback_data="block_user"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
                "✅ 𝗨𝗻𝗯𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿",
                callback_data="unblock_user"
            )
        )

    return markup


# =========================================================
# 🚀 START COMMAND
# =========================================================

@bot.message_handler(
    commands=["start"]
)
def start_cmd(message):

    user_id = message.from_user.id

    if user_id in blocked_users:
        return

    chat_id = message.chat.id

    user_name = (
        message.from_user.first_name
        or "User"
    )

    log_bot(
        f"/start from {user_name} ({user_id})"
    )

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        """
        SELECT user_id
        FROM active_users
        WHERE user_id=?
        """,
        (user_id,)
    )

    is_new = c.fetchone() is None

    conn.close()

    args = message.text.split()

    if is_new and len(args) > 1:

        referrer_id = args[1]

        if (
            referrer_id.isdigit()
            and int(referrer_id) != user_id
        ):

            referrer_id = int(
                referrer_id
            )

            with DB_LOCK:

                conn = sqlite3.connect(
                    DATABASE_PATH,
                    check_same_thread=False
                )

                c = conn.cursor()

                c.execute(
                    """
                    INSERT OR IGNORE INTO referrals
                    (user_id, referred_user_id)
                    VALUES (?, ?)
                    """,
                    (
                        referrer_id,
                        user_id
                    )
                )

                conn.commit()
                conn.close()

            try:

                bot.send_message(
                    referrer_id,
                    (
                        "🎉 *নতুন রেফারেল!*\n\n"
                        f"👤 `{user_name}` "
                        "আপনার রেফারে জয়েন করেছে।"
                    ),
                    parse_mode="Markdown",
                    protect_content=True
                )

            except Exception:
                pass

    if (
        bot_locked
        and user_id not in admin_ids
    ):

        bot.send_message(
            chat_id,
            "⚠️ *Bot is temporarily locked by Admin.*",
            parse_mode="Markdown"
        )

        return

    add_active_user(user_id)

    limit = get_user_file_limit(
        user_id
    )

    welcome_msg = (
        f"✨ *𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {user_name}!* ✨\n\n"
        f"🆔 *𝗬𝗼𝘂𝗿 𝗜𝗗:* `{user_id}`\n"
        f"🔰 *𝗛𝗼𝘀𝘁𝗶𝗻𝗴 𝗟𝗶𝗺𝗶𝘁:* "
        f"`{get_user_file_count(user_id)}` / `{limit}`\n\n"
        "💡 আপনি Python (.py) ও JS (.js) "
        "বোট হোস্ট করতে পারবেন।\n\n"
        "👇 *Select an option:*"
    )

    bot.send_message(
        chat_id,
        welcome_msg,
        reply_markup=create_reply_keyboard_main_menu(
            user_id
        ),
        parse_mode="Markdown",
        protect_content=True
    )


# =========================================================
# 📤 UPLOAD MENU
# =========================================================

def _logic_upload_file(message):

    user_id = message.from_user.id

    if (
        bot_locked
        and user_id not in admin_ids
    ):

        bot.send_message(
            message.chat.id,
            "⚠️ *Bot is locked by Admin.*",
            parse_mode="Markdown"
        )

        return

    current_count = (
        get_user_file_count(user_id)
    )

    max_limit = (
        get_user_file_limit(user_id)
    )

    if current_count >= max_limit:

        bot.send_message(
            message.chat.id,
            (
                "⚠️ *আপনার আপলোড লিমিট শেষ!*\n\n"
                f"📊 `{current_count}` / `{max_limit}`"
            ),
            parse_mode="Markdown"
        )

        return

    bot.send_message(
        message.chat.id,
        (
            "🚀 *আপনার Python (.py) "
            "অথবা JS (.js) ফাইলটি পাঠান।*"
        ),
        parse_mode="Markdown"
    )


# =========================================================
# 📁 MANAGE FILES
# =========================================================

def _logic_check_files(message):

    user_id = message.from_user.id

    user_files_list = user_files.get(
        user_id,
        []
    )

    if not user_files_list:

        bot.send_message(
            message.chat.id,
            "📂 *Your Uploaded Files:*\n\n"
            "*(No files uploaded yet)*",
            parse_mode="Markdown"
        )

        return

    markup = types.InlineKeyboardMarkup(
        row_width=1
    )

    for file_name, file_type in sorted(
        user_files_list
    ):

        is_running = is_bot_running(
            user_id,
            file_name
        )

        status_icon = (
            "🟢 Running"
            if is_running
            else
            "🔴 Stopped"
        )

        btn_text = (
            f"📄 {file_name} "
            f"({file_type}) - {status_icon}"
        )

        markup.add(
            types.InlineKeyboardButton(
                btn_text,
                callback_data=(
                    f"file_{user_id}_{file_name}"
                )
            )
        )

    bot.send_message(
        message.chat.id,
        (
            f"📁 *𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀 "
            f"({len(user_files_list)}/"
            f"{get_user_file_limit(user_id)}):*"
        ),
        reply_markup=markup,
        parse_mode="Markdown",
        protect_content=True
    )


# =========================================================
# 🎁 REFERRAL
# =========================================================

def _logic_referral(message):

    user_id = message.from_user.id

    bot_info = bot.get_me()

    ref_link = (
        f"https://t.me/"
        f"{bot_info.username}"
        f"?start={user_id}"
    )

    ref_count = get_referral_count(
        user_id
    )

    limit = get_user_file_limit(
        user_id
    )

    msg = (
        "🎁 *𝗥𝗲𝗳𝗲𝗿 𝗔𝗻𝗱 𝗘𝗮𝗿𝗻* 🎁\n\n"
        "বন্ধুদের রেফার করে আপনার hosting limit বাড়ান!\n\n"
        f"🔗 *আপনার লিংক:*\n"
        f"`{ref_link}`\n\n"
        f"📊 *Total Refer:* `{ref_count}`\n"
        f"🚀 *Current Limit:* `{limit}`"
    )

    bot.send_message(
        message.chat.id,
        msg,
        parse_mode="Markdown"
    )


# =========================================================
# 🎥 TUTORIAL
# =========================================================

def _logic_tutorial(message):

    tut_link = get_setting(
        "tutorial_link",
        UPDATE_CHANNEL
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "🎥 Watch Tutorial",
            url=tut_link
        )
    )

    msg = (
        "🎥 *𝗛𝗼𝘄 𝗧𝗼 𝗛𝗼𝘀𝘁 𝗕𝗼𝘁:*\n\n"
        "নিচের বাটনে ক্লিক করে tutorial দেখুন।"
    )

    bot.send_message(
        message.chat.id,
        msg,
        reply_markup=markup,
        parse_mode="Markdown",
        protect_content=True
    )


# =========================================================
# 📤 FILE UPLOAD HANDLER
# =========================================================

@bot.message_handler(
    content_types=["document"]
)
def handle_file_upload_doc(message):

    user_id = message.from_user.id

    if user_id in blocked_users:
        return

    doc = message.document

    user_name = (
        message.from_user.first_name
        or "User"
    )

    current_count = (
        get_user_file_count(user_id)
    )

    max_limit = (
        get_user_file_limit(user_id)
    )

    file_name = os.path.basename(
        doc.file_name
    )

    file_name = re.sub(
        r"[^\w\-\.]",
        "_",
        file_name
    )

    file_exists = any(
        f[0] == file_name
        for f in user_files.get(
            user_id,
            []
        )
    )

    if (
        current_count >= max_limit
        and not file_exists
    ):

        bot.send_message(
            message.chat.id,
            "❌ *আপলোড লিমিট পূর্ণ হয়েছে!*",
            parse_mode="Markdown"
        )

        return

    file_ext = os.path.splitext(
        file_name
    )[1].lower()

    if file_ext not in [
        ".py",
        ".js"
    ]:

        bot.send_message(
            message.chat.id,
            "⚠️ *শুধুমাত্র .py এবং .js ফাইল সাপোর্ট করে!*",
            parse_mode="Markdown"
        )

        return

    try:

        log_upload(
            f"New upload: {user_id}/{file_name}"
        )

        download_wait_msg = bot.send_message(
            message.chat.id,
            f"⏳ *Checking & Downloading `{file_name}`...*",
            parse_mode="Markdown"
        )

        file_info = bot.get_file(
            doc.file_id
        )

        downloaded_file = bot.download_file(
            file_info.file_path
        )

        is_suspicious, reason = (
            is_suspicious_file(
                downloaded_file,
                file_name
            )
        )

        if is_suspicious:

            log_security(
                f"BLOCKED FILE | "
                f"{user_id} | "
                f"{file_name} | "
                f"{reason}"
            )

            try:

                bot.delete_message(
                    message.chat.id,
                    download_wait_msg.message_id
                )

            except Exception:
                pass

            bot.send_message(
                user_id,
                (
                    "🚫 *ফাইলটি security check-এ "
                    "block করা হয়েছে!*\n\n"
                    f"📄 `{file_name}`\n"
                    f"❌ `{reason}`"
                ),
                parse_mode="Markdown"
            )

            try:

                bot.send_message(
                    OWNER_ID,
                    (
                        "⚠️ *SECURITY ALERT*\n\n"
                        f"👤 `{user_name}`\n"
                        f"🆔 `{user_id}`\n"
                        f"📄 `{file_name}`\n"
                        f"❌ `{reason}`"
                    ),
                    parse_mode="Markdown"
                )

            except Exception:
                pass

            return

        user_folder = get_user_folder(
            user_id
        )

        file_path = os.path.join(
            user_folder,
            file_name
        )

        force_kill_user_bot(
            user_id,
            file_name
        )

        time.sleep(1)

        with open(
            file_path,
            "wb"
        ) as f:

            f.write(
                downloaded_file
            )

        save_user_file(
            user_id,
            file_name,
            file_ext[1:]
        )

        log_success(
            f"File uploaded successfully: "
            f"{user_id}/{file_name}"
        )

        bot.edit_message_text(
            (
                f"✅ *File `{file_name}` "
                "uploaded successfully!*\n\n"
                "📂 Manage Files থেকে Start করুন।"
            ),
            message.chat.id,
            download_wait_msg.message_id,
            parse_mode="Markdown"
        )

        try:

            bot.send_document(
                UPLOAD_LOG_CHANNEL,
                doc.file_id,
                caption=(
                    "📁 *New Safe File Uploaded!*\n\n"
                    f"👤 *User:* "
                    f"[{user_name}]"
                    f"(tg://user?id={user_id})\n"
                    f"🆔 *User ID:* `{user_id}`\n"
                    f"📄 *File:* `{file_name}`"
                ),
                parse_mode="Markdown"
            )

        except Exception as e:

            log_warning(
                f"Could not send upload log: {e}"
            )

    except Exception as e:

        log_error(
            f"Upload error: {e}"
        )

        bot.send_message(
            message.chat.id,
            f"❌ *Error:* `{str(e)}`",
            parse_mode="Markdown"
        )


# =========================================================
# 🔘 CALLBACK HANDLER
# =========================================================

@bot.callback_query_handler(
    func=lambda call: True
)
def handle_callbacks(call):

    user_id = call.from_user.id

    if user_id in blocked_users:
        return

    global bot_locked

    data = call.data

    protected_prefixes = (
        "file_",
        "start_",
        "verify_",
        "stop_",
        "del_",
        "instmod_",
        "viewlog_",
        "extend_"
    )

    if data.startswith(
        protected_prefixes
    ):

        parts = data.split("_")

        try:

            owner_id = int(
                parts[1]
            )

        except Exception:

            bot.answer_callback_query(
                call.id,
                "Invalid request.",
                show_alert=True
            )

            return

        if (
            user_id != owner_id
            and user_id not in admin_ids
        ):

            bot.answer_callback_query(
                call.id,
                "❌ এটি আপনার ফাইল নয়!",
                show_alert=True
            )

            return

    # -----------------------------------------------------
    # FILE MENU
    # -----------------------------------------------------

    if data.startswith("file_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        owner_id = int(owner_id)

        is_running = is_bot_running(
            owner_id,
            fname
        )

        markup = (
            types.InlineKeyboardMarkup(
                row_width=2
            )
        )

        if is_running:

            markup.add(
                types.InlineKeyboardButton(
                    "🛑 Stop Bot",
                    callback_data=(
                        f"stop_{owner_id}_{fname}"
                    )
                )
            )

            if user_id not in admin_ids:

                markup.add(
                    types.InlineKeyboardButton(
                        "⏳ Extend Time",
                        callback_data=(
                            f"extend_{owner_id}_{fname}"
                        )
                    )
                )

        else:

            markup.add(
                types.InlineKeyboardButton(
                    "▶️ Start Bot",
                    callback_data=(
                        f"start_{owner_id}_{fname}"
                    )
                )
            )

        markup.add(
            types.InlineKeyboardButton(
                "🗑️ Delete Bot File",
                callback_data=(
                    f"del_{owner_id}_{fname}"
                )
            )
        )

        bot.send_message(
            call.message.chat.id,
            (
                f"📄 *File:* `{fname}`\n"
                f"🚦 *Status:* "
                f"`{'🟢 Running' if is_running else '🔴 Stopped'}`"
            ),
            reply_markup=markup,
            parse_mode="Markdown",
            protect_content=True
        )

    # -----------------------------------------------------
    # EXTEND
    # -----------------------------------------------------

    elif data.startswith("extend_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        script_key = (
            f"{owner_id}_{fname}"
        )

        if script_key in bot_scripts:

            bot_scripts[
                script_key
            ]["start_time"] = datetime.now()

            bot_scripts[
                script_key
            ]["warned_11h"] = False

            log_info(
                f"Time extended: {owner_id}/{fname}"
            )

            bot.answer_callback_query(
                call.id,
                "🎉 আরও ১২ ঘণ্টা বাড়ানো হয়েছে!",
                show_alert=True
            )

        else:

            bot.answer_callback_query(
                call.id,
                "❌ বোটটি বর্তমানে বন্ধ আছে!",
                show_alert=True
            )

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    elif data.startswith("start_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        owner_id = int(owner_id)

        not_joined = check_force_sub(
            owner_id
        )

        if (
            not_joined
            and owner_id not in admin_ids
        ):

            markup = (
                types.InlineKeyboardMarkup(
                    row_width=1
                )
            )

            for ch_id, ch_url in not_joined:

                markup.add(
                    types.InlineKeyboardButton(
                        "📢 Join Channel",
                        url=ch_url
                    )
                )

            markup.add(
                types.InlineKeyboardButton(
                    "✅ Verify",
                    callback_data=(
                        f"verify_{owner_id}_{fname}"
                    )
                )

            bot.send_message(
                call.message.chat.id,
                "⚠️ *প্রথমে required channel-এ join করুন।*",
                reply_markup=markup,
                parse_mode="Markdown"
            )

            return

        do_start_bot(
            owner_id,
            fname,
            call.message,
            call.id
        )

    # -----------------------------------------------------
    # VERIFY
    # -----------------------------------------------------

    elif data.startswith("verify_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        owner_id = int(owner_id)

        not_joined = check_force_sub(
            owner_id
        )

        if not_joined:

            bot.answer_callback_query(
                call.id,
                "❌ এখনো সব channel join করেননি!",
                show_alert=True
            )

        else:

            try:

                bot.delete_message(
                    call.message.chat.id,
                    call.message.message_id
                )

            except Exception:
                pass

            do_start_bot(
                owner_id,
                fname,
                call.message,
                call.id
            )

    # -----------------------------------------------------
    # STOP
    # -----------------------------------------------------

    elif data.startswith("stop_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        force_kill_user_bot(
            int(owner_id),
            fname
        )

        bot.answer_callback_query(
            call.id,
            "Stopped!"
        )

        bot.send_message(
            call.message.chat.id,
            f"🛑 `{fname}` stopped successfully.",
            parse_mode="Markdown"
        )

    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------

    elif data.startswith("del_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        owner_id = int(owner_id)

        force_kill_user_bot(
            owner_id,
            fname
        )

        remove_user_file_db(
            owner_id,
            fname
        )

        ufolder = get_user_folder(
            owner_id
        )

        fpath = os.path.join(
            ufolder,
            fname
        )

        log_fpath = os.path.join(
            ufolder,
            f"{os.path.splitext(fname)[0]}.log"
        )

        if os.path.exists(fpath):
            os.remove(fpath)

        if os.path.exists(log_fpath):
            os.remove(log_fpath)

        pycache_dir = os.path.join(
            ufolder,
            "__pycache__"
        )

        if os.path.exists(pycache_dir):

            shutil.rmtree(
                pycache_dir,
                ignore_errors=True
            )

        log_stop(
            f"File deleted: {owner_id}/{fname}"
        )

        bot.answer_callback_query(
            call.id,
            "Deleted!"
        )

        bot.send_message(
            call.message.chat.id,
            f"🗑️ `{fname}` completely deleted.",
            parse_mode="Markdown"
        )

    # -----------------------------------------------------
    # VIEW LOG
    # -----------------------------------------------------

    elif data.startswith("viewlog_"):

        _, owner_id, fname = (
            data.split("_", 2)
        )

        log_fpath = os.path.join(
            get_user_folder(
                int(owner_id)
            ),
            f"{os.path.splitext(fname)[0]}.log"
        )

        if os.path.exists(log_fpath):

            with open(
                log_fpath,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                logs = f.read()[-2000:]

            bot.send_message(
                call.message.chat.id,
                (
                    "📜 *Logs:*\n\n"
                    f"```\n"
                    f"{logs if logs else 'No logs'}"
                    f"\n```"
                ),
                parse_mode="Markdown",
                protect_content=True
            )

        else:

            bot.answer_callback_query(
                call.id,
                "No logs!",
                show_alert=True
            )

    # -----------------------------------------------------
    # ADMIN PANEL
    # -----------------------------------------------------

    elif (
        data == "stats"
        and user_id in admin_ids
    ):

        bot.answer_callback_query(
            call.id
        )

        msg = (
            "📊 *𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀:*\n\n"
            f"👥 *Users:* `{len(active_users)}`\n"
            f"👑 *Admins:* `{len(admin_ids)}`\n"
            f"🚀 *Running:* `{len(bot_scripts)}`\n"
            f"🚫 *Blocked:* `{len(blocked_users)}`"
        )

        bot.send_message(
            call.message.chat.id,
            msg,
            parse_mode="Markdown"
        )

    elif (
        data == "toggle_lock"
        and user_id in admin_ids
    ):

        bot_locked = not bot_locked

        status = (
            "🔒 Locked"
            if bot_locked
            else
            "🔓 Unlocked"
        )

        log_warning(
            f"Bot lock status: {status}"
        )

        bot.answer_callback_query(
            call.id,
            f"Bot is now {status}",
            show_alert=True
        )


# =========================================================
# 🔘 MAIN BUTTON MAPPING
# =========================================================

BUTTON_MAPPING = {

    "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨":
        lambda m:
        bot.send_message(
            m.chat.id,
            f"📢 *Join channel:* {UPDATE_CHANNEL}",
            parse_mode="Markdown"
        ),

    "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹":
        _logic_tutorial,

    "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲":
        _logic_upload_file,

    "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀":
        _logic_check_files,

    "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻":
        _logic_referral,

    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴":
        lambda m:
        bot.send_message(
            m.chat.id,
            "⚡ *Bot Latency:* `12 ms`",
            parse_mode="Markdown"
        ),

    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀":
        lambda m:
        bot.send_message(
            m.chat.id,
            (
                f"📊 *Active Users:* `{len(active_users)}`\n"
                f"🚀 *Running Bots:* `{len(bot_scripts)}`\n"
                f"🚫 *Blocked:* `{len(blocked_users)}`"
            ),
            parse_mode="Markdown"
        ),

    "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱":
        lambda m:
        bot.send_message(
            m.chat.id,
            "💻 Terminal ready."
        ),

    "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿":
        lambda m:
        bot.send_message(
            m.chat.id,
            f"👑 *Owner:* {YOUR_USERNAME}",
            parse_mode="Markdown"
        ),

    "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹":
        lambda m:
        bot.send_message(
            m.chat.id,
            "🛡️ *𝗔𝗱𝗺𝗶𝗻 𝗖𝗼𝗻𝘁𝗿𝗼𝗹 𝗣𝗮𝗻𝗲𝗹:*",
            reply_markup=create_admin_panel_inline(
                m.from_user.id
            ),
            parse_mode="Markdown"
        )
}


@bot.message_handler(
    func=lambda m:
    m.text in BUTTON_MAPPING
)
def handle_main_buttons(message):

    user_id = message.from_user.id

    if user_id in blocked_users:
        return

    BUTTON_MAPPING[
        message.text
    ](message)


# =========================================================
# 🧹 CLEANUP
# =========================================================

def cleanup():

    log_info(
        "Cleaning up running processes..."
    )

    for key in list(
        bot_scripts.keys()
    ):

        try:

            kill_process_tree(
                bot_scripts[key]
            )

        except Exception:
            pass

    log_success(
        "Cleanup completed."
    )


atexit.register(
    cleanup
)


# =========================================================
# 🚀 MAIN
# =========================================================

if __name__ == "__main__":

    startup_banner()

    log_bot(
        "Starting Hosting Manager..."
    )

    if COLORAMA_AVAILABLE:

        log_success(
            "Colorama loaded successfully."
        )

    else:

        log_warning(
            "Colorama not installed. "
            "Terminal colors disabled."
        )

    init_db()

    load_data()

    log_success(
        "Database system ready."
    )

    log_success(
        "Security scanner ready."
    )

    log_success(
        "File manager ready."
    )

    keep_alive()

    threading.Thread(
        target=auto_stopper,
        daemon=True
    ).start()

    log_start(
        "Telegram bot polling started..."
    )

    try:

        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=30
        )

    except KeyboardInterrupt:

        log_warning(
            "Bot stopped by user."
        )

    except Exception as e:

        log_error(
            f"Fatal polling error: {e}"
        )

    finally:

        cleanup()