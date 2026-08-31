# -*- coding: utf-8 -*-
import atexit
import ast
from datetime import datetime, timedelta
from html import escape
import hashlib
import hmac
import io
import importlib.util
import json
import logging
import mimetypes
import os
import re
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from flask import Flask
from threading import Thread
import psutil
import requests
import telebot
from telebot import types

# --- Configurable Conversion Rate ---
USDT_BDT_RATE = 120.0  # 1 USDT = 120 BDT (প্রয়োজনে পরিবর্তন করতে পারেন)

def positive_int_env(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# --- Flask Keep Alive ---
app = Flask("")


@app.route("/")
def home():
    return "I'm Mukesh File Host"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")


# --- End Flask Keep Alive ---

# --- Configuration ---
# To change the bot from this file, replace only the value below with the
# complete token copied from BotFather. Do not add TELEGRAM_BOT_TOKEN= here.
BOT_TOKEN = "8634271135:AAFsHsHBYhK9j-Rnlmtc_ElJgT4MeSnOQwk"
TOKEN = BOT_TOKEN.strip()
OWNER_ID = 8814363793
ADMIN_ID = 8814363793
YOUR_USERNAME = "@tanjimsaykot"
UPDATE_CHANNEL = "https://t.me/rjonlinejobbd"

# --- Referral/Coin Configuration ---
# Defaults are intentionally configurable through normal environment variables.
REFERRAL_REWARD_COINS = positive_int_env("REFERRAL_REWARD_COINS", 10)
BOT_RUN_COST_COINS = positive_int_env("BOT_RUN_COST_COINS", 1)
COIN_RUN_DURATION_HOURS = positive_int_env("COIN_RUN_DURATION_HOURS", 24)
COIN_PACKAGE_COINS = positive_int_env("COIN_PACKAGE_COINS", 10)
COIN_PACKAGE_PRICE_BDT = 100.0
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ZIP_SCRIPTS = 20
MAX_EXPORT_ARCHIVE_BYTES = 49 * 1024 * 1024
PYTHON_DEPENDENCY_TIMEOUT_SECONDS = positive_int_env(
    "PYTHON_DEPENDENCY_TIMEOUT_SECONDS", 300
)
MAX_AUTO_DEPENDENCIES = positive_int_env("MAX_AUTO_DEPENDENCIES", 30)
SUPPORTED_UPLOAD_EXTENSIONS = {".py", ".js", ".json", ".db", ".zip"}
# Uploaded file records historically store the type without the leading dot
# ("py", "js", "json", "db"), while upload validation uses pathlib extensions
# (" .py", ".js", ...).  Keep both representations accepted so old records
# remain runnable and manageable.
RUNNABLE_FILE_EXTENSIONS = {".py", ".js", "py", "js"}
DATA_FILE_EXTENSIONS = {".json", ".db", "json", "db"}

# Folder setup - using absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data.db")

# File upload limits
# Uploaded code and data files belong to the user and must remain available
# together.  Plans still control how many runnable bots may run at once below,
# but they do not prevent a user from restoring a multi-file bot project.
FREE_USER_LIMIT = float("inf")
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float("inf")

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Validate the token before constructing TeleBot. Passing a placeholder such as
# "MISSING_TELEGRAM_BOT_TOKEN" to TeleBot causes the misleading error
# "Token must contain a colon" before the startup check below can run.
if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is empty. Replace PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE "
        "with the complete token copied from BotFather."
    )
if ":" not in TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is invalid. It must be the complete BotFather token "
        "in the format <bot_id>:<token>."
    )

# TeleBot can be constructed before the main guard so decorators remain available.
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
user_selected_plan = {}  # Temp state for upload flow
pending_code_replacements = {}
bot_username = None

# --- Malware Detection Configuration ---
MALWARE_SIGNATURES = [
    b"MZ",  # Windows executable
    b"\x7fELF",  # Linux executable
    b"\xfe\xed\xfa",  # Mach-O binary
    b"\xce\xfa\xed\xfe",  # Mach-O binary (reverse)
    b"PK",  # ZIP archive
    b"Rar!",  # RAR archive
]

ENCRYPTED_FILE_INDICATORS = [
    b"openssl",
    b"encrypted",
    b"cipher",
    b"AES",
    b"DES",
    b"RSA",
    b"GPG",
    b"PGP",
]

SUSPICIOUS_KEYWORDS = [
    b"ransomware",
    b"trojan",
    b"virus",
    b"malware",
    b"backdoor",
    b"exploit",
    b"payload",
    b"botnet",
    b"keylogger",
    b"rootkit",
]

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 𝗨𝗽𝗱𝗮𝘁𝗲𝘀", "👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲"],
    ["📤 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📂 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀", "🪙 𝗕𝘂𝘆 𝗖𝗼𝗶𝗻𝘀"],
    ["🔗 𝗥𝗲𝗳𝗲𝗿 & 𝗖𝗼𝗶𝗻𝘀", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿", "🆘 𝗛𝗲𝗹𝗽"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 𝗨𝗽𝗱𝗮𝘁𝗲𝘀", "👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲"],
    ["📤 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📂 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀", "🪙 𝗕𝘂𝘆 𝗖𝗼𝗶𝗻𝘀"],
    ["🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹", "🔗 𝗥𝗲𝗳𝗲𝗿 & 𝗖𝗼𝗶𝗻𝘀"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
    ["💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹", "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
    ["🆘 𝗛𝗲𝗹𝗽"],
]

# --- Database Setup ---
DB_LOCK = threading.Lock()


def init_db():
    """Initialize the database with required tables"""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, plan_name TEXT, expiry TEXT)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS plans
                     (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, file_limit INTEGER, price TEXT, duration INTEGER, buy_link TEXT)"""
        )

        # The original database used file_limit/buy_link for the old payment
        # flow. Keep those columns for existing installations, but add the
        # fields used by the configurable VIP plan system.
        existing_plan_columns = {
            row[1] for row in c.execute("PRAGMA table_info(plans)").fetchall()
        }
        if "max_bots" not in existing_plan_columns:
            c.execute("ALTER TABLE plans ADD COLUMN max_bots INTEGER")
        if "bkash_number" not in existing_plan_columns:
            c.execute("ALTER TABLE plans ADD COLUMN bkash_number TEXT")
        if "nagad_number" not in existing_plan_columns:
            c.execute("ALTER TABLE plans ADD COLUMN nagad_number TEXT")

        existing_subscription_columns = {
            row[1]
            for row in c.execute("PRAGMA table_info(subscriptions)").fetchall()
        }
        if "plan_id" not in existing_subscription_columns:
            c.execute("ALTER TABLE subscriptions ADD COLUMN plan_id INTEGER")
        if "max_bots" not in existing_subscription_columns:
            c.execute("ALTER TABLE subscriptions ADD COLUMN max_bots INTEGER")

        # 🆕 Table for tracking partial payments
        c.execute(
            """CREATE TABLE IF NOT EXISTS pending_payments
                     (user_id INTEGER, plan_id INTEGER, paid_amount REAL,
                      PRIMARY KEY (user_id, plan_id))"""
        )

        # 🆕 Table for tracking used TxIDs to prevent double spending
        c.execute(
            """CREATE TABLE IF NOT EXISTS used_txids
                     (tx_id TEXT PRIMARY KEY)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS payment_requests
                     (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      plan_id INTEGER NOT NULL,
                      method TEXT NOT NULL,
                      transaction_code TEXT NOT NULL,
                      amount REAL NOT NULL,
                      status TEXT NOT NULL DEFAULT 'pending',
                      created_at TEXT NOT NULL,
                      reviewed_at TEXT,
                      reviewed_by INTEGER)"""
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_payment_requests_status "
            "ON payment_requests(status)"
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_requests_tx_code "
            "ON payment_requests(transaction_code)"
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS coin_payment_requests
                     (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      method TEXT NOT NULL,
                      transaction_code TEXT NOT NULL,
                      amount REAL NOT NULL,
                      coins INTEGER NOT NULL,
                      status TEXT NOT NULL DEFAULT 'pending',
                      created_at TEXT NOT NULL,
                      reviewed_at TEXT,
                      reviewed_by INTEGER)"""
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_coin_payment_requests_status "
            "ON coin_payment_requests(status)"
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_coin_payment_requests_tx_code "
            "ON coin_payment_requests(transaction_code)"
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS user_coins
                     (user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS referrals
                     (referred_user_id INTEGER PRIMARY KEY,
                      referrer_id INTEGER NOT NULL,
                      reward_coins INTEGER NOT NULL,
                      created_at TEXT NOT NULL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS bot_settings
                     (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)"""
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("referral_reward_coins", str(REFERRAL_REWARD_COINS)),
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("bot_run_cost_coins", str(BOT_RUN_COST_COINS)),
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("coin_run_duration_minutes", str(COIN_RUN_DURATION_HOURS * 60)),
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("coin_package_coins", str(COIN_PACKAGE_COINS)),
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("coin_package_price_bdt", f"{COIN_PACKAGE_PRICE_BDT:g}"),
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("coin_bkash_number", ""),
        )
        c.execute(
            "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
            ("coin_nagad_number", ""),
        )

        c.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,)
        )
        if ADMIN_ID != OWNER_ID:
            c.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,)
            )

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)


def load_data():
    """Load data from database into memory"""
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute(
            "SELECT user_id, plan_name, expiry, plan_id, max_bots "
            "FROM subscriptions"
        )
        for row in c.fetchall():
            user_id = row[0]
            plan_name = row[1] or "Premium"
            expiry = row[2]
            try:
                user_subscriptions[user_id] = {
                    "plan_name": plan_name,
                    "expiry": datetime.fromisoformat(expiry),
                    "plan_id": row[3],
                    "max_bots": row[4] or SUBSCRIBED_USER_LIMIT,
                }
            except ValueError:
                logger.warning(
                    f"⚠️ Invalid expiry date format for user {user_id}: {expiry}. Skipping."
                )

        c.execute("SELECT user_id, file_name, file_type FROM user_files")
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        c.execute("SELECT user_id FROM active_users")
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute("SELECT user_id FROM admins")
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        conn.close()
        logger.info(f"Data loaded successfully.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)


init_db()
load_data()


# --- Referral and Coin Helpers ---
def get_db_connection():
    """Return a SQLite connection with a useful timeout for bot callbacks."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_coin_setting(setting_key, default_value):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT setting_value FROM bot_settings WHERE setting_key = ?",
            (setting_key,),
        ).fetchone()
        if not row:
            return int(default_value)
        try:
            value = int(row[0])
        except (TypeError, ValueError):
            return int(default_value)
        return value if value > 0 else int(default_value)
    finally:
        conn.close()


def set_coin_setting(setting_key, value):
    value = int(value)
    if value <= 0:
        raise ValueError("Setting must be a positive integer")
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                """INSERT INTO bot_settings (setting_key, setting_value)
                   VALUES (?, ?)
                   ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value""",
                (setting_key, str(value)),
            )
            conn.commit()
        finally:
            conn.close()
    return value


def get_referral_reward_coins():
    return get_coin_setting("referral_reward_coins", REFERRAL_REWARD_COINS)


def get_bot_run_cost_coins():
    return get_coin_setting("bot_run_cost_coins", BOT_RUN_COST_COINS)


def get_coin_run_duration_minutes():
    return get_coin_setting(
        "coin_run_duration_minutes", COIN_RUN_DURATION_HOURS * 60
    )


def format_coin_run_duration(minutes=None):
    minutes = minutes or get_coin_run_duration_minutes()
    if minutes % (24 * 60) == 0:
        days = minutes // (24 * 60)
        return f"{days} day" if days == 1 else f"{days} days"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"


def get_text_coin_setting(setting_key, default_value=""):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT setting_value FROM bot_settings WHERE setting_key = ?",
            (setting_key,),
        ).fetchone()
        return str(row[0]) if row and row[0] is not None else str(default_value)
    finally:
        conn.close()


def set_text_coin_setting(setting_key, value):
    value = str(value).strip()
    if not value:
        raise ValueError("Setting cannot be empty")
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                """INSERT INTO bot_settings (setting_key, setting_value)
                   VALUES (?, ?)
                   ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value""",
                (setting_key, value),
            )
            conn.commit()
        finally:
            conn.close()
    return value


def get_coin_package_coins():
    return get_coin_setting("coin_package_coins", COIN_PACKAGE_COINS)


def get_coin_package_price_bdt():
    raw_price = get_text_coin_setting(
        "coin_package_price_bdt", f"{COIN_PACKAGE_PRICE_BDT:g}"
    )
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return COIN_PACKAGE_PRICE_BDT
    return price if price > 0 else COIN_PACKAGE_PRICE_BDT


def get_coin_payment_number(method):
    setting_key = "coin_bkash_number" if method == "bKash" else "coin_nagad_number"
    return get_text_coin_setting(setting_key, "")


def ensure_coin_wallet(user_id):
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO user_coins (user_id, balance) VALUES (?, 0)",
                (user_id,),
            )
            conn.commit()
        finally:
            conn.close()


