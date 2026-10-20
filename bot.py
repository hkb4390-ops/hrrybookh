import os
import time
import sqlite3
import logging
import threading
from contextlib import contextmanager

import telebot
from telebot import types
from dotenv import load_dotenv

load_dotenv()

# ==============================
# CONFIGURATION
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "hrrrrrrrrry_bot").strip().lstrip("@")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1004498096954").strip()
CHANNEL_USERNAME = os.getenv(
    "CHANNEL_USERNAME", "hrbseb10thallcorse"
).strip().lstrip("@")

DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")
REQUIRED_REFERRALS = 10

CHANNEL_URL = f"https://t.me/{CHANNEL_USERNAME}"

# PDF links — use only files you are allowed to distribute.
PDF_LINKS = [
    ("📘 Economics", "https://drive.google.com/file/d/1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view"),
    ("📗 Physics", "https://drive.google.com/file/d/1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view"),
    ("📙 Civics", "https://drive.google.com/file/d/1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view"),
    ("📕 History", "https://drive.google.com/file/d/1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view"),
    ("📐 Mathematics", "https://drive.google.com/file/d/1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view"),
    ("🧪 Chemistry", "https://drive.google.com/file/d/1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view"),
    ("🧬 Biology", "https://drive.google.com/file/d/1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view"),
    ("📖 Sanskrit", "https://drive.google.com/file/d/1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view"),
    ("📚 English", "https://drive.google.com/file/d/1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view"),
]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("bhramastra-bot")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# Serialize writes and prevent duplicate referral credits.
db_lock = threading.RLock()


# ==============================
# DATABASE
# ==============================

@contextmanager
def db():
    with db_lock:
        conn = sqlite3.connect(DATABASE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db():
    folder = os.path.dirname(DATABASE_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                joined_channel INTEGER NOT NULL DEFAULT 0,
                referrals INTEGER NOT NULL DEFAULT 0,
                unlocked INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_links (
                owner_id INTEGER PRIMARY KEY,
                invite_link TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_events (
                referred_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                credited_at INTEGER NOT NULL
            )
        """)


def register_user(user):
    with db() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id, first_name, username, created_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name=excluded.first_name,
                username=excluded.username
        """, (
            user.id,
            user.first_name or "",
            user.username or "",
            int(time.time()),
        ))


def get_user(user_id):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()


def get_referral_count(user_id):
    row = get_user(user_id)
    return int(row["referrals"]) if row else 0


def is_unlocked(user_id):
    row = get_user(user_id)
    return bool(row and row["unlocked"])


def set_channel_verified(user_id):
    with db() as conn:
        conn.execute(
            "UPDATE users SET joined_channel=1 WHERE user_id=?",
            (user_id,),
        )


# ==============================
# CHANNEL MEMBERSHIP
# ==============================

def check_membership(user_id):
    """
    Returns:
        True  = member
        False = not a member
        None  = Telegram/API error
    """
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("creator", "administrator", "member") or (
            member.status == "restricted"
            and getattr(member, "is_member", False)
        )
    except Exception:
        log.exception("Membership check failed for user %s", user_id)
        return None


# ==============================
# PERSONAL REFERRAL LINKS
# ==============================

def get_personal_referral_link(user_id):
    with db() as conn:
        row = conn.execute(
            "SELECT invite_link FROM referral_links WHERE owner_id=?",
            (user_id,),
        ).fetchone()

        if row:
            return row["invite_link"]

        # This link is created by THIS bot for the configured channel.
        invite = bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=f"Referral {user_id}",
            creates_join_request=False,
        )

        conn.execute("""
            INSERT INTO referral_links (owner_id, invite_link, created_at)
            VALUES (?, ?, ?)
        """, (user_id, invite.invite_link, int(time.time())))

        return invite.invite_link


# ==============================
# REFERRAL CREDIT
# ==============================

def credit_referral(owner_id, referred_id):
    """
    Call only after a real Telegram membership update confirms
    that the referred user joined using a known personal invite link.
    """
    if owner_id == referred_id:
        return False

    with db() as conn:
        owner = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?",
            (owner_id,),
        ).fetchone()

        referred = conn.execute(
            "SELECT joined_channel FROM users WHERE user_id=?",
            (referred_id,),
        ).fetchone()

        if not owner or not referred:
            return False

        if not referred["joined_channel"]:
            return False

        # PRIMARY KEY prevents counting the same referred user twice.
        cur = conn.execute("""
            INSERT OR IGNORE INTO referral_events (
                referred_id, owner_id, credited_at
            ) VALUES (?, ?, ?)
        """, (referred_id, owner_id, int(time.time())))

        if cur.rowcount != 1:
            return False

        conn.execute("""
            UPDATE users
            SET referrals=referrals+1,
                unlocked=CASE
                    WHEN referrals+1 >= ? THEN 1
                    ELSE unlocked
                END
            WHERE user_id=?
        """, (REQUIRED_REFERRALS, owner_id))

    return True


