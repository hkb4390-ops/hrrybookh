import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import sqlite3
from dotenv import load_dotenv

# --- RENDER KE LIYE ENVIRONMENT SETUP ---
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '8858220246:AAHaEwMfb-9I6hAX-SlQqcvsamZt8scM5Mg')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'hrrrrrrrrry_bot')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@hrbseb10thallcorse')
ADMIN_ID = os.getenv('ADMIN_ID', '0') # Default 0 agar admin id set nahi hai
try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    ADMIN_ID = 0

bot = telebot.TeleBot(BOT_TOKEN)

# --- PREMIUM CONTENT DATA ---
# Yahan aap image link daal sakte hain jo start command par aayegi
WELCOME_IMAGE = "https://i.postimg.cc/q7zvQKQ0/bhramastra-banner.jpg" # Isko aap apne kisi banner link se replace kar sakte hain

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

# --- DATABASE SETUP (ROBUST) ---
conn = sqlite3.connect('premium_bot_data.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, 
                    first_name TEXT,
                    referrals INTEGER DEFAULT 0,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# --- HELPER FUNCTIONS ---
def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        if status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"Sub check error: {e}")
        return False

def get_user_data(user_id):
    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    return res[0] if res else 0

def add_user(user_id, first_name):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, first_name, referrals) VALUES (?, ?, ?)", (user_id, first_name, 0))
        conn.commit()
        return True
    return False

# --- MAIN LOGIC ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    text_parts = message.text.split()
    
    is_new_user = add_user(user_id, first_name)
    
    # Referral Logic
    if is_new_user and len(text_parts) > 1:
        referrer_id = text_parts[1]
        try:
            referrer_id = int(referrer_id)
            if referrer_id != user_id:
                cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (referrer_id,))
                conn.commit()
                # Notify Referrer with Premium Style
                bot.send_message(
                    referrer_id, 
                    f"🎉 **VIP ALERT!**\n\nEk naye dost ne aapke link se join kiya hai.\n📈 Aapka Score Badh Gaya! Check your Dashboard.", 
                    parse_mode="Markdown"
                )
        except ValueError:
            pass

    show_main_menu(message)

def show_main_menu(message, edit_msg_id=None):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    
    if not is_subscribed(user_id):
        # Premium Force Sub Menu
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 Join Official Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"))
        markup.add(InlineKeyboardButton("🔄 Verify Join", callback_data="verify_sub"))
        
        text = f"✋ **Rukiye {first_name}!**\n\nBhramastra Premium PDFs 📚 aur sabhi updates ke liye aapko hamara official channel join karna hoga.\n\n👇 **Pehle channel join karein, fir 'Verify Join' dabayein.**"
        
        if edit_msg_id:
            try:
                bot.edit_message_text(text, user_id, edit_msg_id, reply_markup=markup, parse_mode="Markdown")
            except: pass
        else:
            # Agar chaho toh start me image bhejne ke liye isko uncomment kar sakte ho
            # bot.send_photo(user_id, WELCOME_IMAGE, caption=text, reply_markup=markup, parse_mode="Markdown")
            bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")
        return

    # Premium Main Menu Layout
    markup = InlineKeyboardMarkup(row_width=2)
    btn_dash = InlineKeyboardButton("📊 My Dashboard", callback_data="open_dashboard")
    btn_link = InlineKeyboardButton("🔗 Generate VIP Link", callback_data="open_referral")
    btn_pdfs = InlineKeyboardButton("📚 Premium PDFs Center", callback_data="open_pdfs")
    btn_leader = InlineKeyboardButton("🏆 Top Referrers", callback_data="leaderboard")
    
    markup.add(btn_dash, btn_link)
    markup.add(btn_pdfs)
    markup.add(btn_leader)
    
    text = f"🔰 **Welcome to Bhramastra VIP Hub, {first_name}!** 🔰\n\n"
    text += "🔹 Yahan aapko class 10th ki sabhi Premium PDF books milengi.\n"
    text += "🔹 Doston ko invite karein aur PDFs unlock karein.\n\n"
    text += "⚡ _Apna option niche select karein:_"

    if edit_msg_id:
        try:
            bot.edit_message_text(text, user_id, edit_msg_id, reply_markup=markup, parse_mode="Markdown")
        except: pass
    else:
        bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