def get_coin_balance(user_id):
    ensure_coin_wallet(user_id)
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT balance FROM user_coins WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def add_coins(user_id, amount):
    """Credit coins atomically and return the new balance."""
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Coin amount must be positive")
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO user_coins (user_id, balance) VALUES (?, 0)",
                (user_id,),
            )
            conn.execute(
                "UPDATE user_coins SET balance = balance + ? WHERE user_id = ?",
                (amount, user_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT balance FROM user_coins WHERE user_id = ?", (user_id,)
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()


def remove_coins(user_id, amount):
    """Remove coins without allowing a user's balance to go below zero."""
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Coin amount must be positive")
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO user_coins (user_id, balance) VALUES (?, 0)",
                (user_id,),
            )
            conn.execute(
                """UPDATE user_coins
                   SET balance = CASE
                       WHEN balance >= ? THEN balance - ?
                       ELSE 0
                   END
                   WHERE user_id = ?""",
                (amount, amount, user_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT balance FROM user_coins WHERE user_id = ?", (user_id,)
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()


def spend_coins(user_id, amount):
    """Spend coins atomically; return (success, remaining_balance)."""
    amount = int(amount)
    if amount <= 0:
        return True, get_coin_balance(user_id)
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO user_coins (user_id, balance) VALUES (?, 0)",
                (user_id,),
            )
            cursor = conn.execute(
                """UPDATE user_coins
                   SET balance = balance - ?
                   WHERE user_id = ? AND balance >= ?""",
                (amount, user_id, amount),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                row = conn.execute(
                    "SELECT balance FROM user_coins WHERE user_id = ?", (user_id,)
                ).fetchone()
                return False, int(row[0]) if row else 0
            conn.commit()
            row = conn.execute(
                "SELECT balance FROM user_coins WHERE user_id = ?", (user_id,)
            ).fetchone()
            return True, int(row[0]) if row else 0
        finally:
            conn.close()


def register_referral(referred_user_id, referrer_id):
    """Reward a referrer only once when a new user opens a referral link."""
    try:
        referred_user_id = int(referred_user_id)
        referrer_id = int(referrer_id)
    except (TypeError, ValueError):
        return None
    if referred_user_id == referrer_id:
        return None

    reward_coins = get_referral_reward_coins()
    with DB_LOCK:
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO referrals
                   (referred_user_id, referrer_id, reward_coins, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    referred_user_id,
                    referrer_id,
                    reward_coins,
                    datetime.now().isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return None

            conn.execute(
                "INSERT OR IGNORE INTO user_coins (user_id, balance) VALUES (?, 0)",
                (referrer_id,),
            )
            conn.execute(
                "UPDATE user_coins SET balance = balance + ? WHERE user_id = ?",
                (reward_coins, referrer_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT balance FROM user_coins WHERE user_id = ?", (referrer_id,)
            ).fetchone()
            return int(row[0]) if row else reward_coins
        finally:
            conn.close()


def get_bot_username():
    global bot_username
    if bot_username:
        return bot_username
    try:
        bot_username = bot.get_me().username
    except Exception as exc:
        logger.warning("Unable to load bot username for referral link: %s", exc)
    return bot_username


def has_active_subscription(user_id):
    subscription = user_subscriptions.get(user_id)
    return bool(subscription and subscription["expiry"] > datetime.now())


def get_user_bot_limit(user_id):
    """Return the number of bots a user may run at the same time."""
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
    subscription = user_subscriptions.get(user_id)
    if subscription and subscription["expiry"] > datetime.now():
        return int(subscription.get("max_bots") or SUBSCRIBED_USER_LIMIT)
    return FREE_USER_LIMIT


def get_running_bot_count(user_id):
    """Count currently running scripts owned by a user."""
    running = 0
    for info in list(bot_scripts.values()):
        if info.get("script_owner_id") != user_id:
            continue
        if is_bot_running(user_id, info.get("file_name", "")):
            running += 1
    return running


def can_start_bot(user_id):
    limit = get_user_bot_limit(user_id)
    return limit == float("inf") or get_running_bot_count(user_id) < limit


def can_upload_or_run(user_id):
    """Paid users keep their old access; referral coins unlock free runs."""
    if user_id in admin_ids or user_id == OWNER_ID or has_active_subscription(user_id):
        return True
    return get_coin_balance(user_id) >= get_bot_run_cost_coins()


def consume_run_coin_if_needed(user_id):
    """Return (allowed, charged, remaining_coins)."""
    if user_id in admin_ids or user_id == OWNER_ID or has_active_subscription(user_id):
        return True, False, get_coin_balance(user_id)
    run_cost = get_bot_run_cost_coins()
    success, remaining = spend_coins(user_id, run_cost)
    return success, success, remaining


def safe_upload_name(file_name):
    """Reject path traversal while keeping normal Telegram filenames usable."""
    name = str(file_name or "").strip()
    if (
        not name
        or name in {".", ".."}
        or "\x00" in name
        or "/" in name
        or "\\" in name
        or len(name) > 120
    ):
        return None
    return name


def can_manage_file(actor_id, owner_id):
    return actor_id == owner_id or actor_id in admin_ids or actor_id == OWNER_ID


# --- Database Helper Operations ---
def parse_price_to_bdt(price_str):
    """Extract a positive BDT price from a plan's price field."""
    numbers = re.findall(r"\d+(?:\.\d+)?", str(price_str or "").strip())
    if not numbers:
        raise ValueError("দাম হিসেবে একটি positive number দিন")
    amount = float(numbers[0])
    if amount <= 0:
        raise ValueError("দাম ০-এর বেশি হতে হবে")
    return amount


def add_plan_db(name, max_bots, price, duration, bkash_number, nagad_number):
    with DB_LOCK:
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO plans
               (name, file_limit, price, duration, buy_link,
                max_bots, bkash_number, nagad_number)
               VALUES (?, ?, ?, ?, '', ?, ?, ?)""",
            (
                name,
                max_bots,
                f"{price:g} BDT",
                duration,
                max_bots,
                bkash_number,
                nagad_number,
            ),
        )
        conn.commit()
        conn.close()


def get_all_plans():
    conn = get_db_connection()
    plans = conn.execute(
        """SELECT plan_id, name, COALESCE(max_bots, file_limit), price,
                  duration, COALESCE(bkash_number, ''), COALESCE(nagad_number, '')
           FROM plans
           ORDER BY plan_id"""
    )
    rows = plans.fetchall()
    conn.close()
    return rows


def get_plan_by_id(plan_id):
    conn = get_db_connection()
    plan = conn.execute(
        """SELECT plan_id, name, COALESCE(max_bots, file_limit), price,
                  duration, COALESCE(bkash_number, ''), COALESCE(nagad_number, '')
           FROM plans WHERE plan_id = ?""",
        (plan_id,),
    ).fetchone()
    conn.close()
    return plan


def update_plan_db(
    plan_id, name, max_bots, price, duration, bkash_number, nagad_number
):
    with DB_LOCK:
        conn = get_db_connection()
        conn.execute(
            """UPDATE plans
               SET name = ?, file_limit = ?, price = ?, duration = ?,
                   max_bots = ?, bkash_number = ?, nagad_number = ?
               WHERE plan_id = ?""",
            (
                name,
                max_bots,
                f"{price:g} BDT",
                duration,
                max_bots,
                bkash_number,
                nagad_number,
                plan_id,
            ),
        )
        conn.commit()
        conn.close()


def delete_plan_db(plan_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
        conn.commit()
        conn.close()


def is_txid_used(tx_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT tx_id FROM used_txids WHERE tx_id=?", (str(tx_id).strip(),)
    ).fetchone()
    conn.close()
    return row is not None


def add_used_txid(tx_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO used_txids (tx_id) VALUES (?)",
            (str(tx_id).strip(),),
        )
        conn.commit()
        conn.close()


def create_payment_request(user_id, plan_id, method, transaction_code, amount):
    with DB_LOCK:
        conn = get_db_connection()
        cursor = conn.execute(
            """INSERT INTO payment_requests
               (user_id, plan_id, method, transaction_code, amount, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                plan_id,
                method,
                transaction_code,
                amount,
                datetime.now().isoformat(),
            ),
        )
        request_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return request_id


def create_coin_payment_request(
    user_id, method, transaction_code, amount, coins
):
    with DB_LOCK:
        conn = get_db_connection()
        cursor = conn.execute(
            """INSERT INTO coin_payment_requests
               (user_id, method, transaction_code, amount, coins, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                method,
                transaction_code,
                amount,
                coins,
                datetime.now().isoformat(),
            ),
        )
        request_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return request_id


def get_pending_coin_payment_requests():
    conn = get_db_connection()
    rows = conn.execute(
        """SELECT request_id, user_id, method, transaction_code,
                  amount, coins, created_at
           FROM coin_payment_requests
           WHERE status = 'pending'
           ORDER BY request_id"""
    ).fetchall()
    conn.close()
    return rows


def review_coin_payment_request(request_id, reviewer_id, approve):
    """Approve/reject a coin purchase exactly once."""
    with DB_LOCK:
        conn = get_db_connection()
        row = conn.execute(
            """SELECT request_id, user_id, method, transaction_code,
                      amount, coins, status
               FROM coin_payment_requests WHERE request_id = ?""",
            (request_id,),
        ).fetchone()
        if not row:
            conn.close()
            return None, "কয়েন payment request পাওয়া যায়নি"
        if row[6] != "pending":
            conn.close()
            return None, f"এই coin request আগেই {row[6]} হয়েছে"
        if approve:
            try:
                conn.execute(
                    "INSERT INTO used_txids (tx_id) VALUES (?)", (row[3],)
                )
            except sqlite3.IntegrityError:
                conn.close()
                return None, "এই ট্রানজেকশন কোডটি আগে ব্যবহার হয়েছে"
        new_status = "approved" if approve else "rejected"
        conn.execute(
            """UPDATE coin_payment_requests
               SET status = ?, reviewed_at = ?, reviewed_by = ?
               WHERE request_id = ? AND status = 'pending'""",
            (new_status, datetime.now().isoformat(), reviewer_id, request_id),
        )
        conn.commit()
        conn.close()
        return row, None


def get_payment_request(request_id):
    conn = get_db_connection()
    row = conn.execute(
        """SELECT request_id, user_id, plan_id, method, transaction_code,
                  amount, status, created_at, reviewed_at, reviewed_by
           FROM payment_requests WHERE request_id = ?""",
        (request_id,),
    ).fetchone()
    conn.close()
    return row


def has_payment_transaction(transaction_code):
    code = str(transaction_code).strip()
    conn = get_db_connection()
    row = conn.execute(
        """SELECT 1 FROM used_txids WHERE tx_id = ?
           UNION SELECT 1 FROM payment_requests
           WHERE transaction_code = ?
           UNION SELECT 1 FROM coin_payment_requests
           WHERE transaction_code = ? LIMIT 1""",
        (code, code, code),
    ).fetchone()
    conn.close()
    return row is not None


def get_pending_payment_requests():
    conn = get_db_connection()
    rows = conn.execute(
        """SELECT request_id, user_id, plan_id, method, transaction_code,
                  amount, created_at
           FROM payment_requests
           WHERE status = 'pending'
           ORDER BY request_id"""
    ).fetchall()
    conn.close()
    return rows


def review_payment_request(request_id, reviewer_id, approve):
    """Approve/reject a payment request exactly once."""
    with DB_LOCK:
        conn = get_db_connection()
        row = conn.execute(
            """SELECT request_id, user_id, plan_id, method, transaction_code,
                      amount, status
               FROM payment_requests WHERE request_id = ?""",
            (request_id,),
        ).fetchone()
        if not row:
            conn.close()
            return None, "পেমেন্ট রিকোয়েস্ট পাওয়া যায়নি"
        if row[6] != "pending":
            conn.close()
            return None, f"এই রিকোয়েস্ট আগেই {row[6]} হয়েছে"
        if approve:
            try:
                conn.execute(
                    "INSERT INTO used_txids (tx_id) VALUES (?)", (row[4],)
                )
            except sqlite3.IntegrityError:
                conn.close()
                return None, "এই ট্রানজেকশন কোডটি আগে ব্যবহার হয়েছে"
        new_status = "approved" if approve else "rejected"
        conn.execute(
            """UPDATE payment_requests
               SET status = ?, reviewed_at = ?, reviewed_by = ?
               WHERE request_id = ? AND status = 'pending'""",
            (new_status, datetime.now().isoformat(), reviewer_id, request_id),
        )
        conn.commit()
        conn.close()
        return row, None


# --- Malware Detection Functions ---
def is_suspicious_file(file_content, file_name):
    file_lower = file_name.lower()
    suspicious_extensions = [
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".scr",
        ".com",
        ".pif",
        ".application",
        ".gadget",
        ".msi",
        ".msp",
        ".com",
        ".scr",
        ".hta",
        ".cpl",
        ".msc",
        ".jar",
        ".bin",
        ".deb",
        ".rpm",
        ".apk",
        ".app",
        ".dmg",
        ".iso",
        ".img",
    ]
    if any(file_lower.endswith(ext) for ext in suspicious_extensions):
        return True, f"Suspicious file extension: {file_name}"
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature):
            return True, f"Malware signature detected: {signature}"
    sample_size = min(len(file_content), 4096)
    file_sample = file_content[:sample_size]
    for indicator in ENCRYPTED_FILE_INDICATORS:
        if indicator in file_sample:
            return (
                True,
                f"Encrypted file indicator: {indicator.decode('utf-8', errors='ignore')}",
            )
    sample_text = file_sample.decode("utf-8", errors="ignore").lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.decode("utf-8").lower() in sample_text:
            return True, f"Suspicious keyword found: {keyword.decode('utf-8')}"
    return False, "File appears safe"


def scan_file_for_malware(file_content, file_name, user_id):
    if user_id == OWNER_ID:
        return True, "Owner bypassed security check"
    is_suspicious, reason = is_suspicious_file(file_content, file_name)
    if is_suspicious:
        logger.warning(
            f"🚨 Malware detected in {file_name} from user {user_id}: {reason}"
        )
        return False, f"Security violation: {reason}"
    return True, "File passed security check"


# --- Helper Functions ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder


def get_user_file_limit(user_id):
    """Return the storage file limit.

    A project often needs its entrypoint plus several JSON/database files.
    Storage is therefore unlimited (within Telegram, per-file, and ZIP size
    safeguards); subscription limits remain enforced by get_user_bot_limit().
    """
    return FREE_USER_LIMIT


def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))


def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get("process"):
        try:
            proc = psutil.Process(script_info["process"].pid)
            is_running = (
                proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            )
            if not is_running:
                if (
                    "log_file" in script_info
                    and hasattr(script_info["log_file"], "close")
                    and not script_info["log_file"].closed
                ):
                    try:
                        script_info["log_file"].close()
                    except Exception:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception:
            return False
    return False


def kill_process_tree(process_info):
    """Stop a bot process and all of its child processes completely."""
    try:
        if (
            "log_file" in process_info
            and hasattr(process_info["log_file"], "close")
            and not process_info["log_file"].closed
        ):
            try:
                process_info["log_file"].close()
            except Exception:
                pass
        process = process_info.get("process")
        if process and hasattr(process, "pid"):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    processes = parent.children(recursive=True)
                    processes.append(parent)

                    for child in processes:
                        try:
                            child.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    _, alive = psutil.wait_procs(processes, timeout=3)
                    for child in alive:
                        try:
                            child.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    if hasattr(process, "wait"):
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # The process already exited, so there is nothing left to stop.
                    pass
    except Exception as e:
        logger.error(f"❌ Error killing process: {e}")


def stop_bot_process(script_owner_id, file_name):
    """Stop one tracked bot and remove its process record."""
    script_key = f"{script_owner_id}_{file_name}"
    process_info = bot_scripts.pop(script_key, None)
    if process_info:
        kill_process_tree(process_info)
    return process_info


def monitor_coin_run_expiry(
    script_owner_id, file_name, expires_at, chat_id
):
    """Stop a bot when its coin-funded run window expires."""
    while True:
        remaining_seconds = (expires_at - datetime.now()).total_seconds()
        if remaining_seconds <= 0:
            break
        time.sleep(min(remaining_seconds, 60))

    script_key = f"{script_owner_id}_{file_name}"
    current_info = bot_scripts.get(script_key)
    if not current_info:
        return
    if current_info.get("coin_run_expires_at") != expires_at:
        return
    if not is_bot_running(script_owner_id, file_name):
        return

    stop_bot_process(script_owner_id, file_name)
    try:
        bot.send_message(
            chat_id,
            f"⏳ `{file_name}`-এর coin-funded run time শেষ হয়েছে। "
            "বটটি automatically stopped করা হয়েছে। আবার চালাতে নতুন coin লাগবে।",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.info("Could not notify coin run expiry for %s: %s", file_name, exc)


# --- Module / Package Mapping ---
TELEGRAM_MODULES = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "python_telegram_bot": "python-telegram-bot",
    "aiogram": "aiogram",
    "pyrogram": "pyrogram",
    "telethon": "telethon",
    "bs4": "beautifulsoup4",
    "requests": "requests",
    "pillow": "Pillow",
    "cv2": "opencv-python",
    "flask": "Flask",
    "psutil": "psutil",
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "lxml": "lxml",
    "dateutil": "python-dateutil",
    "jwt": "PyJWT",
    "websocket": "websocket-client",
    "magic": "python-magic",
    "pydantic": "pydantic",
    "numpy": "numpy",
    "pandas": "pandas",
    "openpyxl": "openpyxl",
    "rich": "rich",
    "aiohttp": "aiohttp",
}


SCRIPT_PREPARATION_LOCK = threading.Lock()
scripts_being_prepared = set()
PYTHON_STDLIB_MODULES = set(
    getattr(sys, "stdlib_module_names", set(sys.builtin_module_names))
)


def get_python_package_install_command(packages):
    """Build a package install command for the active Python environment."""
    try:
        pip_check = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pip_check = None

    if pip_check and pip_check.returncode == 0:
        return [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            *packages,
        ]

    uv_path = shutil.which("uv")
    if uv_path:
        # Replit's managed .pythonlibs environment commonly has uv but not pip.
        return [uv_path, "pip", "install", "--python", sys.executable, *packages]

    return None


def get_python_imports(script_path):
    """Return top-level absolute imports used by a Python script."""
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as script_file:
            source = script_file.read()
        tree = ast.parse(source, filename=script_path)
    except (OSError, SyntaxError) as exc:
        logger.warning("Could not inspect imports for %s: %s", script_path, exc)
        return set()

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name.split(".", 1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported_modules.add(node.module.split(".", 1)[0])
    return {
        module
        for module in imported_modules
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", module)
    }


def python_module_is_available(module_name, user_folder, script_path):
    """Check stdlib, installed, and uploaded local modules before using pip."""
    if module_name in PYTHON_STDLIB_MODULES:
        return True

    script_stem = os.path.splitext(os.path.basename(script_path))[0]
    if module_name == script_stem:
        return True
    if os.path.isfile(os.path.join(user_folder, f"{module_name}.py")):
        return True
    if os.path.isdir(os.path.join(user_folder, module_name)):
        return True

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def install_python_dependencies(
    script_path, user_folder, file_name, message_obj_for_reply
):
    """Install missing third-party imports before starting a user script."""
    imported_modules = get_python_imports(script_path)
    missing_modules = sorted(
        module
        for module in imported_modules
        if not python_module_is_available(module, user_folder, script_path)
    )

    if not missing_modules:
        bot.reply_to(
            message_obj_for_reply,
            f"✅ `{file_name}`-এর প্রয়োজনীয় Python package আগে থেকেই প্রস্তুত আছে।",
            parse_mode="Markdown",
        )
        return True

    if len(missing_modules) > MAX_AUTO_DEPENDENCIES:
        bot.reply_to(
            message_obj_for_reply,
            f"❌ এই ফাইলে একসাথে {len(missing_modules)}টি নতুন package পাওয়া গেছে। "
            f"নিরাপত্তার জন্য সর্বোচ্চ {MAX_AUTO_DEPENDENCIES}টি package একবারে "
            "automatic install করা যায়।",
        )
        return False

    packages = [
        TELEGRAM_MODULES.get(module.lower(), module)
        for module in missing_modules
    ]
    bot.reply_to(
        message_obj_for_reply,
        "📦 Python dependency পাওয়া গেছে:\n"
        + "\n".join(f"• `{package}`" for package in packages)
        + "\n\n⏳ এগুলো automatic install করা হচ্ছে। Install শেষ হলে script চালু হবে...",
        parse_mode="Markdown",
    )

    install_command = get_python_package_install_command(packages)
    if not install_command:
        bot.reply_to(
            message_obj_for_reply,
            "❌ এই Python environment-এ package installer পাওয়া যায়নি "
            "(pip বা uv কোনোটিই নেই)। Script চালু করা হয়নি।",
        )
        return False

    try:
        result = subprocess.run(
            install_command,
            cwd=user_folder,
            capture_output=True,
            text=True,
            timeout=PYTHON_DEPENDENCY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        bot.reply_to(
            message_obj_for_reply,
            f"❌ Package install timeout হয়েছে ({PYTHON_DEPENDENCY_TIMEOUT_SECONDS} "
            "সেকেন্ড)। Script চালু করা হয়নি।",
        )
        return False
    except OSError as exc:
        logger.exception("Could not start pip for %s", file_name)
        bot.reply_to(
            message_obj_for_reply,
            f"❌ Python package installer চালু করা যায়নি: `{str(exc)[:300]}`",
            parse_mode="Markdown",
        )
        return False

    if result.returncode != 0:
        install_output = (result.stderr or result.stdout or "").strip()
        bot.reply_to(
            message_obj_for_reply,
            "❌ প্রয়োজনীয় package install ব্যর্থ হয়েছে। Script চালু করা হয়নি।\n\n"
            f"```text\n{install_output[-1800:] or 'pip কোনো বিস্তারিত error দেয়নি'}\n```",
            parse_mode="Markdown",
        )
        return False

    unresolved_modules = [
        module
        for module in missing_modules
        if not python_module_is_available(module, user_folder, script_path)
    ]
    if unresolved_modules:
        bot.reply_to(
            message_obj_for_reply,
            "❌ Install শেষ হলেও এই module-গুলো import করা যাচ্ছে না: "
            + ", ".join(f"`{module}`" for module in unresolved_modules)
            + "\nScript চালু করা হয়নি।",
            parse_mode="Markdown",
        )
        return False

    bot.reply_to(
        message_obj_for_reply,
        "✅ প্রয়োজনীয় Python package install সম্পন্ন হয়েছে। এখন script চালু হচ্ছে...",
    )
    return True


# --- Automatic & Guided Script Running ---
def monitor_and_guide_error(
    process, log_file_path, script_owner_id, file_name, message_obj_for_reply
):
    """রানিং স্ক্রিপ্ট ব্যাকগ্রাউন্ডে চেক করে কোনো এরর থাকলে ইউজারকে বাটন দিয়ে বুঝিয়ে দেবে"""
    time.sleep(3)
    if process.poll() is not None:
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                log_content = f.read()

            match_py = re.search(
                r"(?:ModuleNotFoundError|ImportError): No module named '(.+?)'",
                log_content,
            )
            match_js = re.search(r"Cannot find module '(.+?)'", log_content)

            missing_module = None
            if match_py:
                missing_module = match_py.group(1).split(".")[0].strip("'\"")
            elif match_js:
                missing_module = match_js.group(1).split("/")[0].strip("'\"")

            if missing_module:
                pkg_name = TELEGRAM_MODULES.get(
                    missing_module.lower(), missing_module
                )
                ext = os.path.splitext(file_name)[1].lower()
                cmd_text = (
                    f"npm install {pkg_name}"
                    if ext == ".js"
                    else f"pip install {pkg_name}"
                )

                error_msg = (
                    f"⚠️ **ফাইল রান হতে সমস্যা হয়েছে!**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"❌ **সমস্যা:** আপনার কোডে `{missing_module}` মডিউলটি মিসিং আছে।\n"
                    f"💻 **প্রয়োজনীয় কমান্ড:** `{cmd_text}`\n\n"
                    f"👇 *নিচের বাটনে প্রেস করে সরাসরি মডিউলটি ইনস্টল করুন:*"
                )

                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(
                        f"📦 Install {pkg_name}",
                        callback_data=f"instmod_{script_owner_id}_{missing_module}_{file_name}",
                    )
                )
                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=f"viewlog_{script_owner_id}_{file_name}",
                    )
                )

                bot.reply_to(
                    message_obj_for_reply,
                    error_msg,
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
            else:
                error_msg = (
                    f"⚠️ **আপনার কোডে ভুল (Syntax/Runtime Error) পাওয়া গেছে!**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"সুনির্দিষ্ট এরর জানতে নিচের **View Logs** বাটনে ক্লিক করুন।"
                )
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=f"viewlog_{script_owner_id}_{file_name}",
                    )
                )
                bot.reply_to(
                    message_obj_for_reply,
                    error_msg,
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Error checking log file: {e}")


def run_script(
    script_path,
    script_owner_id,
    user_folder,
    file_name,
    message_obj_for_reply,
    charge_run=True,
    coin_run_expires_at=None,
):
    script_key = f"{script_owner_id}_{file_name}"
    charged = False
    run_cost = get_bot_run_cost_coins()
    with SCRIPT_PREPARATION_LOCK:
        if script_key in scripts_being_prepared:
            bot.reply_to(
                message_obj_for_reply,
                f"⏳ `{file_name}`-এর package preparation ইতিমধ্যে চলছে।",
                parse_mode="Markdown",
            )
            return
        scripts_being_prepared.add(script_key)

    try:
        if is_bot_running(script_owner_id, file_name):
            bot.reply_to(message_obj_for_reply, f"ℹ️ `{file_name}` is already running.")
            return
        if not can_start_bot(script_owner_id):
            bot.reply_to(
                message_obj_for_reply,
                f"❌ আপনার active plan-এ একসাথে সর্বোচ্চ "
                f"`{get_user_bot_limit(script_owner_id)}`টি bot চালানো যাবে। "
                "আগে একটি bot বন্ধ করুন অথবা plan upgrade করুন।",
                parse_mode="Markdown",
            )
            return

        if charge_run:
            allowed, charged, remaining_coins = consume_run_coin_if_needed(
                script_owner_id
            )
            if not allowed:
                bot.reply_to(
                    message_obj_for_reply,
                    f"❌ এই বট চালাতে {run_cost} কয়েন প্রয়োজন।\n"
                    f"🪙 আপনার বর্তমান ব্যালেন্স: `{remaining_coins}`\n"
                    "রেফার করে কয়েন সংগ্রহ করুন।",
                    parse_mode="Markdown",
                )
                return

        if not install_python_dependencies(
            script_path, user_folder, file_name, message_obj_for_reply
        ):
            if charged:
                add_coins(script_owner_id, run_cost)
                charged = False
            return

        log_file_path = os.path.join(
            user_folder, f"{os.path.splitext(file_name)[0]}.log"
        )
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            start_new_session=True,
        )

        bot_scripts[script_key] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "script_owner_id": script_owner_id,
            "start_time": datetime.now(),
            "user_folder": user_folder,
            "type": "py",
            "script_key": script_key,
            "coin_run_expires_at": (
                coin_run_expires_at
                if coin_run_expires_at is not None
                else (
                    datetime.now()
                    + timedelta(minutes=get_coin_run_duration_minutes())
                    if charged
                    else None
                )
            ),
        }

        bot.reply_to(
            message_obj_for_reply,
            f"🚀 **Python Script Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`",
            parse_mode="Markdown",
        )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply,
            ),
        ).start()
        if bot_scripts[script_key].get("coin_run_expires_at"):
            threading.Thread(
                target=monitor_coin_run_expiry,
                args=(
                    script_owner_id,
                    file_name,
                    bot_scripts[script_key]["coin_run_expires_at"],
                    message_obj_for_reply.chat.id,
                ),
                daemon=True,
            ).start()

    except Exception as e:
        if charged:
            add_coins(script_owner_id, run_cost)
        bot.reply_to(message_obj_for_reply, f"❌ Error running script: {str(e)}")
    finally:
        with SCRIPT_PREPARATION_LOCK:
            scripts_being_prepared.discard(script_key)


def run_js_script(
    script_path,
    script_owner_id,
    user_folder,
    file_name,
    message_obj_for_reply,
    charge_run=True,
    coin_run_expires_at=None,
):
    script_key = f"{script_owner_id}_{file_name}"
    charged = False
    run_cost = get_bot_run_cost_coins()
    try:
        if is_bot_running(script_owner_id, file_name):
            bot.reply_to(message_obj_for_reply, f"ℹ️ `{file_name}` is already running.")
            return
        if not can_start_bot(script_owner_id):
            bot.reply_to(
                message_obj_for_reply,
                f"❌ আপনার active plan-এ একসাথে সর্বোচ্চ "
                f"`{get_user_bot_limit(script_owner_id)}`টি bot চালানো যাবে। "
                "আগে একটি bot বন্ধ করুন অথবা plan upgrade করুন।",
                parse_mode="Markdown",
            )
            return

        if charge_run:
            allowed, charged, remaining_coins = consume_run_coin_if_needed(
                script_owner_id
            )
            if not allowed:
                bot.reply_to(
                    message_obj_for_reply,
                    f"❌ এই বট চালাতে {run_cost} কয়েন প্রয়োজন।\n"
                    f"🪙 আপনার বর্তমান ব্যালেন্স: `{remaining_coins}`\n"
                    "রেফার করে কয়েন সংগ্রহ করুন।",
                    parse_mode="Markdown",
                )
                return

        log_file_path = os.path.join(
            user_folder, f"{os.path.splitext(file_name)[0]}.log"
        )
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        process = subprocess.Popen(
            ["node", script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            start_new_session=True,
        )

        bot_scripts[script_key] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "script_owner_id": script_owner_id,
            "start_time": datetime.now(),
            "user_folder": user_folder,
            "type": "js",
            "script_key": script_key,
            "coin_run_expires_at": (
                coin_run_expires_at
                if coin_run_expires_at is not None
                else (
                    datetime.now()
                    + timedelta(minutes=get_coin_run_duration_minutes())
                    if charged
                    else None
                )
            ),
        }

        bot.reply_to(
            message_obj_for_reply,
            f"🚀 **JS Script Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`",
            parse_mode="Markdown",
        )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply,
            ),
        ).start()
        if bot_scripts[script_key].get("coin_run_expires_at"):
            threading.Thread(
                target=monitor_coin_run_expiry,
                args=(
                    script_owner_id,
                    file_name,
                    bot_scripts[script_key]["coin_run_expires_at"],
                    message_obj_for_reply.chat.id,
                ),
                daemon=True,
            ).start()

    except Exception as e:
        if charged:
            add_coins(script_owner_id, run_cost)
        bot.reply_to(
            message_obj_for_reply, f"❌ Error running JS script: {str(e)}"
        )


# --- Database Operations ---
def save_user_file(user_id, file_name, file_type="py"):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)",
            (user_id, file_name, file_type),
        )
        conn.commit()
        conn.close()
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id] = [
            (fn, ft) for fn, ft in user_files[user_id] if fn != file_name
        ]
        user_files[user_id].append((file_name, file_type))


def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "DELETE FROM user_files WHERE user_id = ? AND file_name = ?",
            (user_id, file_name),
        )
        conn.commit()
        conn.close()
        if user_id in user_files:
            user_files[user_id] = [
                f for f in user_files[user_id] if f[0] != file_name
            ]


def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,)
        )
        conn.commit()
        conn.close()


def save_subscription(user_id, plan_name, expiry, plan_id=None, max_bots=None):
    with DB_LOCK:
        conn = get_db_connection()
        conn.execute(
            """INSERT OR REPLACE INTO subscriptions
               (user_id, plan_name, expiry, plan_id, max_bots)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, plan_name, expiry.isoformat(), plan_id, max_bots),
        )
        conn.commit()
        conn.close()
        user_subscriptions[user_id] = {
            "plan_name": plan_name,
            "expiry": expiry,
            "plan_id": plan_id,
            "max_bots": max_bots or SUBSCRIBED_USER_LIMIT,
        }


def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        if user_id in user_subscriptions:
            del user_subscriptions[user_id]


# --- Menu Creation ---
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = (
        ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC
        if user_id in admin_ids
        else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    )
    for row in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup


def create_admin_panel_inline():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ 𝗔𝗱𝗱 𝗩𝗜𝗣 𝗣𝗹𝗮𝗻", callback_data="add_plan_init"),
        types.InlineKeyboardButton(
            "🗑️ 𝗠𝗮𝗻𝗮𝗴𝗲 𝗣𝗹𝗮𝗻𝘀", callback_data="manage_plans"
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "🧾 𝗣𝗲𝗻𝗱𝗶𝗻𝗴 𝗣𝗮𝘆𝗺𝗲𝗻𝘁𝘀", callback_data="pending_payments"
        ),
        types.InlineKeyboardButton(
            "🪙 𝗣𝗲𝗻𝗱𝗶𝗻𝗴 𝗖𝗼𝗶𝗻 𝗗𝗲𝗽𝗼𝘀𝗶𝘁𝘀",
            callback_data="pending_coin_payments",
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "💎 𝗔𝗱𝗱 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻", callback_data="add_subscription"
        ),
        types.InlineKeyboardButton(
            "❌ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗦𝘂𝗯", callback_data="remove_subscription"
        ),
    )
    markup.add(
        types.InlineKeyboardButton("👑 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻", callback_data="add_admin"),
        types.InlineKeyboardButton(
            "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻", callback_data="remove_admin"
        ),
    )
    markup.add(
        types.InlineKeyboardButton("🪙 𝗖𝗼𝗶𝗻 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀", callback_data="coin_settings"),
        types.InlineKeyboardButton("➕ 𝗔𝗱𝗱 𝗖𝗼𝗶𝗻𝘀", callback_data="add_coins"),
    )
    markup.add(
        types.InlineKeyboardButton("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗼𝗶𝗻𝘀", callback_data="remove_coins"),
        types.InlineKeyboardButton(
            "🎁 𝗦𝗲𝘁 𝗥𝗲𝗳𝗲𝗿 𝗥𝗲𝘄𝗮𝗿𝗱", callback_data="set_referral_reward"
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "⚙️ 𝗦𝗲𝘁 𝗕𝗼𝘁 𝗥𝘂𝗻 𝗖𝗼𝘀𝘁", callback_data="set_run_cost"
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "⏱️ 𝗦𝗲𝘁 𝗖𝗼𝗶𝗻 𝗥𝘂𝗻 𝗧𝗶𝗺𝗲", callback_data="set_coin_duration"
        ),
        types.InlineKeyboardButton(
            "💰 𝗦𝗲𝘁 𝗖𝗼𝗶𝗻 𝗣𝗿𝗶𝗰𝗲", callback_data="set_coin_price"
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "📱 𝗦𝗲𝘁 𝗖𝗼𝗶𝗻 𝗣𝗮𝘆𝗺𝗲𝗻𝘁", callback_data="set_coin_payment_numbers"
        ),
    )
    markup.add(
        types.InlineKeyboardButton("📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="broadcast"),
        types.InlineKeyboardButton(
            "🔐 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸", callback_data="toggle_lock"
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀", callback_data="run_all_scripts"
        ),
        types.InlineKeyboardButton("📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", callback_data="stats"),
    )
    markup.add(
        types.InlineKeyboardButton(
            "📂 𝗔𝗹𝗹 𝗨𝘀𝗲𝗿 𝗙𝗶𝗹𝗲𝘀", callback_data="admin_user_files"
        ),
    )
    return markup


# --- Core User Logic ---
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ **Bot is temporarily locked by Admin.**")
        return

    if user_id not in active_users:
        add_active_user(user_id)

    if user_id == OWNER_ID:
        user_status = "👑 **Owner**"
    elif user_id in admin_ids:
        user_status = "🛡️ **Admin**"
    elif (
        user_id in user_subscriptions
        and user_subscriptions[user_id]["expiry"] > datetime.now()
    ):
        sub = user_subscriptions[user_id]
        days_left = (sub["expiry"] - datetime.now()).days
        user_status = f"💎 **{sub.get('plan_name', 'Premium')} Active** ({days_left} Days left)"
    else:
        user_status = "🆓 **No Active Plan**"

    welcome_msg = (
        f"✨ **𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {user_name}!** ✨\n\n"
        f"🆔 **𝗬𝗼𝘂𝗿 𝗜𝗗:** `{user_id}`\n"
        f"🔰 **𝗦𝘁𝗮𝘁𝘂𝘀:** {user_status}\n"
        f"🪙 **𝗖𝗼𝗶𝗻𝘀:** `{get_coin_balance(user_id)}`\n"
        f"📁 **𝗨𝗽𝗹𝗼𝗮𝗱𝗲𝗱 𝗙𝗶𝗹𝗲𝘀:** `{get_user_file_count(user_id)}` / `Unlimited`\n\n"
        f"💡 **𝗛𝗼𝘀𝘁 & 𝗥𝘂𝗻 𝘆𝗼𝘂𝗿 𝗣𝘆𝘁𝗵𝗼𝗻 (.𝗽𝘆) & 𝗝𝗦 (.𝗷𝘀) 𝗯𝗼𝘁𝘀 𝟮𝟰/𝟳.**\n"
        f"👇 *Select an option from the menu below:* "
    )
    bot.send_message(
        chat_id,
        welcome_msg,
        reply_markup=create_reply_keyboard_main_menu(user_id),
        parse_mode="Markdown",
    )


def get_referral_stats(user_id):
    """Return (referral_count, earned_coins) for a user."""
    conn = get_db_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
        ).fetchone()[0]
        earned_coins = conn.execute(
            "SELECT COALESCE(SUM(reward_coins), 0) FROM referrals WHERE referrer_id = ?",
            (user_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    return int(count), int(earned_coins)


def _logic_profile(message):
    """Show the user's essential account information in a compact card."""
    user = message.from_user
    user_id = user.id
    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)
    username = getattr(user, "username", None)
    username_text = f"@{username}" if username else "Not set"

    if user_id == OWNER_ID:
        account_status = "Owner"
    elif user_id in admin_ids:
        account_status = "Admin"
    elif has_active_subscription(user_id):
        account_status = "Premium Active"
    else:
        account_status = "Free User"

    subscription = user_subscriptions.get(user_id)
    if subscription and subscription["expiry"] > datetime.now():
        plan_text = subscription.get("plan_name", "Premium")
        expiry_text = subscription["expiry"].strftime("%d %b %Y, %H:%M")
    else:
        plan_text = "No active plan"
        expiry_text = "—"

    profile_text = (
        "👤 <b>MY PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👋 <b>Name:</b> {escape(full_name or 'Not set')}\n"
        f"🔗 <b>Username:</b> {escape(username_text)}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n\n"
        f"🛡️ <b>Status:</b> {escape(account_status)}\n"
        f"💎 <b>Plan:</b> {escape(plan_text)}\n"
        f"📅 <b>Expiry:</b> {escape(expiry_text)}\n"
        f"🪙 <b>Coins:</b> <code>{get_coin_balance(user_id)}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    bot.reply_to(
        message,
        profile_text,
        reply_markup=create_reply_keyboard_main_menu(user_id),
        parse_mode="HTML",
    )


def _logic_referral(message, user_id=None):
    user_id = user_id or message.from_user.id
    referral_reward = get_referral_reward_coins()
    run_cost = get_bot_run_cost_coins()
    referral_count, earned_coins = get_referral_stats(user_id)
    username = get_bot_username()
    if username:
        referral_link = f"https://t.me/{username}?start=ref_{user_id}"
        link_text = f"🔗 **আপনার Referral Link:**\n`{referral_link}`"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "📤 Share Referral Link",
                url=f"https://t.me/share/url?url={referral_link}",
            )
        )
    else:
        link_text = (
            "⚠️ Referral link তৈরি করা যাচ্ছে না। বটের username সেট করা আছে কিনা দেখুন।"
        )
        markup = None

    bot.reply_to(
        message,
        f"🪙 **Referral & Coin Wallet**\n\n"
        f"{link_text}\n\n"
        f"✅ একজন নতুন ইউজার আপনার লিংক দিয়ে প্রথমবার `/start` করলে "
        f"আপনি **{referral_reward} কয়েন** পাবেন।\n"
        f"👥 মোট referral: **{referral_count} জন**\n"
        f"🎁 Referral থেকে earned: **{earned_coins} কয়েন**\n"
        f"▶️ একটি বট চালাতে খরচ: **{run_cost} কয়েন**\n"
        f"💰 বর্তমান ব্যালেন্স: **{get_coin_balance(user_id)} কয়েন**",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def _logic_buy_coins(message):
    """Show the configured coin package and manual deposit options."""
    coins = get_coin_package_coins()
    price = get_coin_package_price_bdt()
    bkash_number = get_coin_payment_number("bKash")
    nagad_number = get_coin_payment_number("Nagad")
    markup = types.InlineKeyboardMarkup(row_width=2)
    if bkash_number:
        markup.add(
            types.InlineKeyboardButton(
                "📱 Deposit via bKash", callback_data="buy_coins_bkash"
            )
        )
    if nagad_number:
        markup.add(
            types.InlineKeyboardButton(
                "📱 Deposit via Nagad", callback_data="buy_coins_nagad"
            )
        )
    payment_text = (
        f"📱 bKash: `{bkash_number}`\n" if bkash_number else ""
    ) + (f"📱 Nagad: `{nagad_number}`\n" if nagad_number else "")
    if not payment_text:
        payment_text = "⚠️ Admin এখনো coin deposit number সেট করেননি।"

    bot.reply_to(
        message,
        f"🪙 **Buy Coins / Coin Deposit**\n\n"
        f"📦 Package: `{coins}` coins\n"
        f"💰 Price: `{price:g} BDT`\n"
        f"⏱️ প্রতি coin-funded run: `{format_coin_run_duration()}`\n\n"
        f"{payment_text}\n"
        "টাকা পাঠানোর পর payment method বেছে নিয়ে Transaction Code দিন। "
        "Admin approve করলে আপনার wallet-এ coins যোগ হবে।",
        reply_markup=markup if (bkash_number or nagad_number) else None,
        parse_mode="Markdown",
    )


def _logic_view_plans(message_or_call):
    chat_id = (
        message_or_call.chat.id
        if isinstance(message_or_call, telebot.types.Message)
        else message_or_call.message.chat.id
    )
    plans = get_all_plans()

    if not plans:
        bot.send_message(
            chat_id,
            "ℹ️ **বর্তমানে কোনো প্ল্যান উপলব্ধ নেই।**",
            parse_mode="Markdown",
        )
        return

    bot.send_message(
        chat_id,
        "💳 **আপনার জন্য उपलब्ध VIP Plan**\n\n"
        "যে প্ল্যান পছন্দ করবেন সেটির Buy বাটনে গিয়ে বিকাশ বা নগদে টাকা পাঠিয়ে "
        "Transaction Code জমা দিন। Admin approve করার পরেই প্ল্যান চালু হবে।",
        parse_mode="Markdown",
    )

    for plan in plans:
        plan_id, name, limit, price, duration, bkash_number, nagad_number = plan
        card_text = (
            f"📦 **VIP Plan:** `{name}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 **একসাথে চলবে:** `{limit}টি Bot`\n"
            f"⏱️ **মেয়াদ:** `{duration} দিন`\n"
            f"💰 **মূল্য:** `{price}`\n"
            f"📱 **বিকাশ:** `{bkash_number or 'Admin সেট করেননি'}`\n"
            f"📱 **নগদ:** `{nagad_number or 'Admin সেট করেননি'}`\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                f"🛒 Buy {name}",
                callback_data=f"buy_plan_{plan_id}",
            )
        )

        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")


def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ **Bot is locked by Admin.**")
        return

    has_active_plan = False
    plan_name = "None"

    if user_id in admin_ids or user_id == OWNER_ID:
        has_active_plan = True
        plan_name = "Admin / Owner Unlimited"
    elif has_active_subscription(user_id):
        sub = user_subscriptions[user_id]
        has_active_plan = True
        plan_name = sub.get("plan_name", "Premium Plan")

    coin_access = not has_active_plan and can_upload_or_run(user_id)
    if not has_active_plan and not coin_access:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "💳 View Plans & Buy", callback_data="view_plans_cb"
            )
        )
        markup.add(
            types.InlineKeyboardButton(
                "🪙 Refer & Get Coins", callback_data="referral_info"
            )
        )
        bot.reply_to(
            message,
            "❌ **আপনার কোন এক্টিভ প্ল্যান নেই!**\n\n"
            "ফাইল আপলোড/রান করতে একটি প্ল্যান অথবা পর্যাপ্ত রেফারেল কয়েন প্রয়োজন।",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            f"✅ Continue with {plan_name if has_active_plan else 'Coin Access'}",
            callback_data="confirm_plan_upload",
        )
    )
    bot.reply_to(
        message,
        f"🔰 **𝗔𝗰𝘁𝗶𝘃𝗲 𝗣𝗹𝗮𝗻 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱:** `{plan_name}`\n\n"
        f"ফাইল আপলোড চালু করতে নিচের বাটনে সিলেক্ট করুন:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(
            message,
            "📂 **Your Uploaded Files:**\n\n*(No files uploaded yet)*",
            parse_mode="Markdown",
        )
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        if file_type in {"py", "js"}:
            is_running = is_bot_running(user_id, file_name)
            status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        else:
            status_icon = "🗃️ Data file"
        btn_text = f"📄 {file_name} ({file_type}) - {status_icon}"
        markup.add(
            types.InlineKeyboardButton(
                btn_text, callback_data=f"file_{user_id}_{file_name}"
            )
        )
    bot.reply_to(
        message,
        "📁 **𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀:**",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def create_user_data_archive(user_id):
    """Create a ZIP snapshot of everything in one user's persistent folder."""
    user_folder = get_user_folder(user_id)
    files_to_archive = []
    for root, directories, filenames in os.walk(user_folder):
        directories[:] = [
            directory
            for directory in directories
            if directory != "__pycache__"
        ]
        for filename in filenames:
            file_path = os.path.join(root, filename)
            if os.path.isfile(file_path) and not os.path.islink(file_path):
                relative_path = os.path.relpath(file_path, user_folder)
                files_to_archive.append((file_path, relative_path))

    if not files_to_archive:
        return None

    archive_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f"bot_data_{user_id}_",
            suffix=".zip",
            dir=tempfile.gettempdir(),
            delete=False,
        ) as archive_file:
            archive_path = archive_file.name

        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for file_path, relative_path in files_to_archive:
                archive.write(file_path, arcname=relative_path)

        if os.path.getsize(archive_path) > MAX_EXPORT_ARCHIVE_BYTES:
            raise ValueError(
                f"আপনার data archive Telegram-এর {MAX_EXPORT_ARCHIVE_BYTES // (1024 * 1024)} MB "
                "সীমার চেয়ে বড়।"
            )
        return archive_path
    except Exception:
        if archive_path and os.path.exists(archive_path):
            os.remove(archive_path)
        raise


