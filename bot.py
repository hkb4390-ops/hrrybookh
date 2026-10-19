# ================================================================
#  BHRAMASTRA PREMIUM PDF & CHANNEL GROWTH ENGINE
#  Python + pyTelegramBotAPI + SQLite
#  Hosting: Render Background Worker
# ================================================================

import os
import re
import time
import html
import sqlite3
import logging
import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from urllib.parse import quote

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
from dotenv import load_dotenv


# ================================================================
# 1. ENVIRONMENT CONFIGURATION
# ================================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv(
    "BOT_USERNAME", "hrrrrrrrrry_bot"
).strip().lstrip("@")

CHANNEL_USERNAME = os.getenv(
    "CHANNEL_USERNAME", "@hrbseb10thallcorse"
).strip()

ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
DATABASE_PATH = os.getenv(
    "DATABASE_PATH", "bot_database.db"
).strip()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from environment.")

if not ADMIN_ID_RAW.isdigit():
    raise RuntimeError("ADMIN_ID must be your numeric Telegram user ID.")

ADMIN_ID = int(ADMIN_ID_RAW)

if not DATABASE_PATH:
    raise RuntimeError("DATABASE_PATH cannot be empty.")

os.makedirs(
    os.path.dirname(os.path.abspath(DATABASE_PATH)),
    exist_ok=True
)


# ================================================================
# 2. LOGGING
# ================================================================

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("bhramastra")


# ================================================================
# 3. TELEGRAM BOT INITIALIZATION
# ================================================================

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML",
    threaded=True,
    num_threads=8
)

BOT_ID = None

DB_LOCK = threading.RLock()


# ================================================================
# 4. PREMIUM PDF REWARDS
# ================================================================

PDF_REWARDS = [
    {
        "id": 1,
        "name": "Economics",
        "emoji": "💰",
        "url": (
            "https://drive.google.com/file/d/"
            "1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view"
        )
    },
    {
        "id": 2,
        "name": "Physics",
        "emoji": "⚡",
        "url": (
            "https://drive.google.com/file/d/"
            "1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view"
        )
    },
    {
        "id": 3,
        "name": "Civics",
        "emoji": "🏛️",
        "url": (
            "https://drive.google.com/file/d/"
            "1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view"
        )
    },
    {
        "id": 4,
        "name": "History",
        "emoji": "📜",
        "url": (
            "https://drive.google.com/file/d/"
            "1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view"
        )
    },
    {
        "id": 5,
        "name": "Maths",
        "emoji": "📐",
        "url": (
            "https://drive.google.com/file/d/"
            "1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view"
        )
    },
    {
        "id": 6,
        "name": "Chemistry",
        "emoji": "🧪",
        "url": (
            "https://drive.google.com/file/d/"
            "1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view"
        )
    },
    {
        "id": 7,
        "name": "Biology",
        "emoji": "🧬",
        "url": (
            "https://drive.google.com/file/d/"
            "1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view"
        )
    },
    {
        "id": 8,
        "name": "Sanskrit",
        "emoji": "🕉️",
        "url": (
            "https://drive.google.com/file/d/"
            "1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view"
        )
    },
    {
        "id": 9,
        "name": "English",
        "emoji": "📖",
        "url": (
            "https://drive.google.com/file/d/"
            "1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view"
        )
    }
]

TOTAL_REWARDS = len(PDF_REWARDS)


# ================================================================
# 5. DATABASE INITIALIZATION
# ================================================================

