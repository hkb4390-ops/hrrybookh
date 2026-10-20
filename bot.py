import os
import time
import html
import sqlite3
import logging
import threading

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException


# ============================================================
# BHRAMASTRA BOOKS — PROFESSIONAL TELEGRAM REFERRAL BOT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

CHANNEL_ID = os.getenv(
    "CHANNEL_ID",
    "-1004498096954"
).strip()

CHANNEL_USERNAME = os.getenv(
    "CHANNEL_USERNAME",
    "hrbseb10thallcorse"
).strip().lstrip("@")

ADMIN_ID = os.getenv("ADMIN_ID", "").strip()

REQUIRED_REFERRALS = 10

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "bot_database.db"
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("bhramastra")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is missing."
    )

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML",
    threaded=True
)

db_lock = threading.RLock()


# ============================================================
# BOOK LIBRARY
# Only add books you are authorized to distribute.
# ============================================================

BOOKS = [
    {
        "name": "Economics",
        "url": (
            "https://drive.google.com/file/d/"
            "1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view"
        )
    },
    {
        "name": "Physics",
        "url": (
            "https://drive.google.com/file/d/"
            "1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view"
        )
    },
    {
        "name": "Civics",
        "url": (
            "https://drive.google.com/file/d/"
            "1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view"
        )
    },
    {
        "name": "History",
        "url": (
            "https://drive.google.com/file/d/"
            "1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view"
        )
    },
    {
        "name": "Mathematics",
        "url": (
            "https://drive.google.com/file/d/"
            "1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view"
        )
    },
    {
        "name": "Chemistry",
        "url": (
            "https://drive.google.com/file/d/"
            "1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view"
        )
    },
    {
        "name": "Biology",
        "url": (
            "https://drive.google.com/file/d/"
            "1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view"
        )
    },
    {
        "name": "Sanskrit",
        "url": (
            "https://drive.google.com/file/d/"
            "1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view"
        )
    },
    {
        "name": "English",
        "url": (
            "https://drive.google.com/file/d/"
            "1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view"
        )
    }
]


# ============================================================
# DATABASE
# ============================================================

def connect_db():
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")

    return connection


