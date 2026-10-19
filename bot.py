import os
import time
import html
import sqlite3
import logging
import threading
from datetime import datetime, timezone
from contextlib import contextmanager

import telebot
from telebot import types
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
CHANNEL_USERNAME = os.getenv(
    "CHANNEL_USERNAME", "hrbseb10thallcorse"
).strip().lstrip("@")
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0").strip()
DATABASE_PATH = os.getenv(
    "DATABASE_PATH", "bot_database.db"
).strip()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from environment variables.")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID.")

if not CHANNEL_ID:
    raise RuntimeError("CHANNEL_ID is missing from environment variables.")

try:
    CHANNEL_ID = int(CHANNEL_ID)
except ValueError:
    raise RuntimeError("CHANNEL_ID must be a numeric channel ID.")

if not BOT_USERNAME:
    raise RuntimeError("BOT_USERNAME is missing from environment variables.")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("bhramastra-bot")

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML",
    threaded=True,
    num_threads=8,
)

DB_LOCK = threading.RLock()

# ============================================================
# PDF REWARDS
# ============================================================

PDF_REWARDS = [
    {
        "id": 1,
        "title": "Economics",
        "emoji": "📊",
        "threshold": 1,
        "url": "https://drive.google.com/file/d/1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view?usp=drivesdk",
    },
    {
        "id": 2,
        "title": "Physics",
        "emoji": "⚡",
        "threshold": 2,
        "url": "https://drive.google.com/file/d/1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view?usp=drivesdk",
    },
    {
        "id": 3,
        "title": "Civics",
        "emoji": "🏛️",
        "threshold": 3,
        "url": "https://drive.google.com/file/d/1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view?usp=drivesdk",
    },
    {
        "id": 4,
        "title": "History",
        "emoji": "📜",
        "threshold": 4,
        "url": "https://drive.google.com/file/d/1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view?usp=drivesdk",
    },
    {
        "id": 5,
        "title": "Mathematics",
        "emoji": "📐",
        "threshold": 5,
        "url": "https://drive.google.com/file/d/1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view?usp=drivesdk",
    },
    {
        "id": 6,
        "title": "Chemistry",
        "emoji": "🧪",
        "threshold": 6,
        "url": "https://drive.google.com/file/d/1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view?usp=drivesdk",
    },
    {
        "id": 7,
        "title": "Biology",
        "emoji": "🧬",
        "threshold": 7,
        "url": "https://drive.google.com/file/d/1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view?usp=drivesdk",
    },
    {
        "id": 8,
        "title": "Sanskrit",
        "emoji": "🕉️",
        "threshold": 8,
        "url": "https://drive.google.com/file/d/1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view?usp=drivesdk",
    },
    {
        "id": 9,
        "title": "English",
        "emoji": "📘",
        "threshold": 9,
        "url": "https://drive.google.com/file/d/1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view?usp=drivesdk",
    },
]

# ============================================================
# DATABASE
# ============================================================

@contextmanager
def db_connection():
    """
    Open a short-lived SQLite connection.
    WAL mode improves read/write concurrency.
    """
    parent = os.path.dirname(os.path.abspath(DATABASE_PATH))
    os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
        check_same_thread=False,
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
    with DB_LOCK, db_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                joined_bot_at TEXT NOT NULL,
                referral_count INTEGER NOT NULL DEFAULT 0,
                is_banned INTEGER NOT NULL DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS invite_links (
                invite_link TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                referred_user_id INTEGER NOT NULL UNIQUE,
                invite_link TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referral_owner
            ON referral_events(owner_id)
        """)

    logger.info("Database initialized.")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def register_user(user):
    with DB_LOCK, db_connection() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id, username, first_name, joined_bot_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            now_iso(),
        ))


def get_user(user_id):
    with DB_LOCK, db_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def get_referral_count(user_id):
    with DB_LOCK, db_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total
            FROM referral_events
            WHERE owner_id = ?
        """, (user_id,)).fetchone()

    return int(row["total"])