@contextmanager
def get_db():
    """
    Open a SQLite connection for one operation.
    Connections are not shared between worker threads.
    """
    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def init_database():
    """Create tables and indexes if they do not exist."""

    with DB_LOCK, get_db() as conn:

        conn.execute("PRAGMA journal_mode = WAL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL DEFAULT '',
                invite_link TEXT UNIQUE,
                joins_count INTEGER NOT NULL DEFAULT 0,
                joined_date TEXT NOT NULL,
                last_seen TEXT,
                is_blocked INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Tracks actual referral events to prevent duplicates.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_user_id INTEGER NOT NULL UNIQUE,
                invite_link TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                UNIQUE(referrer_id, referred_user_id)
            )
        """)

        # Tracks invite links created and owned by users.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invite_links (
                invite_link TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Saves dashboard message IDs for editing.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_messages (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_joins
            ON users(joins_count DESC)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_owner
            ON referral_events(referrer_id)
        """)

    logger.info("SQLite database initialized.")


# ================================================================
# 6. DATABASE HELPERS
# ================================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_user(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()


def register_user(user_id, first_name):
    """
    Register a new user without overwriting referral data
    when an existing user opens the bot again.
    """

    now = utc_now()

    with DB_LOCK, get_db() as conn:

        conn.execute("""
            INSERT INTO users (
                user_id,
                first_name,
                joined_date,
                last_seen
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_seen = excluded.last_seen,
                is_blocked = 0
        """, (
            user_id,
            first_name or "Student",
            now,
            now
        ))


def save_invite_link(user_id, invite_link):
    with DB_LOCK, get_db() as conn:

        conn.execute("""
            INSERT INTO invite_links (
                invite_link,
                owner_id,
                created_at
            )
            VALUES (?, ?, ?)

            ON CONFLICT(invite_link) DO NOTHING
        """, (
            invite_link,
            user_id,
            utc_now()
        ))

        conn.execute("""
            UPDATE users
            SET invite_link = ?
            WHERE user_id = ?
        """, (
            invite_link,
            user_id
        ))


def get_invite_owner(invite_link):
    if not invite_link:
        return None

    with get_db() as conn:
        row = conn.execute("""
            SELECT owner_id
            FROM invite_links
            WHERE invite_link = ?
        """, (invite_link,)).fetchone()

    return row["owner_id"] if row else None


def get_total_users():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM users"
        ).fetchone()

    return row["total"]


def get_total_referrals():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM referral_events"
        ).fetchone()

    return row["total"]


def get_total_unlocked():
    with get_db() as conn:
        row = conn.execute(
            "SELECT SUM(joins_count) AS total FROM users"
        ).fetchone()

    return row["total"] or 0


# ================================================================
# 7. TELEGRAM MEMBERSHIP VERIFICATION
# ================================================================

def is_channel_member(user_id):
    """
    Return True only when Telegram confirms membership.

    An API error must not be treated as proof of membership.
    """

    try:
        member = bot.get_chat_member(
            CHANNEL_USERNAME,
            user_id
        )

        return member.status in (
            "creator",
            "administrator",
            "member"
        ) or (
            member.status == "restricted"
            and getattr(member, "is_member", False)
        )

    except ApiTelegramException as exc:
        logger.warning(
            "Membership check failed for %s: %s",
            user_id,
            exc
        )
        return False

    except Exception:
        logger.exception("Unexpected membership error.")
        return False


# ================================================================
# 8. INLINE KEYBOARDS
# ================================================================

def subscription_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "📢 Join Official Channel",
            url="https://t.me/" +
                CHANNEL_USERNAME.lstrip("@")
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Verify Membership",
            callback_data="verify_join"
        )
    )

    return keyboard


def main_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.row(
        types.InlineKeyboardButton(
            "🔗 Generate VIP Link",
            callback_data="generate_link"
        ),
        types.InlineKeyboardButton(
            "📊 My Dashboard",
            callback_data="dashboard"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📚 Premium PDF Center",
            callback_data="pdf_center"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🏆 Global Leaderboard",
            callback_data="leaderboard"
        )
    )

    return keyboard


def back_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ Main Menu",
            callback_data="main_menu"
        )
    )

    return keyboard


# ================================================================
# 9. MESSAGE HELPERS
# ================================================================