@bot.chat_member_handler()
def on_channel_member_update(update):
    """
    Telegram must deliver chat_member updates.
    The bot must be an administrator in the channel.
    """
    try:
        if str(update.chat.id) != str(CHANNEL_ID):
            return

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        was_member = old_status in (
            "creator", "administrator", "member"
        ) or (
            old_status == "restricted"
            and getattr(update.old_chat_member, "is_member", False)
        )

        is_member_now = new_status in (
            "creator", "administrator", "member"
        ) or (
            new_status == "restricted"
            and getattr(update.new_chat_member, "is_member", False)
        )

        member_user = update.new_chat_member.user
        register_user(member_user)

        if is_member_now:
            set_channel_verified(member_user.id)

        # Credit only on a transition from non-member to member.
        if was_member or not is_member_now:
            return

        invite = getattr(update, "invite_link", None)
        invite_url = getattr(invite, "invite_link", None)

        if not invite_url:
            log.info(
                "Join detected for %s without invite-link attribution.",
                member_user.id,
            )
            return

        with db() as conn:
            row = conn.execute(
                "SELECT owner_id FROM referral_links WHERE invite_link=?",
                (invite_url,),
            ).fetchone()

        if not row:
            log.info("Join used an invite link not created by this bot.")
            return

        owner_id = int(row["owner_id"])

        if credit_referral(owner_id, member_user.id):
            count = get_referral_count(owner_id)
            log.info(
                "Referral credited: owner=%s count=%s",
                owner_id, count,
            )

            try:
                bot.send_message(
                    owner_id,
                    "🎉 <b>New successful referral!</b>\n\n"
                    f"Your progress: <b>{count}/{REQUIRED_REFERRALS}</b>\n"
                    "Invite more friends to unlock the PDF collection.",
                    parse_mode="HTML",
                )
            except Exception:
                log.exception("Could not notify referral owner")

            if count >= REQUIRED_REFERRALS:
                try:
                    bot.send_message(
                        owner_id,
                        "🏆 <b>Congratulations!</b>\n\n"
                        "आपके 10 successful referrals पूरे हो गए हैं।\n"
                        "अब Bhramastra PDF collection unlock हो गई है।\n\n"
                        "PDF पाने के लिए /pdf लिखें।",
                        parse_mode="HTML",
                    )
                except Exception:
                    log.exception("Could not send unlock message")

    except Exception:
        log.exception("Error processing channel membership update")


# ==============================
# KEYBOARDS
# ==============================

def join_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(
            "📢 JOIN CHANNEL",
            url=CHANNEL_URL,
        ),
        types.InlineKeyboardButton(
            "✅ VERIFY MEMBERSHIP",
            callback_data="verify_membership",
        ),
    )
    return keyboard


def main_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "🔗 My Referral Link",
            callback_data="my_referral",
        ),
        types.InlineKeyboardButton(
            "📊 My Progress",
            callback_data="my_progress",
        ),
        types.InlineKeyboardButton(
            "📚 Get PDF Books",
            callback_data="get_pdfs",
        ),
        types.InlineKeyboardButton(
            "📢 Join Channel",
            url=CHANNEL_URL,
        ),
    )
    return keyboard


# ==============================
# START MESSAGE
# ==============================

