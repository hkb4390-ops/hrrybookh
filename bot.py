import os
import time
import html
import sqlite3
import logging
import threading
from urllib.parse import quote

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException


# ============================================================
# BHRAMASTRA BOOKS — CONFIGURATION
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

CHANNEL_ID = os.getenv(
    "CHANNEL_ID", "-1004498096954"
).strip()

CHANNEL_USERNAME = os.getenv(
    "CHANNEL_USERNAME", "hrbseb10thallcorse"
).strip().lstrip("@")

ADMIN_ID = os.getenv("ADMIN_ID", "").strip()

DATABASE_PATH = os.getenv(
    "DATABASE_PATH", "bot_database.db"
)

REQUIRED_REFERRALS = 10

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("bhramastra")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML",
    threaded=True
)

db_lock = threading.RLock()


# ============================================================
# PDF LIBRARY
# Distribute only books you have permission to share.
# ============================================================

BOOKS = [
    {
        "name": "Economics",
        "url": "https://drive.google.com/file/d/1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view"
    },
    {
        "name": "Physics",
        "url": "https://drive.google.com/file/d/1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view"
    },
    {
        "name": "Civics",
        "url": "https://drive.google.com/file/d/1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view"
    },
    {
        "name": "History",
        "url": "https://drive.google.com/file/d/1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view"
    },
    {
        "name": "Mathematics",
        "url": "https://drive.google.com/file/d/1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view"
    },
    {
        "name": "Chemistry",
        "url": "https://drive.google.com/file/d/1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view"
    },
    {
        "name": "Biology",
        "url": "https://drive.google.com/file/d/1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view"
    },
    {
        "name": "Sanskrit",
        "url": "https://drive.google.com/file/d/1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view"
    },
    {
        "name": "English",
        "url": "https://drive.google.com/file/d/1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view"
    }
]


# ============================================================
# DATABASE
# ============================================================

def connect_db():
    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    os.makedirs(
        os.path.dirname(os.path.abspath(DATABASE_PATH)),
        exist_ok=True
    )

    with db_lock:
        conn = connect_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT DEFAULT '',
                    username TEXT DEFAULT '',
                    referrals INTEGER DEFAULT 0,
                    joined_channel INTEGER DEFAULT 0,
                    dashboard_chat_id INTEGER,
                    dashboard_message_id INTEGER,
                    pending_referrer INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS referral_events (
                    referred_id INTEGER PRIMARY KEY,
                    referrer_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS referral_rewards (
                    user_id INTEGER NOT NULL,
                    reward_number INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, reward_number)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            # Safe migrations for databases created by earlier versions.
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(users)"
                ).fetchall()
            }

            migrations = {
                "referrals": "INTEGER DEFAULT 0",
                "joined_channel": "INTEGER DEFAULT 0",
                "dashboard_chat_id": "INTEGER",
                "dashboard_message_id": "INTEGER",
                "pending_referrer": "INTEGER",
                "first_name": "TEXT DEFAULT ''",
                "username": "TEXT DEFAULT ''",
                "created_at": "INTEGER NOT NULL DEFAULT 0",
                "updated_at": "INTEGER NOT NULL DEFAULT 0",
            }

            for column, definition in migrations.items():
                if column not in columns:
                    conn.execute(
                        f"ALTER TABLE users ADD COLUMN {column} {definition}"
                    )

            conn.commit()
        finally:
            conn.close()


def get_user(user_id):
    with db_lock:
        conn = connect_db()
        try:
            return conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
        finally:
            conn.close()


def register_user(user):
    now = int(time.time())

    with db_lock:
        conn = connect_db()
        try:
            conn.execute("""
                INSERT INTO users (
                    user_id, first_name, username,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username = excluded.username,
                    updated_at = excluded.updated_at
            """, (
                user.id,
                user.first_name or "",
                user.username or "",
                now,
                now
            ))
            conn.commit()
        finally:
            conn.close()


def save_dashboard(user_id, chat_id, message_id):
    with db_lock:
        conn = connect_db()
        try:
            conn.execute("""
                UPDATE users
                SET dashboard_chat_id = ?,
                    dashboard_message_id = ?,
                    updated_at = ?
                WHERE user_id = ?
            """, (
                chat_id, message_id, int(time.time()), user_id
            ))
            conn.commit()
        finally:
            conn.close()