def send_or_edit_callback(call, text, keyboard=None):
    """
    Edit the existing callback message when possible.
    Send a new message if editing is not possible.
    """

    try:
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except ApiTelegramException as exc:
        # Telegram returns an error if the content is unchanged.
        if "message is not modified" in str(exc).lower():
            return

        try:
            bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except Exception:
            logger.exception("Could not send callback response.")


def send_main_menu(chat_id, user):
    first_name = html.escape(
        user.first_name or "Student"
    )

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "   ⚡ <b>BHRAMASTRA PREMIUM</b>\n"
        "      REWARD ENGINE\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👋 Welcome, <b>{first_name}</b>!\n\n"
        "🎯 <b>Invite Friends. Unlock Books.</b>\n"
        "📚 Unlock all 9 premium study PDFs.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 Your personal reward center is ready.\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Choose an option below:</b>"
    )

    bot.send_message(
        chat_id,
        text,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True
    )


def send_force_subscription(chat_id):
    text = (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "       🛑 <b>CHANNEL ACCESS REQUIRED</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Bhramastra ki premium books unlock karne "
        "ke liye pehle hamara official Telegram "
        "channel join karein.\n\n"
        "📚 Join the channel, then tap Verify.\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    bot.send_message(
        chat_id,
        text,
        reply_markup=subscription_keyboard(),
        disable_web_page_preview=True
    )


# ================================================================
# 10. REFERRAL DASHBOARD
# ================================================================

def build_progress(joins_count):
    joins_count = max(
        0,
        min(joins_count, TOTAL_REWARDS)
    )

    return (
        "🟢" * joins_count
        + "🔴" * (TOTAL_REWARDS - joins_count)
    )


def dashboard_text(user):
    joins = min(
        user["joins_count"],
        TOTAL_REWARDS
    )

    first_name = html.escape(
        user["first_name"] or "Student"
    )

    unlocked = joins

    if joins >= TOTAL_REWARDS:
        next_reward_text = "🎉 All 9 PDFs unlocked!"
        needed_text = "0"
    else:
        next_reward = PDF_REWARDS[joins]
        next_reward_text = (
            f"{next_reward['emoji']} "
            f"{html.escape(next_reward['name'])}"
        )
        needed_text = "1"

    return (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "       📊 <b>MY DASHBOARD</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👤 Name: <b>{first_name}</b>\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n\n"
        f"👥 Successful Referrals: "
        f"<b>{joins}/9</b>\n"
        f"📚 PDFs Unlocked: "
        f"<b>{unlocked}/9</b>\n\n"
        "<b>YOUR PROGRESS</b>\n"
        f"{build_progress(joins)}\n\n"
        f"🎯 Next Reward: {next_reward_text}\n"
        f"👥 More Referrals Needed: "
        f"<b>{needed_text}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ Invite friends to unlock your next book."
    )


def show_dashboard(chat_id, user_id, save_message=False):
    user = get_user(user_id)

    if not user:
        return

    text = dashboard_text(user)

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "🔗 Generate VIP Link",
            callback_data="generate_link"
        ),
        types.InlineKeyboardButton(
            "📚 Open PDF Center",
            callback_data="pdf_center"
        ),
        types.InlineKeyboardButton(
            "🔄 Refresh Dashboard",
            callback_data="dashboard_refresh"
        ),
        types.InlineKeyboardButton(
            "⬅️ Main Menu",
            callback_data="main_menu"
        )
    )

    msg = bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

    if save_message:
        with DB_LOCK, get_db() as conn:
            conn.execute("""
                INSERT INTO dashboard_messages (
                    user_id,
                    chat_id,
                    message_id,
                    updated_at
                )
                VALUES (?, ?, ?, ?)

                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    message_id = excluded.message_id,
                    updated_at = excluded.updated_at
            """, (
                user_id,
                chat_id,
                msg.message_id,
                utc_now()
            ))