def send_user_data_archive(chat_id, user_id, requester_id=None):
    """Send a user's complete persistent folder after checking access."""
    if requester_id is not None and not can_manage_file(requester_id, user_id):
        bot.send_message(chat_id, "❌ এই data backup download করার অনুমতি নেই।")
        return False

    archive_path = create_user_data_archive(user_id)
    if not archive_path:
        if requester_id == user_id:
            bot.send_message(chat_id, "📂 আপনার download করার মতো কোনো file নেই।")
        else:
            bot.send_message(chat_id, "📂 এই user-এর download করার মতো কোনো file নেই।")
        return False

    try:
        with open(archive_path, "rb") as archive_file:
            bot.send_document(
                chat_id,
                archive_file,
                caption=(
                    "📦 আপনার সম্পূর্ণ bot data backup\n"
                    "এর মধ্যে uploaded code, JSON, database, নতুন data এবং log আছে।"
                ),
            )
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)
    return True


def send_single_user_file(chat_id, owner_id, file_name):
    """Send one stored file after its ownership and filename were verified."""
    if not safe_upload_name(file_name):
        bot.send_message(chat_id, "❌ অবৈধ filename।")
        return False
    if not any(name == file_name for name, _ in user_files.get(owner_id, [])):
        bot.send_message(chat_id, "❌ ফাইল পাওয়া যায়নি।")
        return False

    file_path = os.path.join(get_user_folder(owner_id), file_name)
    if not os.path.isfile(file_path):
        bot.send_message(chat_id, "❌ ফাইলটি storage-এ পাওয়া যায়নি।")
        return False

    with open(file_path, "rb") as file_handle:
        bot.send_document(
            chat_id,
            file_handle,
            caption=f"📄 User `{owner_id}`-এর file: `{file_name}`",
            parse_mode="Markdown",
        )
    return True