def set_membership(user_id, joined):
    with db_lock:
        conn = connect_db()
        try:
            conn.execute("""
                UPDATE users
                SET joined_channel = ?, updated_at = ?
                WHERE user_id = ?
            """, (
                int(joined), int(time.time()), user_id
            ))
            conn.commit()
        finally:
            conn.close()


def get_referral_count(user_id):
    with db_lock:
        conn = connect_db()
        try:
            result = conn.execute("""
                SELECT COUNT(*) AS total
                FROM referral_events
                WHERE referrer_id = ?
            """, (user_id,)).fetchone()
            return int(result["total"])
        finally:
            conn.close()


def is_unlocked(user_id):
    return get_referral_count(user_id) >= REQUIRED_REFERRALS


# ============================================================
# REFERRAL PAYLOAD
# ============================================================

def save_pending_referrer(user_id, referrer_id):
    if not referrer_id or user_id == referrer_id:
        return

    # Do not replace an existing attribution with a different link.
    with db_lock:
        conn = connect_db()
        try:
            conn.execute("""
                UPDATE users
                SET pending_referrer = ?,
                    updated_at = ?
                WHERE user_id = ?
                  AND pending_referrer IS NULL
            """, (
                referrer_id, int(time.time()), user_id
            ))
            conn.commit()
        finally:
            conn.close()


def get_pending_referrer(user_id):
    row = get_user(user_id)
    return row["pending_referrer"] if row else None


def credit_referral(referred_id):
    with db_lock:
        conn = connect_db()
        try:
            conn.execute("BEGIN IMMEDIATE")

            referred = conn.execute("""
                SELECT pending_referrer, joined_channel
                FROM users
                WHERE user_id = ?
            """, (referred_id,)).fetchone()

            if not referred:
                conn.rollback()
                return None

            referrer_id = referred["pending_referrer"]

            if (
                not referrer_id
                or int(referrer_id) == int(referred_id)
                or not referred["joined_channel"]
            ):
                conn.rollback()
                return None

            referrer = conn.execute("""
                SELECT user_id
                FROM users
                WHERE user_id = ?
            """, (referrer_id,)).fetchone()

            if not referrer:
                conn.rollback()
                return None

            cursor = conn.execute("""
                INSERT OR IGNORE INTO referral_events (
                    referred_id, referrer_id, created_at
                )
                VALUES (?, ?, ?)
            """, (
                referred_id, referrer_id, int(time.time())
            ))

            if cursor.rowcount == 0:
                conn.rollback()
                return None

            total = conn.execute("""
                SELECT COUNT(*) AS total
                FROM referral_events
                WHERE referrer_id = ?
            """, (referrer_id,)).fetchone()["total"]

            conn.execute("""
                UPDATE users
                SET referrals = ?, updated_at = ?
                WHERE user_id = ?
            """, (total, int(time.time()), referrer_id))

            conn.commit()

            return {
                "referrer_id": int(referrer_id),
                "count": int(total)
            }

        except Exception:
            conn.rollback()
            logger.exception("Referral credit failed")
            return None
        finally:
            conn.close()


# ============================================================
# MEMBERSHIP
# ============================================================

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)

        return (
            member.status in ("creator", "administrator", "member")
            or (
                member.status == "restricted"
                and getattr(member, "is_member", False)
            )
        )
    except ApiTelegramException:
        logger.exception("Membership check failed for %s", user_id)
        return None


def channel_url():
    return f"https://t.me/{CHANNEL_USERNAME}"


def personal_bot_link(user_id):
    username = BOT_USERNAME or bot.get_me().username
    return f"https://t.me/{username}?start=ref_{user_id}"


# ============================================================
# UI
# ============================================================

def progress_bar(count):
    count = max(0, min(int(count), REQUIRED_REFERRALS))
    return "█" * count + "░" * (REQUIRED_REFERRALS - count)


def safe_name(user):
    return html.escape(user.first_name or "Learner")


def section_text(title, subtitle, body=""):
    result = (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"       ✦ <b>{title}</b> ✦\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{subtitle}"
    )
    if body:
        result += "\n\n" + body
    return result