def init_db():
    folder = os.path.dirname(
        os.path.abspath(DATABASE_PATH)
    )

    os.makedirs(folder, exist_ok=True)

    with db_lock:
        connection = connect_db()

        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT DEFAULT '',
                    username TEXT DEFAULT '',
                    referrals INTEGER DEFAULT 0,
                    joined_channel INTEGER DEFAULT 0,
                    unlocked INTEGER DEFAULT 0,
                    dashboard_chat_id INTEGER,
                    dashboard_message_id INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS referral_links (
                    user_id INTEGER PRIMARY KEY,
                    invite_link TEXT UNIQUE NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS referral_events (
                    referred_id INTEGER PRIMARY KEY,
                    referrer_id INTEGER NOT NULL,
                    invite_link TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_referrer
                ON referral_events(referrer_id);
            """)

            connection.commit()

        finally:
            connection.close()


def get_user(user_id):
    with db_lock:
        connection = connect_db()

        try:
            return connection.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()

        finally:
            connection.close()


def register_user(user):
    now = int(time.time())

    first_name = user.first_name or ""
    username = user.username or ""

    with db_lock:
        connection = connect_db()

        try:
            connection.execute("""
                INSERT INTO users (
                    user_id,
                    first_name,
                    username,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)

                ON CONFLICT(user_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username = excluded.username,
                    updated_at = excluded.updated_at
            """, (
                user.id,
                first_name,
                username,
                now,
                now
            ))

            connection.commit()

        finally:
            connection.close()


def save_dashboard(user_id, chat_id, message_id):
    with db_lock:
        connection = connect_db()

        try:
            connection.execute("""
                UPDATE users
                SET dashboard_chat_id = ?,
                    dashboard_message_id = ?,
                    updated_at = ?
                WHERE user_id = ?
            """, (
                chat_id,
                message_id,
                int(time.time()),
                user_id
            ))

            connection.commit()

        finally:
            connection.close()


def set_membership(user_id, joined):
    with db_lock:
        connection = connect_db()

        try:
            connection.execute("""
                UPDATE users
                SET joined_channel = ?,
                    updated_at = ?
                WHERE user_id = ?
            """, (
                1 if joined else 0,
                int(time.time()),
                user_id
            ))

            connection.commit()

        finally:
            connection.close()


def get_referral_count(user_id):
    with db_lock:
        connection = connect_db()

        try:
            row = connection.execute("""
                SELECT COUNT(*) AS total
                FROM referral_events
                WHERE referrer_id = ?
            """, (user_id,)).fetchone()

            return int(row["total"])

        finally:
            connection.close()


def is_unlocked(user_id):
    return get_referral_count(user_id) >= REQUIRED_REFERRALS


# ============================================================
# MEMBERSHIP CHECK
# ============================================================

def check_membership(user_id):
    try:
        member = bot.get_chat_member(
            CHANNEL_ID,
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

    except ApiTelegramException as error:
        logger.warning(
            "Membership check failed for %s: %s",
            user_id,
            error
        )

        return None

    except Exception:
        logger.exception(
            "Unexpected membership error for %s",
            user_id
        )

        return None


# ============================================================
# PERSONAL CHANNEL INVITE LINKS
# ============================================================

def get_personal_referral_link(user_id):
    with db_lock:
        connection = connect_db()

        try:
            existing = connection.execute("""
                SELECT invite_link
                FROM referral_links
                WHERE user_id = ?
            """, (user_id,)).fetchone()

        finally:
            connection.close()

    if existing:
        return existing["invite_link"]

    try:
        invite = bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=f"Referral {user_id}",
            creates_join_request=False
        )

        invite_url = invite.invite_link

        with db_lock:
            connection = connect_db()

            try:
                connection.execute("""
                    INSERT OR IGNORE INTO referral_links (
                        user_id,
                        invite_link,
                        created_at
                    )
                    VALUES (?, ?, ?)
                """, (
                    user_id,
                    invite_url,
                    int(time.time())
                ))

                connection.commit()

                saved = connection.execute("""
                    SELECT invite_link
                    FROM referral_links
                    WHERE user_id = ?
                """, (user_id,)).fetchone()

                return saved["invite_link"]

            finally:
                connection.close()

    except Exception:
        logger.exception(
            "Could not create referral link for %s",
            user_id
        )

        return None


# ============================================================
# REFERRAL TRACKING
# ============================================================

def credit_referral(referred_id, invite_link):
    if not invite_link:
        return False

    with db_lock:
        connection = connect_db()

        try:
            link_row = connection.execute("""
                SELECT user_id
                FROM referral_links
                WHERE invite_link = ?
            """, (invite_link,)).fetchone()

            if not link_row:
                return False

            referrer_id = int(link_row["user_id"])

            if referrer_id == referred_id:
                return False

            referred = connection.execute("""
                SELECT joined_channel
                FROM users
                WHERE user_id = ?
            """, (referred_id,)).fetchone()

            referrer = connection.execute("""
                SELECT user_id
                FROM users
                WHERE user_id = ?
            """, (referrer_id,)).fetchone()

            if not referred or not referrer:
                return False

            # A referral only counts after channel membership
            # has been recorded for the new member.
            if not referred["joined_channel"]:
                return False

            cursor = connection.execute("""
                INSERT OR IGNORE INTO referral_events (
                    referred_id,
                    referrer_id,
                    invite_link,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                referred_id,
                referrer_id,
                invite_link,
                int(time.time())
            ))

            if cursor.rowcount == 0:
                return False

            count_row = connection.execute("""
                SELECT COUNT(*) AS total
                FROM referral_events
                WHERE referrer_id = ?
            """, (referrer_id,)).fetchone()

            total = int(count_row["total"])

            connection.execute("""
                UPDATE users
                SET referrals = ?,
                    unlocked = ?,
                    updated_at = ?
                WHERE user_id = ?
            """, (
                total,
                1 if total >= REQUIRED_REFERRALS else 0,
                int(time.time()),
                referrer_id
            ))

            connection.commit()

            return True

        except Exception:
            connection.rollback()
            logger.exception("Referral credit failed")
            return False

        finally:
            connection.close()


# ============================================================
# PROFESSIONAL UI HELPERS
# ============================================================

def progress_bar(count):
    count = max(0, min(count, REQUIRED_REFERRALS))

    filled = count
    empty = REQUIRED_REFERRALS - filled

    return "▰" * filled + "▱" * empty


def safe_name(user):
    return html.escape(
        (user.first_name or "Learner").strip()
    )


def channel_url():
    return f"https://t.me/{CHANNEL_USERNAME}"


def main_keyboard(user_id, joined):
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.row(
        types.InlineKeyboardButton(
            "🔗 INVITE",
            callback_data="invite"
        ),
        types.InlineKeyboardButton(
            "📊 PROGRESS",
            callback_data="progress"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📚 MY BOOKS",
            callback_data="books"
        ),
        types.InlineKeyboardButton(
            "📢 CHANNEL",
            url=channel_url()
        )
    )

    if not joined:
        keyboard.row(
            types.InlineKeyboardButton(
                "✅ VERIFY MEMBERSHIP",
                callback_data="verify"
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            "🏠 HOME",
            callback_data="home"
        ),
        types.InlineKeyboardButton(
            "ℹ️ HELP",
            callback_data="help"
        )
    )

    return keyboard


def home_text(user):
    name = safe_name(user)
    user_id = user.id

    row = get_user(user_id)

    referrals = get_referral_count(user_id)
    unlocked = referrals >= REQUIRED_REFERRALS

    joined = bool(
        row["joined_channel"]
    ) if row else False

    bar = progress_bar(referrals)

    membership_status = (
        "● CHANNEL VERIFIED"
        if joined
        else "● VERIFICATION REQUIRED"
    )

    reward_status = (
        "🎉 YOUR BOOK LIBRARY IS UNLOCKED!"
        if unlocked
        else f"{REQUIRED_REFERRALS - referrals} referrals to unlock"
    )

    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "       ✦ <b>BHRAMASTRA</b> ✦\n"
        "        <b>BOOKS LIBRARY</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

        f"  Welcome back, <b>{name}</b>! 👋\n"
        "  Your personal learning space.\n\n"

        "┌──────────────────────┐\n"
        "│  🛡️ <b>MEMBERSHIP</b>\n"
        f"│  {membership_status}\n"
        "│\n"
        "│  <b>REFERRAL PROGRESS</b>\n"
        f"│  {bar}  <b>{referrals}/{REQUIRED_REFERRALS}</b>\n"
        f"│  {reward_status}\n"
        "└──────────────────────┘\n\n"

        "       <b>YOUR LIBRARY</b>\n"
        "  Access your book collection\n\n"

        "✦ <i>INVITE FRIENDS · UNLOCK BOOKS</i> ✦"
    )


def section_text(title, subtitle, body=""):
    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"       ✦ <b>{title}</b> ✦\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{subtitle}"
    )

    if body:
        text += "\n\n" + body

    return text