def send_admin_user_list(chat_id):
    """Show every user who has persisted files, including running counts."""
    users_with_files = [
        (owner_id, entries)
        for owner_id, entries in user_files.items()
        if entries
    ]
    if not users_with_files:
        bot.send_message(chat_id, "📂 কোনো user file পাওয়া যায়নি।")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for owner_id, entries in sorted(users_with_files):
        running_count = sum(
            1
            for file_name, file_type in entries
            if file_type in {"py", "js"} and is_bot_running(owner_id, file_name)
        )
        markup.add(
            types.InlineKeyboardButton(
                f"👤 {owner_id} · {len(entries)} files · 🟢 {running_count} running",
                callback_data=f"admin_user_files_{owner_id}",
            )
        )
    bot.send_message(
        chat_id,
        "📂 **All User Files**\n\nএকজন user নির্বাচন করে তার running status "
        "দেখুন। Admin এখান থেকে কোনো user file download করতে পারবেন না।",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def send_admin_user_file_list(chat_id, owner_id):
    """Show one user's stored files without any download controls."""
    entries = sorted(user_files.get(owner_id, []))
    if not entries:
        bot.send_message(chat_id, "📂 এই user-এর কোনো stored file নেই।")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in entries:
        if file_type in {"py", "js"}:
            status = "🟢 Running" if is_bot_running(owner_id, file_name) else "🔴 Stopped"
        else:
            status = "🗃️ Data"
        markup.add(
            types.InlineKeyboardButton(
                f"👁️ {file_name} ({file_type}) · {status}",
                callback_data=f"file_{owner_id}_{file_name}",
            )
        )
    markup.add(
        types.InlineKeyboardButton(
            "⬅️ Back to All Users", callback_data="admin_user_files"
        )
    )
    bot.send_message(
        chat_id,
        f"📂 **User `{owner_id}` Files**\n"
        "🟢 Running · 🔴 Stopped · 🗃️ Data file\n"
        "👁️ Admin শুধু file status দেখতে পারবেন; download করতে পারবেন না।",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def extract_zip_scripts(file_content):
    """Extract safe code and persistent data files from a ZIP archive."""
    scripts = []
    seen_names = set()
    total_size = 0
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/")
                if (
                    normalized.startswith("/")
                    or normalized.startswith("../")
                    or "/../" in normalized
                ):
                    raise ValueError("ZIP-এর ভিতরে অনিরাপদ path পাওয়া গেছে")
                safe_name = safe_upload_name(os.path.basename(normalized))
                if not safe_name:
                    raise ValueError("ZIP-এর ভিতরে অনিরাপদ filename পাওয়া গেছে")
                if os.path.splitext(safe_name)[1].lower() not in (
                    RUNNABLE_FILE_EXTENSIONS | DATA_FILE_EXTENSIONS
                ):
                    continue
                if safe_name in seen_names:
                    raise ValueError(f"ZIP-এ একই filename একাধিকবার আছে: {safe_name}")
                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted ZIP ফাইল অনুমোদিত নয়")
                total_size += info.file_size
                if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise ValueError("ZIP ফাইলের মোট uncompressed size সীমা ছাড়িয়েছে")
                if len(scripts) >= MAX_ZIP_SCRIPTS:
                    raise ValueError(
                        f"একটি ZIP-এ সর্বোচ্চ {MAX_ZIP_SCRIPTS}টি file রাখা যাবে"
                    )
                scripts.append((safe_name, archive.read(info)))
                seen_names.add(safe_name)
    except zipfile.BadZipFile as exc:
        raise ValueError("সঠিক ZIP ফাইল নয়") from exc

    if not scripts:
        raise ValueError(
            "ZIP-এর ভিতরে কোনো supported .py, .js, .json বা .db file পাওয়া যায়নি"
        )
    return scripts


def request_code_replacement(actor_id, owner_id, file_name):
    """Remember which runnable file the next document should replace."""
    pending_code_replacements[actor_id] = {
        "owner_id": owner_id,
        "file_name": file_name,
        "created_at": time.time(),
    }


def process_code_replacement(message, replacement):
    """Replace only a selected .py/.js file and preserve its user folder."""
    actor_id = message.from_user.id
    owner_id = int(replacement["owner_id"])
    target_name = replacement["file_name"]

    if not can_manage_file(actor_id, owner_id):
        bot.reply_to(message, "❌ এই coding file replace করার অনুমতি নেই।")
        return
    if not safe_upload_name(target_name):
        bot.reply_to(message, "❌ অবৈধ coding filename।")
        return

    target_entry = next(
        (
            (name, file_type)
            for name, file_type in user_files.get(owner_id, [])
            if name == target_name
        ),
        None,
    )
    if not target_entry or target_entry[1] not in {"py", "js"}:
        bot.reply_to(message, "❌ শুধু `.py` বা `.js` coding file replace করা যাবে।")
        return

    incoming_name = safe_upload_name(message.document.file_name)
    incoming_ext = os.path.splitext(incoming_name or "")[1].lower()
    target_ext = os.path.splitext(target_name)[1].lower()
    if incoming_ext not in RUNNABLE_FILE_EXTENSIONS:
        bot.reply_to(message, "❌ Replace করতে শুধু `.py` অথবা `.js` file পাঠান।")
        return
    if incoming_ext != target_ext:
        bot.reply_to(
            message,
            f"❌ `{target_name}` replace করতে একই `{target_ext}` extension-এর file দিন।",
            parse_mode="Markdown",
        )
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        content = bot.download_file(file_info.file_path)
        if len(content) > MAX_UPLOAD_BYTES:
            bot.reply_to(
                message,
                f"❌ নতুন coding file-এর size সর্বোচ্চ "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB হতে পারে।",
            )
            return
        if owner_id != OWNER_ID:
            is_safe, reason = scan_file_for_malware(content, target_name, owner_id)
            if not is_safe:
                bot.reply_to(message, f"🚨 **Security Alert:** {reason}", parse_mode="Markdown")
                return

        user_folder = get_user_folder(owner_id)
        target_path = os.path.join(user_folder, target_name)
        if not os.path.isfile(target_path):
            bot.reply_to(message, "❌ পুরোনো coding file storage-এ পাওয়া যায়নি।")
            return

        script_key = f"{owner_id}_{target_name}"
        was_running = is_bot_running(owner_id, target_name)
        if was_running and script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target_name}.",
                suffix=".replace",
                dir=user_folder,
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.write(content)
            os.replace(temp_path, target_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        pending_code_replacements.pop(actor_id, None)
        bot.reply_to(
            message,
            f"✅ `{target_name}` coding file সফলভাবে replace হয়েছে।\n"
            "🗃️ আগের JSON/database/data/log একই user folder-এ রাখা হয়েছে।\n"
            + ("🛑 পুরোনো running bot stop করা হয়েছে। এখন চাইলে আবার Run করুন।"
               if was_running
               else "▶️ নতুন code চালাতে Manage Files থেকে Run করুন।"),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception(
            "Could not replace file %s for user %s", target_name, owner_id
        )
        bot.reply_to(message, "❌ Coding file replace করা যায়নি।")


# --- Document Upload Processing ---
@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document

    replacement = pending_code_replacements.get(user_id)
    if replacement:
        if time.time() - replacement.get("created_at", 0) > 900:
            pending_code_replacements.pop(user_id, None)
        else:
            process_code_replacement(message, replacement)
            return

    if not can_upload_or_run(user_id):
        bot.reply_to(
            message,
            "❌ **আপনার পর্যাপ্ত access নেই!**\n"
            "ফাইল আপলোড/রান করতে একটি active plan অথবা referral coins প্রয়োজন।",
            parse_mode="Markdown",
        )
        return

    file_name = safe_upload_name(doc.file_name)
    if not file_name:
        bot.reply_to(message, "❌ অনিরাপদ বা অবৈধ filename ব্যবহার করা যাবে না।")
        return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in SUPPORTED_UPLOAD_EXTENSIONS:
        bot.reply_to(
            message,
            "⚠️ শুধু `.py`, `.js`, `.json`, `.db` এবং `.zip` files supported।",
            parse_mode="Markdown",
        )
        return

    try:
        download_wait_msg = bot.reply_to(
            message,
            f"⏳ **Downloading `{file_name}`...**",
            parse_mode="Markdown",
        )
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        if len(downloaded_file_content) > MAX_UPLOAD_BYTES:
            bot.edit_message_text(
                f"❌ ফাইলের size সর্বোচ্চ {MAX_UPLOAD_BYTES // (1024 * 1024)} MB হতে পারে।",
                chat_id,
                download_wait_msg.message_id,
            )
            return

        user_folder = get_user_folder(user_id)
        if file_ext == ".zip":
            uploaded_files = extract_zip_scripts(downloaded_file_content)
        else:
            uploaded_files = [(file_name, downloaded_file_content)]

        for script_name, script_content in uploaded_files:
            if user_id != OWNER_ID:
                is_safe, reason = scan_file_for_malware(
                    script_content, script_name, user_id
                )
                if not is_safe:
                    bot.edit_message_text(
                        f"🚨 **Security Alert:** {reason}",
                        chat_id,
                        download_wait_msg.message_id,
                        parse_mode="Markdown",
                    )
                    return

        existing_names = {name for name, _ in user_files.get(user_id, [])}
        new_names = [name for name, _ in uploaded_files if name not in existing_names]
        file_limit = get_user_file_limit(user_id)
        if file_limit != float("inf") and len(existing_names) + len(new_names) > file_limit:
            bot.edit_message_text(
                f"❌ আপনার file limit `{int(file_limit)}`। "
                f"নতুন file: `{len(new_names)}`।",
                chat_id,
                download_wait_msg.message_id,
                parse_mode="Markdown",
            )
            return

        runnable_files = [
            (name, content)
            for name, content in uploaded_files
            if os.path.splitext(name)[1].lower() in RUNNABLE_FILE_EXTENSIONS
        ]
        bot_limit = get_user_bot_limit(user_id)
        running_count = get_running_bot_count(user_id)
        if (
            bot_limit != float("inf")
            and running_count + len(runnable_files) > bot_limit
        ):
            bot.edit_message_text(
                f"❌ আপনার plan-এ একসাথে সর্বোচ্চ `{int(bot_limit)}`টি bot চলতে পারবে।\n"
                f"🟢 এখন চলছে: `{running_count}`টি\n"
                f"📤 এই upload-এ চালু হবে: `{len(runnable_files)}`টি",
                chat_id,
                download_wait_msg.message_id,
                parse_mode="Markdown",
            )
            return

        run_cost = get_bot_run_cost_coins()
        if (
            user_id not in admin_ids
            and user_id != OWNER_ID
            and not has_active_subscription(user_id)
            and get_coin_balance(user_id) < len(runnable_files) * run_cost
        ):
            bot.edit_message_text(
                f"❌ এই upload-এর {len(runnable_files)}টি bot চালাতে "
                f"`{len(runnable_files) * run_cost}` কয়েন প্রয়োজন।",
                chat_id,
                download_wait_msg.message_id,
                parse_mode="Markdown",
            )
            return

        for script_name, script_content in uploaded_files:
            script_path = os.path.join(user_folder, script_name)
            with open(script_path, "wb") as f:
                f.write(script_content)
            script_ext = os.path.splitext(script_name)[1].lower()
            save_user_file(user_id, script_name, script_ext[1:])

        bot.edit_message_text(
            f"✅ **{len(uploaded_files)}টি file সফলভাবে upload হয়েছে!**\n"
            f"▶️ Auto-run হবে: `{len(runnable_files)}`টি code file\n"
            f"🗃️ Data file রাখা হয়েছে: "
            f"`{len(uploaded_files) - len(runnable_files)}`টি",
            chat_id,
            download_wait_msg.message_id,
            parse_mode="Markdown",
        )

        for script_name, _ in runnable_files:
            script_path = os.path.join(user_folder, script_name)
            script_ext = os.path.splitext(script_name)[1].lower()
            if script_ext == ".js":
                threading.Thread(
                    target=run_js_script,
                    args=(script_path, user_id, user_folder, script_name, message),
                    daemon=True,
                ).start()
            else:
                threading.Thread(
                    target=run_script,
                    args=(script_path, user_id, user_folder, script_name, message),
                    daemon=True,
                ).start()

    except Exception as e:
        bot.reply_to(message, f"❌ **Error:** {str(e)}")


# --- Callback Routing ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    if data == "view_plans_cb":
        bot.answer_callback_query(call.id)
        _logic_view_plans(call)

    elif data == "referral_info":
        bot.answer_callback_query(call.id)
        _logic_referral(call.message, user_id)

    elif data in {"buy_coins_bkash", "buy_coins_nagad"}:
        method = "bKash" if data.endswith("bkash") else "Nagad"
        payment_number = get_coin_payment_number(method)
        if not payment_number:
            bot.answer_callback_query(
                call.id, f"{method} number সেট করা হয়নি।", show_alert=True
            )
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            f"📱 **{method} Coin Deposit**\n\n"
            f"এই নম্বরে `{get_coin_package_price_bdt():g} BDT` পাঠান:\n"
            f"`{payment_number}`\n\n"
            "টাকা পাঠানোর পর শুধু Transaction Code লিখে পাঠান। "
            "Admin approve করলে coins যোগ হবে।",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(
            msg, lambda m: process_coin_payment(m, method)
        )

    elif data == "confirm_plan_upload":
        bot.answer_callback_query(call.id, "✅ Plan Verified!")
        bot.send_message(
            call.message.chat.id,
            "🚀 **এখন আপনার `.py`, `.js`, `.json`, `.db` অথবা এগুলোসহ "
            "একটি `.zip` ফাইল মেসেজে পাঠান।**\n"
            "একই user folder-এ পুরোনো data রাখা থাকবে এবং শুধু code file auto-run হবে।",
            parse_mode="Markdown",
        )

    # --- Interactive Module Installer Handler ---
    elif data.startswith("instmod_"):
        _, owner_id, mod_name, fname = data.split("_", 3)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id,
                "❌ আপনি অন্য ইউজারের ফাইল কাস্টমাইজ করতে পারবেন না!",
                show_alert=True,
            )
            return
        if not safe_upload_name(fname) or not any(
            name == fname for name, _ in user_files.get(owner_id, [])
        ):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        pkg_name = TELEGRAM_MODULES.get(mod_name.lower(), mod_name)
        ext = os.path.splitext(fname)[1].lower()

        status_msg = bot.send_message(
            call.message.chat.id,
            f"⏳ **`{pkg_name}` মডিউলটি ইনস্টল করা হচ্ছে...**",
            parse_mode="Markdown",
        )

        def do_pip_install():
            if ext == ".js":
                cmd = ["npm", "install", pkg_name]
            else:
                cmd = get_python_package_install_command([pkg_name])
                if not cmd:
                    bot.edit_message_text(
                        "❌ এই Python environment-এ pip বা uv package installer পাওয়া যায়নি।",
                        call.message.chat.id,
                        status_msg.message_id,
                    )
                    return

            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=PYTHON_DEPENDENCY_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                bot.edit_message_text(
                    f"❌ Package install timeout হয়েছে "
                    f"({PYTHON_DEPENDENCY_TIMEOUT_SECONDS} সেকেন্ড)।",
                    call.message.chat.id,
                    status_msg.message_id,
                )
                return
            except OSError as exc:
                bot.edit_message_text(
                    f"❌ Package installer চালু করা যায়নি: {str(exc)[:300]}",
                    call.message.chat.id,
                    status_msg.message_id,
                )
                return

            if res.returncode == 0:
                bot.edit_message_text(
                    f"✅ **`{pkg_name}` মডিউলটি সফলভাবে ইনস্টল হয়েছে!**\n🚀 ফাইলটি পুনরায় চালু করা হচ্ছে...",
                    call.message.chat.id,
                    status_msg.message_id,
                    parse_mode="Markdown",
                )
                time.sleep(1)
                ufolder = get_user_folder(owner_id)
                fpath = os.path.join(ufolder, fname)
                if ext == ".js":
                    run_js_script(
                        fpath, owner_id, ufolder, fname, call.message
                    )
                else:
                    run_script(
                        fpath, owner_id, ufolder, fname, call.message
                    )
            else:
                bot.edit_message_text(
                    f"❌ **ইনস্টলেশন ব্যর্থ হয়েছে!**\n\n```\n{res.stderr[:300]}\n```",
                    call.message.chat.id,
                    status_msg.message_id,
                    parse_mode="Markdown",
                )

        threading.Thread(target=do_pip_install).start()

    # --- Error Log Viewer Handler ---
    elif data.startswith("viewlog_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইলের log দেখার অনুমতি নেই।", show_alert=True
            )
            return
        if not safe_upload_name(fname):
            bot.answer_callback_query(call.id, "অবৈধ filename।", show_alert=True)
            return
        ufolder = get_user_folder(int(owner_id))
        log_fpath = os.path.join(
            ufolder, f"{os.path.splitext(fname)[0]}.log"
        )
        if os.path.exists(log_fpath):
            with open(log_fpath, "r", encoding="utf-8", errors="ignore") as f:
                logs = f.read()[-2000:]
            bot.send_message(
                call.message.chat.id,
                f"📜 **Error Log for `{fname}`:**\n\n```\n{logs if logs else 'No logs recorded.'}\n```",
                parse_mode="Markdown",
            )
        else:
            bot.answer_callback_query(
                call.id, "No log file found!", show_alert=True
            )

    # --- Manual bKash/Nagad payment flow ---
    elif data.startswith("buy_plan_"):
        plan_id = int(data.split("_")[2])
        plan = get_plan_by_id(plan_id)
        if not plan:
            bot.answer_callback_query(call.id, "Plan not found!")
            return
        bot.answer_callback_query(call.id)
        _, name, limit, price, duration, bkash_number, nagad_number = plan
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "📱 bKash দিয়ে পেমেন্ট", callback_data=f"pay_bkash_{plan_id}"
            ),
            types.InlineKeyboardButton(
                "📱 নগদ দিয়ে পেমেন্ট", callback_data=f"pay_nagad_{plan_id}"
            ),
        )
        bot.send_message(
            call.message.chat.id,
            f"💎 **{name}**\n"
            f"🤖 একসাথে চলবে: `{limit}`টি bot\n"
            f"⏱️ মেয়াদ: `{duration}` দিন\n"
            f"💰 দিতে হবে: `{price}`\n\n"
            "Payment method বেছে নিন। টাকা পাঠানোর পর Transaction Code জমা "
            "দিলে Admin যাচাই করে approve করবেন।",
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif data.startswith("pay_bkash_") or data.startswith("pay_nagad_"):
        plan_id = int(data.split("_")[2])
        method = "bKash" if data.startswith("pay_bkash_") else "Nagad"
        plan = get_plan_by_id(plan_id)
        if not plan:
            bot.answer_callback_query(call.id, "Plan not found!", show_alert=True)
            return
        number = plan[5] if method == "bKash" else plan[6]
        if not number:
            bot.answer_callback_query(
                call.id, f"{method} number সেট করা হয়নি", show_alert=True
            )
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            f"📱 **{method} পেমেন্ট**\n\n"
            f"এই নম্বরে `{plan[3]}` পাঠান:\n`{number}`\n\n"
            "টাকা পাঠানোর পর শুধু Transaction Code লিখে পাঠান। "
            "Admin approve না করা পর্যন্ত plan active হবে না।",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(
            msg, lambda m: process_manual_payment(m, plan_id, method)
        )

    # --- Admin Callbacks ---
    elif data == "add_plan_init" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "📝 **VIP Plan details দিন**\n\n"
            "`PlanName | MaxBots | PriceBDT | DurationDays | bKashNumber | NagadNumber`\n\n"
            "উদাহরণ:\n"
            "`VIP 1 | 2 | 500 | 30 | 01XXXXXXXXX | 01XXXXXXXXX`\n\n"
            "প্রতিটি plan-এর bot limit, দাম, মেয়াদ ও দুই payment number আপনার ইচ্ছামতো দিন।",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_add_plan)

    elif data == "manage_plans" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        plans = get_all_plans()
        if not plans:
            bot.send_message(call.message.chat.id, "No plans found.")
            return
        markup = types.InlineKeyboardMarkup()
        for p in plans:
            markup.add(
                types.InlineKeyboardButton(
                    f"✏️ Edit {p[1]}", callback_data=f"edit_plan_{p[0]}"
                ),
                types.InlineKeyboardButton(
                    "🗑️ Delete", callback_data=f"del_plan_{p[0]}"
                ),
            )
        bot.send_message(
            call.message.chat.id,
            "🗑️ **Select a Plan to Delete:**",
            reply_markup=markup,
        )

    elif data.startswith("edit_plan_") and user_id in admin_ids:
        pid = int(data.split("_")[2])
        if not get_plan_by_id(pid):
            bot.answer_callback_query(call.id, "Plan not found!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "✏️ নতুন details দিন:\n"
            "`PlanName | MaxBots | PriceBDT | DurationDays | bKashNumber | NagadNumber`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, lambda m: process_edit_plan(m, pid))

    elif data.startswith("del_plan_") and user_id in admin_ids:
        pid = int(data.split("_")[2])
        delete_plan_db(pid)
        bot.answer_callback_query(call.id, "Plan Deleted!")
        bot.send_message(call.message.chat.id, "✅ Plan successfully deleted.")

    elif data == "pending_payments" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        requests_list = get_pending_payment_requests()
        if not requests_list:
            bot.send_message(call.message.chat.id, "✅ কোনো pending payment নেই।")
            return
        for req in requests_list:
            rid, payer_id, plan_id, method, code, amount, created_at = req
            plan = get_plan_by_id(plan_id)
            plan_name = plan[1] if plan else "Deleted plan"
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "✅ Approve", callback_data=f"approve_payment_{rid}"
                ),
                types.InlineKeyboardButton(
                    "❌ Reject", callback_data=f"reject_payment_{rid}"
                ),
            )
            bot.send_message(
                call.message.chat.id,
                f"🧾 **Payment Request #{rid}**\n"
                f"👤 User ID: `{payer_id}`\n"
                f"💎 Plan: `{plan_name}`\n"
                f"📱 Method: `{method}`\n"
                f"💰 Amount: `{amount:g} BDT`\n"
                f"🔐 Transaction Code: `{code}`\n"
                f"🕒 সময়: `{created_at[:19]}`",
                reply_markup=markup,
                parse_mode="Markdown",
            )

    elif data == "pending_coin_payments" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        requests_list = get_pending_coin_payment_requests()
        if not requests_list:
            bot.send_message(call.message.chat.id, "✅ কোনো pending coin deposit নেই।")
            return
        for req in requests_list:
            rid, payer_id, method, code, amount, coins, created_at = req
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "✅ Approve Coins",
                    callback_data=f"approve_coin_payment_{rid}",
                ),
                types.InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_coin_payment_{rid}",
                ),
            )
            bot.send_message(
                call.message.chat.id,
                f"🪙 **Coin Deposit Request #{rid}**\n"
                f"👤 User: `{payer_id}`\n"
                f"📱 Method: `{method}`\n"
                f"💰 Amount: `{amount:g} BDT`\n"
                f"🪙 Coins: `{coins}`\n"
                f"🔐 Transaction Code: `{code}`\n"
                f"🕒 সময়: `{created_at[:19]}`",
                reply_markup=markup,
                parse_mode="Markdown",
            )

    elif (
        data.startswith("approve_coin_payment_")
        or data.startswith("reject_coin_payment_")
    ) and user_id in admin_ids:
        request_id = int(data.rsplit("_", 1)[1])
        approve = data.startswith("approve_coin_payment_")
        row, error = review_coin_payment_request(request_id, user_id, approve)
        if error:
            bot.answer_callback_query(call.id, error, show_alert=True)
            return
        bot.answer_callback_query(call.id, "Approved" if approve else "Rejected")
        payer_id, method, code, amount, coins = row[1], row[2], row[3], row[4], row[5]
        if approve:
            balance = add_coins(payer_id, coins)
            bot.send_message(
                payer_id,
                f"🎉 আপনার coin deposit approve হয়েছে!\n"
                f"🪙 যোগ হয়েছে: `{coins}` coins\n"
                f"💰 বর্তমান balance: `{balance}` coins",
                parse_mode="Markdown",
            )
            bot.send_message(
                call.message.chat.id,
                f"✅ User `{payer_id}`-কে `{coins}` coins যোগ করা হয়েছে।",
                parse_mode="Markdown",
            )
        else:
            bot.send_message(
                payer_id,
                f"❌ আপনার `{amount:g} BDT` coin deposit reject করা হয়েছে। "
                "সঠিক Transaction Code দিয়ে আবার চেষ্টা করুন।",
            )

    elif (
        data.startswith("approve_payment_") or data.startswith("reject_payment_")
    ) and user_id in admin_ids:
        request_id = int(data.rsplit("_", 1)[1])
        approve = data.startswith("approve_payment_")
        row, error = review_payment_request(request_id, user_id, approve)
        if error:
            bot.answer_callback_query(call.id, error, show_alert=True)
            return
        bot.answer_callback_query(call.id, "Approved" if approve else "Rejected")
        payer_id, plan_id = row[1], row[2]
        plan = get_plan_by_id(plan_id)
        if approve and plan:
            _, name, max_bots, _, duration, _, _ = plan
            expiry = datetime.now() + timedelta(days=duration)
            save_subscription(payer_id, name, expiry, plan_id, max_bots)
            bot.send_message(
                payer_id,
                f"🎉 আপনার payment approve হয়েছে!\n"
                f"💎 Plan: `{name}`\n"
                f"🤖 একসাথে চলবে: `{max_bots}`টি bot\n"
                f"📅 মেয়াদ শেষ: `{expiry.strftime('%Y-%m-%d %H:%M')}`",
                parse_mode="Markdown",
            )
            bot.send_message(
                call.message.chat.id,
                f"✅ User `{payer_id}`-এর `{name}` plan active হয়েছে।",
                parse_mode="Markdown",
            )
        else:
            bot.send_message(
                payer_id,
                "❌ আপনার payment request reject করা হয়েছে। সঠিক Transaction Code "
                "দিয়ে আবার চেষ্টা করুন অথবা Admin-এর সাথে যোগাযোগ করুন।",
            )

    elif data == "add_subscription" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "💎 **Enter User ID, Plan Name & Days:**\nFormat: `UserID PlanName Days`\n*Example:* `123456789 VIP 30`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_add_subscription)

    elif data == "add_admin" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "👑 যে User-কে admin করতে চান তার Telegram User ID দিন:",
        )
        bot.register_next_step_handler(msg, process_add_admin)

    elif data == "remove_admin" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "➖ যে admin-কে remove করতে চান তার Telegram User ID দিন:",
        )
        bot.register_next_step_handler(msg, process_remove_admin)

    elif data == "broadcast" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id, "📣 যে message broadcast করতে চান সেটি লিখুন:"
        )
        bot.register_next_step_handler(msg, process_broadcast)

    elif data == "coin_settings" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"🪙 **Coin Control Settings**\n\n"
            f"🎁 Referral reward: `{get_referral_reward_coins()}` coins\n"
            f"▶️ Bot run cost: `{get_bot_run_cost_coins()}` coins\n"
            f"⏱️ Coin run time: `{format_coin_run_duration()}` per coin run\n"
            f"📦 Coin package: `{get_coin_package_coins()}` coins = "
            f"`{get_coin_package_price_bdt():g} BDT`\n"
            f"📱 bKash: `{get_coin_payment_number('bKash') or 'Not set'}`\n"
            f"📱 Nagad: `{get_coin_payment_number('Nagad') or 'Not set'}`\n\n"
            "নিচের Admin Panel buttons দিয়ে এগুলো পরিবর্তন বা নির্দিষ্ট "
            "ইউজারের coins add/remove করুন।",
            reply_markup=create_admin_panel_inline(),
            parse_mode="Markdown",
        )

    elif data == "add_coins" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "➕ Format: `TelegramUserID Amount`\nউদাহরণ: `123456789 25`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(
            msg, lambda m: process_coin_adjustment(m, "add")
        )

    elif data == "remove_coins" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "➖ Format: `TelegramUserID Amount`\nউদাহরণ: `123456789 10`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(
            msg, lambda m: process_coin_adjustment(m, "remove")
        )

    elif data == "set_referral_reward" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🎁 নতুন referral reward কত coins হবে? শুধু একটি positive number দিন:",
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_set_coin_setting(
                m, "referral_reward_coins", "Referral reward"
            ),
        )

    elif data == "set_run_cost" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "⚙️ একটি bot run করতে কত coins লাগবে? শুধু একটি positive number দিন:",
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_set_coin_setting(
                m, "bot_run_cost_coins", "Bot run cost"
            ),
        )

    elif data == "set_coin_duration" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "⏱️ Coin দিয়ে চালানো একটি bot কতক্ষণ চলবে?\n"
            "Format: `12 hours` অথবা `2 days`\n"
            "উদাহরণ: `48 hours`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_set_coin_duration)

    elif data == "set_coin_price" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "💰 Coin package-এর দাম সেট করুন:\n"
            "Format: `Coins | PriceBDT`\n"
            "উদাহরণ: `10 | 100`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_set_coin_price)

    elif data == "set_coin_payment_numbers" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "📱 Coin deposit-এর payment number দিন:\n"
            "Format: `bKashNumber | NagadNumber`\n"
            "উদাহরণ: `01XXXXXXXXX | 01XXXXXXXXX`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_set_coin_payment_numbers)

    elif data == "toggle_lock" and user_id in admin_ids:
        global bot_locked
        bot_locked = not bot_locked
        bot.answer_callback_query(call.id, f"Bot Locked: {bot_locked}")
        bot.send_message(
            call.message.chat.id,
            f"🔐 **Bot status changed to:** `{'Locked' if bot_locked else 'Unlocked'}`",
            parse_mode="Markdown",
        )

    elif data == "stats" and user_id in admin_ids:
        conn = get_db_connection()
        try:
            file_total = conn.execute(
                "SELECT COUNT(*) FROM user_files"
            ).fetchone()[0]
            coin_total = conn.execute(
                "SELECT COALESCE(SUM(balance), 0) FROM user_coins"
            ).fetchone()[0]
        finally:
            conn.close()
        running_total = sum(
            1 for info in list(bot_scripts.values()) if info.get("process")
        )
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"📊 **Bot Statistics**\n"
            f"👥 Active users: `{len(active_users)}`\n"
            f"📁 Stored files: `{file_total}`\n"
            f"🚀 Running bots: `{running_total}`\n"
            f"🪙 Total coins: `{coin_total}`",
            parse_mode="Markdown",
        )

    elif data == "admin_user_files" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        send_admin_user_list(call.message.chat.id)

    elif data.startswith("admin_user_files_") and user_id in admin_ids:
        try:
            owner_id = int(data.rsplit("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "অবৈধ user ID।", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        send_admin_user_file_list(call.message.chat.id, owner_id)

    elif data.startswith("admin_dl_all_") and user_id in admin_ids:
        bot.answer_callback_query(
            call.id,
            "Admin user file download করতে পারবেন না; শুধু দেখতে পারবেন।",
            show_alert=True,
        )

    elif data.startswith("admin_dl_file_") and user_id in admin_ids:
        bot.answer_callback_query(
            call.id,
            "Admin user file download করতে পারবেন না; শুধু দেখতে পারবেন।",
            show_alert=True,
        )

    elif data == "run_all_scripts" and user_id in admin_ids:
        bot.answer_callback_query(call.id, "সব script চালু করা হচ্ছে...")
        started = 0
        for owner_id, files in list(user_files.items()):
            user_folder = get_user_folder(owner_id)
            for fname, file_type in list(files):
                if file_type not in RUNNABLE_FILE_EXTENSIONS:
                    continue
                if is_bot_running(owner_id, fname):
                    continue
                file_path = os.path.join(user_folder, fname)
                if not os.path.isfile(file_path):
                    continue
                runner = run_js_script if file_type == "js" else run_script
                threading.Thread(
                    target=runner,
                    args=(file_path, owner_id, user_folder, fname, call.message),
                    daemon=True,
                ).start()
                started += 1
        bot.send_message(
            call.message.chat.id,
            f"✅ মোট `{started}`টি stopped script চালু করার চেষ্টা করা হয়েছে।",
            parse_mode="Markdown",
        )

    # --- File Management Callbacks ---
    elif data.startswith("file_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল ম্যানেজ করার অনুমতি নেই।", show_alert=True
            )
            return
        if not any(name == fname for name, _ in user_files.get(owner_id, [])):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return
        file_type = next(
            file_type
            for name, file_type in user_files.get(owner_id, [])
            if name == fname
        )
        is_runnable = file_type in RUNNABLE_FILE_EXTENSIONS
        is_running = is_bot_running(owner_id, fname) if is_runnable else False
        markup = types.InlineKeyboardMarkup(row_width=2)
        if is_runnable:
            if is_running:
                markup.add(
                    types.InlineKeyboardButton(
                        "🛑 Stop", callback_data=f"stop_{owner_id}_{fname}"
                    )
                )
            else:
                markup.add(
                    types.InlineKeyboardButton(
                        "▶️ Start", callback_data=f"start_{owner_id}_{fname}"
                    )
                )
            markup.add(
                types.InlineKeyboardButton(
                    "🔄 Restart", callback_data=f"restart_{owner_id}_{fname}"
                )
            )
        else:
            markup.add(
                types.InlineKeyboardButton(
                    "🗃️ Data File (not runnable)",
                    callback_data=f"data_file_info_{owner_id}_{fname}",
                )
            )
        if user_id not in admin_ids:
            markup.add(
                types.InlineKeyboardButton(
                    "📦 Download All Bot Data",
                    callback_data=f"download_all_user_data_{owner_id}",
                )
            )
        if is_runnable:
            markup.add(
                types.InlineKeyboardButton(
                    "🔄 Replace Code File",
                    callback_data=f"replace_code_{owner_id}_{fname}",
                )
            )
        bot.send_message(
            call.message.chat.id,
            f"📄 **File:** `{fname}`\n"
            f"🗂️ Type: `{file_type}`\n"
            + (
                f"🚦 Status: `{'Running' if is_running else 'Stopped'}`"
                if is_runnable
                else "🗃️ Persistent data file — শুধু data হিসেবে ব্যবহার হবে"
            ),
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif data.startswith("data_file_info_"):
        parts = data.split("_", 4)
        if len(parts) != 5:
            bot.answer_callback_query(call.id, "অবৈধ file request।", show_alert=True)
            return
        try:
            owner_id = int(parts[3])
        except ValueError:
            bot.answer_callback_query(call.id, "অবৈধ user ID।", show_alert=True)
            return
        fname = parts[4]
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল ম্যানেজ করার অনুমতি নেই।", show_alert=True
            )
            return
        if not safe_upload_name(fname) or not any(
            name == fname for name, file_type in user_files.get(owner_id, [])
            if file_type in DATA_FILE_EXTENSIONS
        ):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return

        runnable_files = [
            (name, file_type)
            for name, file_type in user_files.get(owner_id, [])
            if file_type in RUNNABLE_FILE_EXTENSIONS
            and os.path.isfile(os.path.join(get_user_folder(owner_id), name))
        ]
        markup = types.InlineKeyboardMarkup(row_width=2)
        for script_name, script_type in sorted(runnable_files):
            running = is_bot_running(owner_id, script_name)
            if running:
                markup.add(
                    types.InlineKeyboardButton(
                        f"🛑 Stop {script_name}",
                        callback_data=f"stop_{owner_id}_{script_name}",
                    )
                )
            else:
                markup.add(
                    types.InlineKeyboardButton(
                        f"▶️ Run {script_name}",
                        callback_data=f"start_{owner_id}_{script_name}",
                    )
                )
            markup.add(
                types.InlineKeyboardButton(
                    f"🔄 Restart {script_name}",
                    callback_data=f"restart_{owner_id}_{script_name}",
                )
            )

        bot.answer_callback_query(call.id)
        if runnable_files:
            bot.send_message(
                call.message.chat.id,
                f"🗃️ **Data File:** `{fname}`\n\n"
                "এই data file নিজে executable নয়। একই user folder-এর bot "
                "control এখান থেকে চালানো যাবে—Run, Stop বা Restart করলে "
                "সংশ্লিষ্ট coding bot-ই নিয়ন্ত্রিত হবে।",
                reply_markup=markup,
                parse_mode="Markdown",
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f"🗃️ **Data File:** `{fname}`\n\n"
                "এই data file নিজে runnable নয় এবং এর সঙ্গে কোনো `.py` বা "
                "`.js` bot পাওয়া যায়নি। Bot চালাতে আগে একটি coding file upload করুন।",
                parse_mode="Markdown",
            )

    elif data.startswith("replace_code_"):
        parts = data.split("_", 3)
        if len(parts) != 4:
            bot.answer_callback_query(call.id, "অবৈধ replace request।", show_alert=True)
            return
        try:
            owner_id = int(parts[2])
        except ValueError:
            bot.answer_callback_query(call.id, "অবৈধ user ID।", show_alert=True)
            return
        fname = parts[3]
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই coding file replace করার অনুমতি নেই।", show_alert=True
            )
            return
        file_type = next(
            (
                file_type
                for name, file_type in user_files.get(owner_id, [])
                if name == fname
            ),
            None,
        )
        if file_type not in {"py", "js"}:
            bot.answer_callback_query(
                call.id, "শুধু .py বা .js coding file replace করা যাবে।", show_alert=True
            )
            return
        request_code_replacement(user_id, owner_id, fname)
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"🔄 **`{fname}` replace করার জন্য নতুন coding file পাঠান।**\n\n"
            f"শুধু `{os.path.splitext(fname)[1].lower()}` file পাঠাবেন।\n"
            "পুরোনো JSON, database, data এবং log file মুছে যাবে না।",
            parse_mode="Markdown",
        )

    elif data.startswith("download_all_user_data_"):
        try:
            owner_id = int(data.rsplit("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "অবৈধ user ID।", show_alert=True)
            return
        if user_id in admin_ids:
            bot.answer_callback_query(
                call.id,
                "Admin user file download করতে পারবেন না; শুধু দেখতে পারবেন।",
                show_alert=True,
            )
            return
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id,
                "❌ এই data backup download করার অনুমতি নেই।",
                show_alert=True,
            )
            return
        bot.answer_callback_query(call.id, "Full backup তৈরি হচ্ছে...")
        try:
            send_user_data_archive(
                call.message.chat.id, owner_id, requester_id=user_id
            )
        except ValueError as exc:
            bot.send_message(call.message.chat.id, f"❌ {exc}")
        except Exception:
            logger.exception("Could not download full data for user %s", owner_id)
            bot.send_message(call.message.chat.id, "❌ Full data download করা যায়নি।")

    elif data.startswith("download_file_"):
        _, _, owner_id, fname = data.split("_", 3)
        owner_id = int(owner_id)
        if user_id in admin_ids:
            bot.answer_callback_query(
                call.id,
                "Admin user file download করতে পারবেন না; শুধু দেখতে পারবেন।",
                show_alert=True,
            )
            return
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল download করার অনুমতি নেই।", show_alert=True
            )
            return
        bot.answer_callback_query(call.id, "Download শুরু হচ্ছে...")
        try:
            send_single_user_file(call.message.chat.id, owner_id, fname)
        except Exception:
            logger.exception("Could not download file %s for user %s", fname, owner_id)
            bot.send_message(call.message.chat.id, "❌ File download করা যায়নি।")

    elif data.startswith("start_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল চালানোর অনুমতি নেই।", show_alert=True
            )
            return
        if not safe_upload_name(fname) or not any(
            name == fname for name, _ in user_files.get(owner_id, [])
        ):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return
        ufolder = get_user_folder(owner_id)
        fpath = os.path.join(ufolder, fname)
        if not os.path.isfile(fpath):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return
        file_type = next(
            file_type
            for name, file_type in user_files.get(owner_id, [])
            if name == fname
        )
        if file_type not in RUNNABLE_FILE_EXTENSIONS:
            bot.answer_callback_query(
                call.id,
                "এটি data file; শুধু .py বা .js file run করা যায়।",
                show_alert=True,
            )
            return
        bot.answer_callback_query(call.id, "চালু করা হচ্ছে...")
        if fname.lower().endswith(".js"):
            threading.Thread(
                target=run_js_script,
                args=(fpath, owner_id, ufolder, fname, call.message),
                daemon=True,
            ).start()
        else:
            threading.Thread(
                target=run_script,
                args=(fpath, owner_id, ufolder, fname, call.message),
                daemon=True,
            ).start()

    elif data.startswith("restart_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল Restart করার অনুমতি নেই।", show_alert=True
            )
            return
        if not safe_upload_name(fname) or not any(
            name == fname for name, _ in user_files.get(owner_id, [])
        ):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return

        file_type = next(
            (
                file_type
                for name, file_type in user_files.get(owner_id, [])
                if name == fname
            ),
            None,
        )
        if file_type not in RUNNABLE_FILE_EXTENSIONS:
            bot.answer_callback_query(
                call.id,
                "Data file নিজে runnable নয়; পাশে থাকা bot-এর Restart ব্যবহার করুন।",
                show_alert=True,
            )
            return

        ufolder = get_user_folder(owner_id)
        fpath = os.path.join(ufolder, fname)
        if not os.path.isfile(fpath):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return

        was_running = is_bot_running(owner_id, fname)
        previous_info = stop_bot_process(owner_id, fname)
        previous_expiry = (
            previous_info.get("coin_run_expires_at")
            if previous_info and was_running
            else None
        )
        bot.answer_callback_query(
            call.id,
            "পুরোনো process বন্ধ হয়েছে, নতুন process চালু করা হচ্ছে...",
        )
        runner = run_js_script if file_type == "js" else run_script
        threading.Thread(
            target=runner,
            args=(
                fpath,
                owner_id,
                ufolder,
                fname,
                call.message,
                not was_running,
                previous_expiry,
            ),
            daemon=True,
        ).start()

    elif data.startswith("stop_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল বন্ধ করার অনুমতি নেই।", show_alert=True
            )
            return
        if not safe_upload_name(fname) or not any(
            name == fname for name, _ in user_files.get(owner_id, [])
        ):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return
        stopped = stop_bot_process(owner_id, fname)
        bot.answer_callback_query(
            call.id, "Stopped!" if stopped else "Bot already stopped."
        )
        bot.send_message(
            call.message.chat.id,
            f"🛑 Script `{fname}` stopped completely."
            if stopped
            else f"ℹ️ Script `{fname}` আগে থেকেই stopped ছিল।",
            parse_mode="Markdown",
        )

    elif data.startswith("del_") and not data.startswith("del_plan_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if not can_manage_file(user_id, owner_id):
            bot.answer_callback_query(
                call.id, "❌ এই ফাইল delete করার অনুমতি নেই।", show_alert=True
            )
            return
        if not safe_upload_name(fname) or not any(
            name == fname for name, _ in user_files.get(owner_id, [])
        ):
            bot.answer_callback_query(call.id, "ফাইল পাওয়া যায়নি।", show_alert=True)
            return
        skey = f"{owner_id}_{fname}"
        if skey in bot_scripts:
            kill_process_tree(bot_scripts[skey])
            del bot_scripts[skey]
        remove_user_file_db(int(owner_id), fname)
        ufolder = get_user_folder(int(owner_id))
        fpath = os.path.join(ufolder, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
        bot.answer_callback_query(call.id, "Deleted!")
        bot.send_message(
            call.message.chat.id,
            f"🗑️ File `{fname}` deleted.",
            parse_mode="Markdown",
        )


# --- Step Handlers ---
def process_coin_payment(message, method):
    transaction_code = (message.text or "").strip()
    user_id = message.from_user.id
    if len(transaction_code) < 3 or len(transaction_code) > 100:
        bot.reply_to(message, "❌ সঠিক Transaction Code দিন।")
        return
    if has_payment_transaction(transaction_code):
        bot.reply_to(message, "❌ এই Transaction Code আগে জমা দেওয়া হয়েছে।")
        return

    coins = get_coin_package_coins()
    amount = get_coin_package_price_bdt()
    try:
        request_id = create_coin_payment_request(
            user_id, method, transaction_code, amount, coins
        )
    except sqlite3.IntegrityError:
        bot.reply_to(message, "❌ এই Transaction Code আগে জমা দেওয়া হয়েছে।")
        return

    bot.reply_to(
        message,
        f"✅ আপনার coin deposit request জমা হয়েছে।\n"
        f"🧾 Request: `{request_id}`\n"
        f"🪙 Coins: `{coins}`\n"
        "Admin টাকা যাচাই করে approve করলে wallet-এ coins যোগ হবে।",
        parse_mode="Markdown",
    )
    for admin_id in list(admin_ids):
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "✅ Approve Coins",
                    callback_data=f"approve_coin_payment_{request_id}",
                ),
                types.InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_coin_payment_{request_id}",
                ),
            )
            bot.send_message(
                admin_id,
                f"🔔 **নতুন Coin Deposit Request**\n"
                f"🧾 Request: `{request_id}`\n"
                f"👤 User: `{user_id}`\n"
                f"📱 Method: `{method}`\n"
                f"💰 Amount: `{amount:g} BDT`\n"
                f"🪙 Coins: `{coins}`\n"
                f"🔐 Transaction Code: `{transaction_code}`",
                reply_markup=markup,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.info("Could not notify admin %s about coin payment: %s", admin_id, exc)


def process_set_coin_duration(message):
    try:
        raw_value = (message.text or "").strip().lower()
        match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|m|hours?|hrs?|h|days?|d)",
            raw_value,
        )
        if not match:
            raise ValueError("Format হবে `12 hours` অথবা `2 days`")
        value = float(match.group(1))
        unit = match.group(2)
        multiplier = 1 if unit.startswith(("m", "min")) else (
            60 if unit.startswith(("h", "hr")) else 24 * 60
        )
        minutes = int(value * multiplier)
        if minutes <= 0:
            raise ValueError("সময় ০-এর বেশি হতে হবে")
        set_coin_setting("coin_run_duration_minutes", minutes)
        bot.reply_to(
            message,
            f"✅ Coin-funded bot run time এখন `{format_coin_run_duration(minutes)}`।",
            parse_mode="Markdown",
        )
    except (TypeError, ValueError) as exc:
        bot.reply_to(
            message,
            f"❌ {exc}\nFormat: `12 hours` অথবা `2 days`",
            parse_mode="Markdown",
        )