def get_total_users():
    with DB_LOCK, db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM users"
        ).fetchone()
    return int(row["total"])


def get_total_referrals():
    with DB_LOCK, db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM referral_events"
        ).fetchone()
    return int(row["total"])


def get_leaderboard(limit=10):
    with DB_LOCK, db_connection() as conn:
        return conn.execute("""
            SELECT
                u.user_id,
                u.username,
                u.first_name,
                COUNT(r.id) AS total
            FROM users u
            LEFT JOIN referral_events r
                ON r.owner_id = u.user_id
            WHERE u.is_banned = 0
            GROUP BY u.user_id
            ORDER BY total DESC, u.joined_bot_at ASC
            LIMIT ?
        """, (limit,)).fetchall()


def save_invite_link(link, owner_id):
    with DB_LOCK, db_connection() as conn:
        conn.execute("""
            INSERT INTO invite_links (
                invite_link, owner_id, created_at, is_active
            )
            VALUES (?, ?, ?, 1)
            ON CONFLICT(invite_link) DO UPDATE SET
                owner_id = excluded.owner_id,
                is_active = 1
        """, (link, owner_id, now_iso()))


def get_invite_owner(invite_link):
    with DB_LOCK, db_connection() as conn:
        row = conn.execute("""
            SELECT owner_id
            FROM invite_links
            WHERE invite_link = ? AND is_active = 1
        """, (invite_link,)).fetchone()

    return int(row["owner_id"]) if row else None


def record_referral(owner_id, referred_user_id, invite_link):
    """
    Count each referred Telegram user at most once.
    Prevent self-referrals and referrals for unknown owners.
    """
    if owner_id == referred_user_id:
        return False

    with DB_LOCK, db_connection() as conn:
        owner = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (owner_id,),
        ).fetchone()

        referred = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (referred_user_id,),
        ).fetchone()

        if not owner or not referred:
            return False

        existing = conn.execute(
            "SELECT id FROM referral_events WHERE referred_user_id = ?",
            (referred_user_id,),
        ).fetchone()

        if existing:
            return False

        conn.execute("""
            INSERT INTO referral_events (
                owner_id, referred_user_id, invite_link, created_at
            )
            VALUES (?, ?, ?, ?)
        """, (owner_id, referred_user_id, invite_link, now_iso()))

        conn.execute("""
            UPDATE users
            SET referral_count = referral_count + 1
            WHERE user_id = ?
        """, (owner_id,))

    return True


# ============================================================
# UI HELPERS
# ============================================================

def safe_name(user):
    name = user.first_name if user else "Student"
    return html.escape(name or "Student")


def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.add(
        types.InlineKeyboardButton(
            "🎁 Get Referral Link",
            callback_data="get_link",
        ),
        types.InlineKeyboardButton(
            "📊 My Dashboard",
            callback_data="dashboard",
        ),
    )

    markup.add(
        types.InlineKeyboardButton(
            "📚 PDF Center",
            callback_data="pdf_center",
        ),
        types.InlineKeyboardButton(
            "🏆 Leaderboard",
            callback_data="leaderboard",
        ),
    )

    markup.add(
        types.InlineKeyboardButton(
            "📢 Study Channel",
            url=f"https://t.me/{CHANNEL_USERNAME}",
        )
    )

    return markup


def home_text(user):
    referrals = get_referral_count(user.id)
    unlocked = sum(
        1 for reward in PDF_REWARDS
        if referrals >= reward["threshold"]
    )

    return (
        "✨ <b>BHRAMASTRA • CLASS 10</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👋 Welcome, <b>{safe_name(user)}</b>!\n\n"
        "📚 <b>Your Study Rewards</b>\n"
        "Invite friends and unlock study PDFs.\n\n"
        f"👥 Successful referrals: <b>{referrals}</b>\n"
        f"🔓 PDFs unlocked: <b>{unlocked}/{len(PDF_REWARDS)}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Choose an option below to continue."
    )