def send_welcome(chat_id, first_name):
    text = (
        "📚 <b>BHRAMASTRA BOOKS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"नमस्ते <b>{first_name}</b>! 👋\n\n"
        "🎓 <b>Full Book PDF Free Download</b>\n"
        "अपनी study books और PDF collection पाने के लिए "
        "पहले हमारे official channel को Join करें।\n\n"
        "👇 <b>पहले Join करें, फिर Verify करें।</b>"
    )

    bot.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=join_keyboard(),
    )


@bot.message_handler(commands=["start"])
def start_command(message):
    user = message.from_user
    register_user(user)

    # Referral deep-link is not proof of a successful referral.
    # Actual credit occurs only after Telegram confirms channel join
    # through the recorded invite link.
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            owner_id = int(parts[1][4:])
            if owner_id != user.id and get_user(owner_id):
                log.info(
                    "Referral start recorded: owner=%s user=%s",
                    owner_id, user.id,
                )
        except ValueError:
            pass

    send_welcome(message.chat.id, user.first_name or "Student")


# ==============================
# VERIFY CHANNEL
# ==============================

@bot.callback_query_handler(func=lambda call: call.data == "verify_membership")
def verify_membership(call):
    user_id = call.from_user.id

    try:
        bot.answer_callback_query(
            call.id,
            "Membership check हो रही है…",
        )
    except Exception:
        pass

    result = check_membership(user_id)

    if result is None:
        bot.send_message(
            call.message.chat.id,
            "⚠️ अभी membership verify नहीं हो पाई।\n"
            "कुछ देर बाद फिर कोशिश करें।",
            reply_markup=join_keyboard(),
        )
        return

    if not result:
        bot.send_message(
            call.message.chat.id,
            "❌ <b>आप अभी channel में joined नहीं हैं।</b>\n\n"
            "पहले Join Channel दबाएँ। Join करने के बाद "
            "Verify Membership दबाएँ।",
            parse_mode="HTML",
            reply_markup=join_keyboard(),
        )
        return

    register_user(call.from_user)
    set_channel_verified(user_id)

    count = get_referral_count(user_id)

    success_text = (
        "✅ <b>MEMBERSHIP VERIFIED!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎉 आपका channel verification सफल हो गया है!\n\n"
        "📚 <b>Bhramastra Books — Full Book PDF</b>\n\n"
        f"🔗 PDF collection unlock करने के लिए "
        f"<b>{REQUIRED_REFERRALS}</b> successful referrals पूरे करें।\n\n"
        f"📊 आपका progress: <b>{count}/{REQUIRED_REFERRALS}</b>\n\n"
        "नीचे My Referral Link दबाकर अपना personal invite link पाएँ।"
    )

    bot.send_message(
        call.message.chat.id,
        success_text,
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


# ==============================
# REFERRAL LINK BUTTON
# ==============================

@bot.callback_query_handler(func=lambda call: call.data == "my_referral")
def my_referral(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    user_id = call.from_user.id
    result = check_membership(user_id)

    if result is not True:
        bot.send_message(
            call.message.chat.id,
            "पहले channel Join करके Verify करें।",
            reply_markup=join_keyboard(),
        )
        return

    register_user(call.from_user)
    set_channel_verified(user_id)

    try:
        link = get_personal_referral_link(user_id)
    except Exception:
        log.exception("Could not create personal invite link")
        bot.send_message(
            call.message.chat.id,
            "⚠️ Referral link नहीं बन पाया।\n"
            "कृपया जाँचें कि bot channel का administrator है "
            "और उसे invite links बनाने की permission है।",
        )
        return

    count = get_referral_count(user_id)

    bot.send_message(
        call.message.chat.id,
        "🔗 <b>YOUR PERSONAL REFERRAL LINK</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<code>{link}</code>\n\n"
        "📤 इस link को अपने दोस्तों के साथ share करें।\n"
        "जब कोई नया user इस link से channel Join करेगा "
        "और Telegram उसका invite-link attribution देगा, "
        "तभी referral count होगा।\n\n"
        f"🎯 Progress: <b>{count}/{REQUIRED_REFERRALS}</b>\n"
        "🏆 10 valid referrals पर PDF collection unlock होगी।",
        parse_mode="HTML",
    )


# ==============================
# PROGRESS BUTTON
# ==============================

@bot.callback_query_handler(func=lambda call: call.data == "my_progress")
def my_progress(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    user_id = call.from_user.id
    count = get_referral_count(user_id)
    unlocked = is_unlocked(user_id)

    if unlocked:
        status = "🔓 <b>PDF ACCESS UNLOCKED!</b>"
    else:
        status = (
            f"🔒 <b>{REQUIRED_REFERRALS - count}</b> "
            "और successful referrals चाहिए।"
        )

    bot.send_message(
        call.message.chat.id,
        "📊 <b>YOUR REFERRAL DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Successful referrals: <b>{count}</b>\n"
        f"🎯 Target: <b>{REQUIRED_REFERRALS}</b>\n"
        f"📈 Progress: <b>{min(count, REQUIRED_REFERRALS)}/"
        f"{REQUIRED_REFERRALS}</b>\n\n"
        f"{status}\n\n"
        "अपना link पाने के लिए My Referral Link दबाएँ।",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


# ==============================
# PDF CENTER
# ==============================

@bot.callback_query_handler(func=lambda call: call.data == "get_pdfs")
def pdf_button(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    show_pdfs(call.message.chat.id, call.from_user.id)


@bot.message_handler(commands=["pdf"])
def pdf_command(message):
    show_pdfs(message.chat.id, message.from_user.id)


def show_pdfs(chat_id, user_id):
    result = check_membership(user_id)

    if result is not True:
        bot.send_message(
            chat_id,
            "📢 PDF collection देखने से पहले channel Join करके Verify करें।",
            reply_markup=join_keyboard(),
        )
        return

    register_user(bot.get_chat_member(CHANNEL_ID, user_id).user)
    set_channel_verified(user_id)

    if not is_unlocked(user_id):
        count = get_referral_count(user_id)
        bot.send_message(
            chat_id,
            "🔒 <b>PDF COLLECTION LOCKED</b>\n\n"
            "आपको PDF collection unlock करने के लिए "
            f"<b>{REQUIRED_REFERRALS}</b> successful referrals पूरे करने हैं।\n\n"
            f"आपका progress: <b>{count}/{REQUIRED_REFERRALS}</b>\n\n"
            "My Referral Link दबाकर अपना personal link पाएँ।",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        return

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for title, url in PDF_LINKS:
        keyboard.add(
            types.InlineKeyboardButton(title, url=url)
        )

    bot.send_message(
        chat_id,
        "🏆 <b>BHRAMASTRA PDF COLLECTION</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎉 आपके 10 valid referrals पूरे हो चुके हैं!\n"
        "नीचे अपनी आवश्यक PDF चुनें।",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ==============================
# ADMIN STATS
# ==============================

def is_admin(user_id):
    admin_id = os.getenv("ADMIN_ID", "").strip()
    return bool(admin_id) and str(user_id) == admin_id


@bot.message_handler(commands=["stats"])
def stats_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin only.")
        return

    with db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM users"
        ).fetchone()["n"]

        verified = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE joined_channel=1"
        ).fetchone()["n"]

        unlocked = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE unlocked=1"
        ).fetchone()["n"]

        referrals = conn.execute(
            "SELECT COUNT(*) AS n FROM referral_events"
        ).fetchone()["n"]

    bot.reply_to(
        message,
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Registered users: <b>{total}</b>\n"
        f"✅ Verified users: <b>{verified}</b>\n"
        f"🔗 Successful referrals: <b>{referrals}</b>\n"
        f"🏆 Users unlocked: <b>{unlocked}</b>",
        parse_mode="HTML",
    )


# ==============================
# HELP
# ==============================

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.reply_to(
        message,
        "📚 <b>Bhramastra Books Bot</b>\n\n"
        "/start — Start bot\n"
        "/pdf — Open PDF collection\n"
        "/help — Help",
        parse_mode="HTML",
    )


# ==============================
# STARTUP
# ==============================

if __name__ == "__main__":
    init_db()

    me = bot.get_me()
    log.info("Database initialized.")
    log.info("Starting bot @%s (ID %s)", me.username, me.id)

    # IMPORTANT:
    # Only ONE process/service may poll this bot token.
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=25,
        allowed_updates=[
            "message",
            "callback_query",
            "chat_member",
        ],
        skip_pending=False,
    )