def process_set_coin_price(message):
    try:
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 2:
            raise ValueError("দুটি field দিন: Coins | PriceBDT")
        coins = int(parts[0])
        price = parse_price_to_bdt(parts[1])
        if coins <= 0:
            raise ValueError("Coins ০-এর বেশি হতে হবে")
        set_coin_setting("coin_package_coins", coins)
        set_text_coin_setting("coin_package_price_bdt", f"{price:g}")
        bot.reply_to(
            message,
            f"✅ Coin price এখন `{coins} coins = {price:g} BDT`।",
            parse_mode="Markdown",
        )
    except (TypeError, ValueError) as exc:
        bot.reply_to(
            message,
            f"❌ Format ভুল: {exc}\nউদাহরণ: `10 | 100`",
            parse_mode="Markdown",
        )


def process_set_coin_payment_numbers(message):
    try:
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("bKash এবং Nagad দুইটি number দিন")
        set_text_coin_setting("coin_bkash_number", parts[0])
        set_text_coin_setting("coin_nagad_number", parts[1])
        bot.reply_to(
            message,
            f"✅ Coin deposit numbers update হয়েছে।\n"
            f"📱 bKash: `{parts[0]}`\n"
            f"📱 Nagad: `{parts[1]}`",
            parse_mode="Markdown",
        )
    except (TypeError, ValueError) as exc:
        bot.reply_to(
            message,
            f"❌ Format ভুল: {exc}\nউদাহরণ: `01XXXXXXXXX | 01XXXXXXXXX`",
            parse_mode="Markdown",
        )