# --- CALLBACK HANDLERS (Interactivity) ---
@bot.callback_query_handler(func=lambda call: True)
def query_handler(call):
    user_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if call.data == "verify_sub":
        if is_subscribed(user_id):
            bot.answer_callback_query(call.id, "✅ Verification Successful! Welcome to Premium Hub.", show_alert=True)
            show_main_menu(call.message, msg_id)
        else:
            bot.answer_callback_query(call.id, "❌ Aapne abhi tak Join nahi kiya. Channel check karein!", show_alert=True)
            
    elif call.data == "open_dashboard":
        if not is_subscribed(user_id): return show_main_menu(call.message, msg_id)
        
        refs = get_user_data(user_id)
        unlocked = min(refs, 9)
        progress_bar = "🟢" * unlocked + "🔴" * (9 - unlocked)
        
        text = "🎛 **YOUR VIP DASHBOARD** 🎛\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"👤 **Profile:** `{call.from_user.first_name}`\n"
        text += f"🆔 **Account ID:** `{user_id}`\n\n"
        text += f"👥 **Total Invites:** `{refs}` Friends\n"
        text += f"🔓 **Unlocked Items:** `{unlocked}/9` PDFs\n"
        text += f"📊 **Progress:** [{progress_bar}]\n━━━━━━━━━━━━━━━━━━━━\n"
        
        if unlocked < 9:
            text += f"⚠️ _Agli PDF unlock karne ke liye aur logo ko invite karein!_"
        else:
            text += f"🎉 _Congratulations! Aapne sabhi PDFs unlock kar li hain._"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
        bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "open_referral":
        if not is_subscribed(user_id): return show_main_menu(call.message, msg_id)
        
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        
        text = "💎 **YOUR VIP INVITE SYSTEM** 💎\n\n"
        text += "Niche diye gaye link par click karke copy karein:\n"
        text += f"👉 `{ref_link}` 👈\n\n"
        text += "🚀 **Rules:**\n"
        text += "1️⃣ Apne doston ko ye link bhejein.\n"
        text += "2️⃣ Unko channel join karwayein.\n"
        text += "3️⃣ Aapka PDF unlock ho jayega! 🔓"
        
        markup = InlineKeyboardMarkup()
        share_url = f"https://t.me/share/url?url={ref_link}&text=🔥%20Bhramastra%20Class%2010th%20ki%20saari%20Premium%20PDFs%20FREE%20me%20chahiye?%20Ye%20Bot%20join%20karo%20fast!%20🚀"
        markup.add(InlineKeyboardButton("🚀 Share Directly on Telegram", url=share_url))
        markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
        
        bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "open_pdfs":
        if not is_subscribed(user_id): return show_main_menu(call.message, msg_id)
        
        refs = get_user_data(user_id)
        
        text = "📚 **PREMIUM PDF CENTER** 📚\n\n"
        text += f"Aapke paas **{refs} Invites** hain.\n\n"
        
        markup = InlineKeyboardMarkup(row_width=1)
        
        if refs == 0:
            text += "🔒 _Oops! Aapka saara khazana lock hai. Pehle kisi dost ko invite karein!_"
            markup.add(InlineKeyboardButton("🔗 Invite Friends to Unlock", callback_data="open_referral"))
        else:
            for i in range(1, 10):
                if refs >= i:
                    text += f"✅ **Unlocked:** {PDF_LINKS[i]['name']}\n"
                    markup.add(InlineKeyboardButton(f"📥 Download {PDF_LINKS[i]['name']} PDF", url=PDF_LINKS[i]['link']))
                else:
                    text += f"🔒 **Locked:** {PDF_LINKS[i]['name']} (Need {i} Invites)\n"
        
        markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
        bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")
        
    elif call.data == "leaderboard":
        # Extra Feature: Top users dekhne ke liye
        cursor.execute("SELECT first_name, referrals FROM users ORDER BY referrals DESC LIMIT 5")
        top_users = cursor.fetchall()
        
        text = "🏆 **GLOBAL LEADERBOARD (TOP 5)** 🏆\n━━━━━━━━━━━━━━━━━━━━\n"
        if not top_users or top_users[0][1] == 0:
            text += "Abhi tak kisi ne invite nahi kiya hai. Aap pehle ban sakte hain!\n"
        else:
            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            for idx, user in enumerate(top_users):
                if user[1] > 0:
                    name = user[0] if user[0] else "User"
                    text += f"{medals[idx]} **{name}** - `{user[1]} Invites`\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
        bot.edit_message_text(text, user_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "back_home":
        show_main_menu(call.message, msg_id)

# --- ADMIN BROADCAST SYSTEM (Premium Feature) ---
# Command: /broadcast <message>
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    user_id = message.chat.id
    if user_id != ADMIN_ID and ADMIN_ID != 0:
        bot.reply_to(message, "❌ Ye command sirf Admin ke liye hai.")
        return
        
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.reply_to(message, "⚠️ Format: `/broadcast Aapka message yahan likhein`", parse_mode="Markdown")
        return
        
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    
    success = 0
    failed = 0
    bot.reply_to(message, f"⏳ Broadcasting to {len(users)} users...")
    
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **ADMIN UPDATE**\n\n{text}", parse_mode="Markdown")
            success += 1
        except:
            failed += 1
            
    bot.send_message(user_id, f"✅ **Broadcast Complete!**\n\n📤 Sent: {success}\n❌ Failed (Blocked bot): {failed}")


print("🚀 Premium Bot is booting up...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