def back_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🏠 HOME DASHBOARD",
            callback_data="home"
        )
    )

    return keyboard


# ============================================================
# DASHBOARD MESSAGE MANAGEMENT
# ============================================================

def show_dashboard(chat_id, user, text, keyboard=None):
    register_user(user)

    row = get_user(user.id)

    old_chat_id = row["dashboard_chat_id"] if row else None
    old_message_id = row["dashboard_message_id"] if row else None

    # Edit the saved dashboard instead of sending a new one.
    if old_chat_id and old_message_id:
        try:
            message = bot.edit_message_text(
                text,
                chat_id=old_chat_id,
                message_id=old_message_id,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

            return message

        except ApiTelegramException as error:
            error_text = str(error).lower()

            # Telegram returns this when the content is already
            # identical. The existing dashboard is still valid.
            if "message is not modified" in error_text:
                return None

            # If the message was deleted or cannot be edited,
            # create a replacement dashboard.
            logger.info(
                "Replacing dashboard for %s: %s",
                user.id,
                error
            )

        except Exception:
            logger.exception(
                "Dashboard edit failed for %s",
                user.id
            )

    message = bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    save_dashboard(
        user.id,
        message.chat.id,
        message.message_id
    )

    return message


def render_home(chat_id, user):
    register_user(user)

    membership = check_membership(user.id)

    if membership is True:
        set_membership(user.id, True)

    row = get_user(user.id)
    joined = bool(row["joined_channel"]) if row else False

    text = home_text(user)

    return show_dashboard(
        chat_id,
        user,
        text,
        main_keyboard(user.id, joined)
    )


# ============================================================
# START
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    user = message.from_user

    register_user(user)

    membership = check_membership(user.id)

    if membership is True:
        set_membership(user.id, True)

    row = get_user(user.id)
    joined = bool(row["joined_channel"]) if row else False

    # The start screen and home dashboard share one message.
    # If a saved dashboard exists, it is edited.
    if not joined:
        text = (
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "       ✦ <b>BHRAMASTRA</b> ✦\n"
            "        <b>BOOKS LIBRARY</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

            f"नमस्ते <b>{safe_name(user)}</b>! 👋\n\n"

            "📚 <b>Full Book PDF Collection</b>\n"
            "अपनी study books और PDF collection पाने के "
            "लिए पहले हमारे official channel को Join करें।\n\n"

            "👇 <b>पहले Join करें, फिर Verify करें।</b>"
        )

        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "📢 JOIN CHANNEL",
                url=channel_url()
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "✅ VERIFY MEMBERSHIP",
                callback_data="verify"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 OPEN DASHBOARD",
                callback_data="home"
            )
        )

        show_dashboard(
            message.chat.id,
            user,
            text,
            keyboard
        )

    else:
        render_home(message.chat.id, user)