def process_manual_payment(message, plan_id, method):
    transaction_code = (message.text or "").strip()
    user_id = message.from_user.id
    plan = get_plan_by_id(plan_id)
    if not plan:
        bot.reply_to(message, "❌ প্ল্যান পাওয়া যায়নি!")
        return
    if len(transaction_code) < 3 or len(transaction_code) > 100:
        bot.reply_to(message, "❌ সঠিক Transaction Code দিন।")
        return
    if has_payment_transaction(transaction_code):
        bot.reply_to(message, "❌ এই Transaction Code আগে জমা দেওয়া হয়েছে।")
        return
    amount = parse_price_to_bdt(plan[3])
    try:
        request_id = create_payment_request(
            user_id, plan_id, method, transaction_code, amount
        )
    except sqlite3.IntegrityError:
        bot.reply_to(message, "❌ এই Transaction Code আগে জমা দেওয়া হয়েছে।")
        return
    bot.reply_to(
        message,
        f"✅ আপনার payment request জমা হয়েছে।\n"
        f"🧾 Request: `{request_id}`\n"
        "Admin টাকা যাচাই করে approve করলে আপনার plan চালু হবে।",
        parse_mode="Markdown",
    )
    plan_name = plan[1]
    for admin_id in list(admin_ids):
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "✅ Approve", callback_data=f"approve_payment_{request_id}"
                ),
                types.InlineKeyboardButton(
                    "❌ Reject", callback_data=f"reject_payment_{request_id}"
                ),
            )
            bot.send_message(
                admin_id,
                f"🔔 **নতুন Payment Request**\n"
                f"🧾 Request: `{request_id}`\n"
                f"👤 User: `{user_id}`\n"
                f"💎 Plan: `{plan_name}`\n"
                f"📱 Method: `{method}`\n"
                f"💰 Amount: `{amount:g} BDT`\n"
                f"🔐 Transaction Code: `{transaction_code}`",
                reply_markup=markup,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.info("Could not notify admin %s: %s", admin_id, exc)


def process_add_plan(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 6:
            raise ValueError("৬টি field দিন")
        name, limit, price, duration, bkash_number, nagad_number = (
            parts[0],
            int(parts[1]),
            parse_price_to_bdt(parts[2]),
            int(parts[3]),
            parts[4],
            parts[5],
        )
        if not name or limit <= 0 or duration <= 0 or not bkash_number or not nagad_number:
            raise ValueError("সব field সঠিকভাবে পূরণ করুন")
        add_plan_db(name, limit, price, duration, bkash_number, nagad_number)
        bot.reply_to(
            message,
            f"✅ **VIP Plan `{name}` added successfully!**\n"
            f"🤖 Max bots: `{limit}` | 💰 `{price:g} BDT`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Format ভুল: {e}\n"
            "`PlanName | MaxBots | PriceBDT | DurationDays | bKashNumber | NagadNumber`",
            parse_mode="Markdown",
        )


def process_edit_plan(message, plan_id):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 6:
            raise ValueError("৬টি field দিন")
        name, max_bots, price, duration, bkash_number, nagad_number = (
            parts[0],
            int(parts[1]),
            parse_price_to_bdt(parts[2]),
            int(parts[3]),
            parts[4],
            parts[5],
        )
        if not name or max_bots <= 0 or duration <= 0 or not bkash_number or not nagad_number:
            raise ValueError("সব field সঠিকভাবে পূরণ করুন")
        update_plan_db(
            plan_id, name, max_bots, price, duration, bkash_number, nagad_number
        )
        bot.reply_to(message, f"✅ VIP Plan `{name}` update হয়েছে।", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Format ভুল: {e}", parse_mode="Markdown")


def process_add_subscription(message):
    try:
        parts = message.text.split()
        sub_uid, pname, days = int(parts[0]), parts[1], int(parts[2])
        exp = datetime.now() + timedelta(days=days)
        save_subscription(sub_uid, pname, exp)
        bot.reply_to(
            message,
            f"✅ **Subscription active for User `{sub_uid}` under Plan `{pname}` for {days} days!**",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


def save_admin_db(user_id):
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
            )
            conn.commit()
        finally:
            conn.close()
    admin_ids.add(user_id)


def remove_admin_db(user_id):
    if user_id in {OWNER_ID, ADMIN_ID}:
        return False
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()
    admin_ids.discard(user_id)
    return True


def process_add_admin(message):
    try:
        target_id = int((message.text or "").strip())
        save_admin_db(target_id)
        bot.reply_to(message, f"✅ User `{target_id}` এখন admin।", parse_mode="Markdown")
    except (TypeError, ValueError):
        bot.reply_to(message, "❌ সঠিক numeric Telegram User ID দিন।")


def process_remove_admin(message):
    try:
        target_id = int((message.text or "").strip())
        if remove_admin_db(target_id):
            bot.reply_to(
                message, f"✅ User `{target_id}` admin থেকে remove করা হয়েছে।",
                parse_mode="Markdown",
            )
        else:
            bot.reply_to(message, "❌ Owner বা মূল Admin-কে remove করা যাবে না।")
    except (TypeError, ValueError):
        bot.reply_to(message, "❌ সঠিক numeric Telegram User ID দিন।")


def process_broadcast(message):
    text = (message.text or "").strip()
    if not text:
        bot.reply_to(message, "❌ Broadcast message খালি হতে পারে না।")
        return
    delivered = 0
    for target_id in list(active_users):
        try:
            bot.send_message(target_id, f"📢 Broadcast\n\n{text}")
            delivered += 1
        except Exception as exc:
            logger.info("Broadcast failed for %s: %s", target_id, exc)
    bot.reply_to(message, f"✅ Broadcast শেষ। Delivered: `{delivered}`", parse_mode="Markdown")


def process_coin_adjustment(message, action):
    """Admin input format: TelegramUserID Amount."""
    try:
        raw_text = (message.text or "").strip()
        # Accept the documented space-separated format as well as common
        # clipboard-friendly variants such as "12345, 10" and "12345 | 10".
        parts = re.sub(r"[,|]+", " ", raw_text).split()
        if len(parts) != 2:
            raise ValueError("expected user ID and amount")
        target_id, amount = int(parts[0]), int(parts[1])
        if target_id <= 0 or amount <= 0:
            raise ValueError
        if action == "add":
            balance = add_coins(target_id, amount)
            verb = "যোগ"
        else:
            balance = remove_coins(target_id, amount)
            verb = "কাটা"
        bot.reply_to(
            message,
            f"✅ User `{target_id}`-এর ব্যালেন্স থেকে `{amount}` কয়েন {verb} হয়েছে।\n"
            f"💰 বর্তমান ব্যালেন্স: `{balance}`",
            parse_mode="Markdown",
        )
    except (IndexError, TypeError, ValueError):
        bot.reply_to(
            message,
            "❌ সঠিক format দিন:\n"
            "`TelegramUserID Amount`\n\n"
            "উদাহরণ: `123456789 25`\n"
            "শুধু Chat ID দিলে হবে না—শেষে কত coins যোগ করবেন সেটিও দিতে হবে।",
            parse_mode="Markdown",
        )


def process_set_coin_setting(message, setting_key, label):
    try:
        value = int((message.text or "").strip())
        if value <= 0:
            raise ValueError
        set_coin_setting(setting_key, value)
        bot.reply_to(
            message,
            f"✅ {label} এখন `{value}` কয়েন সেট করা হয়েছে।",
            parse_mode="Markdown",
        )
    except (TypeError, ValueError):
        bot.reply_to(message, "❌ শুধু ১ বা তার বেশি একটি পূর্ণ সংখ্যা দিন।")


def _logic_help(message):
    bot.reply_to(
        message,
        "প্রতিটি button-এর emoji তার কাজ অনুযায়ী দেওয়া হয়েছে।\n\n"
        "যেকোনো সমস্যায় Contact Owner বাটন ব্যবহার করুন।",
        reply_markup=create_reply_keyboard_main_menu(message.from_user.id),
    )


def _logic_updates(message):
    """Show the configured update channel with a direct Telegram button."""
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "📢 Join Updates Channel",
            url=UPDATE_CHANNEL,
        )
    )
    bot.reply_to(
        message,
        "📢 **Bot Updates Channel**\n\n"
        "নতুন আপডেট, maintenance notice এবং গুরুত্বপূর্ণ announcement পেতে "
        "নিচের বাটনে ক্লিক করুন।",
        reply_markup=markup,
        parse_mode="Markdown",
    )


# --- Text Handler Mapping ---
BUTTON_MAPPING = {
    "📢 𝗨𝗽𝗱𝗮𝘁𝗲𝘀": _logic_updates,
    "👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲": _logic_profile,
    "📤 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "📂 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀": _logic_check_files,
    "💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀": _logic_view_plans,
    "🪙 𝗕𝘂𝘆 𝗖𝗼𝗶𝗻𝘀": _logic_buy_coins,
    "🔗 𝗥𝗲𝗳𝗲𝗿 & 𝗖𝗼𝗶𝗻𝘀": _logic_referral,
    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴": lambda m: bot.reply_to(
        m, "⚡ **Bot Latency:** `12 ms` (Server Active)"
    ),
    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀": lambda m: bot.reply_to(
        m,
        f"📊 **Active Users:** `{len(active_users)}`\n"
        f"🪙 **Your Coins:** `{get_coin_balance(m.from_user.id)}`",
    ),
    "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹": lambda m: bot.reply_to(m, "💻 Terminal ready."),
    "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿": lambda m: bot.reply_to(
        m, f"👑 **Owner:** {YOUR_USERNAME}"
    ),
    "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹": lambda m: bot.reply_to(
        m,
        "🛡️ **𝗔𝗱𝗺𝗶𝗻 𝗖𝗼𝗻𝘁𝗿𝗼𝗹 𝗣𝗮𝗻𝗲𝗹:**",
        reply_markup=create_admin_panel_inline(),
        parse_mode="Markdown",
    ),
    "🆘 𝗛𝗲𝗹𝗽": _logic_help,
    # Previous color-only labels are kept working for users with an older keyboard.
    # Keep old labels working for users who have not refreshed their keyboard.
    "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨": _logic_updates,
    "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "🚀 𝗨𝗽𝗹𝗼𝗮d 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀": _logic_check_files,
    "👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲": _logic_profile,
    "💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀": _logic_view_plans,
    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴": lambda m: bot.reply_to(
        m, "⚡ **Bot Latency:** `12 ms` (Server Active)"
    ),
    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀": lambda m: bot.reply_to(
        m,
        f"📊 **Active Users:** `{len(active_users)}`\n"
        f"🪙 **Your Coins:** `{get_coin_balance(m.from_user.id)}`",
    ),
    "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱": lambda m: bot.reply_to(m, "💻 Terminal ready."),
    "🪙 𝗥𝗲𝗳𝗲𝗿 & 𝗖𝗼𝗶𝗻𝘀": _logic_referral,
    "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿": lambda m: bot.reply_to(
        m, f"👑 **Owner:** {YOUR_USERNAME}"
    ),
    "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹": lambda m: bot.reply_to(
        m,
        "🛡️ **𝗔𝗱𝗺𝗶𝗻 𝗖𝗼𝗻𝘁𝗿𝗼𝗹 𝗣𝗮𝗻𝗲𝗹:**",
        reply_markup=create_admin_panel_inline(),
        parse_mode="Markdown",
    ),
}