def refresh_saved_dashboard(user_id):
    """
    Edit a saved dashboard when referral counts change.
    Telegram errors do not interrupt referral processing.
    """

    user = get_user(user_id)

    if not user:
        return

    with get_db() as conn:
        row = conn.execute("""
            SELECT chat_id, message_id
            FROM dashboard_messages
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "📚 Premium PDF Center",
            callback_data="pdf_center"
        ),
        types.InlineKeyboardButton(
            "🔄 Refresh Dashboard",
            callback_data="dashboard_refresh"
        ),
        types.InlineKeyboardButton(
            "⬅️ Main Menu",
            callback_data="main_menu"
        )
    )

    try:
        bot.edit_message_text(
            dashboard_text(user),
            chat_id=row["chat_id"],
            message_id=row["message_id"],
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    except ApiTelegramException as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning(
                "Dashboard update failed for %s: %s",
                user_id,
                exc
            )


# ================================================================
# 11. PDF CENTER
# ================================================================

def pdf_center_text(user):
    joins = user["joins_count"]

    lines = [
        "╭━━━━━━━━━━━━━━━━━━━━╮",
        "       📚 <b>PREMIUM PDF CENTER</b>",
        "╰━━━━━━━━━━━━━━━━━━━━╯",
        "",
        f"🔓 Unlocked: <b>{min(joins, 9)}/9</b>",
        ""
    ]

    for pdf in PDF_REWARDS:
        if joins >= pdf["id"]:
            status = "✅ UNLOCKED"
        else:
            status = (
                f"🔒 Need {pdf['id']} referral"
                f"{'s' if pdf['id'] != 1 else ''}"
            )

        lines.append(
            f"{pdf['emoji']} <b>{pdf['id']}. "
            f"{html.escape(pdf['name'])}</b>"
        )
        lines.append(f"   {status}")
        lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Invite more friends to unlock locked PDFs."
    )

    return "\n".join(lines)


def pdf_center_keyboard(user):
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    joins = user["joins_count"]

    for pdf in PDF_REWARDS:
        if joins >= pdf["id"]:
            keyboard.add(
                types.InlineKeyboardButton(
                    f"📥 {pdf['name']} — Download",
                    url=pdf["url"]
                )
            )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔗 Generate VIP Link",
            callback_data="generate_link"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ Main Menu",
            callback_data="main_menu"
        )
    )

    return keyboard


# ================================================================
# 12. UNIQUE VIP INVITE LINK
# ================================================================

def generate_invite_link(user_id):
    """
    Reuse the existing link whenever Telegram still recognizes it.
    Generate a new link only when necessary.

    Invite links are mapped in the database so joins can be
    attributed to the correct referrer.
    """

    user = get_user(user_id)

    if user and user["invite_link"]:
        return user["invite_link"]

    try:
        invite = bot.create_chat_invite_link(
            CHANNEL_USERNAME,
            name=f"Invite_{user_id}",
            creates_join_request=False
        )

        link = invite.invite_link

        save_invite_link(
            user_id,
            link
        )

        return link

    except ApiTelegramException:
        logger.exception(
            "Invite creation failed for %s",
            user_id
        )
        return None


def invite_link_message(user_id):
    link = generate_invite_link(user_id)

    if not link:
        return (
            "❌ <b>Invite link could not be created.</b>\n\n"
            "Please try again later. If the issue continues, "
            "check the bot's channel administrator permissions."
        ), back_keyboard()

    share_text = (
        "Join our official Telegram channel and "
        "help me unlock Bhramastra premium study PDFs!\n\n"
        f"{link}"
    )

    share_url = (
        "https://t.me/share/url?url="
        + quote(link, safe="")
        + "&text="
        + quote(
            "Join our official channel! "
            "Help me unlock Bhramastra premium study PDFs.",
            safe=""
        )
    )

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "📤 Share VIP Link",
            url=share_url
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📊 My Dashboard",
            callback_data="dashboard"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ Main Menu",
            callback_data="main_menu"
        )
    )

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "       🔗 <b>YOUR VIP INVITE LINK</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "🎯 Share your unique invite link with friends.\n\n"
        f"<code>{html.escape(link)}</code>\n\n"
        "📚 Every eligible new member who joins through "
        "your link can unlock one reward for you.\n\n"
        "⚠️ Only confirmed, unique channel joins count.\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    return text, keyboard


# ================================================================
# 13. LEADERBOARD
# ================================================================

def leaderboard_text():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT user_id, first_name, joins_count
            FROM users
            WHERE joins_count > 0
            ORDER BY joins_count DESC, joined_date ASC
            LIMIT 5
        """).fetchall()

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    lines = [
        "╭━━━━━━━━━━━━━━━━━━━━╮",
        "       🏆 <b>GLOBAL LEADERBOARD</b>",
        "╰━━━━━━━━━━━━━━━━━━━━╯",
        "",
        "🔥 Top 5 Referral Champions",
        ""
    ]

    if not rows:
        lines.append(
            "No champions yet. Be the first to join the race!"
        )
    else:
        for index, row in enumerate(rows):
            name = html.escape(
                row["first_name"] or "Student"
            )

            lines.append(
                f"{medals[index]} <b>{name}</b>\n"
                f"   👥 {row['joins_count']} successful referrals\n"
            )

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        "🚀 Invite friends and climb the rankings!"
    ])

    return "\n".join(lines)