# ============================================================
# CALLBACKS
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

        if membership is True:
            set_membership(user.id, True)

            # The join event handler credits the inviter when
            # Telegram supplies the invite link in chat_member.
            text = (
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "       ✅ <b>VERIFIED</b>\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

                "🎉 आपका channel verification सफल हो गया है!\n\n"
                "📚 <b>Bhramastra Books Library</b>\n"
                "अब आप अपना personal referral link बना सकते हैं।\n\n"

                "🔗 PDF collection unlock करने के लिए "
                "<b>10 successful referrals</b> पूरे करें।\n\n"

                "👇 अपना Dashboard खोलें।"
            )

            show_dashboard(
                chat_id,
                user,
                text,
                back_keyboard()
            )

        elif membership is False:
            keyboard = types.InlineKeyboardMarkup()

            keyboard.row(
                types.InlineKeyboardButton(
                    "📢 JOIN CHANNEL",
                    url=channel_url()
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "🔄 CHECK AGAIN",
                    callback_data="verify"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "🏠 HOME",
                    callback_data="home"
                )
            )

            show_dashboard(
                chat_id,
                user,
                (
                    "🔒 <b>MEMBERSHIP REQUIRED</b>\n\n"
                    "आप अभी हमारे channel के member नहीं हैं।\n"
                    "पहले channel Join करें, फिर Verify दबाएँ।"
                ),
                keyboard
            )

        else:
            show_dashboard(
                chat_id,
                user,
                (
                    "⚠️ <b>VERIFICATION TEMPORARILY UNAVAILABLE</b>\n\n"
                    "Membership check नहीं हो पाया। कुछ देर बाद "
                    "फिर प्रयास करें। अगर समस्या बनी रहे, तो "
                    "जाँचें कि bot channel में administrator है।"
                ),
                back_keyboard()
            )

        return

    # All other sections require verified membership.
    membership = check_membership(user.id)

    if membership is True:
        set_membership(user.id, True)

    row = get_user(user.id)
    joined = bool(row["joined_channel"]) if row else False

    if action in ("invite", "progress", "books") and not joined:
        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "📢 JOIN CHANNEL",
                url=channel_url()
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "✅ VERIFY MEMBERSHIP",
                callback_data="verify"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME",
                callback_data="home"
            )
        )

        show_dashboard(
            chat_id,
            user,
            (
                "🔐 <b>MEMBERSHIP REQUIRED</b>\n\n"
                "इस सेक्शन को खोलने से पहले channel verify करें।"
            ),
            keyboard
        )

        return

    referrals = get_referral_count(user.id)
    unlocked = referrals >= REQUIRED_REFERRALS

    if action == "invite":
        invite_url = get_personal_referral_link(user.id)

        if not invite_url:
            show_dashboard(
                chat_id,
                user,
                (
                    "⚠️ <b>INVITE LINK UNAVAILABLE</b>\n\n"
                    "Link अभी नहीं बन पाया। कुछ देर बाद दोबारा "
                    "प्रयास करें।"
                ),
                back_keyboard()
            )
            return

        share_url = (
            "https://t.me/share/url?"
            "url=" + invite_url
            "&text=Join%20Bhramastra%20Books%20Library"
        )

        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "📤 SHARE INVITE LINK",
                url=share_url
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "📊 VIEW PROGRESS",
                callback_data="progress"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME DASHBOARD",
                callback_data="home"
            )
        )

        text = section_text(
            "YOUR INVITE LINK",
            "🔗 <b>PERSONAL REFERRAL LINK</b>",
            (
                f"<code>{html.escape(invite_url)}</code>\n\n"
                "इस link को अपने दोस्तों के साथ share करें।\n\n"
                f"📊 Your progress: <b>{referrals}/10</b>\n"
                "🎁 10 successful referrals पर PDF Library unlock होगी।\n\n"
                "ℹ️ Referral तभी गिना जाएगा जब नया user "
                "आपके invite link से channel join करे।"
            )
        )

        show_dashboard(
            chat_id,
            user,
            text,
            keyboard
        )

        return

    if action == "progress":
        keyboard = types.InlineKeyboardMarkup()

        keyboard.row(
            types.InlineKeyboardButton(
                "🔗 MY REFERRAL LINK",
                callback_data="invite"
            )
        )

        if unlocked:
            keyboard.row(
                types.InlineKeyboardButton(
                    "📚 OPEN PDF LIBRARY",
                    callback_data="books"
                )
            )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME DASHBOARD",
                callback_data="home"
            )
        )

        remaining = max(
            0,
            REQUIRED_REFERRALS - referrals
        )

        text = section_text(
            "YOUR PROGRESS",
            "📊 <b>REFERRAL STATISTICS</b>",
            (
                f"┌──────────────────────┐\n"
                f"│ Successful referrals: <b>{referrals}</b>\n"
                f"│ Target: <b>{REQUIRED_REFERRALS}</b>\n"
                f"│ {progress_bar(referrals)}\n"
                f"│ Remaining: <b>{remaining}</b>\n"
                f"└──────────────────────┘\n\n"
                + (
                    "🎉 <b>PDF LIBRARY UNLOCKED!</b>"
                    if unlocked
                    else "🎁 अपने invite link को share करते रहें।"
                )
            )
        )

        show_dashboard(
            chat_id,
            user,
            text,
            keyboard
        )

        return

    if action == "books":
        if not unlocked:
            keyboard = types.InlineKeyboardMarkup()

            keyboard.row(
                types.InlineKeyboardButton(
                    "🔗 GET REFERRAL LINK",
                    callback_data="invite"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "📊 VIEW PROGRESS",
                    callback_data="progress"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    "🏠 HOME",
                    callback_data="home"
                )
            )

            show_dashboard(
                chat_id,
                user,
                section_text(
                    "PDF LIBRARY",
                    "🔒 <b>BOOKS LOCKED</b>",
                    (
                        f"आपका progress: <b>{referrals}/10</b>\n\n"
                        "PDF Books unlock करने के लिए "
                        "10 successful referrals पूरे करें।"
                    )
                ),
                keyboard
            )

            return

        keyboard = types.InlineKeyboardMarkup(row_width=1)

        for book in BOOKS:
            keyboard.row(
                types.InlineKeyboardButton(
                    f"📘 {book['name']}",
                    url=book["url"]
                )
            )

        keyboard.row(
            types.InlineKeyboardButton(
                "🏠 HOME DASHBOARD",
                callback_data="home"
            )
        )

        show_dashboard(
            chat_id,
            user,
            section_text(
                "BOOKS LIBRARY",
                "📚 <b>YOUR PDF COLLECTION IS UNLOCKED</b>",
                (
                    "अपनी उपलब्ध book चुनें।\n\n"
                    "🔓 Unlock status: <b>ACTIVE</b>"
                )
            ),
            keyboard
        )

        return

    if action == "help":
        text = section_text(
            "HELP & RULES",
            "ℹ️ <b>HOW TO UNLOCK BOOKS</b>",
            (
                "1. Official channel Join करें।\n"
                "2. Membership Verify करें।\n"
                "3. अपना Personal Referral Link लें।\n"
                "4. नए users को link share करें।\n"
                "5. 10 successful referrals पूरे करें।\n"
                "6. PDF Library खोलें।\n\n"
                "⚠️ एक ही user को बार-बार referral "
                "नहीं गिना जाएगा।"
            )
        )

        show_dashboard(
            chat_id,
            user,
            text,
            back_keyboard()
        )

        return

    show_dashboard(
        chat_id,
        user,
        home_text(user),
        main_keyboard(user.id, joined)
    )