def home_text(user):
    row = get_user(user.id)
    referrals = get_referral_count(user.id)
    joined = bool(row["joined_channel"]) if row else False
    unlocked = referrals >= REQUIRED_REFERRALS

    status = (
        "● CHANNEL VERIFIED"
        if joined else "● VERIFICATION REQUIRED"
    )

    reward = (
        "🎉 PDF LIBRARY UNLOCKED!"
        if unlocked
        else f"{REQUIRED_REFERRALS - referrals} referrals to unlock"
    )

    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "       ✦ <b>BHRAMASTRA</b> ✦\n"
        "        <b>BOOKS LIBRARY</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"  Welcome back, <b>{safe_name(user)}</b>! 👋\n"
        "  Your personal learning space.\n\n"
        "┌──────────────────────┐\n"
        "│  🛡️ <b>MEMBERSHIP</b>\n"
        f"│  {status}\n"
        "│\n"
        "│  <b>REFERRAL PROGRESS</b>\n"
        f"│  {progress_bar(referrals)}  <b>{referrals}/10</b>\n"
        f"│  {reward}\n"
        "└──────────────────────┘\n\n"
        "       <b>YOUR LIBRARY</b>\n"
        "  Access your book collection\n\n"
        "✦ <i>INVITE FRIENDS · UNLOCK BOOKS</i> ✦"
    )


def home_keyboard(joined):
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.row(
        types.InlineKeyboardButton(
            "🔗 INVITE", callback_data="invite"
        ),
        types.InlineKeyboardButton(
            "📊 PROGRESS", callback_data="progress"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📚 MY BOOKS", callback_data="books"
        ),
        types.InlineKeyboardButton(
            "📢 CHANNEL", url=channel_url()
        )
    )

    if not joined:
        keyboard.row(
            types.InlineKeyboardButton(
                "✅ VERIFY MEMBERSHIP", callback_data="verify"
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            "🏠 HOME", callback_data="home"
        ),
        types.InlineKeyboardButton(
            "ℹ️ HELP", callback_data="help"
        )
    )

    return keyboard


def back_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton(
            "🏠 HOME DASHBOARD", callback_data="home"
        )
    )
    return keyboard


