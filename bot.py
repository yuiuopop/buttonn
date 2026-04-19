import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import os

# --- Configuration ---
# Replace with your actual Bot Token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
# Add your Telegram User ID here so you have admin access
ADMIN_USER_IDS = [123456789] 

DB_PATH = "bot_data.db"
bot = telebot.TeleBot(BOT_TOKEN)

# In-memory dictionary to store admin states during setup processes
admin_states = {}

# --- Database Management ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            message_text TEXT NOT NULL,
            keyboard_type TEXT NOT NULL DEFAULT 'inline' 
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_data TEXT NOT NULL,
            row_index INTEGER DEFAULT 0,
            FOREIGN KEY(menu_id) REFERENCES menus(id)
        )
    ''')

    # Seed default Start menu if not exists
    cursor.execute('SELECT COUNT(*) FROM menus')
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO menus (id, name, message_text, keyboard_type) VALUES (1, 'Main Start Menu', 'Welcome! Please select an option:', 'inline')")
        conn.commit()
    conn.close()

def execute_query(query, params=(), commit=False, fetchone=False, fetchall=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = None
    if commit:
        conn.commit()
        result = cursor.lastrowid
    elif fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
    conn.close()
    return result

init_db()

# --- Middleware/Helper ---
def is_admin(user_id):
    return user_id in ADMIN_USER_IDS

# ==========================================
#          USER DYNAMIC DISPATCHER
# ==========================================

def render_menu(chat_id, menu_id, message_id=None):
    menu = execute_query("SELECT id, name, message_text, keyboard_type FROM menus WHERE id=?", (menu_id,), fetchone=True)
    if not menu:
        bot.send_message(chat_id, "Menu not found.")
        return

    m_id, m_name, m_text, kb_type = menu
    buttons = execute_query("SELECT id, text, action_type, action_data, row_index FROM buttons WHERE menu_id=? ORDER BY row_index, id", (menu_id,), fetchall=True)

    markup = None
    
    if kb_type == 'inline':
        markup = InlineKeyboardMarkup()
        # Group by row_index
        rows = {}
        for b_id, b_text, act_type, act_data, r_idx in buttons:
            if r_idx not in rows:
                rows[r_idx] = []
            
            # Action logic encoding
            cb_data = f"{act_type}:{act_data}"
            if len(cb_data) > 64: 
                # Telegram limits callback_data to 64 bytes. In a production app, we'd use a shorthand or store state.
                cb_data = cb_data[:64]

            if act_type == 'url':
                rows[r_idx].append(InlineKeyboardButton(text=b_text, url=act_data))
            else:
                rows[r_idx].append(InlineKeyboardButton(text=b_text, callback_data=cb_data))
        
        for r_idx in sorted(rows.keys()):
            markup.row(*rows[r_idx])
            
    elif kb_type == 'reply':
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        rows = {}
        for b_id, b_text, act_type, act_data, r_idx in buttons:
            if r_idx not in rows:
                rows[r_idx] = []
            rows[r_idx].append(KeyboardButton(b_text))
        for r_idx in sorted(rows.keys()):
            markup.row(*rows[r_idx])
            
    if message_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=m_text, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            # If message content is exactly the same, telegram throws an error. Also fallback if edit fails
            bot.send_message(chat_id, m_text, reply_markup=markup)
    else:
        bot.send_message(chat_id, m_text, reply_markup=markup)

@bot.message_handler(commands=['start'])
def handle_start(message):
    # Load Main Menu (ID 1)
    render_menu(message.chat.id, menu_id=1)

@bot.callback_query_handler(func=lambda call: not call.data.startswith("admin_"))
def handle_dynamic_callback(call):
    data = call.data

    action_type, *action_data_parts = data.split(":", 1)
    action_data = action_data_parts[0] if action_data_parts else ""

    if action_type == "nav":
        # Navigate to another menu
        try:
            target_menu_id = int(action_data)
            render_menu(call.message.chat.id, target_menu_id, call.message.message_id)
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid Target Menu", show_alert=True)
            
    elif action_type == "msg":
        # Send a pop-up alert or a text message
        bot.answer_callback_query(call.id, text=action_data, show_alert=True)
        
    # Always acknowledge the query
    try:
        bot.answer_callback_query(call.id)
    except:
        pass


# ==========================================
#          ADMIN BUILDER PANEL
# ==========================================

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "You are not authorized to use the admin panel.")
        return
        
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🖼 Manage Menus", callback_data="admin_manage_menus"),
        InlineKeyboardButton("➕ Create Menu", callback_data="admin_create_menu")
    )
    markup.row(InlineKeyboardButton("🛠 View all Buttons", callback_data="admin_all_buttons"))
    
    bot.send_message(message.chat.id, "Welcome to the Bot Builder Admin Dashboard.\n\nHere you can create pages/menus and add buttons to them.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callback_handler(call):
    if not is_admin(call.from_user.id):
        return

    chat_id = call.message.chat.id
    data = call.data

    if data == "admin_manage_menus":
        menus = execute_query("SELECT id, name FROM menus", fetchall=True)
        markup = InlineKeyboardMarkup()
        for m_id, m_name in menus:
            markup.add(InlineKeyboardButton(f"Menu: {m_name}", callback_data=f"admin_view_menu:{m_id}"))
        bot.edit_message_text("Select a menu to edit:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
        
    elif data == "admin_create_menu":
        msg = bot.send_message(chat_id, "Please enter the internal name for this new menu (e.g., 'Help Menu'):")
        bot.register_next_step_handler(msg, process_menu_name)
        
    elif data.startswith("admin_view_menu:"):
        menu_id = int(data.split(":")[1])
        menu = execute_query("SELECT name, message_text, keyboard_type FROM menus WHERE id=?", (menu_id,), fetchone=True)
        if menu:
            m_name, m_text, kb_type = menu
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("➕ Add Button Context", callback_data=f"admin_add_btn:{menu_id}"))
            markup.row(
                InlineKeyboardButton("👁 Preview Menu", callback_data=f"admin_preview:{menu_id}"),
                InlineKeyboardButton("🗑 Delete Menu", callback_data=f"admin_del_menu:{menu_id}")
            )
            markup.add(InlineKeyboardButton("🔙 Back to Menus", callback_data="admin_manage_menus"))
            
            info_text = f"**Menu [{m_name}]**\nType: {kb_type}\nText: {m_text}\n\nWhat would you like to do?"
            bot.edit_message_text(info_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif data.startswith("admin_add_btn:"):
        menu_id = int(data.split(":")[1])
        admin_states[chat_id] = {'menu_id': menu_id}
        msg = bot.send_message(chat_id, "What should the text of the button be?")
        bot.register_next_step_handler(msg, process_btn_text)
        
    elif data.startswith("admin_preview:"):
        menu_id = int(data.split(":")[1])
        bot.send_message(chat_id, "Previewing:")
        render_menu(chat_id, menu_id)

# --- Admin Menu Creation Steps ---
def process_menu_name(message):
    if not message.text: return
    chat_id = message.chat.id
    admin_states[chat_id] = {'name': message.text}
    bot.send_message(chat_id, "What should the message text be for this menu? (This is the message users see when the menu loads)")
    bot.register_next_step_handler(message, process_menu_text)

def process_menu_text(message):
    if not message.text: return
    chat_id = message.chat.id
    admin_states[chat_id]['text'] = message.text
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Inline Buttons", callback_data="admin_set_kbtype:inline"),
        InlineKeyboardButton("Reply Menu", callback_data="admin_set_kbtype:reply")
    )
    bot.send_message(chat_id, "What type of buttons should this menu use?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_set_kbtype:"))
def process_menu_kbtype(call):
    chat_id = call.message.chat.id
    if chat_id not in admin_states or 'name' not in admin_states[chat_id]:
        return
    kb_type = call.data.split(":")[1]
    
    m_name = admin_states[chat_id]['name']
    m_text = admin_states[chat_id]['text']
    
    execute_query("INSERT INTO menus (name, message_text, keyboard_type) VALUES (?, ?, ?)", 
                  (m_name, m_text, kb_type), commit=True)
    
    bot.edit_message_text(f"Menu '{m_name}' created successfully! Use /admin to manage it.", chat_id=chat_id, message_id=call.message.message_id)
    del admin_states[chat_id]

# --- Admin Button Creation Steps ---
def process_btn_text(message):
    if not message.text: return
    chat_id = message.chat.id
    admin_states[chat_id]['btn_text'] = message.text
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("Switch Menu", callback_data="admin_btnaction:nav"),
               InlineKeyboardButton("Open URL", callback_data="admin_btnaction:url"))
    markup.row(InlineKeyboardButton("Show Message Alert", callback_data="admin_btnaction:msg"))
    
    bot.send_message(chat_id, "What should this button do?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_btnaction:"))
def process_btn_action(call):
    chat_id = call.message.chat.id
    if chat_id not in admin_states or 'btn_text' not in admin_states[chat_id]:
        return
    
    action_type = call.data.split(":")[1]
    admin_states[chat_id]['action_type'] = action_type
    
    if action_type == "nav":
        menus = execute_query("SELECT id, name FROM menus", fetchall=True)
        m_str = "\n".join([f"ID {m[0]}: {m[1]}" for m in menus])
        msg = bot.send_message(chat_id, f"Available Menus:\n{m_str}\n\nPlease reply with the ID of the menu to navigate to:")
        bot.register_next_step_handler(msg, process_btn_data)
        
    elif action_type == "url":
        msg = bot.send_message(chat_id, "Please reply with the full URL (e.g., https://google.com):")
        bot.register_next_step_handler(msg, process_btn_data)
        
    elif action_type == "msg":
        msg = bot.send_message(chat_id, "Please reply with the text to show when the button is clicked:")
        bot.register_next_step_handler(msg, process_btn_data)

def process_btn_data(message):
    if not message.text: return
    chat_id = message.chat.id
    if chat_id not in admin_states: return
    
    state = admin_states[chat_id]
    action_data = message.text
    
    # Optional: ask for row index. For now just set row 0 to simplify. 
    # Can enhance later.
    
    execute_query("INSERT INTO buttons (menu_id, text, action_type, action_data, row_index) VALUES (?, ?, ?, ?, ?)",
                  (state['menu_id'], state['btn_text'], state['action_type'], action_data, 0), commit=True)
                  
    bot.send_message(chat_id, f"Button '{state['btn_text']}' added successfully! Use /admin to preview.")
    del admin_states[chat_id]


print("Admin Control Bot is running...")
bot.infinity_polling()