# ================================================================
# 14. REFERRAL EVENT PROCESSING
# ================================================================

def process_referral(new_member_id, invite_link):
    """
    Count one eligible join per referred Telegram user.

    The database UNIQUE constraint prevents duplicate event
    processing when Telegram sends the same update more than once.
    """

    owner_id = get_invite_owner(invite_link)

    if not owner_id:
        return

    # Never count self-referrals.
    if owner_id == new_member_id:
        logger.warning(
            "Self-referral rejected for %s",
            owner_id
        )
        return

    owner = get_user(owner_id)

    if not owner:
        return

    # A referred user must be registered with the bot first.
    if not get_user(new_member_id):
        logger.info(
            "Referral ignored: referred user %s is not registered.",
            new_member_id
        )
        return

    now = utc_now()

    try:
        with DB_LOCK, get_db() as conn:

            cursor = conn.execute("""
                INSERT OR IGNORE INTO referral_events (
                    referrer_id,
                    referred_user_id,
                    invite_link,
                    joined_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                owner_id,
                new_member_id,
                invite_link,
                now
            ))

            # Duplicate or previously counted referral.
            if cursor.rowcount != 1:
                return

            conn.execute("""
                UPDATE users
                SET joins_count = (
                    SELECT COUNT(*)
                    FROM referral_events
                    WHERE referrer_id = ?
                )
                WHERE user_id = ?
            """, (
                owner_id,
                owner_id
            ))

    except sqlite3.Error:
        logger.exception("Referral database update failed.")
        return

    logger.info(
        "Referral confirmed: referrer=%s referred=%s",
        owner_id,
        new_member_id
    )

    refresh_saved_dashboard(owner_id)

    try:
        updated = get_user(owner_id)

        if updated:
            count = min(
                updated["joins_count"],
                TOTAL_REWARDS
            )

            if count >= TOTAL_REWARDS:
                reward_text = (
                    "🎉 Congratulations! All 9 PDFs are unlocked."
                )
            else:
                reward = PDF_REWARDS[count - 1]

                reward_text = (
                    f"🎁 Newly unlocked: "
                    f"{reward['emoji']} {reward['name']}"
                )

            bot.send_message(
                owner_id,
                "🎉 <b>VIP REFERRAL CONFIRMED!</b>\n\n"
                "A new eligible member joined through your link.\n\n"
                f"👥 Total referrals: <b>{count}</b>\n"
                f"📚 PDFs unlocked: <b>{count}/9</b>\n\n"
                f"{reward_text}\n\n"
                "Open your dashboard to see your progress.",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton(
                        "📊 Open Dashboard",
                        callback_data="dashboard"
                    ),
                    types.InlineKeyboardButton(
                        "📚 PDF Center",
                        callback_data="pdf_center"
                    )
                )
            )

    except Exception:
        logger.exception(
            "Referral notification failed for %s",
            owner_id
        )


# ================================================================
# 15. /START COMMAND
# ================================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id

    register_user(
        user_id,
        message.from_user.first_name
    )

    # Register the user first, even when they have not joined
    # the required channel. Referral tracking requires a DB record.
    args = message.text.split(maxsplit=1)

    # Optional deep-link support: /start ref_123456789
    if len(args) > 1:
        payload = args[1].strip()

        if re.fullmatch(r"ref_\d{1,20}", payload):
            referrer_id = int(payload[4:])

            if referrer_id != user_id:
                logger.info(
                    "Deep-link referral request: %s -> %s",
                    referrer_id,
                    user_id
                )

    if not is_channel_member(user_id):
        send_force_subscription(
            message.chat.id
        )
        return

    send_main_menu(
        message.chat.id,
        message.from_user
    )


# ================================================================
# 16. /HELP COMMAND
# ================================================================

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.reply_to(
        message,
        "📚 <b>Bhramastra Premium Help</b>\n\n"
        "/start — Open the premium menu\n"
        "/help — Show this help message\n"
        "/broadcast — Admin-only broadcast command\n\n"
        "Use your personal invite link to unlock PDFs."
    )


# ================================================================
# 17. ADMIN STATISTICS
# ================================================================

@bot.message_handler(commands=["stats"])
def stats_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(
            message,
            "⛔ You are not authorized to use this command."
        )
        return

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "       🛡️ <b>ADMIN STATISTICS</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👥 Registered users: <b>{get_total_users()}</b>\n"
        f"🔗 Confirmed referrals: "
        f"<b>{get_total_referrals()}</b>\n"
        f"📚 Total referral credits: "
        f"<b>{get_total_unlocked()}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    bot.reply_to(message, text)


# ================================================================
# 18. ADMIN BROADCAST
# ================================================================

@bot.message_handler(
    commands=["broadcast"],
    func=lambda message: message.from_user.id == ADMIN_ID
)
def broadcast_command(message):
    """
    Usage:
        /broadcast Hello everyone!

    Broadcast text to registered users.
    This handler is restricted to ADMIN_ID.
    """

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(
            message,
            "Usage:\n<code>/broadcast Your message here</code>"
        )
        return

    broadcast_text = parts[1].strip()

    if len(broadcast_text) > 4000:
        bot.reply_to(
            message,
            "❌ Message too long. Keep it under 4000 characters."
        )
        return

    with get_db() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

    total = len(rows)
    sent = 0
    failed = 0
    blocked = 0

    status_message = bot.reply_to(
        message,
        "📡 <b>Broadcast Started</b>\n\n"
        f"👥 Recipients: {total}\n"
        "⏳ Status: Processing..."
    )

    for index, row in enumerate(rows, start=1):
        target_id = row["user_id"]

        try:
            bot.send_message(
                target_id,
                "📢 <b>ANNOUNCEMENT</b>\n\n"
                + html.escape(broadcast_text),
                disable_web_page_preview=True
            )

            sent += 1

            with get_db() as conn:
                conn.execute("""
                    UPDATE users
                    SET is_blocked = 0
                    WHERE user_id = ?
                """, (target_id,))

        except ApiTelegramException as exc:
            failed += 1

            error_text = str(exc).lower()

            if (
                "bot was blocked by the user" in error_text
                or "user is deactivated" in error_text
                or "chat not found" in error_text
            ):
                blocked += 1

                with get_db() as conn:
                    conn.execute("""
                        UPDATE users
                        SET is_blocked = 1
                        WHERE user_id = ?
                    """, (target_id,))

            else:
                logger.warning(
                    "Broadcast failed for %s: %s",
                    target_id,
                    exc
                )

        except Exception:
            failed += 1
            logger.exception(
                "Unexpected broadcast error for %s",
                target_id
            )

        # Stay below Telegram's practical message throughput.
        time.sleep(0.05)

        # Edit the progress message periodically.
        if index % 25 == 0:
            try:
                bot.edit_message_text(
                    "📡 <b>BROADCAST IN PROGRESS</b>\n\n"
                    f"👥 Total: {total}\n"
                    f"✅ Sent: {sent}\n"
                    f"❌ Failed: {failed}\n"
                    f"🔄 Processed: {index}/{total}",
                    chat_id=status_message.chat.id,
                    message_id=status_message.message_id
                )
            except Exception:
                pass

    try:
        bot.edit_message_text(
            "╭━━━━━━━━━━━━━━━━━━━━╮\n"
            "       📡 <b>BROADCAST COMPLETE</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"👥 Total recipients: <b>{total}</b>\n"
            f"✅ Successfully sent: <b>{sent}</b>\n"
            f"❌ Failed: <b>{failed}</b>\n"
            f"🚫 Blocked/unavailable: <b>{blocked}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id
        )
    except Exception:
        logger.exception("Could not update broadcast summary.")


@bot.message_handler(
    commands=["broadcast"],
    func=lambda message: message.from_user.id != ADMIN_ID
)
def unauthorized_broadcast(message):
    bot.reply_to(
        message,
        "⛔ You are not authorized to use this command."
    )


# ================================================================
# 19. CALLBACK QUERY HANDLER
# ================================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data or ""

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    # Ensure every callback user is registered.
    register_user(
        user_id,
        call.from_user.first_name
    )

    # Verify membership.
    if data == "verify_join":
        if is_channel_member(user_id):
            try:
                bot.answer_callback_query(
                    call.id,
                    "✅ Membership verified!",
                    show_alert=False
                )
            except Exception:
                pass

            send_or_edit_callback(
                call,
                "🎉 <b>VERIFICATION SUCCESSFUL!</b>\n\n"
                "Welcome to Bhramastra Premium.\n"
                "Your reward journey starts now.",
                main_menu_keyboard()
            )
        else:
            try:
                bot.answer_callback_query(
                    call.id,
                    "Please join the channel first.",
                    show_alert=True
                )
            except Exception:
                pass

        return

    # Enforce channel membership for every premium action.
    if not is_channel_member(user_id):
        try:
            bot.answer_callback_query(
                call.id,
                "Join the official channel to continue.",
                show_alert=True
            )
        except Exception:
            pass

        send_force_subscription(
            call.message.chat.id
        )
        return

    # Main menu.
    if data == "main_menu":
        send_or_edit_callback(
            call,
            "⚡ <b>BHRAMASTRA PREMIUM</b>\n\n"
            "Welcome back! Choose your next action.",
            main_menu_keyboard()
        )
        return

    # Generate/retrieve invite link.
    if data == "generate_link":
        text, keyboard = invite_link_message(user_id)

        send_or_edit_callback(
            call,
            text,
            keyboard
        )
        return

    # Dashboard.
    if data in ("dashboard", "dashboard_refresh"):
        user = get_user(user_id)

        if user:
            text = dashboard_text(user)

            keyboard = types.InlineKeyboardMarkup(row_width=1)

            keyboard.add(
                types.InlineKeyboardButton(
                    "🔗 Generate VIP Link",
                    callback_data="generate_link"
                ),
                types.InlineKeyboardButton(
                    "📚 Premium PDF Center",
                    callback_data="pdf_center"
                ),
                types.InlineKeyboardButton(
                    "🔄 Refresh Dashboard",
                    callback_data="dashboard_refresh"
                ),
                types.InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="main_menu"
                )
            )

            send_or_edit_callback(
                call,
                text,
                keyboard
            )

            # Save the current message for future automatic updates.
            with DB_LOCK, get_db() as conn:
                conn.execute("""
                    INSERT INTO dashboard_messages (
                        user_id,
                        chat_id,
                        message_id,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)

                    ON CONFLICT(user_id) DO UPDATE SET
                        chat_id = excluded.chat_id,
                        message_id = excluded.message_id,
                        updated_at = excluded.updated_at
                """, (
                    user_id,
                    call.message.chat.id,
                    call.message.message_id,
                    utc_now()
                ))

        return

    # PDF center.
    if data == "pdf_center":
        user = get_user(user_id)

        if user:
            send_or_edit_callback(
                call,
                pdf_center_text(user),
                pdf_center_keyboard(user)
            )
        return

    # Leaderboard.
    if data == "leaderboard":
        send_or_edit_callback(
            call,
            leaderboard_text(),
            back_keyboard()
        )
        return

    # Unknown callback.
    try:
        bot.answer_callback_query(
            call.id,
            "This button is no longer available.",
            show_alert=True
        )
    except Exception:
        pass


# ================================================================
# 20. LIVE CHANNEL MEMBER EVENTS
# ================================================================

@bot.chat_member_handler()
def channel_member_update(update):
    """
    Telegram sends chat_member updates when the bot is an admin.

    We count a transition into membership only once per referred
    user. A previously counted member who leaves and rejoins will
    not earn another referral credit.
    """

    chat = update.chat

    expected_username = CHANNEL_USERNAME.lstrip("@").lower()

    if chat.username:
        if chat.username.lower() != expected_username:
            return
    elif str(chat.id) != CHANNEL_USERNAME:
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    active_statuses = {
        "member",
        "administrator",
        "creator"
    }

    was_member = (
        old_status in active_statuses
        or (
            old_status == "restricted"
            and getattr(
                update.old_chat_member,
                "is_member",
                False
            )
        )
    )

    is_member_now = (
        new_status in active_statuses
        or (
            new_status == "restricted"
            and getattr(
                update.new_chat_member,
                "is_member",
                False
            )
        )
    )

    # Only process a genuine transition into membership.
    if was_member or not is_member_now:
        return

    new_user = update.new_chat_member.user

    if new_user.is_bot:
        return

    inviter = getattr(
        update,
        "invite_link",
        None
    )

    if not inviter:
        logger.info(
            "Join without invite link: user=%s",
            new_user.id
        )
        return

    process_referral(
        new_user.id,
        inviter.invite_link
    )


# ================================================================
# 21. BOT COMMAND MENU
# ================================================================

def setup_commands():
    commands = [
        types.BotCommand(
            "start",
            "Open Bhramastra Premium"
        ),
        types.BotCommand(
            "help",
            "Help and instructions"
        ),
        types.BotCommand(
            "stats",
            "Admin statistics"
        )
    ]

    bot.set_my_commands(commands)


# ================================================================
# 22. STARTUP AND POLLING
# ================================================================

def main():
    global BOT_ID

    init_database()

    me = bot.get_me()

    BOT_ID = me.id

    logger.info(
        "Bot started: @%s (ID: %s)",
        me.username,
        me.id
    )

    logger.info(
        "Channel configured: %s",
        CHANNEL_USERNAME
    )

    setup_commands()

    # Remove any previous webhook before using long polling.
    # This must be the only active polling instance for this token.
    bot.delete_webhook(drop_pending_updates=False)

    logger.info("Starting Telegram long polling...")

    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=25,
        skip_pending=False,
        allowed_updates=[
            "message",
            "callback_query",
            "chat_member"
        ]
    )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")

    except Exception:
        logger.exception("Fatal bot startup/runtime error.")
        raise