# ============================================================
# CHANNEL MEMBERSHIP EVENTS
# ============================================================

@bot.chat_member_handler()
def channel_member_update(update):
    try:
        chat = update.chat

        if str(chat.id) != str(CHANNEL_ID):
            return

        member_user = update.new_chat_member.user

        if member_user.is_bot:
            return

        register_user(member_user)

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        old_member = old_status in (
            "creator",
            "administrator",
            "member"
        )

        new_member = new_status in (
            "creator",
            "administrator",
            "member"
        )

        if (
            new_status == "restricted"
            and getattr(
                update.new_chat_member,
                "is_member",
                False
            )
        ):
            new_member = True

        if new_member:
            set_membership(member_user.id, True)

            invite = getattr(update, "invite_link", None)

            if invite:
                was_credited = credit_referral(
                    member_user.id,
                    invite.invite_link
                )

                if was_credited:
                    logger.info(
                        "Referral credited: user=%s",
                        member_user.id
                    )

                    notify_referrer(member_user.id, invite.invite_link)

        elif old_member and not new_member:
            set_membership(member_user.id, False)

    except Exception:
        logger.exception("Channel member event processing failed")


def notify_referrer(referred_id, invite_link):
    with db_lock:
        connection = connect_db()

        try:
            row = connection.execute("""
                SELECT user_id
                FROM referral_links
                WHERE invite_link = ?
            """, (invite_link,)).fetchone()

        finally:
            connection.close()

    if not row:
        return

    referrer_id = int(row["user_id"])
    count = get_referral_count(referrer_id)

    try:
        bot.send_message(
            referrer_id,
            (
                "🎉 <b>NEW SUCCESSFUL REFERRAL!</b>\n\n"
                f"📊 Your progress: <b>{count}/10</b>\n"
                f"{progress_bar(count)}\n\n"
                + (
                    "🔓 <b>Your PDF Library is now unlocked!</b>"
                    if count >= REQUIRED_REFERRALS
                    else "अपने invite link को share करते रहें।"
                )
            ),
            parse_mode="HTML"
        )

    except Exception:
        logger.info(
            "Referrer notification could not be sent: %s",
            referrer_id
        )