def show_dashboard(chat_id, user, text, keyboard=None):
    register_user(user)
    row = get_user(user.id)

    if row and row["dashboard_chat_id"] and row["dashboard_message_id"]:
        try:
            return bot.edit_message_text(
                text,
                chat_id=row["dashboard_chat_id"],
                message_id=row["dashboard_message_id"],
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except ApiTelegramException as error:
            if "message is not modified" in str(error).lower():
                return None
            logger.info("Dashboard will be recreated: %s", error)

    message = bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    save_dashboard(user.id, message.chat.id, message.message_id)
    return message


def render_home(chat_id, user):
    register_user(user)

    membership = check_membership(user.id)

    if membership is True:
        set_membership(user.id, True)

    row = get_user(user.id)
    joined = bool(row["joined_channel"]) if row else False

    return show_dashboard(
        chat_id,
        user,
        home_text(user),
        home_keyboard(joined)
    )


# ============================================================
# REWARD: ONE PDF PER SUCCESSFUL REFERRAL
# ============================================================

def get_unlocked_books(user_id):
    count = get_referral_count(user_id)
    return BOOKS[:min(count, len(BOOKS))]


def reward_notification(referrer_id, count):
    if count < 1:
        return

    reward_index = min(count, len(BOOKS))

    with db_lock:
        conn = connect_db()
        try:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO referral_rewards (
                    user_id, reward_number, created_at
                )
                VALUES (?, ?, ?)
            """, (referrer_id, reward_index, int(time.time())))

            conn.commit()

            if cursor.rowcount == 0:
                return
        finally:
            conn.close()

    if reward_index <= len(BOOKS):
        book = BOOKS[reward_index - 1]

        try:
            bot.send_message(
                referrer_id,
                (
                    "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "    🎉 <b>NEW MEMBER VERIFIED!</b>\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "✅ Referral successfully counted.\n"
                    f"📊 Progress: <b>{count}/10</b>\n"
                    f"{progress_bar(count)}\n\n"
                    "🔓 <b>New PDF unlocked:</b>\n"
                    f"📘 {html.escape(book['name'])}\n\n"
                    f"📥 <a href=\"{book['url']}\">OPEN PDF</a>\n\n"
                    + (
                        "🏆 <b>All 10 referrals completed!</b>\n"
                        "Your complete library is unlocked."
                        if count >= REQUIRED_REFERRALS
                        else "Invite more friends to unlock more books."
                    )
                ),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            logger.exception("Reward notification failed")


# ============================================================
# START COMMAND — BOT DEEP LINK REFERRAL
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    user = message.from_user
    register_user(user)

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) > 1:
        payload = parts[1].strip()

        if payload.startswith("ref_"):
            try:
                referrer_id = int(payload[4:])
                save_pending_referrer(user.id, referrer_id)
            except ValueError:
                pass

    membership = check_membership(user.id)

    if membership is True:
        set_membership(user.id, True)

    row = get_user(user.id)

    if row and row["joined_channel"]:
        render_home(message.chat.id, user)
        return

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 JOIN CHANNEL", url=channel_url()
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "✅ VERIFY MEMBERSHIP", callback_data="verify"
        )
    )

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "       ✦ <b>BHRAMASTRA</b> ✦\n"
        "        <b>BOOKS LIBRARY</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"नमस्ते <b>{safe_name(user)}</b>! 👋\n\n"
        "📚 <b>Full Book PDF Collection</b>\n"
        "अपनी Book PDF Library पाने के लिए पहले हमारे "
        "Official Channel को Join करें।\n\n"
        "👇 पहले Join करें, फिर Verify करें।"
    )

    show_dashboard(
        message.chat.id,
        user,
        text,
        keyboard
    )


# ============================================================
# CALLBACK NAVIGATION — EDIT EXISTING DASHBOARD
# ============================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    user = call.from_user
    action = call.data or ""

    register_user(user)

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    chat_id = call.message.chat.id if call.message else user.id

    if action == "home":
        render_home(chat_id, user)
        return

    if action == "verify":
        membership = check_membership(user.id)

        if membership is not True:
            keyboard = types.InlineKeyboardMarkup()

            keyboard.row(
                types.InlineKeyboardButton(
                    "📢 JOIN CHANNEL", url=channel_url()
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "🔄 VERIFY AGAIN", callback_data="verify"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "🏠 HOME", callback_data="home"
                )
            )

            show_dashboard(
                chat_id,
                user,
                (
                    "🔒 <b>MEMBERSHIP REQUIRED</b>\n\n"
                    "पहले Channel Join करें, फिर Verify दबाएँ।\n\n"
                    "अगर आप पहले से joined हैं, तो कुछ देर बाद "
                    "फिर कोशिश करें।"
                ),
                keyboard
            )
            return

        set_membership(user.id, True)

        credited = credit_referral(user.id)

        if credited:
            reward_notification(
                credited["referrer_id"],
                credited["count"]
            )

        show_dashboard(
            chat_id,
            user,
            (
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "       ✅ <b>VERIFIED</b>\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                "आपकी channel membership verify हो गई है। 🎉\n\n"
                "अब अपना Bhramastra Books Dashboard खोलें।"
            ),
            back_keyboard()
        )
        return

    membership = check_membership(user.id)

    if membership is True:
        set_membership(user.id, True)

    row = get_user(user.id)
    joined = bool(row["joined_channel"]) if row else False

    if action in ("invite", "progress", "books") and not joined:
        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "📢 JOIN CHANNEL", url=channel_url()
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "✅ VERIFY MEMBERSHIP", callback_data="verify"
            )
        )

        show_dashboard(
            chat_id,
            user,
            "🔒 <b>पहले Channel Join और Verify करें।</b>",
            keyboard
        )
        return

    count = get_referral_count(user.id)
    unlocked = count >= REQUIRED_REFERRALS

    if action == "invite":
        link = personal_bot_link(user.id)

        share_url = (
            "https://t.me/share/url?url="
            + quote(link)
            + "&text="
            + quote("Join Bhramastra Books Library!")
        )

        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "📤 SHARE INVITE LINK", url=share_url
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "📊 VIEW PROGRESS", callback_data="progress"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME DASHBOARD", callback_data="home"
            )
        )

        show_dashboard(
            chat_id,
            user,
            section_text(
                "YOUR INVITE LINK",
                "🔗 <b>PERSONAL BOT REFERRAL LINK</b>",
                (
                    f"<code>{html.escape(link)}</code>\n\n"
                    "यह link सीधे Bhramastra Bot खोलेगा।\n"
                    "नया user Channel Join करके Verify करेगा, "
                    "तभी referral count होगा।\n\n"
                    f"📊 Progress: <b>{count}/10</b>"
                )
            ),
            keyboard
        )
        return

    if action == "progress":
        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "🔗 MY REFERRAL LINK", callback_data="invite"
            )
        )

        if unlocked:
            keyboard.row(
                types.InlineKeyboardButton(
                    "📚 OPEN PDF LIBRARY", callback_data="books"
                )
            )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME DASHBOARD", callback_data="home"
            )
        )

        show_dashboard(
            chat_id,
            user,
            section_text(
                "YOUR PROGRESS",
                "📊 <b>REFERRAL STATISTICS</b>",
                (
                    f"Successful referrals: <b>{count}/10</b>\n"
                    f"{progress_bar(count)}\n\n"
                    f"Remaining: <b>{max(0, 10-count)}</b>\n\n"
                    + (
                        "🎉 Complete Library Unlocked!"
                        if unlocked
                        else "Invite friends to unlock PDFs."
                    )
                )
            ),
            keyboard
        )
        return

    if action == "books":
        books = get_unlocked_books(user.id)

        if not books:
            keyboard = types.InlineKeyboardMarkup()

            keyboard.row(
                types.InlineKeyboardButton(
                    "🔗 GET REFERRAL LINK", callback_data="invite"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "📊 VIEW PROGRESS", callback_data="progress"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "🏠 HOME", callback_data="home"
                )
            )

            show_dashboard(
                chat_id,
                user,
                section_text(
                    "BOOKS LIBRARY",
                    "🔒 <b>PDF LIBRARY LOCKED</b>",
                    (
                        f"Your progress: <b>{count}/10</b>\n\n"
                        "हर सफल रेफरल पर अगली PDF अनलॉक होगी।\n"
                        "10 सफल रेफरल पर पूरी Library अनलॉक होगी।"
                    )
                ),
                keyboard
            )
            return

        keyboard = types.InlineKeyboardMarkup(row_width=1)

        for book in books:
            keyboard.row(
                types.InlineKeyboardButton(
                    f"📘 {book['name']}", url=book["url"]
                )
            )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME DASHBOARD", callback_data="home"
            )
        )

        show_dashboard(
            chat_id,
            user,
            section_text(
                "BOOKS LIBRARY",
                "📚 <b>YOUR UNLOCKED BOOKS</b>",
                (
                    f"Unlocked: <b>{len(books)}/{len(BOOKS)}</b>\n\n"
                    "अपनी उपलब्ध PDF चुनें।"
                )
            ),
            keyboard
        )
        return

    if action == "help":
        show_dashboard(
            chat_id,
            user,
            section_text(
                "HELP & RULES",
                "ℹ️ <b>HOW IT WORKS</b>",
                (
                    "1. Channel Join करें।\n"
                    "2. Verify Membership दबाएँ।\n"
                    "3. Personal Bot Referral Link share करें।\n"
                    "4. नए user के Verify करने पर referral count होगा।\n"
                    "5. हर successful referral पर एक PDF unlock होगी।\n"
                    "6. 10 successful referrals पर पूरी Library मिलेगी।"
                )
            ),
            back_keyboard()
        )
        return

    render_home(chat_id, user)


# ============================================================
# ADMIN STATISTICS
# ============================================================

@bot.message_handler(commands=["stats"])
def stats_command(message):
    if not ADMIN_ID or str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin access required.")
        return

    with db_lock:
        conn = connect_db()
        try:
            users = conn.execute(
                "SELECT COUNT(*) AS n FROM users"
            ).fetchone()["n"]

            verified = conn.execute("""
                SELECT COUNT(*) AS n
                FROM users WHERE joined_channel = 1
            """).fetchone()["n"]

            referrals = conn.execute(
                "SELECT COUNT(*) AS n FROM referral_events"
            ).fetchone()["n"]
        finally:
            conn.close()

    bot.reply_to(
        message,
        (
            "📊 <b>BHRAMASTRA ADMIN STATS</b>\n\n"
            f"👥 Users: <b>{users}</b>\n"
            f"✅ Verified: <b>{verified}</b>\n"
            f"🎁 Referrals: <b>{referrals}</b>"
        )
    )


# ============================================================
# POLLING
# ============================================================

if __name__ == "__main__":
    init_db()

    me = bot.get_me()

    if BOT_USERNAME and me.username.lower() != BOT_USERNAME.lower():
        logger.warning(
            "BOT_USERNAME does not match actual bot username: @%s",
            me.username
        )

    logger.info("Bhramastra Books started as @%s", me.username)

    bot.infinity_polling(
        skip_pending=False,
        allowed_updates=["message", "callback_query"],
        timeout=30,
        long_polling_timeout=25
    )
