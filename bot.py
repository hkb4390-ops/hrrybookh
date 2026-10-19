import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '8858220246:AAHePTJ3SXHbS-baO3XtRE1DqmsE0Aojfqs')
# Yahan channel ka numeric ID ya public username dena zaroori hai invite links generate karne ke liye.
# ID hamesha -100 se start hoti hai.
CHANNEL_ID = os.getenv('CHANNEL_ID', '-1004498096954') 
ADMIN_ID = os.getenv('ADMIN_ID', '0')
try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    ADMIN_ID = 0

bot = telebot.TeleBot(BOT_TOKEN)

# --- PDF LINKS ---
PDF_LINKS = {
    1: {"name": "Economic", "link": "https://drive.google.com/file/d/1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view?usp=drivesdk"},
    2: {"name": "Physics", "link": "https://drive.google.com/file/d/1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view?usp=drivesdk"},
    3: {"name": "Civics", "link": "https://drive.google.com/file/d/1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view?usp=drivesdk"},
    4: {"name": "History", "link": "https://drive.google.com/file/d/1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view?usp=drivesdk"},
    5: {"name": "Maths", "link": "https://drive.google.com/file/d/1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view?usp=drivesdk"},
    6: {"name": "Chemistry", "link": "https://drive.google.com/file/d/1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view?usp=drivesdk"},
    7: {"name": "Biology", "link": "https://drive.google.com/file/d/1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view?usp=drivesdk"},
    8: {"name": "Sanskrit", "link": "https://drive.google.com/file/d/1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view?usp=drivesdk"},
    9: {"name": "English", "link": "https://drive.google.com/file/d/1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view?usp=drivesdk"}
}

