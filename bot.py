import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import threading

# ================= Configuration =================
# Replace with your actual Bot Token from BotFather
BOT_TOKEN = "8756272091:AAGEvJTyq0jPh1aFzDeYhvZ39c1D-TGCEok"

# List of admin Telegram User IDs
ADMIN_IDS = [8305774350] 

# Economics
FREE_STARTING_POINTS = 10
MEDIA_COST = 1
REFERRAL_BONUS = 2


# ================= Database =================
local = threading.local()

def get_db():
    if not hasattr(local, 'db'):
        local.db = sqlite3.connect('media_bot.sqlite', check_same_thread=False)
    return local.db

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 10,
            referred_by INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            media_type TEXT
        )
    ''')
    conn.commit()

def add_user(user_id, username, starting_points, referred_by=None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (user_id, username, points, referred_by) VALUES (?, ?, ?, ?)",
            (user_id, username, starting_points, referred_by)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, points, referred_by FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def update_points(user_id, delta):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    
def get_points(user_id):
    user = get_user(user_id)
    return user[2] if user else 0

def add_media(file_id, media_type):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO media (file_id, media_type) VALUES (?, ?)", (file_id, media_type))
    conn.commit()
    return cursor.lastrowid

def get_random_media():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, media_type FROM media ORDER BY RANDOM() LIMIT 1")
    return cursor.fetchone()
    
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM media")
    media_count = cursor.fetchone()[0]
    return users_count, media_count


# ================= Keyboards =================
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_watch = KeyboardButton("📺 Watch Media")
    btn_referral = KeyboardButton("🔗 Referral")
    markup.add(btn_watch, btn_referral)
    return markup


# ================= Bot Handlers =================
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("[ERROR] Please set your BOT_TOKEN in the configuration section at the top of the file.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

def is_admin(user_id):
    return user_id in ADMIN_IDS

# --- User Handlers ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            referred_by = referrer_id

    is_new = add_user(user_id, username, FREE_STARTING_POINTS, referred_by)
    
    if is_new and referred_by:
        update_points(referred_by, REFERRAL_BONUS)
        try:
            bot.send_message(referred_by, f"🎉 Someone joined using your referral link! You earned {REFERRAL_BONUS} points.")
        except:
            pass
            
    bot.reply_to(message, "Welcome to the Media Bot! 📺\nUse the menu below to watch media or invite friends to earn free points.", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📺 Watch Media")
def handle_watch_media(message):
    user_id = message.from_user.id
    
    points = get_points(user_id)
    if points < MEDIA_COST:
        bot.reply_to(message, "❌ You don't have enough points left to watch media!\nClick '🔗 Referral' to get your invite link and earn more points.")
        return
        
    media = get_random_media()
    if not media:
        bot.reply_to(message, "Currently there is no media available. Check back later!")
        return
        
    file_id, media_type = media
    update_points(user_id, -MEDIA_COST)
    new_points = points - MEDIA_COST
    
    try:
        if media_type == 'photo':
            bot.send_photo(user_id, file_id, caption=f"Enjoy! 🍿\nRemaining points: {new_points}")
        elif media_type == 'video':
            bot.send_video(user_id, file_id, caption=f"Enjoy! 🍿\nRemaining points: {new_points}")
        else:
             bot.send_document(user_id, file_id, caption=f"Enjoy! 🍿\nRemaining points: {new_points}")
    except Exception as e:
        update_points(user_id, MEDIA_COST) # Refund point
        bot.reply_to(message, "❌ Error sending media. Your point was refunded.")

@bot.message_handler(func=lambda message: message.text == "🔗 Referral")
def handle_referral(message):
    user_id = message.from_user.id
    points = get_points(user_id)
    
    bot_info = bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = (f"⭐️ **Your Stats**\n"
            f"Current Points: {points}\n\n"
            f"🔗 **Your Referral Link**\n"
            f"`{referral_link}`\n\n"
            f"Share this link with your friends. For every friend who joins, you get {REFERRAL_BONUS} extra points!")
            
    bot.reply_to(message, text, parse_mode="Markdown")

# --- Admin Handlers ---
@bot.message_handler(commands=['stats'])
def handle_stats(message):
    if not is_admin(message.from_user.id):
        return
    
    users_count, media_count = get_stats()
    text = f"📊 **Bot Stats**\nTotal Users: {users_count}\nTotal Media: {media_count}"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['addpoints'])
def handle_add_points(message):
    if not is_admin(message.from_user.id):
        return
        
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "Usage: /addpoints <user_id> <amount>")
        return
        
    try:
        target_user_id = int(args[1])
        amount = int(args[2])
        update_points(target_user_id, amount)
        bot.reply_to(message, f"✅ Added {amount} points to {target_user_id}.")
        
        try:
            bot.send_message(target_user_id, f"🎁 An admin has added {amount} points to your account!")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "Invalid user ID or amount.")

@bot.message_handler(content_types=['photo', 'video', 'document'])
def handle_media_upload(message):
    if not is_admin(message.from_user.id):
        return
        
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        media_type = 'video'
    elif message.document:
        file_id = message.document.file_id
        media_type = 'document'
    else:
        return
        
    add_media(file_id, media_type)
    bot.reply_to(message, f"✅ Media added to database! Type: {media_type}")

# ================= Main Execution =================
if __name__ == "__main__":
    init_db()
    print("Database initialized.")
    print("Bot is polling...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Error while polling: {e}")