def send_home(chat_id, user):
    bot.send_message(
        chat_id,
        home_text(user),
        reply_markup=main_menu(),
        disable_web_page_preview=True,
    )


def get_or_create_invite(user_id):
    """
    Reuse a previously saved active link where possible.
    If it no longer works, create a replacement.
    """
    with DB_LOCK, db_connection() as conn:
        rows = conn.execute("""
            SELECT invite_link
            FROM invite_links
            WHERE owner_id = ? AND is_active = 1
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()

    for row in rows:
        link = row["invite_link"]

        try:
            member = bot.get_chat_member(CHANNEL_ID, user_id)
            if member.status in ("left", "kicked"):
                # The owner need not already be a member to share a link.
                pass
        except Exception:
            pass

        try:
            bot.get_chat_member(CHANNEL_ID, bot.get_me().id)
            # The bot must have sufficient channel permissions.
        except Exception as exc:
            logger.warning("Cannot verify bot channel access: %s", exc)

        # A saved link may still work; use it to avoid link duplication.
        return link

    created = bot.create_chat_invite_link(
        CHANNEL_ID,
        name=f"ref_{user_id}",
        creates_join_request=False,
    )

    save_invite_link(created.invite_link, user_id)
    return created.invite_link


# ============================================================
# START / REFERRAL DEEP LINKS
# ============================================================

@bot.message_handler(commands=["start"])
def start_handler(message):
    user = message.from_user
    register_user(user)

    # A referral deep link looks like /start ref_123456789
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) == 2:
        payload = parts[1].strip()

        if payload.startswith("ref_"):
            try:
                owner_id = int(payload[4:])
                if owner_id != user.id:
                    # The bot deep-link registers an interest, but the
                    # referral is credited only after a tracked channel join.
                    with DB_LOCK, db_connection() as conn:
                        conn.execute("""
                            INSERT INTO settings (key, value)
                            VALUES (?, ?)
                            ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """, (
                            f"pending_ref_{user.id}",
                            str(owner_id),
                        ))
            except ValueError:
                pass

    send_home(message.chat.id, user)


# ============================================================
# CALLBACKS
# ============================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user = call.from_user
    register_user(user)

    try:
        if call.data == "home":
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                home_text(user),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu(),
                disable_web_page_preview=True,
            )
            return

        if call.data == "get_link":
            link = get_or_create_invite(user.id)

            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "📢 Open Channel",
                    url=f"https://t.me/{CHANNEL_USERNAME}",
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "🔄 Refresh Dashboard",
                    callback_data="dashboard",
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="home",
                )
            )

            text = (
                "🎁 <b>YOUR PERSONAL INVITE LINK</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Share this channel invitation with your friends:\n\n"
                f"<code>{html.escape(link)}</code>\n\n"
                "📌 <b>How it works</b>\n"
                "1. Share your unique link.\n"
                "2. A new person must join the channel through it.\n"
                "3. The bot records eligible joins.\n"
                "4. Your PDF rewards unlock as you progress.\n\n"
                "⚠️ Existing members and repeated joins do not count."
            )

            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            return

        if call.data == "dashboard":
            count = get_referral_count(user.id)
            unlocked = sum(
                1 for reward in PDF_REWARDS
                if count >= reward["threshold"]
            )
            next_reward = next(
                (
                    reward for reward in PDF_REWARDS
                    if count < reward["threshold"]
                ),
                None,
            )

            progress = (
                f"Next reward: <b>{html.escape(next_reward['title'])}</b>\n"
                f"Need <b>{next_reward['threshold'] - count}</b> more referral(s)."
                if next_reward else
                "🎉 <b>All PDF rewards unlocked!</b>"
            )

            text = (
                "📊 <b>MY REFERRAL DASHBOARD</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 Student: <b>{safe_name(user)}</b>\n"
                f"🆔 Telegram ID: <code>{user.id}</code>\n\n"
                f"👥 Successful referrals: <b>{count}</b>\n"
                f"🔓 Unlocked PDFs: <b>{unlocked}/{len(PDF_REWARDS)}</b>\n\n"
                f"{progress}\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Counts are based on eligible, uniquely tracked channel joins."
            )

            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton(
                    "🎁 Get Invite Link",
                    callback_data="get_link",
                ),
                types.InlineKeyboardButton(
                    "📚 PDF Center",
                    callback_data="pdf_center",
                ),
            )
            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="home",
                )
            )

            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
            )
            return

        if call.data == "pdf_center":
            count = get_referral_count(user.id)
            lines = [
                "📚 <b>BHRAMASTRA PDF CENTER</b>",
                "━━━━━━━━━━━━━━━━━━",
                "",
                f"Your referrals: <b>{count}</b>",
                "",
            ]

            markup = types.InlineKeyboardMarkup(row_width=1)

            for reward in PDF_REWARDS:
                unlocked = count >= reward["threshold"]
                status = "✅ UNLOCKED" if unlocked else "🔒 LOCKED"

                lines.append(
                    f"{reward['emoji']} <b>{html.escape(reward['title'])}</b>"
                    f" — {status}"
                )

                if unlocked:
                    markup.add(
                        types.InlineKeyboardButton(
                            f"📥 {reward['title']} PDF",
                            url=reward["url"],
                        )
                    )
                else:
                    lines.append(
                        f"   Unlock at {reward['threshold']} referral(s)."
                    )

            markup.add(
                types.InlineKeyboardButton(
                    "🎁 Get Invite Link",
                    callback_data="get_link",
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="home",
                )
            )

            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "\n".join(lines),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            return

        if call.data == "leaderboard":
            rows = get_leaderboard(10)
            lines = [
                "🏆 <b>TOP REFERRERS</b>",
                "━━━━━━━━━━━━━━━━━━",
                "",
            ]

            if not rows:
                lines.append("No referrals yet. Be the first!")
            else:
                medals = ["🥇", "🥈", "🥉"]
                for index, row in enumerate(rows):
                    name = row["first_name"] or "Student"
                    name = html.escape(name)
                    prefix = medals[index] if index < 3 else f"{index + 1}."
                    lines.append(
                        f"{prefix} <b>{name}</b> — "
                        f"{row['total']} referral(s)"
                    )

            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="home",
                )
            )

            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "\n".join(lines),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
            )
            return

        bot.answer_callback_query(
            call.id,
            "This option is not available.",
            show_alert=True,
        )

    except Exception:
        logger.exception("Callback failed: %s", call.data)
        try:
            bot.answer_callback_query(
                call.id,
                "Something went wrong. Please try again.",
                show_alert=True,
            )
        except Exception:
            pass


# ============================================================
# CHANNEL JOIN TRACKING
# ============================================================

@bot.chat_member_handler()
def channel_member_handler(update):
    """
    Telegram must send chat_member updates to the bot.
    The bot must be an administrator in the target channel.

    The actual invite link in chat_member.invite_link is the primary
    source for attribution. A /start referral payload is not treated
    as proof of a channel join.
    """
    try:
        if update.chat.id != CHANNEL_ID:
            return

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        was_member = old_status in ("member", "administrator", "creator")
        is_member = new_status in ("member", "administrator", "creator")

        # Count only a transition from non-member to member.
        if was_member or not is_member:
            return

        joined_user = update.new_chat_member.user

        if joined_user.is_bot:
            return

        register_user(joined_user)

        invite_obj = getattr(update, "invite_link", None)
        invite_url = getattr(invite_obj, "invite_link", None)

        owner_id = None

        if invite_url:
            owner_id = get_invite_owner(invite_url)

        # Fallback: pending deep-link owner, but only if that owner
        # has a known active invite link recorded by this bot.
        if owner_id is None:
            with DB_LOCK, db_connection() as conn:
                row = conn.execute("""
                    SELECT value FROM settings WHERE key = ?
                """, (f"pending_ref_{joined_user.id}",)).fetchone()

            if row:
                try:
                    candidate = int(row["value"])
                    with DB_LOCK, db_connection() as conn:
                        known = conn.execute("""
                            SELECT invite_link
                            FROM invite_links
                            WHERE owner_id = ? AND is_active = 1
                            LIMIT 1
                        """, (candidate,)).fetchone()

                    if known:
                        owner_id = candidate
                except ValueError:
                    pass

        if owner_id is None:
            logger.info(
                "New channel member %s joined without a known referral link.",
                joined_user.id,
            )
            return

        credited = record_referral(
            owner_id,
            joined_user.id,
            invite_url or "deep_link_fallback",
        )

        if not credited:
            logger.info(
                "Referral not credited: owner=%s referred=%s",
                owner_id,
                joined_user.id,
            )
            return

        count = get_referral_count(owner_id)

        try:
            bot.send_message(
                owner_id,
                "🎉 <b>NEW REFERRAL CONFIRMED!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "A new member joined through your referral.\n\n"
                f"👥 Total successful referrals: <b>{count}</b>\n"
                "📚 Open your dashboard to see unlocked rewards.",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton(
                        "📊 Open Dashboard",
                        callback_data="dashboard",
                    )
                ),
            )
        except Exception as exc:
            logger.info("Referral notification could not be sent: %s", exc)

        # Remove any pending deep-link marker after successful credit.
        with DB_LOCK, db_connection() as conn:
            conn.execute(
                "DELETE FROM settings WHERE key = ?",
                (f"pending_ref_{joined_user.id}",),
            )

    except Exception:
        logger.exception("Channel member update handler failed.")


# ============================================================
# ADMIN COMMANDS
# ============================================================

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


@bot.message_handler(commands=["stats"])
def stats_handler(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin only.")
        return

    bot.reply_to(
        message,
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Registered users: <b>{get_total_users()}</b>\n"
        f"🎁 Confirmed referrals: <b>{get_total_referrals()}</b>",
    )


@bot.message_handler(commands=["broadcast"])
def broadcast_handler(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin only.")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Usage:\n<code>/broadcast Your announcement here</code>",
        )
        return

    announcement = parts[1].strip()

    with DB_LOCK, db_connection() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE is_banned = 0"
        ).fetchall()

    bot.reply_to(
        message,
        f"📣 Broadcast started for {len(rows)} registered users.",
    )

    sent = 0
    failed = 0

    for row in rows:
        try:
            bot.send_message(
                int(row["user_id"]),
                "📢 <b>ANNOUNCEMENT</b>\n\n" + html.escape(announcement),
            )
            sent += 1
            time.sleep(0.04)
        except Exception:
            failed += 1

    bot.send_message(
        message.chat.id,
        "✅ <b>Broadcast finished</b>\n\n"
        f"📨 Sent: {sent}\n"
        f"⚠️ Failed: {failed}",
    )


@bot.message_handler(commands=["help"])
def help_handler(message):
    text = (
        "ℹ️ <b>BHRAMASTRA BOT HELP</b>\n\n"
        "/start — Open the main menu\n"
        "/help — Show this help message\n"
    )

    if is_admin(message.from_user.id):
        text += (
            "\n<b>Admin commands</b>\n"
            "/stats — View bot statistics\n"
            "/broadcast message — Send an announcement\n"
        )

    bot.reply_to(message, text)


# ============================================================
# ERROR HANDLING AND STARTUP
# ============================================================

def main():
    init_database()

    me = bot.get_me()
    logger.info("Starting bot @%s (ID %s)", me.username, me.id)

    # Polling and webhook cannot be active simultaneously.
    # This bot uses polling; remove any existing webhook first.
    bot.remove_webhook()

    # chat_member is required for channel join tracking.
    allowed_updates = [
        "message",
        "callback_query",
        "chat_member",
    ]

    logger.info("Bot polling started.")
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        allowed_updates=allowed_updates,
        skip_pending=False,
    )


if __name__ == "__main__":
    main()