# ============================================================
# ADMIN COMMANDS
# ============================================================

@bot.message_handler(commands=["stats"])
def stats_command(message):
    if not ADMIN_ID or str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin access required.")
        return

    with db_lock:
        connection = connect_db()

        try:
            users = connection.execute(
                "SELECT COUNT(*) AS n FROM users"
            ).fetchone()["n"]

            verified = connection.execute("""
                SELECT COUNT(*) AS n
                FROM users
                WHERE joined_channel = 1
            """).fetchone()["n"]

            unlocked = connection.execute("""
                SELECT COUNT(*) AS n
                FROM users
                WHERE unlocked = 1
            """).fetchone()["n"]

            referrals = connection.execute(
                "SELECT COUNT(*) AS n FROM referral_events"
            ).fetchone()["n"]

        finally:
            connection.close()

    bot.reply_to(
        message,
        (
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "   📊 <b>ADMIN STATISTICS</b>\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"👥 Total users: <b>{users}</b>\n"
            f"✅ Verified users: <b>{verified}</b>\n"
            f"🔗 Successful referrals: <b>{referrals}</b>\n"
            f"📚 Unlocked users: <b>{unlocked}</b>"
        ),
        parse_mode="HTML"
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    render_home(message.chat.id, message.from_user)


# ============================================================
# START POLLING
# ============================================================

if __name__ == "__main__":
    init_db()

    logger.info("Bhramastra Books bot starting...")

    # Only one active polling process should use this token.
    while True:
        try:
            bot.infinity_polling(
                skip_pending=False,
                allowed_updates=[
                    "message",
                    "callback_query",
                    "chat_member"
                ],
                timeout=30,
                long_polling_timeout=25
            )

        except Exception:
            logger.exception(
                "Polling stopped unexpectedly. Restarting soon."
            )

            time.sleep(5)