# --- DATABASE SETUP ---
conn = sqlite3.connect('channel_growth_bot.db', check_same_thread=False)
cursor = conn.cursor()
# Users table store karega: user id, channel ka unka special link, aur kitne logo ne join kiya.
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, 
                    invite_link TEXT,
                    joins_count INTEGER DEFAULT 0)''')
conn.commit()

# --- HELPER FUNCTION: Get or Create Invite Link ---
def get_user_invite_link(user_id):
    cursor.execute("SELECT invite_link FROM users WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    
    if res and res[0]:
        return res[0]
    
    # Agar link nahi hai, toh channel par naya link generate karo
    try:
        # Bot must have 'Add Users' admin right in the channel
        invite_link_obj = bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=f"Invite by {user_id}", # Ye channel admins ko dikhega
            creates_join_request=False
        )
        new_link = invite_link_obj.invite_link
        
        # Save to database
        if res:
            cursor.execute("UPDATE users SET invite_link=? WHERE user_id=?", (new_link, user_id))
        else:
            cursor.execute("INSERT INTO users (user_id, invite_link, joins_count) VALUES (?, ?, 0)", (user_id, new_link))
        conn.commit()
        return new_link
    except Exception as e:
        print(f"Error creating link: {e}")
        return None

# --- COMMANDS ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    
    # Ensure user exists in DB
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, invite_link, joins_count) VALUES (?, NULL, 0)", (user_id,))
        conn.commit()

    show_main_menu(message)

def show_main_menu(message, edit_msg_id=None):
    user_id = message.chat.id
    
    markup = InlineKeyboardMarkup(row_width=2)
    btn_link = InlineKeyboardButton("🔗 Get Channel Invite Link", callback_data="get_channel_link")
    btn_dash = InlineKeyboardButton("📊 My Dashboard", callback_data="open_dashboard")
    btn_pdfs = InlineKeyboardButton("📚 My PDFs", callback_data="open_pdfs")
    
    markup.add(btn_link)
    markup.add(btn_dash, btn_pdfs)
    
    text = f"🔰 **Welcome to Bhramastra PDF Bot!** 🔰\n\n"
    text += "Yahan aap Class 10th ki Bhramastra books FREE me unlock kar sakte hain.\n\n"
    text += "**Kaise Unlock Karein?**\n"
    text += "1️⃣ `Get Channel Invite Link` par click karein.\n"
    text += "2️⃣ Us link ko doston ke sath share karein.\n"
    text += "3️⃣ Jaise hi wo aapke link se **Hamara Channel Join** karenge, aapki PDFs unlock ho jayengi! 🚀"

    if edit_msg_id:
        try:
            bot.edit_message_text(text, user_id, edit_msg_id, reply_markup=markup, parse_mode="Markdown")
        except: pass
    else:
        bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

# --- CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda call: True)
def query_handler(call):
    user_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if call.data == "get_channel_link":
        invite_link = get_user_invite_link(user_id)
        
        if invite_link:
            text = "💎 **YOUR CHANNEL INVITE LINK** 💎\n\n"
            text += "Niche diye gaye link ko copy karein aur share karein:\n\n"
            text += f"`{invite_link}`\n\n"
            text += "⚠️ _Dhyan rahe: Jab log is link se channel join karenge, tabhi aapka count badhega._"
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
            bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ Error: Bot ko Channel me Admin banayein aur 'Manage Invite Links' ki permission dein.", show_alert=True)

    elif call.data == "open_dashboard":
        cursor.execute("SELECT joins_count FROM users WHERE user_id=?", (user_id,))
        res = cursor.fetchone()
        joins = res[0] if res else 0
        unlocked = min(joins, 9)
        progress_bar = "🟢" * unlocked + "🔴" * (9 - unlocked)
        
        text = "🎛 **YOUR CHANNEL GROWTH DASHBOARD** 🎛\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"👥 **People Joined Channel:** `{joins}`\n"
        text += f"🔓 **Unlocked PDFs:** `{unlocked}/9`\n"
        text += f"📊 **Progress:** [{progress_bar}]\n━━━━━━━━━━━━━━━━━━━━\n"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
        bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "open_pdfs":
        cursor.execute("SELECT joins_count FROM users WHERE user_id=?", (user_id,))
        res = cursor.fetchone()
        joins = res[0] if res else 0
        
        text = "📚 **PREMIUM PDF CENTER** 📚\n\n"
        
        markup = InlineKeyboardMarkup(row_width=1)
        
        if joins == 0:
            text += "🔒 _Oops! Aapka saara khazana lock hai. Apne link se kisi ko channel join karwayein!_"
        else:
            for i in range(1, 10):
                if joins >= i:
                    text += f"✅ **Unlocked:** {PDF_LINKS[i]['name']}\n"
                    markup.add(InlineKeyboardButton(f"📥 Download {PDF_LINKS[i]['name']} PDF", url=PDF_LINKS[i]['link']))
                else:
                    text += f"🔒 **Locked:** {PDF_LINKS[i]['name']} (Need {i} Channel Joins)\n"
        
        markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
        bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")
        
    elif call.data == "back_home":
        show_main_menu(call.message, msg_id)


# =======================================================
# 🔥 THE MOST IMPORTANT PART: TRACKING CHANNEL JOINS 🔥
# =======================================================
# Jab bhi koi channel join karta hai invite link ke through, 
# telegram update bhejta hai jise hum chat_member update kehte hain.

@bot.chat_member_handler()
def handle_chat_member_update(message: telebot.types.ChatMemberUpdated):
    # Sirf un updates ko dekho jisme naya member add hua ho
    new_chat_member = message.new_chat_member
    old_chat_member = message.old_chat_member

    # Agar koi user channel me naya aaya hai (pehle left tha ya tha hi nahi, aur ab member ban gaya)
    if (old_chat_member.status in ['left', 'kicked'] and new_chat_member.status in ['member', 'restricted']) or \
       (old_chat_member.status == 'left' and new_chat_member.status == 'member'):
        
        # message.invite_link me us link ki detail hoti hai jisse user ne join kiya hai
        if message.invite_link:
            used_link = message.invite_link.invite_link
            
            # Database me check karo ki ye link kis user ka tha
            cursor.execute("SELECT user_id FROM users WHERE invite_link=?", (used_link,))
            res = cursor.fetchone()
            
            if res:
                referrer_id = res[0]
                # Jisne link banwaya tha, uska count badha do
                cursor.execute("UPDATE users SET joins_count = joins_count + 1 WHERE user_id=?", (referrer_id,))
                conn.commit()
                
                # Referrer ko bot message bhej dega ki kisi ne join kiya
                try:
                    bot.send_message(
                        referrer_id, 
                        "🎉 **Badhai Ho!**\n\nEk naye dost ne aapke link se **Channel Join** kar liya hai! Aapka PDF status update ho gaya hai.",
                        parse_mode="Markdown"
                    )
                except:
                    pass

print("🚀 Advanced Channel Tracker Bot is running...")
# allowed_updates=['chat_member', 'message', 'callback_query'] dena zaroori hai taaki bot joins ko track kar sake
bot.infinity_polling(allowed_updates=['chat_member', 'message', 'callback_query'])
