import os
import sqlite3
import uuid
import logging
from datetime import datetime, timezone
from html import escape

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.constants import (
    ChatType,
    ChatMemberStatus,
)

from telegram.error import (
    TelegramError,
    BadRequest,
    Forbidden,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8852375747:AAFNuh3gsrZk2-k_ehJ9FJ3ialg105CfVFw").strip()

# তোমার দেওয়া Admin / Owner ID
OWNER_ID = 8814363793

DB_FILE = "pollmaker.db"

MIN_OPTIONS = 2
MAX_OPTIONS = 40

MAX_QUESTION_LENGTH = 250
MAX_OPTION_LENGTH = 80

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("POLL-MAKER")


# ============================================================
# CONVERSATION STATES
# ============================================================

TARGET = 1
PHOTO = 2
QUESTION = 3
OPTIONS = 4
CONFIRM = 5


# ============================================================
# DATABASE
# ============================================================

def db():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = db()

    try:

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS polls (
            id TEXT PRIMARY KEY,
            target_chat_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            message_id INTEGER,
            question TEXT NOT NULL,
            photo_file_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS poll_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id TEXT NOT NULL,
            option_name TEXT NOT NULL,
            votes INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (poll_id)
            REFERENCES polls(id)
            ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS votes (
            poll_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            option_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            PRIMARY KEY (
                poll_id,
                user_id
            ),

            FOREIGN KEY (poll_id)
            REFERENCES polls(id)
            ON DELETE CASCADE,

            FOREIGN KEY (option_id)
            REFERENCES poll_options(id)
            ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            joined_at TEXT NOT NULL
        );
        """)

        conn.commit()

    finally:

        conn.close()


# ============================================================
# SAVE USER
# ============================================================

def save_user(user):

    if not user:
        return

    conn = db()

    try:

        conn.execute("""
        INSERT INTO users (
            user_id,
            first_name,
            username,
            joined_at
        )

        VALUES (?, ?, ?, ?)

        ON CONFLICT(user_id)

        DO UPDATE SET
            first_name=excluded.first_name,
            username=excluded.username
        """, (
            user.id,
            user.first_name or "",
            user.username or "",
            datetime.now(timezone.utc).isoformat()
        ))

        conn.commit()

    finally:

        conn.close()


# ============================================================
# NORMALIZE USERNAME
# ============================================================

def normalize_username(text):

    text = text.strip()

    text = text.replace(
        "https://t.me/",
        "",
        1
    )

    text = text.replace(
        "http://t.me/",
        "",
        1
    )

    text = text.replace(
        "t.me/",
        "",
        1
    )

    text = text.strip("/ ")

    if not text.startswith("@"):
        text = "@" + text

    return text


# ============================================================
# CHECK TARGET
# ============================================================

async def verify_target(
    context,
    username
):

    try:

        chat = await context.bot.get_chat(
            username
        )

    except Forbidden:

        return (
            None,
            "❌ Telegram Bot API access denied."
        )

    except BadRequest as e:

        return (
            None,
            "❌ এই Username পাওয়া যায়নি।\n\n"
            f"Telegram: {str(e)}"
        )

    except TelegramError as e:

        return (
            None,
            "❌ Target যাচাই করা যায়নি।\n\n"
            f"Error: {str(e)}"
        )

    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL
    ):

        return (
            None,
            "❌ শুধু Group / Supergroup / Channel "
            "দেওয়া যাবে।"
        )

    # --------------------------------------------------------
    # BOT INFO
    # --------------------------------------------------------

    try:

        bot = await context.bot.get_me()

        member = await context.bot.get_chat_member(
            chat_id=chat.id,
            user_id=bot.id
        )

    except TelegramError as e:

        return (
            None,
            "❌ Bot Admin status যাচাই করা যায়নি.\n\n"
            f"Error: {str(e)}"
        )

    # --------------------------------------------------------
    # ADMIN CHECK
    # --------------------------------------------------------

    if member.status not in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ):

        return (
            None,
            "❌ <b>Bot Admin নয়!</b>\n\n"
            "আগে Bot-কে Target Group/Channel-এ "
            "Admin করুন।"
        )

    # --------------------------------------------------------
    # CHANNEL PERMISSION
    # --------------------------------------------------------

    if chat.type == ChatType.CHANNEL:

        if (
            member.status == ChatMemberStatus.ADMINISTRATOR
            and member.can_post_messages is False
        ):

            return (
                None,
                "❌ Bot-এর <b>Post Messages</b> "
                "permission নেই।\n\n"
                "Channel → Administrators → Bot → "
                "<b>Post Messages ON</b> করুন।"
            )

    # --------------------------------------------------------
    # GROUP PERMISSION
    # --------------------------------------------------------

    if chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    ):

        if (
            member.status == ChatMemberStatus.ADMINISTRATOR
            and member.can_manage_chat is False
            and member.can_delete_messages is False
        ):
            # এখানে শুধু hard reject করছি না।
            # কারণ কিছু group configuration-এ
            # permission field সীমিত হতে পারে।
            pass

    return chat, None


# ============================================================
# CREATE POLL DATABASE
# ============================================================

def create_poll(
    target_chat_id,
    creator_id,
    question,
    photo_file_id,
    options
):

    poll_id = uuid.uuid4().hex

    conn = db()

    try:

        conn.execute("BEGIN")

        conn.execute("""
        INSERT INTO polls (
            id,
            target_chat_id,
            creator_id,
            question,
            photo_file_id,
            status,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (
            poll_id,
            target_chat_id,
            creator_id,
            question,
            photo_file_id,
            datetime.now(timezone.utc).isoformat()
        ))

        for option in options:

            conn.execute("""
            INSERT INTO poll_options (
                poll_id,
                option_name,
                votes
            )

            VALUES (?, ?, 0)
            """, (
                poll_id,
                option
            ))

        conn.commit()

        return poll_id

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


# ============================================================
# GET POLL
# ============================================================

def get_poll(poll_id):

    conn = db()

    try:

        return conn.execute("""
        SELECT *
        FROM polls
        WHERE id=?
        """, (
            poll_id,
        )).fetchone()

    finally:

        conn.close()


# ============================================================
# GET OPTIONS
# ============================================================

def get_options(poll_id):

    conn = db()

    try:

        return conn.execute("""
        SELECT
            id,
            option_name,
            votes

        FROM poll_options

        WHERE poll_id=?

        ORDER BY id ASC
        """, (
            poll_id,
        )).fetchall()

    finally:

        conn.close()


# ============================================================
# SET MESSAGE ID
# ============================================================

def save_message_id(
    poll_id,
    message_id
):

    conn = db()

    try:

        conn.execute("""
        UPDATE polls
        SET message_id=?
        WHERE id=?
        """, (
            message_id,
            poll_id
        ))

        conn.commit()

    finally:

        conn.close()


# ============================================================
# POLL CAPTION
# ============================================================

def poll_caption(poll_id):

    poll = get_poll(poll_id)

    if not poll:

        return "❌ Poll not found."

    options = get_options(poll_id)

    total_votes = sum(
        int(row["votes"])
        for row in options
    )

    if poll["status"] == "closed":

        title = "🔒 <b>POLL CLOSED</b>"

    else:

        title = "✈️ <b>প্রিমিয়াম পোলিং সার্ভিস</b>"

    lines = [

        title,

        "━━━━━━━━━━━━━━━━━━━━",

        "",

        "❓ <b>প্রশ্ন:</b>",

        escape(
            poll["question"]
        ),

        "",
    ]

    for row in options:

        lines.append(
            f"👑 {escape(row['option_name'])} — "
            f"<b>{row['votes']}</b>"
        )

    lines.extend([
        "",
        f"📊 <b>Total Votes:</b> {total_votes}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ])

    text = "\n".join(lines)

    # Telegram photo caption limit
    if len(text) > 1024:

        text = text[:1020] + "..."

    return text


# ============================================================
# VOTE KEYBOARD
# ============================================================

def vote_keyboard(
    poll_id,
    closed=False
):

    options = get_options(
        poll_id
    )

    buttons = []

    row = []

    for option in options:

        button = InlineKeyboardButton(
            text=(
                f"📦 {option['votes']} | "
                f"👑 {option['option_name']}"
            ),
            callback_data=(
                f"VOTE|{poll_id}|{option['id']}"
            )
        )

        row.append(button)

        if len(row) == 2:

            buttons.append(row)

            row = []

    if row:

        buttons.append(row)

    if not closed:

        buttons.append([
            InlineKeyboardButton(
                "🛑 পোল বন্ধ করুন",
                callback_data=f"CLOSE|{poll_id}"
            )
        ])

    return InlineKeyboardMarkup(
        buttons
    )


# ============================================================
# CAST VOTE
# ============================================================

def cast_vote(
    poll_id,
    user_id,
    option_id
):

    conn = db()

    try:

        conn.execute("BEGIN IMMEDIATE")

        poll = conn.execute("""
        SELECT status
        FROM polls
        WHERE id=?
        """, (
            poll_id,
        )).fetchone()

        if not poll:

            conn.rollback()

            return "NOT_FOUND"

        if poll["status"] != "active":

            conn.rollback()

            return "CLOSED"

        option = conn.execute("""
        SELECT id
        FROM poll_options

        WHERE
            id=?
            AND poll_id=?
        """, (
            option_id,
            poll_id
        )).fetchone()

        if not option:

            conn.rollback()

            return "INVALID"

        # ====================================================
        # ONE USER ONE VOTE
        # ====================================================

        existing = conn.execute("""
        SELECT option_id
        FROM votes

        WHERE
            poll_id=?
            AND user_id=?
        """, (
            poll_id,
            user_id
        )).fetchone()

        if existing:

            conn.rollback()

            return "ALREADY"

        # ====================================================
        # INSERT VOTE
        # ====================================================

        conn.execute("""
        INSERT INTO votes (
            poll_id,
            user_id,
            option_id,
            created_at
        )

        VALUES (?, ?, ?, ?)
        """, (
            poll_id,
            user_id,
            option_id,
            datetime.now(
                timezone.utc
            ).isoformat()
        ))

        conn.execute("""
        UPDATE poll_options

        SET votes = votes + 1

        WHERE id=?
        """, (
            option_id,
        ))

        conn.commit()

        return "SUCCESS"

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# CLOSE POLL
# ============================================================

def close_poll(
    poll_id
):

    conn = db()

    try:

        result = conn.execute("""
        UPDATE polls

        SET
            status='closed',
            closed_at=?

        WHERE
            id=?
            AND status='active'
        """, (
            datetime.now(
                timezone.utc
            ).isoformat(),
            poll_id
        ))

        conn.commit()

        return result.rowcount > 0

    finally:

        conn.close()


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    save_user(
        update.effective_user
    )

    if update.effective_chat.type != ChatType.PRIVATE:

        await update.effective_message.reply_text(
            "📩 Bot-কে Private Chat-এ খুলে ব্যবহার করুন।"
        )

        return

    text = (
        "╔══════════════════════════╗\n"
        "      📊 <b>POLL MAKER PRO</b>\n"
        "╚══════════════════════════╝\n\n"

        "🚀 Professional Telegram Photo Poll Maker\n\n"

        "✨ <b>Features</b>\n"
        "• 🖼 Photo Poll\n"
        "• 🗳 One User = One Vote\n"
        "• 📊 Live Vote Count\n"
        "• 👥 2–40 Options\n"
        "• 📢 Group / Channel Publish\n"
        "• 🔒 Owner Poll Control\n\n"

        "👇 Poll তৈরি করতে /poll লিখুন।"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# /POLL
# ============================================================

async def poll_start(
    update,
    context
):

    if update.effective_chat.type != ChatType.PRIVATE:

        await update.effective_message.reply_text(
            "❌ /poll শুধু Bot-এর Private Chat থেকে ব্যবহার করুন।"
        )

        return ConversationHandler.END

    save_user(
        update.effective_user
    )

    context.user_data.clear()

    await update.effective_message.reply_text(
        "🎯 <b>POLL CREATOR</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"

        "📍 <b>STEP 1 / 5</b>\n\n"

        "আপনার Public Telegram "
        "<b>Group / Channel Username</b> দিন।\n\n"

        "Example:\n"
        "<code>@mychannel</code>\n\n"

        "অথবা:\n"
        "<code>t.me/mychannel</code>\n\n"

        "⚠️ Bot অবশ্যই ওই Group/Channel-এর Admin হতে হবে।\n\n"

        "❌ Cancel: /cancel",

        parse_mode="HTML"
    )

    return TARGET


# ============================================================
# TARGET RECEIVER
# ============================================================

async def receive_target(
    update,
    context
):

    username = normalize_username(
        update.message.text
    )

    msg = await update.message.reply_text(
        "🔍 <b>Target যাচাই করা হচ্ছে...</b>",
        parse_mode="HTML"
    )

    chat, error = await verify_target(
        context,
        username
    )

    if error:

        await msg.edit_text(
            error,
            parse_mode="HTML"
        )

        return TARGET

    context.user_data[
        "target_username"
    ] = username

    context.user_data[
        "target_chat_id"
    ] = chat.id

    context.user_data[
        "target_title"
    ] = chat.title or username

    context.user_data[
        "target_type"
    ] = chat.type

    await msg.edit_text(
        "✅ <b>TARGET VERIFIED</b>\n\n"

        f"📢 Name: "
        f"<b>{escape(chat.title or 'Unknown')}</b>\n\n"

        f"🔗 Username: "
        f"<code>{escape(username)}</code>\n\n"

        f"🆔 Chat ID: "
        f"<code>{chat.id}</code>\n\n"

        "🤖 Bot Admin: ✅\n"
        "📤 Publishing: ✅\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "🖼 <b>STEP 2 / 5</b>\n\n"

        "এখন Poll-এর <b>Photo</b> পাঠান।",

        parse_mode="HTML"
    )

    return PHOTO


# ============================================================
# PHOTO RECEIVER
# ============================================================

async def receive_photo(
    update,
    context
):

    if not update.message.photo:

        await update.message.reply_text(
            "❌ Photo পাঠান।"
        )

        return PHOTO

    photo = update.message.photo[-1]

    context.user_data[
        "photo_file_id"
    ] = photo.file_id

    await update.message.reply_text(
        "✅ <b>PHOTO RECEIVED</b>\n\n"

        "📝 <b>STEP 3 / 5</b>\n\n"

        "এখন Poll Question লিখুন।\n\n"

        "Example:\n"
        "<code>আমাদের গ্রুপে সবার প্রিয় কে?</code>",

        parse_mode="HTML"
    )

    return QUESTION


# ============================================================
# QUESTION RECEIVER
# ============================================================

async def receive_question(
    update,
    context
):

    question = (
        update.message.text or ""
    ).strip()

    if not question:

        await update.message.reply_text(
            "❌ Question খালি রাখা যাবে না।"
        )

        return QUESTION

    if len(question) > MAX_QUESTION_LENGTH:

        await update.message.reply_text(
            f"❌ Question সর্বোচ্চ "
            f"{MAX_QUESTION_LENGTH} অক্ষর হতে পারবে।"
        )

        return QUESTION

    context.user_data[
        "question"
    ] = question

    await update.message.reply_text(
        "👥 <b>STEP 4 / 5</b>\n\n"

        f"এখন {MIN_OPTIONS} থেকে "
        f"{MAX_OPTIONS} জনের নাম দিতে পারবেন।\n\n"

        "প্রতিটি নাম আলাদা লাইনে দিন।\n\n"

        "Example:\n\n"

        "আসিফ\n"
        "রনি\n"
        "কাজল\n"
        "সাকিব\n"
        "রাকিব\n"
        "নাঈম\n\n"

        "📌 Minimum: <b>2</b>\n"
        "📌 Maximum: <b>40</b>",

        parse_mode="HTML"
    )

    return OPTIONS


# ============================================================
# OPTIONS PARSER
# ============================================================

def parse_options(
    text
):

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if len(lines) < MIN_OPTIONS:

        raise ValueError(
            f"কমপক্ষে {MIN_OPTIONS} জনের নাম দিতে হবে।"
        )

    if len(lines) > MAX_OPTIONS:

        raise ValueError(
            f"সর্বোচ্চ {MAX_OPTIONS} জনের নাম দিতে পারবেন।"
        )

    result = []

    seen = set()

    for name in lines:

        if len(name) > MAX_OPTION_LENGTH:

            raise ValueError(
                f"একটি নাম সর্বোচ্চ "
                f"{MAX_OPTION_LENGTH} অক্ষর হতে পারবে।"
            )

        key = name.casefold()

        if key in seen:

            raise ValueError(
                f"❌ Duplicate নাম পাওয়া গেছে:\n"
                f"<b>{escape(name)}</b>"
            )

        seen.add(key)

        result.append(name)

    return result


# ============================================================
# OPTIONS RECEIVER
# ============================================================

async def receive_options(
    update,
    context
):

    try:

        options = parse_options(
            update.message.text or ""
        )

    except ValueError as e:

        await update.message.reply_text(
            str(e),
            parse_mode="HTML"
        )

        return OPTIONS

    question = context.user_data.get(
        "question"
    )

    photo_file_id = context.user_data.get(
        "photo_file_id"
    )

    target_chat_id = context.user_data.get(
        "target_chat_id"
    )

    if not all([
        question,
        photo_file_id,
        target_chat_id
    ]):

        context.user_data.clear()

        await update.message.reply_text(
            "❌ Session expired।\n\n"
            "আবার /poll দিন।"
        )

        return ConversationHandler.END

    context.user_data[
        "options"
    ] = options

    # ========================================================
    # PREVIEW
    # ========================================================

    preview = (
        "✈️ <b>প্রিমিয়াম পোলিং সার্ভিস</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"❓ <b>প্রশ্ন:</b>\n"
        f"{escape(question)}\n\n"
    )

    for name in options:

        preview += (
            f"👑 {escape(name)} — <b>0</b>\n"
        )

    preview += (
        "\n"
        "📊 <b>Total Votes:</b> 0\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    if len(preview) > 1024:

        await update.message.reply_text(
            "❌ Question/Name অনেক বড় হয়ে গেছে।\n\n"
            "ছোট Question বা নাম ব্যবহার করুন।"
        )

        return OPTIONS

    await update.message.reply_photo(
        photo=photo_file_id,
        caption=preview,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚀 PUBLISH & SEND",
                    callback_data="PUBLISH"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ EDIT",
                    callback_data="EDIT"
                ),
                InlineKeyboardButton(
                    "❌ CANCEL",
                    callback_data="CANCEL"
                )
            ]
        ])
    )

    return CONFIRM


# ============================================================
# CONFIRM CALLBACK
# ============================================================

async def confirm_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    # ========================================================
    # CANCEL
    # ========================================================

    if query.data == "CANCEL":

        context.user_data.clear()

        try:

            await query.edit_message_reply_markup(
                reply_markup=None
            )

        except TelegramError:

            pass

        await query.message.reply_text(
            "❌ Poll Creation Cancelled."
        )

        return ConversationHandler.END

    # ========================================================
    # EDIT
    # ========================================================

    if query.data == "EDIT":

        await query.message.reply_text(
            "✏️ নতুন Question লিখুন।"
        )

        return QUESTION

    # ========================================================
    # PUBLISH
    # ========================================================

    if query.data != "PUBLISH":

        return CONFIRM

    target_chat_id = context.user_data.get(
        "target_chat_id"
    )

    target_username = context.user_data.get(
        "target_username"
    )

    question = context.user_data.get(
        "question"
    )

    photo_file_id = context.user_data.get(
        "photo_file_id"
    )

    options = context.user_data.get(
        "options"
    )

    # ========================================================
    # SESSION CHECK
    # ========================================================

    if not all([
        target_chat_id,
        target_username,
        question,
        photo_file_id,
        options
    ]):

        await query.message.reply_text(
            "❌ Session expired।\n\n"
            "আবার /poll দিন।"
        )

        context.user_data.clear()

        return ConversationHandler.END

    # ========================================================
    # DISABLE PUBLISH BUTTON
    # ========================================================

    try:

        await query.edit_message_reply_markup(
            reply_markup=None
        )

    except TelegramError:

        pass

    status_message = await query.message.reply_text(
        "🚀 <b>Publishing...</b>\n\n"
        "⏳ Target Chat-এ Poll পাঠানো হচ্ছে...",
        parse_mode="HTML"
    )

    poll_id = None

    try:

        # ====================================================
        # CREATE DATABASE POLL
        # ====================================================

        poll_id = create_poll(
            target_chat_id=target_chat_id,
            creator_id=query.from_user.id,
            question=question,
            photo_file_id=photo_file_id,
            options=options
        )

        logger.info(
            "Created poll: %s",
            poll_id
        )

        # ====================================================
        # SEND PHOTO TO TARGET
        # ====================================================

        sent = await context.bot.send_photo(
            chat_id=target_chat_id,
            photo=photo_file_id,
            caption=poll_caption(
                poll_id
            ),
            parse_mode="HTML",
            reply_markup=vote_keyboard(
                poll_id
            )
        )

        # ====================================================
        # SAVE MESSAGE ID
        # ====================================================

        save_message_id(
            poll_id,
            sent.message_id
        )

        logger.info(
            "Published poll %s to %s",
            poll_id,
            target_username
        )

        # ====================================================
        # SUCCESS
        # ====================================================

        await status_message.edit_text(
            "╔══════════════════════════╗\n"
            "       ✅ <b>PUBLISHED</b>\n"
            "╚══════════════════════════╝\n\n"

            "🚀 Poll সফলভাবে Publish হয়েছে!\n\n"

            f"📢 Target:\n"
            f"<code>{escape(target_username)}</code>\n\n"

            f"🖼 Photo: ✅\n"
            f"🗳 Voting: ✅\n"
            f"👥 Options: <b>{len(options)}</b>\n"
            f"📊 Live Vote Count: ✅\n\n"

            f"🆔 Poll ID:\n"
            f"<code>{poll_id}</code>\n\n"

            "🔒 একজন User এই Poll-এ "
            "<b>একবারই Vote</b> দিতে পারবে।",

            parse_mode="HTML"
        )

        context.user_data.clear()

        return ConversationHandler.END

    # ========================================================
    # TELEGRAM ERROR
    # ========================================================

    except TelegramError as e:

        logger.exception(
            "Telegram publish error"
        )

        # যদি DB-তে Poll তৈরি হয়ে থাকে
        # কিন্তু Telegram-এ পাঠানো না যায়,
        # সেটি delete করে দিচ্ছি।

        if poll_id:

            try:

                conn = db()

                conn.execute(
                    "DELETE FROM polls WHERE id=?",
                    (poll_id,)
                )

                conn.commit()

                conn.close()

            except Exception:

                logger.exception(
                    "Database cleanup failed"
                )

        error_text = str(e)

        await status_message.edit_text(
            "❌ <b>PUBLISH FAILED</b>\n\n"

            "Telegram Target Chat-এ Poll পাঠাতে পারেনি।\n\n"

            "📢 Target:\n"
            f"<code>{escape(target_username)}</code>\n\n"

            "সম্ভাব্য কারণ:\n"
            "• Bot Admin নেই\n"
            "• Channel-এ Post Messages OFF\n"
            "• Group-এ Send Messages বন্ধ\n"
            "• Bot restricted\n"
            "• Username ভুল\n\n"

            "🔧 <b>Telegram Error:</b>\n"
            f"<code>{escape(error_text[:700])}</code>",

            parse_mode="HTML"
        )

        return CONFIRM

    # ========================================================
    # UNKNOWN ERROR
    # ========================================================

    except Exception as e:

        logger.exception(
            "Unexpected publish error"
        )

        if poll_id:

            try:

                conn = db()

                conn.execute(
                    "DELETE FROM polls WHERE id=?",
                    (poll_id,)
                )

                conn.commit()

                conn.close()

            except Exception:

                pass

        await status_message.edit_text(
            "❌ <b>Publish Error</b>\n\n"

            f"<code>{escape(str(e)[:700])}</code>\n\n"

            "আবার চেষ্টা করুন।",

            parse_mode="HTML"
        )

        return CONFIRM


# ============================================================
# VOTE CALLBACK
# ============================================================

async def vote_callback(
    update,
    context
):

    query = update.callback_query

    try:

        parts = query.data.split("|")

        if len(parts) != 3:

            await query.answer(
                "❌ Invalid vote.",
                show_alert=True
            )

            return

        poll_id = parts[1]

        option_id = int(
            parts[2]
        )

    except Exception:

        await query.answer(
            "❌ Invalid vote.",
            show_alert=True
        )

        return

    poll = get_poll(
        poll_id
    )

    if not poll:

        await query.answer(
            "❌ Poll পাওয়া যায়নি।",
            show_alert=True
        )

        return

    if poll["status"] != "active":

        await query.answer(
            "🔒 এই Poll বন্ধ হয়ে গেছে।",
            show_alert=True
        )

        return

    try:

        result = cast_vote(
            poll_id=poll_id,
            user_id=query.from_user.id,
            option_id=option_id
        )

    except Exception:

        logger.exception(
            "Vote database error"
        )

        await query.answer(
            "❌ Vote save করা যায়নি।",
            show_alert=True
        )

        return

    # ========================================================
    # VOTE RESULT
    # ========================================================

    if result == "SUCCESS":

        await query.answer(
            "✅ আপনার Vote নেওয়া হয়েছে!"
        )

    elif result == "ALREADY":

        await query.answer(
            "⚠️ আপনি ইতিমধ্যে Vote দিয়েছেন!\n"
            "এই Poll-এ দ্বিতীয়বার Vote দেওয়া যাবে না।",
            show_alert=True
        )

        return

    elif result == "CLOSED":

        await query.answer(
            "🔒 Poll বন্ধ হয়ে গেছে।",
            show_alert=True
        )

        return

    else:

        await query.answer(
            "❌ Invalid option.",
            show_alert=True
        )

        return

    # ========================================================
    # UPDATE LIVE COUNT
    # ========================================================

    try:

        await query.message.edit_caption(
            caption=poll_caption(
                poll_id
            ),
            parse_mode="HTML",
            reply_markup=vote_keyboard(
                poll_id
            )
        )

    except BadRequest as e:

        if "not modified" not in str(e).lower():

            logger.warning(
                "Caption update error: %s",
                e
            )

    except TelegramError as e:

        logger.warning(
            "Telegram edit error: %s",
            e
        )


# ============================================================
# CLOSE POLL
# ============================================================

async def close_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    try:

        poll_id = query.data.split(
            "|",
            1
        )[1]

    except Exception:

        return

    poll = get_poll(
        poll_id
    )

    if not poll:

        await query.answer(
            "❌ Poll পাওয়া যায়নি।",
            show_alert=True
        )

        return

    if poll["status"] != "active":

        await query.answer(
            "🔒 Poll already closed.",
            show_alert=True
        )

        return

    # ========================================================
    # ONLY TARGET CHAT OWNER
    # ========================================================

    try:

        member = await context.bot.get_chat_member(
            chat_id=poll["target_chat_id"],
            user_id=query.from_user.id
        )

    except TelegramError:

        await query.answer(
            "❌ Owner যাচাই করা যায়নি।",
            show_alert=True
        )

        return

    if member.status != ChatMemberStatus.OWNER:

        await query.answer(
            "❌ শুধু Target Chat-এর Owner "
            "Poll বন্ধ করতে পারবেন।",
            show_alert=True
        )

        return

    changed = close_poll(
        poll_id
    )

    if not changed:

        await query.answer(
            "ℹ️ Poll already closed.",
            show_alert=True
        )

        return

    await query.answer(
        "🔒 Poll Closed!"
    )

    try:

        await query.message.edit_caption(
            caption=poll_caption(
                poll_id
            ),
            parse_mode="HTML",
            reply_markup=vote_keyboard(
                poll_id,
                closed=True
            )
        )

    except TelegramError as e:

        logger.warning(
            "Close update error: %s",
            e
        )


# ============================================================
# /CANCEL
# ============================================================

async def cancel(
    update,
    context
):

    context.user_data.clear()

    await update.effective_message.reply_text(
        "❌ Poll creation cancelled."
    )

    return ConversationHandler.END


# ============================================================
# /ADMIN
# ============================================================

async def admin_command(
    update,
    context
):

    if update.effective_user.id != OWNER_ID:

        await update.effective_message.reply_text(
            "❌ Unauthorized."
        )

        return

    conn = db()

    try:

        users = conn.execute("""
        SELECT COUNT(*) AS total
        FROM users
        """).fetchone()["total"]

        polls = conn.execute("""
        SELECT COUNT(*) AS total
        FROM polls
        """).fetchone()["total"]

        active = conn.execute("""
        SELECT COUNT(*) AS total
        FROM polls
        WHERE status='active'
        """).fetchone()["total"]

        votes = conn.execute("""
        SELECT COUNT(*) AS total
        FROM votes
        """).fetchone()["total"]

    finally:

        conn.close()

    await update.effective_message.reply_text(
        "⚙️ <b>ADMIN PANEL</b>\n\n"

        f"👤 Users: <b>{users}</b>\n"
        f"📊 Polls: <b>{polls}</b>\n"
        f"🟢 Active: <b>{active}</b>\n"
        f"🗳 Total Votes: <b>{votes}</b>\n\n"

        f"👑 Owner ID:\n"
        f"<code>{OWNER_ID}</code>",

        parse_mode="HTML"
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context
):

    logger.exception(
        "UNHANDLED ERROR",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN পাওয়া যায়নি!\n"
            ".env ফাইলে BOT_TOKEN=YOUR_BOT_TOKEN দিন।"
        )

    init_db()

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # POLL CONVERSATION
    # ========================================================

    poll_conversation = ConversationHandler(

        entry_points=[
            CommandHandler(
                "poll",
                poll_start
            )
        ],

        states={

            TARGET: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_target
                )

            ],

            PHOTO: [

                MessageHandler(
                    filters.PHOTO,
                    receive_photo
                )

            ],

            QUESTION: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_question
                )

            ],

            OPTIONS: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_options
                )

            ],

            CONFIRM: [

                CallbackQueryHandler(
                    confirm_callback,
                    pattern=r"^(PUBLISH|EDIT|CANCEL)$"
                )

            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel
            )
        ],

        allow_reentry=True,

        per_chat=True,

        per_user=True
    )

    # ========================================================
    # COMMANDS
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            start
        )
    )

    # ========================================================
    # POLL CREATOR
    # ========================================================

    application.add_handler(
        poll_conversation
    )

    # ========================================================
    # VOTE BUTTON
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            vote_callback,
            pattern=r"^VOTE\|[a-f0-9]+\|\d+$"
        )
    )

    # ========================================================
    # CLOSE BUTTON
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            close_callback,
            pattern=r"^CLOSE\|[a-f0-9]+$"
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "======================================"
    )

    logger.info(
        "📊 POLL MAKER PRO STARTED"
    )

    logger.info(
        "👑 OWNER ID: %s",
        OWNER_ID
    )

    logger.info(
        "👥 OPTIONS: %s - %s",
        MIN_OPTIONS,
        MAX_OPTIONS
    )

    logger.info(
        "======================================"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False
    )


# ============================================================
# START BOT
# ============================================================

if __name__ == "__main__":

    main()