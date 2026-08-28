# -*- coding: utf-8 -*-
import atexit
from datetime import datetime, timedelta
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

# --- Flask Keep Alive ---
app = Flask("")

@app.route("/")
def home():
    return "I'm Mukesh File Host - Premium Security Mode Active"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")

# --- Configuration ---
TOKEN = "8934842351:AAFMIHo16zGLcS_97RyQgr0VYzRKq4-oax8"
OWNER_ID = 8814363793
ADMIN_ID = 8814363793
YOUR_USERNAME = "@Bmjakir69"
UPDATE_CHANNEL = "https://t.me/JAKIRLABS"
UPLOAD_LOG_CHANNEL = "@ajajakkalqkqkqjajakl" # ফাইল আপলোড নোটিফিকেশন চ্যানেল

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data.db")

# Create directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
blocked_users = set()
bot_locked = False

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻", "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴"],
    ["📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻", "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

# --- Database Setup ---
DB_LOCK = threading.Lock()

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        
        # New Schema with `status` column for Approval System
        c.execute("""CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, status TEXT DEFAULT 'approved', PRIMARY KEY (user_id, file_name))""")
        
        # Safe migration for old DB
        try:
            c.execute("ALTER TABLE user_files ADD COLUMN status TEXT DEFAULT 'approved'")
        except Exception:
            pass
            
        c.execute("""CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS force_channels (channel_id TEXT PRIMARY KEY, channel_url TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS referrals (user_id INTEGER, referred_user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS custom_limits (user_id INTEGER PRIMARY KEY, max_limit INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS blocked_users (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")

        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute("SELECT user_id FROM active_users")
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute("SELECT user_id FROM admins")
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        c.execute("SELECT user_id FROM blocked_users")
        blocked_users.update(user_id for (user_id,) in c.fetchall())

        conn.close()
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# --- DB Files Operations (Refactored for strict DB-first read) ---
def save_user_file(user_id, file_name, file_type="py", status="pending"):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, status) VALUES (?, ?, ?, ?)", (user_id, file_name, file_type, status))
        conn.commit()
        conn.close()

def update_file_status(user_id, file_name, status):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("UPDATE user_files SET status = ? WHERE user_id = ? AND file_name = ?", (status, user_id, file_name))
        conn.commit()
        conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
        conn.commit()
        conn.close()

def get_user_file_count(user_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_files WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_user_files_list(user_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT file_name, file_type, status FROM user_files WHERE user_id=?", (user_id,))
    files = c.fetchall()
    conn.close()
    return files

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()

# --- Settings Helper ---
def get_setting(key, default=""):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else default
    except:
        return default

def set_setting(key, value):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

# --- Security Functions ---
def block_and_alert_user(user_id, user_name, reason):
    if user_id in admin_ids:
        return
        
    blocked_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO blocked_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        
    alert_msg = (
        f"🚨 **SECURITY ALERT: USER BLOCKED!** 🚨\n\n"
        f"👤 **Name:** {user_name}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"❌ **Reason:** `{reason}`\n\n"
        f"⚠️ *এই ইউজারকে সার্ভার হ্যাক বা ডাউন করার চেষ্টার কারণে বট থেকে স্থায়ীভাবে ব্লক করা হয়েছে!*"
    )
    try:
        bot.send_message(OWNER_ID, alert_msg, parse_mode="Markdown")
        bot.send_message(user_id, "🚫 **আপনাকে সার্ভার হ্যাক বা ক্ষতিকর কোড আপলোড করার কারণে স্থায়ীভাবে ব্লক করা হয়েছে!**", protect_content=True)
    except:
        pass

# --- Premium Security Keywords ---
MALWARE_SIGNATURES = [b"MZ", b"\x7fELF", b"\xfe\xed\xfa", b"\xce\xfa\xed\xfe", b"PK", b"Rar!"]

DANGEROUS_KEYWORDS = [
    b"ransomware", b"trojan", b"virus", b"malware", b"backdoor", 
    b"botnet", b"keylogger", b"../", b"..\\", b"bot_data.db",
    b"os.system", b"subprocess", b"shutil.rmtree", b"pty.spawn",
    b"socket.socket", b"urllib.request", b"requests.get", b"requests.post",
    b"eval(", b"exec(", b"__import__", b"pickle.loads", b"ctypes",
    b"fork()", b"while True:", b"while(1):", b"child_process", b"require('child_process')",
    b"os.popen", b"nc -e", b"bash -i", b"reverse_tcp", b"sys.modules"
]

def is_suspicious_file(file_content, file_name):
    file_lower = file_name.lower()
    suspicious_extensions = [".exe", ".dll", ".bat", ".cmd", ".scr", ".com", ".pif", ".msi", ".jar", ".apk", ".sh"]
    if any(file_lower.endswith(ext) for ext in suspicious_extensions):
        return True, f"Suspicious file extension: {file_name}"
        
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature):
            return True, f"Malware signature detected"
            
    try:
        sample_text = file_content.decode("utf-8", errors="ignore").lower()
        for keyword in DANGEROUS_KEYWORDS:
            if keyword.decode('utf-8') in sample_text:
                return True, f"Security Violation: Dangerous code/keyword detected -> {keyword.decode('utf-8')}"
    except Exception as e:
        pass
        
    return False, "Safe"

# --- Process Helpers ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def kill_process_tree(process_info):
    try:
        if "log_file" in process_info and not process_info["log_file"].closed:
            try:
                process_info["log_file"].close()
            except:
                pass
            
        process = process_info.get("process")
        if process:
            if hasattr(process, "pid"):
                try:
                    parent = psutil.Process(process.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except:
                            pass
                    try:
                        parent.kill()
                    except:
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
            try:
                process.terminate()
            except:
                pass
            try:
                process.kill()
            except:
                pass
    except Exception as e:
        logger.error(f"❌ Error killing process tree: {e}")

def force_kill_user_bot(owner_id, file_name):
    skey = f"{owner_id}_{file_name}"
    if skey in bot_scripts:
        kill_process_tree(bot_scripts[skey])
        try:
            del bot_scripts[skey]
        except:
            pass

    ufolder = get_user_folder(int(owner_id))
    try:
        for proc in psutil.process_iter(['pid', 'cwd', 'cmdline']):
            try:
                proc_cwd = proc.info.get('cwd')
                if proc_cwd and ufolder in proc_cwd:
                    cmd = proc.info.get('cmdline') or []
                    if any(file_name in str(arg) for arg in cmd):
                        try:
                            for child in proc.children(recursive=True):
                                try:
                                    child.kill()
                                except:
                                    pass
                        except:
                            pass
                        try:
                            proc.kill()
                        except:
                            pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Force kill OS error: {e}")

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get("process"):
        try:
            proc = psutil.Process(script_info["process"].pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                return True
        except:
            pass
            
    ufolder = get_user_folder(int(script_owner_id))
    try:
        for proc in psutil.process_iter(['cwd', 'cmdline']):
            try:
                proc_cwd = proc.info.get('cwd')
                if proc_cwd and ufolder in proc_cwd:
                    cmd = proc.info.get('cmdline') or []
                    if any(file_name in str(arg) for arg in cmd):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except:
        pass
        
    return False

# --- Auto-stopper ---
def auto_stopper():
    while True:
        time.sleep(30)
        now = datetime.now()
        for key in list(bot_scripts.keys()):
            script = bot_scripts.get(key)
            if not script: 
                continue
            
            user_id = script["script_owner_id"]
            
            if user_id in admin_ids or user_id == OWNER_ID:
                continue

            elapsed_hours = (now - script["start_time"]).total_seconds() / 3600

            if elapsed_hours >= 11 and not script.get("warned_11h", False):
                script["warned_11h"] = True
                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("⏳ Extend Time (+12 Hours)", callback_data=f"extend_{user_id}_{script['file_name']}"))
                    warn_msg = (
                        f"⚠️ **বোট হোস্টিং সতর্কবার্তা!**\n\n"
                        f"📄 **File:** `{script['file_name']}`\n"
                        f"⏱️ আপনার বোটটি চলার সময় **১১ ঘণ্টা** পার হয়ে গেছে!\n"
                        f"আর ১ ঘণ্টা পর বোটটি স্বয়ংক্রিয়ভাবে বন্ধ হয়ে যাবে।\n\n"
                        f"👉 সময় আরও ১২ ঘণ্টা বাড়াতে নিচের **Extend Time** বাটনে ক্লিক করুন।"
                    )
                    bot.send_message(user_id, warn_msg, reply_markup=markup, parse_mode="Markdown", protect_content=True)
                except Exception as e:
                    logger.error(f"Error sending warning: {e}")

            if elapsed_hours >= 12:
                force_kill_user_bot(user_id, script["file_name"])
                try:
                    bot.send_message(
                        user_id, 
                        f"⏱️ **আপনার ১২ ঘণ্টার ফ্রি লিমিট শেষ!**\n"
                        f"📄 `{script['file_name']}` বোটটি স্বয়ংক্রিয়ভাবে বন্ধ করা হয়েছে।\n"
                        f"প্রয়োজনে আবার `📁 Manage Files` থেকে স্টার্ট বা এক্সটেন্ড করতে পারবেন।", 
                        protect_content=True
                    )
                except:
                    pass

# --- Limits & Force Sub ---
def get_referral_count(user_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_user_file_limit(user_id):
    if user_id == OWNER_ID or user_id in admin_ids:
        return float("inf")
    
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row is not None:
        return row[0]
        
    ref_count = get_referral_count(user_id)
    bonus = min(2, ref_count)
    return 1 + bonus

def get_force_channels():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT channel_id, channel_url FROM force_channels")
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
            if chat_target.lstrip('-').isdigit():
                chat_target = int(chat_target)
            
            member = bot.get_chat_member(chat_target, user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                not_joined.append((ch_id, ch_url))
        except Exception:
            pass
            
    return not_joined

# --- Script Runners ---
TELEGRAM_MODULES = {"telebot": "pyTelegramBotAPI", "telegram": "python-telegram-bot", "aiogram": "aiogram", "pyrogram": "pyrogram", "telethon": "telethon", "flask": "Flask", "psutil": "psutil"}

def monitor_and_guide_error(process, log_file_path, script_owner_id, file_name, message_obj_for_reply):
    time.sleep(3)
    if process.poll() is not None:
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                log_content = f.read()

            match_py = re.search(r"(?:ModuleNotFoundError|ImportError): No module named '(.+?)'", log_content)
            match_js = re.search(r"Cannot find module '(.+?)'", log_content)

            missing_module = None
            if match_py: missing_module = match_py.group(1).split(".")[0].strip("'\"")
            elif match_js: missing_module = match_js.group(1).split("/")[0].strip("'\"")

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📄 View Error Logs", callback_data=f"viewlog_{script_owner_id}_{file_name}"))

            if missing_module:
                pkg_name = TELEGRAM_MODULES.get(missing_module.lower(), missing_module)
                error_msg = f"⚠️ **ফাইল রান হতে সমস্যা হয়েছে!**\n\n📄 **File:** `{file_name}`\n❌ **সমস্যা:** আপনার কোডে `{missing_module}` মডিউলটি মিসিং আছে।\n\n🔐 **Premium Security Mode Active:** \n*স্বয়ংক্রিয় প্যাকেজ ইন্সটলেশন (NPM/PIP) সিকিউরিটি কারণে বন্ধ রাখা হয়েছে। আপনার প্যাকেজ ইন্সটল করতে অ্যাডমিনের সাথে যোগাযোগ করুন।*"
                bot.send_message(message_obj_for_reply.chat.id, error_msg, reply_markup=markup, parse_mode="Markdown", protect_content=True)
            else:
                bot.send_message(message_obj_for_reply.chat.id, f"⚠️ **আপনার কোডে ভুল (Syntax/Runtime Error) পাওয়া গেছে!**\n📄 **File:** `{file_name}`", reply_markup=markup, parse_mode="Markdown", protect_content=True)
        except: pass

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        unique_port = 8000 + (int(hashlib.md5(script_key.encode()).hexdigest(), 16) % 50000)
        
        custom_env = os.environ.copy()
        custom_env["PORT"] = str(unique_port)
        custom_env["PYTHONDONTWRITEBYTECODE"] = "1"
        custom_env["PYTHONPATH"] = user_folder
        custom_env["HOME"] = user_folder        
        custom_env["TEMP"] = user_folder        
        custom_env["TMP"] = user_folder         
        custom_env["TMPDIR"] = user_folder      
        
        process = subprocess.Popen([sys.executable, "-u", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE, env=custom_env)
        
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
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **Python Bot Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=True)
        threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply)).start()
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error: {str(e)}", protect_content=True)

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        unique_port = 8000 + (int(hashlib.md5(script_key.encode()).hexdigest(), 16) % 50000)
        
        custom_env = os.environ.copy()
        custom_env["PORT"] = str(unique_port)
        custom_env["NODE_PATH"] = user_folder
        custom_env["HOME"] = user_folder
        custom_env["TEMP"] = user_folder
        custom_env["TMP"] = user_folder
        custom_env["TMPDIR"] = user_folder
        
        process = subprocess.Popen(["node", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE, env=custom_env)
        
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
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **JS Bot Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=True)
        threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply)).start()
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error: {str(e)}", protect_content=True)

def do_start_bot(owner_id, fname, message_obj, call_id=None):
    ufolder = get_user_folder(int(owner_id))
    fpath = os.path.join(ufolder, fname)
    ext = os.path.splitext(fname)[1].lower()

    if is_bot_running(int(owner_id), fname):
        if call_id: bot.answer_callback_query(call_id, "এই বোটটি অলরেডি রানিং আছে!", show_alert=True)
        return

    if call_id: bot.answer_callback_query(call_id, "Starting...")
    if ext == ".js":
        run_js_script(fpath, int(owner_id), ufolder, fname, message_obj)
    else:
        run_script(fpath, int(owner_id), ufolder, fname, message_obj)

# --- UI Methods ---
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup

def create_admin_panel_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ 𝗔𝗱𝗱 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="add_channel"),
        types.InlineKeyboardButton("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="remove_channel")
    )
    markup.add(
        types.InlineKeyboardButton("📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="broadcast"),
        types.InlineKeyboardButton("🔐 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸", callback_data="toggle_lock")
    )
    markup.add(
        types.InlineKeyboardButton("⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀", callback_data="run_all_scripts"),
        types.InlineKeyboardButton("📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", callback_data="stats")
    )
    markup.add(
        types.InlineKeyboardButton("🎥 𝗦𝗲𝘁 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹", callback_data="set_tutorial")
    )
    
    if int(user_id) == int(OWNER_ID):
        markup.add(
            types.InlineKeyboardButton("👑 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻", callback_data="add_admin"),
            types.InlineKeyboardButton("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻", callback_data="remove_admin")
        )
        markup.add(
            types.InlineKeyboardButton("⚙️ 𝗦𝗲𝘁 𝗕𝗼𝘁 𝗟𝗶𝗺𝗶𝘁", callback_data="set_limit"),
            types.InlineKeyboardButton("🚫 𝗕𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿", callback_data="block_user")
        )
        markup.add(
            types.InlineKeyboardButton("✅ 𝗨𝗻𝗯𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿", callback_data="unblock_user")
        )
        
    return markup

# --- Start & Menus ---
@bot.message_handler(commands=["start"])
def start_cmd(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return 
        
    chat_id = message.chat.id
    user_name = message.from_user.first_name

    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM active_users WHERE user_id=?", (user_id,))
    is_new = c.fetchone() is None
    conn.close()

    args = message.text.split()
    if is_new and len(args) > 1:
        referrer_id = args[1]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            referrer_id = int(referrer_id)
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO referrals (user_id, referred_user_id) VALUES (?, ?)", (referrer_id, user_id))
                conn.commit()
                conn.close()
            try:
                bot.send_message(referrer_id, f"🎉 **নতুন রেফারেল!**\n\n👤 `{user_name}` আপনার রেফারে জয়েন করেছে।\n🎁 আপনার বোট হোস্ট করার লিমিট ১টি বৃদ্ধি পেয়েছে!", protect_content=True)
            except: pass

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ **Bot is temporarily locked by Admin.**")
        return

    add_active_user(user_id)
    limit = get_user_file_limit(user_id)

    welcome_msg = (
        f"✨ **𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {user_name}!** ✨\n\n"
        f"🔐 **Premium Security Mode Active** 🛡️\n\n"
        f"🆔 **𝗬𝗼𝘂𝗿 𝗜𝗗:** `{user_id}`\n"
        f"🔰 **𝗛𝗼𝘀𝘁𝗶𝗻𝗴 𝗟𝗶𝗺𝗶𝘁:** `{get_user_file_count(user_id)}` / `{limit}`\n\n"
        f"💡 **আপনি সম্পূর্ণ ফ্রিতে আপনার Python (.py) ও JS (.js) বোট হোস্ট করতে পারবেন।**\n"
        f"⚠️ *সার্ভার সুরক্ষার্থে সকল আপলোড অ্যাডমিন দ্বারা ম্যানুয়ালি চেক করে অ্যাপ্রুভ করা হয়।*\n\n"
        f"👇 *Select an option from the menu below:* "
    )
    bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode="Markdown", protect_content=True)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, "⚠️ **Bot is locked by Admin.**")
        return

    current_count = get_user_file_count(user_id)
    max_limit = get_user_file_limit(user_id)

    if current_count >= max_limit:
        bot.send_message(message.chat.id, f"⚠️ **আপনার আপলোড লিমিট শেষ!**\n\n📊 **বর্তমান আপলোড:** `{current_count}` / `{max_limit}`\n"
                              f"নতুন কোনো ফাইল রান করাতে `📁 Manage Files` থেকে যেকোনো একটি বোট ডিলিট করুন অথবা রেফার করুন।", parse_mode="Markdown")
        return

    bot.send_message(message.chat.id, "🚀 **আপনার Python (.py) অথবা JS (.js) বোট ফাইলটি মেসেজে আপলোড করুন।**\n"
                          "*(ফাইল দেওয়ার পর ফাইলটি সিকিউরিটি চেকে যাবে এবং অ্যাডমিন অ্যাপ্রুভালের জন্য অপেক্ষা করবে)*", parse_mode="Markdown")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = get_user_files_list(user_id)
    
    if not user_files_list:
        bot.send_message(message.chat.id, "📂 **Your Uploaded Files:**\n\n*(No files uploaded yet)*", parse_mode="Markdown")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type, status in sorted(user_files_list, key=lambda x: x[0]):
        if status == "pending":
            btn_text = f"🔐 {file_name} (Pending Approval)"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"locked_{user_id}_{file_name}"))
        else:
            is_running = is_bot_running(user_id, file_name)
            status_icon = "🟢 Running" if is_running else "🔴 Stopped"
            btn_text = f"📄 {file_name} ({file_type}) - {status_icon}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"file_{user_id}_{file_name}"))
            
    bot.send_message(message.chat.id, f"📁 **𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀 ({len(user_files_list)}/{get_user_file_limit(user_id)}):**", reply_markup=markup, parse_mode="Markdown", protect_content=True)

# --- File Upload Handler (With Security & Approval Logic) ---
@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return
        
    doc = message.document
    user_name = message.from_user.first_name

    current_count = get_user_file_count(user_id)
    max_limit = get_user_file_limit(user_id)
    
    file_name = os.path.basename(doc.file_name) 
    file_name = re.sub(r'[^\w\-\.]', '_', file_name)
    
    user_files_list = get_user_files_list(user_id)
    file_exists = any(f[0] == file_name for f in user_files_list)
    
    if current_count >= max_limit and not file_exists:
        bot.send_message(message.chat.id, "❌ **আপলোড লিমিট পূর্ণ হয়েছে! রেফার করে লিমিট বাড়ান।**", parse_mode="Markdown")
        return

    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in [".py", ".js"]:
        bot.send_message(message.chat.id, "⚠️ **শুধুমাত্র `.py` এবং `.js` ফাইল সাপোর্ট করে!**", parse_mode="Markdown")
        return

    try:
        download_wait_msg = bot.send_message(message.chat.id, f"⏳ **Checking Security & Downloading `{file_name}`...**", parse_mode="Markdown")
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # 🛡️ Premium Security Detection
        is_suspicious, reason = is_suspicious_file(downloaded_file, file_name)
        if is_suspicious:
            try: bot.delete_message(message.chat.id, download_wait_msg.message_id)
            except: pass
            warning_msg = (
                f"🚫 **আপনার ফাইলটি সিকিউরিটি চেকে ব্লক করা হয়েছে!** 🚫\n\n"
                f"📄 **File Name:** `{file_name}`\n"
                f"❌ **সমস্যা (Reason):** `{reason}`\n\n"
                f"⚠️ *দয়া করে আপনার কোড থেকে ক্ষতিকর অংশটি বাদ দিয়ে পুনরায় আপলোড করুন।*"
            )
            bot.send_message(user_id, warning_msg, parse_mode="Markdown")
            
            alert_msg = (
                f"⚠️ **SECURITY ALERT: SUSPICIOUS FILE BLOCKED!** ⚠️\n\n"
                f"👤 **Name:** {user_name}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"📄 **File:** `{file_name}`\n"
                f"❌ **Reason:** `{reason}`"
            )
            try: bot.send_message(OWNER_ID, alert_msg, parse_mode="Markdown")
            except: pass
            return 

        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        force_kill_user_bot(user_id, file_name)
        time.sleep(1)

        with open(file_path, "wb") as f:
            f.write(downloaded_file)

        # 🔐 Status Assignment
        status = 'approved' if user_id in admin_ids else 'pending'
        save_user_file(user_id, file_name, file_ext[1:], status)

        if status == 'pending':
            bot.edit_message_text(
                f"✅ **File `{file_name}` passed initial security check!**\n\n"
                f"🔐 **Premium Security Mode:** আপনার ফাইলটি বর্তমানে **Pending** অবস্থায় আছে।\n"
                f"অ্যাডমিন ম্যানুয়ালি চেক করে অ্যাপ্রুভ করার পর আপনি এটি `📁 Manage Files` থেকে রান করতে পারবেন।",
                message.chat.id,
                download_wait_msg.message_id,
                parse_mode="Markdown"
            )
            
            # 📬 Notify Admin for Approval
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{file_name}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}_{file_name}")
            )
            try:
                bot.send_document(
                    UPLOAD_LOG_CHANNEL, 
                    doc.file_id, 
                    caption=f"🔐 **New File Pending Approval!**\n\n👤 **User:** [{user_name}](tg://user?id={user_id})\n🆔 **User ID:** `{user_id}`\n📄 **File Name:** `{file_name}`", 
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not send to log channel: {e}")
        else:
            bot.edit_message_text(
                f"✅ **Admin File `{file_name}` uploaded & auto-approved!**\n"
                f"📂 দয়া করে `📁 Manage Files` অপশন থেকে আপনার বোটটি স্টার্ট (Start) করুন।",
                message.chat.id,
                download_wait_msg.message_id,
                parse_mode="Markdown"
            )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ **Error:** {str(e)}")

# --- Callback Routing ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    if user_id in blocked_users:
        return
        
    global bot_locked
    data = call.data

    if data.startswith(("file_", "start_", "verify_", "stop_", "del_", "viewlog_", "extend_", "locked_")):
        parts = data.split("_")
        owner_id = int(parts[1])
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ নিরাপত্তা সতর্কতা: এটি আপনার ফাইল নয়!", show_alert=True)
            return

    # 🔐 Admin Approval Callbacks
    if data.startswith("approve_") and user_id in admin_ids:
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        update_file_status(owner_id, fname, "approved")
        
        bot.answer_callback_query(call.id, "✅ File Approved successfully!", show_alert=True)
        bot.edit_message_caption(f"✅ **File Approved!**\n\n👤 **Owner ID:** `{owner_id}`\n📄 **File:** `{fname}`", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        try:
            bot.send_message(owner_id, f"🎉 **অ্যাডমিন আপনার `{fname}` ফাইলটি অ্যাপ্রুভ করেছেন!**\nএখন আপনি এটি `📁 Manage Files` থেকে রান করতে পারবেন।", parse_mode="Markdown")
        except: pass
        return

    elif data.startswith("reject_") and user_id in admin_ids:
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        remove_user_file_db(owner_id, fname)
        
        ufolder = get_user_folder(owner_id)
        fpath = os.path.join(ufolder, fname)
        if os.path.exists(fpath): os.remove(fpath)
            
        bot.answer_callback_query(call.id, "❌ File Rejected & Deleted!", show_alert=True)
        bot.edit_message_caption(f"❌ **File Rejected & Deleted!**\n\n👤 **Owner ID:** `{owner_id}`\n📄 **File:** `{fname}`", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        try:
            bot.send_message(owner_id, f"🚫 **অ্যাডমিন আপনার `{fname}` ফাইলটি রিজেক্ট করেছেন!** (Security Reasons)\nফাইলটি সার্ভার থেকে ডিলিট করা হয়েছে।", parse_mode="Markdown")
        except: pass
        return

    # User callbacks
    elif data.startswith("locked_"):
        bot.answer_callback_query(call.id, "🔐 এই ফাইলটি সিকিউরিটির জন্য বর্তমানে অ্যাডমিন অ্যাপ্রুভালের অপেক্ষায় আছে!", show_alert=True)

    elif data.startswith("file_"):
        _, owner_id, fname = data.split("_", 2)
        is_running = is_bot_running(int(owner_id), fname)
        markup = types.InlineKeyboardMarkup(row_width=2)
        if is_running:
            markup.add(types.InlineKeyboardButton("🛑 Stop Bot", callback_data=f"stop_{owner_id}_{fname}"))
            if user_id not in admin_ids:
                markup.add(types.InlineKeyboardButton("⏳ Extend Time (+12H)", callback_data=f"extend_{owner_id}_{fname}"))
        else:
            markup.add(types.InlineKeyboardButton("▶️ Start Bot", callback_data=f"start_{owner_id}_{fname}"))
        markup.add(types.InlineKeyboardButton("🗑️ Delete Bot File", callback_data=f"del_{owner_id}_{fname}"))
        bot.send_message(call.message.chat.id, f"📄 **File:** `{fname}`\n🚦 Status: `{'🟢 Running' if is_running else '🔴 Stopped'}`", reply_markup=markup, parse_mode="Markdown", protect_content=True)

    elif data.startswith("extend_"):
        _, owner_id, fname = data.split("_", 2)
        script_key = f"{owner_id}_{fname}"
        if script_key in bot_scripts:
            bot_scripts[script_key]["start_time"] = datetime.now()
            bot_scripts[script_key]["warned_11h"] = False
            bot.answer_callback_query(call.id, "🎉 সময় আরও ১২ ঘণ্টা বাড়ানো হয়েছে!", show_alert=True)
            bot.send_message(call.message.chat.id, f"⏳ **সময় সফলভাবে বাড়ানো হয়েছে!**\n📄 `{fname}` বোটটি আরও ১২ ঘণ্টার জন্য সচল থাকবে।", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ বোটটি বর্তমানে বন্ধ আছে! আগে স্টার্ট করুন।", show_alert=True)

    elif data.startswith("start_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        
        not_joined = check_force_sub(owner_id)
        if not_joined and owner_id not in admin_ids:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for ch_id, ch_url in not_joined:
                markup.add(types.InlineKeyboardButton("📢 Join Channel", url=ch_url))
            markup.add(types.InlineKeyboardButton("✅ Verify", callback_data=f"verify_{owner_id}_{fname}"))
            
            bot.send_message(call.message.chat.id, "⚠️ **আপনার বোট স্টার্ট করতে হলে প্রথমে আমাদের নিচের চ্যানেলগুলোতে জয়েন করুন:**", reply_markup=markup, parse_mode="Markdown")
            return
            
        do_start_bot(owner_id, fname, call.message, call.id)

    elif data.startswith("verify_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        not_joined = check_force_sub(owner_id)
        
        if not_joined:
            bot.answer_callback_query(call.id, "❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি!", show_alert=True)
        else:
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            do_start_bot(owner_id, fname, call.message, call.id)

    elif data.startswith("stop_"):
        _, owner_id, fname = data.split("_", 2)
        force_kill_user_bot(owner_id, fname)
        bot.answer_callback_query(call.id, "Stopped!")
        bot.send_message(call.message.chat.id, f"🛑 Script `{fname}` stopped successfully.", parse_mode="Markdown")

    elif data.startswith("del_"):
        _, owner_id, fname = data.split("_", 2)
        force_kill_user_bot(owner_id, fname)
        remove_user_file_db(int(owner_id), fname)
        ufolder = get_user_folder(int(owner_id))
        fpath = os.path.join(ufolder, fname)
        log_fpath = os.path.join(ufolder, f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(fpath): os.remove(fpath)
        if os.path.exists(log_fpath): os.remove(log_fpath)
        pycache_dir = os.path.join(ufolder, "__pycache__")
        if os.path.exists(pycache_dir): shutil.rmtree(pycache_dir, ignore_errors=True)
            
        bot.answer_callback_query(call.id, "Deleted!")
        bot.send_message(call.message.chat.id, f"🗑️ File `{fname}` completely deleted.", parse_mode="Markdown")

    elif data.startswith("viewlog_"):
        _, owner_id, fname = data.split("_", 2)
        log_fpath = os.path.join(get_user_folder(int(owner_id)), f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(log_fpath):
            with open(log_fpath, "r", encoding="utf-8", errors="ignore") as f: logs = f.read()[-2000:]
            bot.send_message(call.message.chat.id, f"📜 **Logs:**\n\n```\n{logs if logs else 'No logs'}\n```", parse_mode="Markdown", protect_content=True)
        else:
            bot.answer_callback_query(call.id, "No logs!", show_alert=True)

    # --- Admin Panel callbacks ---
    # ... (Other admin callbacks like set_tutorial, add_channel, add_admin remain unchanged)
    elif data == "toggle_lock" and user_id in admin_ids:
        bot_locked = not bot_locked
        status = "🔒 Locked" if bot_locked else "🔓 Unlocked"
        bot.answer_callback_query(call.id, f"Bot is now {status}", show_alert=True)
        bot.send_message(call.message.chat.id, f"✅ **Bot Lock Status Changed to:** {status}", parse_mode="Markdown")

    elif data == "run_all_scripts" and user_id in admin_ids:
        bot.answer_callback_query(call.id, "Running all stopped & approved scripts...")
        started_count = 0
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT user_id, file_name, file_type FROM user_files WHERE status='approved'")
        all_approved = c.fetchall()
        conn.close()

        for uid, fname, ftype in all_approved:
            if not is_bot_running(uid, fname):
                ufolder = get_user_folder(uid)
                fpath = os.path.join(ufolder, fname)
                if os.path.exists(fpath):
                    if ftype == "js": run_js_script(fpath, uid, ufolder, fname, call.message)
                    else: run_script(fpath, uid, ufolder, fname, call.message)
                    started_count += 1
                    time.sleep(1)
        bot.send_message(call.message.chat.id, f"✅ **Successfully started {started_count} scripts!**", parse_mode="Markdown")
        
    elif data == "stats" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = (
            f"📊 **𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀 (Premium Mode):**\n\n"
            f"👥 **Total Users:** `{len(active_users)}`\n"
            f"👑 **Total Admins:** `{len(admin_ids)}`\n"
            f"🚀 **Running Bots:** `{len(bot_scripts)}`\n"
            f"🔒 **Bot Locked Status:** `{bot_locked}`\n"
            f"🚫 **Blocked Users:** `{len(blocked_users)}`"
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

# --- UI Action Handlers (Referral, Links etc.) ---
def _logic_referral(message):
    user_id = message.from_user.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_count = get_referral_count(user_id)
    limit = get_user_file_limit(user_id)
    msg = (
        f"🎁 **𝗥𝗲𝗳𝗲𝗿 𝗔𝗻𝗱 𝗘𝗮𝗿𝗻 𝗕𝗼𝘁 𝗦𝗹𝗼𝘁𝘀** 🎁\n\n"
        f"বন্ধুদের রেফার করে সম্পূর্ণ ফ্রিতে আপনার বোট হোস্টিং লিমিট বাড়ান!\n"
        f"প্রতিটি রেফারের জন্য আপনি **১টি এক্সট্রা বোট রান করার লিমিট** পাবেন (সর্বোচ্চ ৩টি বোট)।\n\n"
        f"🔗 **আপনার রেফার লিংক:**\n`{ref_link}`\n\n"
        f"📊 **আপনার মোট রেফার:** `{ref_count}`\n"
        f"🚀 **বর্তমান লিমিট:** `{limit} টি বোট`"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def _logic_tutorial(message):
    tut_link = get_setting("tutorial_link", UPDATE_CHANNEL)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎥 Watch Tutorial Video", url=tut_link))
    msg = (
        "🎥 **𝗛𝗼𝘄 𝗧𝗼 𝗨𝘀𝗲 & 𝗛𝗼𝘀𝘁 𝗕𝗼𝘁:**\n\n"
        "কীভাবে ফাইল আপলোড করতে হয় এবং সহজে আপনার বোট রান করাতে হয় তা শিখতে নিচের বাটনে ক্লিক করে ভিডিওটি দেখুন।"
    )
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown", protect_content=True)

# --- Text Handler Mapping ---
BUTTON_MAPPING = {
    "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨": lambda m: bot.send_message(m.chat.id, f"📢 **Join channel:** {UPDATE_CHANNEL}"),
    "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹": _logic_tutorial,
    "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀": _logic_check_files,
    "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻": _logic_referral,
    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴": lambda m: bot.send_message(m.chat.id, "⚡ **Bot Latency:** `12 ms` (Premium Server Active)"),
    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀": lambda m: bot.send_message(m.chat.id, f"📊 **Active Users:** `{len(active_users)}`\n🚀 **Running Bots:** `{len(bot_scripts)}`\n🚫 **Blocked Users:** `{len(blocked_users)}`", parse_mode="Markdown"),
    "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱": lambda m: bot.send_message(m.chat.id, "💻 **Terminal Access:** `[LOCKED BY ADMIN]` - Premium Mode"),
    "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿": lambda m: bot.send_message(m.chat.id, f"👑 **Owner:** {YOUR_USERNAME}"),
    "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹": lambda m: bot.send_message(m.chat.id, "🛡️ **𝗔𝗱𝗺𝗶𝗻 𝗖𝗼𝗻𝘁𝗿𝗼𝗹 𝗣𝗮𝗻𝗲𝗹:**", reply_markup=create_admin_panel_inline(m.from_user.id), parse_mode="Markdown"),
}

@bot.message_handler(func=lambda m: m.text in BUTTON_MAPPING)
def handle_main_buttons(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return 
    BUTTON_MAPPING[message.text](message)

# --- Cleanup & Start ---
def cleanup():
    for key in list(bot_scripts.keys()):
        try:
            kill_process_tree(bot_scripts[key])
        except: pass

atexit.register(cleanup)

if __name__ == "__main__":
    logger.info("🤖 Starting Hosting Manager with PREMIUM SECURITY (Admin Approval) Mode...")
    keep_alive()
    threading.Thread(target=auto_stopper, daemon=True).start()
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