@bot.message_handler(func=lambda m: m.text in BUTTON_MAPPING)
def handle_main_buttons(message):
    BUTTON_MAPPING[message.text](message)


@bot.message_handler(commands=["start"])
def start_cmd(message):
    referral_balance = None
    referrer_id = None
    referral_reward = get_referral_reward_coins()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referrer_id = int(parts[1][4:])
        except ValueError:
            referrer_id = None

    if (
        referrer_id is not None
        and (not bot_locked or message.from_user.id in admin_ids)
    ):
        referral_balance = register_referral(message.from_user.id, referrer_id)

    _logic_send_welcome(message)
    if referral_balance is not None:
        bot.send_message(
            message.chat.id,
            f"🎉 Referral সফল হয়েছে! আপনার referrer-কে "
            f"{referral_reward} কয়েন দেওয়া হয়েছে।",
        )
        try:
            bot.send_message(
                referrer_id,
                f"🎉 নতুন একজন ইউজার আপনার referral link দিয়ে যুক্ত হয়েছে!\n"
                f"🪙 আপনি {referral_reward} কয়েন পেয়েছেন।\n"
                f"💰 বর্তমান ব্যালেন্স: `{get_coin_balance(referrer_id)}`",
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.info("Could not notify referrer %s: %s", referrer_id, exc)


# --- Cleanup & Start ---
def cleanup():
    for key in list(bot_scripts.keys()):
        kill_process_tree(bot_scripts[key])


atexit.register(cleanup)

if __name__ == "__main__":
    if not TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN is missing. Add it to Replit Secrets before starting."
        )
        raise SystemExit(1)
    logger.info("🤖 Starting Bot with configurable VIP plans and manual payments...")
    keep_alive()
    try:
        bot.remove_webhook()
        bot_info = bot.get_me()
        logger.info(
            "✅ Telegram API connected successfully as @%s (id=%s).",
            bot_info.username or "unknown",
            bot_info.id,
        )
        logger.info("📡 Telegram polling is starting...")
        bot.infinity_polling(
            skip_pending=True,
            timeout=20,
            long_polling_timeout=20,
            logger_level=logging.INFO,
        )
    except Exception:
        logger.exception("❌ Telegram polling could not start or has stopped.")
        raise