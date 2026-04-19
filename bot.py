import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import threading
import math

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
            referred_by INTEGER,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            media_received INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            media_type TEXT
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN media_received INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
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
    cursor.execute("SELECT user_id, username, points, referred_by, DATE(join_date) FROM users WHERE user_id = ?", (user_id,))
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
    cursor.execute("SELECT id, file_id, media_type FROM media ORDER BY RANDOM() LIMIT 1")
    return cursor.fetchone()

def update_media_received(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET media_received = media_received + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def delete_media(media_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM media WHERE id = ?", (media_id,))
    success = cursor.rowcount > 0
    conn.commit()
    return success

def get_media_page(limit, offset):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, media_type FROM media ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    return cursor.fetchall()

def get_media_by_id(media_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, media_type FROM media WHERE id = ?", (media_id,))
    return cursor.fetchone()

def wipe_all_media():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM media")
    conn.commit()

def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM media")
    media_count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(media_received) FROM users")
    total_received_sum = cursor.fetchone()[0]
    total_received = total_received_sum if total_received_sum else 0
    return users_count, media_count, total_received


# ================= UI & Keyboards =================
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_watch = KeyboardButton("📺 Watch Media")
    btn_referral = KeyboardButton("🔗 Referral")
    btn_balance = KeyboardButton("💰 Balance")
    markup.add(btn_watch, btn_referral, btn_balance)
    return markup

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("📺 Watch Media"), KeyboardButton("💰 Balance"))
    markup.add(KeyboardButton("📁 Manage Media"), KeyboardButton("📊 User Stats"))
    return markup

def generate_manage_markup(page):
    markup = InlineKeyboardMarkup()
    
    _, total_media, _ = get_stats()
    limit = 5
    offset = page * limit
    total_pages = math.ceil(total_media / limit) if total_media > 0 else 1
    
    media_items = get_media_page(limit, offset)
    
    if media_items:
        for m_id, m_type in media_items:
            preview_btn = InlineKeyboardButton(f"👀 Preview [{m_type.upper()} {m_id}]", callback_data=f"preview_{m_id}_{page}")
            delete_btn = InlineKeyboardButton(f"❌ Delete", callback_data=f"delmedia_{m_id}_{page}")
            markup.add(preview_btn, delete_btn)
            
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"manage_page_{page-1}"))
        else:
            nav_buttons.append(InlineKeyboardButton(" ", callback_data="ignore"))
            
        nav_buttons.append(InlineKeyboardButton(f"Page {page+1}/{total_pages}", callback_data="ignore"))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"manage_page_{page+1}"))
        else:
            nav_buttons.append(InlineKeyboardButton(" ", callback_data="ignore"))
            
        markup.row(*nav_buttons)
        markup.add(InlineKeyboardButton("🚨 Wipe All Media 🚨", callback_data="wipe_media_init"))
    else:
        markup.add(InlineKeyboardButton("No media found.", callback_data="ignore"))
        
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
    admin_mode = is_admin(user_id)
    
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
            
    if admin_mode:
        bot.reply_to(message, "👑 **Admin Access Granted!** Welcome to the control panel.", reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    else:
        bot.reply_to(message, "Welcome to the Media Bot! 📺\nUse the menu below to watch media or invite friends to earn free points.", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📺 Watch Media")
def handle_watch_media(message):
    user_id = message.from_user.id
    admin_mode = is_admin(user_id)
    
    points = get_points(user_id)
    if not admin_mode and points < MEDIA_COST:
        bot.reply_to(message, "❌ You don't have enough points left to watch media!\nClick '🔗 Referral' to get your invite link and earn more points.")
        return
        
    media = get_random_media()
    if not media:
        bot.reply_to(message, "Currently there is no media available. Check back later!")
        return
        
    _id, file_id, media_type = media
    
    if not admin_mode:
        update_points(user_id, -MEDIA_COST)
        update_media_received(user_id)
        new_points = points - MEDIA_COST
        caption_text = f"Enjoy! 🍿\nRemaining points: {new_points}"
    else:
        caption_text = f"Enjoy! 🍿\n[👑 Admin View: Unlimited]\n[ID: {_id}]"
    
    try:
        if media_type == 'photo':
            bot.send_photo(user_id, file_id, caption=caption_text)
        elif media_type == 'video':
            bot.send_video(user_id, file_id, caption=caption_text)
        else:
             bot.send_document(user_id, file_id, caption=caption_text)
    except Exception as e:
        if not admin_mode:
            update_points(user_id, MEDIA_COST) # Refund point
        bot.reply_to(message, "❌ Error sending media. Your point was refunded." if not admin_mode else "❌ Error sending media.")

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

@bot.message_handler(func=lambda message: message.text == "💰 Balance")
def handle_balance(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "You are not registered. Please type /start first.")
        return
        
    points = user[2]
    join_date = user[4] if len(user) > 4 else "Unknown"
    
    text = (f"👤 **Account Information**\n\n"
            f"💰 **Balance:** {points} points\n"
            f"📅 **Date of Joining:** {join_date}")
            
    bot.reply_to(message, text, parse_mode="Markdown")


# --- Admin Handlers ---
@bot.message_handler(func=lambda message: message.text == "📊 User Stats" or message.text == "/stats")
def handle_stats(message):
    if not is_admin(message.from_user.id):
        return
    
    users_count, media_count, total_received = get_stats()
    text = (f"📊 **Bot Stats Dashboard**\n\n"
            f"👥 **Total Registered Users:** {users_count}\n"
            f"📦 **Total Media Uploaded:** {media_count}\n"
            f"📤 **Total Media Distributed:** {total_received}")
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📁 Manage Media")
def handle_manage_media(message):
    if not is_admin(message.from_user.id):
        return
        
    _, total_media, _ = get_stats()
    text = f"📁 **Media Management**\nTotal pieces of media in library: {total_media}\n\n_Use the buttons below to preview, delete, or navigate._"
    
    markup = generate_manage_markup(0)
    bot.reply_to(message, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['delmedia'])
def handle_delmedia_command(message):
    if not is_admin(message.from_user.id):
        return
        
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: `/delmedia <ID>`", parse_mode="Markdown")
        return
        
    media_id = args[1]
    if delete_media(media_id):
        bot.reply_to(message, f"✅ Media ID {media_id} has been successfully removed from the library.")
    else:
        bot.reply_to(message, "❌ Media not found. It may have already been deleted.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_page_"))
def handle_manage_page(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "Unauthorized.")
    
    page = int(call.data.split('_')[2])
    markup = generate_manage_markup(page)
    _, total_media, _ = get_stats()
    text = f"📁 **Media Management**\nTotal pieces of media in library: {total_media}\n\n_Use the buttons below to preview, delete, or navigate._"
    
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    except Exception as e:
        bot.answer_callback_query(call.id, "Already on this page.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("preview_"))
def handle_preview(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "Unauthorized.")
        
    parts = call.data.split('_')
    media_id = parts[1]
    
    media = get_media_by_id(media_id)
    if not media:
        return bot.answer_callback_query(call.id, "Media no longer exists in DB.")
        
    file_id, media_type = media
    bot.answer_callback_query(call.id, "Sending preview...")
    
    msg_text = f"👀 **Preview of Media ID: {media_id}**"
    try:
        if media_type == 'photo':
            bot.send_photo(call.message.chat.id, file_id, caption=msg_text, parse_mode="Markdown")
        elif media_type == 'video':
            bot.send_video(call.message.chat.id, file_id, caption=msg_text, parse_mode="Markdown")
        else:
            bot.send_document(call.message.chat.id, file_id, caption=msg_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Failed to preview Media ID {media_id}. The file might have been removed from Telegram servers.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmedia_"))
def handle_delete_callback(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "Unauthorized.")
        
    parts = call.data.split('_')
    media_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    
    if delete_media(media_id):
        bot.answer_callback_query(call.id, f"✅ Deleted Media {media_id}!")
    else:
        bot.answer_callback_query(call.id, "Media not found.")
        
    # Refresh the page
    markup = generate_manage_markup(page)
    _, total_media, _ = get_stats()
    text = f"📁 **Media Management**\nTotal pieces of media in library: {total_media}\n\n_Use the buttons below to preview, delete, or navigate._"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "wipe_media_init")
def handle_wipe_init(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "Unauthorized.")
        
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚠️ YES, DELETE EVERYTHING ⚠️", callback_data="wipe_media_confirm"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="manage_page_0"))
    
    bot.edit_message_text("🚨 **WARNING!** 🚨\nAre you sure you want to permanently wipe all media from the database? This action cannot be undone.", 
                          call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "wipe_media_confirm")
def handle_wipe_confirm(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "Unauthorized.")
        
    wipe_all_media()
    bot.answer_callback_query(call.id, "All media wiped successfully!")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Management", callback_data="manage_page_0"))
    bot.edit_message_text("✅ All media has been successfully wiped from the database.",
                          call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "ignore")
def handle_ignore(call):
    bot.answer_callback_query(call.id)

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
        
    m_id = add_media(file_id, media_type)
    bot.reply_to(message, f"✅ Media added to database!\nType: {media_type}\nMedia ID: {m_id}")

# ================= Main Execution =================
if __name__ == "__main__":
    init_db()
    print("Database initialized.")
    print("Bot is polling...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Error while polling: {e}")
