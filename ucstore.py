# -*- coding: utf-8 -*-
"""
Telegram shop bot — як файл (pyTelegramBotAPI + sqlite3)
Ислоҳшуда барои мушаххасоти корбар
"""

import sqlite3
import telebot
from telebot import types
import os
import re
import time

# ---------- Конфиг ----------
BOT_TOKEN = "8394642029:AAH50ltfmxyRRBnPm3QTa3LAtx8MeDSqBU0"  # <- ИН ҶО ТОКЕНРО ГУЗОРЕД
ADMIN_ID = 5808918857     # ID админ
ADMIN_INSTAGRAM = "https://www.instagram.com/garant_alestr?igsh=cTE4bnA3NW5ycHFs"
DB_FILE = "bot.db"

# ---------- Созмондиҳӣ ----------
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# ---------- Database init ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 tg_id INTEGER UNIQUE,
                 phone TEXT,
                 verified INTEGER DEFAULT 0,
                 first_name TEXT,
                 last_name TEXT,
                 username TEXT
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS products (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 category TEXT,
                 code TEXT UNIQUE,
                 title TEXT,
                 price_tjs INTEGER,
                 diamonds INTEGER,
                 description TEXT
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS cart (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 tg_id INTEGER,
                 product_code TEXT,
                 qty INTEGER DEFAULT 1
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS wishlist (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 tg_id INTEGER,
                 product_code TEXT
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 tg_id INTEGER,
                 order_text TEXT,
                 game_id TEXT,
                 status TEXT DEFAULT 'pending',
                 created_at INTEGER,
                 receipt_file_id TEXT
                 )""")
    conn.commit()

    # Insert default products if none
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        diamonds = [
            ("diamond", "D100", "💎100+5", 10, 105, "100+5 diamonds"),
            ("diamond", "D310", "💎310+16", 28, 326, "310+16 diamonds"),
            ("diamond", "D510", "💎510+26", 45, 536, "510+26 diamonds"),
            ("diamond", "D1060", "💎1060+53", 92, 1113, "1060+53 diamonds"),
            ("diamond", "D2180", "💎2180+216", 185, 2396, "2180+216 diamonds"),
            ("diamond", "D5600", "💎5600+560", 460, 6160, "5600+560 diamonds"),
        ]
        for cat, code, title, price, diamonds_count, desc in diamonds:
            c.execute("INSERT INTO products (category, code, title, price_tjs, diamonds, description) VALUES (?, ?, ?, ?, ?, ?)",
                      (cat, code, title, price, diamonds_count, desc))
        vouchers = [
            ("voucher", "V_WEEK", "Неделю - 450💎-17 см", 0, 450, "1 week voucher: 450 diamonds - 17 см"),
            ("voucher", "V_MONTH", "Месяц - 2600💎-97 см", 0, 2600, "1 month voucher: 2600 diamonds - 97 см"),
            ("voucher", "V_LIGHT", "Лайт - 90💎-7 см", 0, 90, "Light voucher: 90 diamonds - 7 см"),
        ]
        for cat, code, title, price, diamonds_count, desc in vouchers:
            c.execute("INSERT INTO products (category, code, title, price_tjs, diamonds, description) VALUES (?, ?, ?, ?, ?, ?)",
                      (cat, code, title, price, diamonds_count, desc))
        conn.commit()
    conn.close()

init_db()

# ---------- In-memory states ----------
user_state = {}  # tg_id -> {"step": "...", "expected": ..., "tmp": {...}}

def set_state(tg_id, step, expected=None, tmp=None):
    user_state[tg_id] = {"step": step, "expected": expected, "tmp": tmp or {}}

def get_state(tg_id):
    return user_state.get(tg_id, {"step": None, "expected": None, "tmp": {}})

def clear_state(tg_id):
    if tg_id in user_state:
        del user_state[tg_id]

# ---------- Keyboards ----------
def main_menu_keyboard(tg_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🛒 Мағоза", "🧺 Сабад")
    markup.row("💖 Дилхоҳо", "ℹ️ Маълумот")
    markup.row("👤 Профили админ", "🛠️ Панели админ")
    return markup

def shop_menu_kb():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔹 Алмаз", callback_data="shop_diamond"))
    markup.add(types.InlineKeyboardButton("🎟️ Воучер", callback_data="shop_voucher"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_to_main"))
    return markup

def diamonds_kb():
    markup = types.InlineKeyboardMarkup(row_width=1)
    labels = [
        ("💎100+5 - 10 TJS", "D100"),
        ("💎310+16 - 28 TJS", "D310"),
        ("💎510+26 - 45 TJS", "D510"),
        ("💎1060+53 - 92 TJS", "D1060"),
        ("💎2180+216 - 185 TJS", "D2180"),
        ("💎5600+560 - 460 TJS", "D5600"),
    ]
    for label, code in labels:
        markup.add(types.InlineKeyboardButton(label, callback_data=f"prod_select:{code}"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="shop_menu_back"))
    return markup

def vouchers_kb():
    markup = types.InlineKeyboardMarkup(row_width=1)
    labels = [
        ("Неделю - 450💎-17 см", "V_WEEK"),
        ("Месяц-2600💎-97 см", "V_MONTH"),
        ("Лайт-90💎-7 см", "V_LIGHT"),
    ]
    for label, code in labels:
        markup.add(types.InlineKeyboardButton(label, callback_data=f"prod_select:{code}"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="shop_menu_back"))
    return markup

def product_action_kb(code):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("➕ Илова ба сабад", callback_data=f"add_cart:{code}"),
               types.InlineKeyboardButton("💖 Илова ба дилхоҳо", callback_data=f"add_wish:{code}"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="shop_menu_back"))
    return markup

def wishlist_item_kb(code):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Илова ба сабад", callback_data=f"wish_to_cart:{code}"))
    markup.add(types.InlineKeyboardButton("🗑️ Пок кардан", callback_data=f"wish_clear_item:{code}"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_to_main"))
    return markup

def cart_item_kb():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛍️ Фармоиш додан", callback_data="order_start"))
    markup.add(types.InlineKeyboardButton("🗑️ Пок кардан", callback_data="cart_clear"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_to_main"))
    return markup

def admin_panel_kb(is_admin=False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if is_admin:
        markup.add(types.InlineKeyboardButton("📋 Рӯйхати корбарон", callback_data="admin_users"))
        markup.add(types.InlineKeyboardButton("📦 Фармоишҳо", callback_data="admin_orders"))
        markup.add(types.InlineKeyboardButton("✉️ Паём ба корбарон", callback_data="admin_broadcast"))
    else:
        markup.add(types.InlineKeyboardButton("🔒 Шумо админ нестед", callback_data="back_to_main"))
    markup.add(types.InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_to_main"))
    return markup

def admin_order_action_kb(order_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Қабул", callback_data=f"admin_accept:{order_id}"),
               types.InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject:{order_id}"))
    return markup

# ---------- DB helpers ----------
def db_execute(query, params=(), fetch=False, many=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if many:
        c.executemany(query, params)
    else:
        c.execute(query, params)
    if fetch:
        res = c.fetchall()
        conn.commit()
        conn.close()
        return res
    conn.commit()
    conn.close()
    return None

def add_user_if_not_exists(tg_user):
    tg_id = tg_user.id
    first = tg_user.first_name or ""
    last = tg_user.last_name or ""
    username = tg_user.username or ""
    existing = db_execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,), fetch=True)
    if not existing:
        db_execute("INSERT INTO users (tg_id, first_name, last_name, username) VALUES (?, ?, ?, ?)",
                   (tg_id, first, last, username))

def set_user_phone(tg_id, phone, verified=0):
    db_execute("UPDATE users SET phone = ?, verified = ? WHERE tg_id = ?", (phone, verified, tg_id))

def set_user_verified(tg_id, v=1):
    db_execute("UPDATE users SET verified = ? WHERE tg_id = ?", (v, tg_id))

def get_user_by_tg(tg_id):
    res = db_execute("SELECT tg_id, phone, verified, first_name, last_name, username FROM users WHERE tg_id = ?", (tg_id,), fetch=True)
    if res:
        tg_id, phone, verified, first_name, last_name, username = res[0]
        return {"tg_id": tg_id, "phone": phone, "verified": verified, "first_name": first_name, "last_name": last_name, "username": username}
    return None

def get_products_by_category(cat):
    return db_execute("SELECT code, title, price_tjs, diamonds, description FROM products WHERE category = ?", (cat,), fetch=True)

def get_product_by_code(code):
    res = db_execute("SELECT code, title, price_tjs, diamonds, description FROM products WHERE code = ?", (code,), fetch=True)
    return res[0] if res else None

def add_to_cart_db(tg_id, product_code, qty=1):
    res = db_execute("SELECT id, qty FROM cart WHERE tg_id = ? AND product_code = ?", (tg_id, product_code), fetch=True)
    if res:
        cid, oldq = res[0]
        db_execute("UPDATE cart SET qty = ? WHERE id = ?", (oldq + qty, cid))
    else:
        db_execute("INSERT INTO cart (tg_id, product_code, qty) VALUES (?, ?, ?)", (tg_id, product_code, qty))

def remove_from_cart_db(tg_id, product_code=None):
    if product_code:
        db_execute("DELETE FROM cart WHERE tg_id = ? AND product_code = ?", (tg_id, product_code))
    else:
        db_execute("DELETE FROM cart WHERE tg_id = ?", (tg_id,))

def get_cart_items(tg_id):
    res = db_execute("SELECT product_code, qty FROM cart WHERE tg_id = ?", (tg_id,), fetch=True)
    return res

def add_to_wishlist_db(tg_id, product_code):
    res = db_execute("SELECT id FROM wishlist WHERE tg_id = ? AND product_code = ?", (tg_id, product_code), fetch=True)
    if not res:
        db_execute("INSERT INTO wishlist (tg_id, product_code) VALUES (?, ?)", (tg_id, product_code))

def remove_from_wishlist_db(tg_id, product_code=None):
    if product_code:
        db_execute("DELETE FROM wishlist WHERE tg_id = ? AND product_code = ?", (tg_id, product_code))
    else:
        db_execute("DELETE FROM wishlist WHERE tg_id = ?", (tg_id,))

def get_wishlist_items(tg_id):
    return db_execute("SELECT product_code FROM wishlist WHERE tg_id = ?", (tg_id,), fetch=True)

def create_order_db(tg_id, order_text, game_id):
    ts = int(time.time())
    db_execute("INSERT INTO orders (tg_id, order_text, game_id, created_at) VALUES (?, ?, ?, ?)", (tg_id, order_text, game_id, ts))
    res = db_execute("SELECT id FROM orders WHERE tg_id = ? ORDER BY id DESC LIMIT 1", (tg_id,), fetch=True)
    return res[0][0] if res else None

def set_order_receipt(order_id, file_id):
    db_execute("UPDATE orders SET receipt_file_id = ? WHERE id = ?", (file_id, order_id))

def set_order_status(order_id, status):
    db_execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))

def get_all_orders():
    return db_execute("SELECT id, tg_id, order_text, game_id, status, created_at, receipt_file_id FROM orders ORDER BY created_at DESC", fetch=True)

def get_order(order_id):
    res = db_execute("SELECT id, tg_id, order_text, game_id, status, created_at, receipt_file_id FROM orders WHERE id = ?", (order_id,), fetch=True)
    return res[0] if res else None

def get_all_users():
    return db_execute("SELECT tg_id, phone, verified, first_name, last_name, username FROM users", fetch=True)

# ---------- Message text helpers ----------
def cart_summary_text(tg_id):
    items = get_cart_items(tg_id)
    if not items:
        return "Сабад холӣ аст."
    lines = []
    total = 0
    for code, qty in items:
        prod = get_product_by_code(code)
        if prod:
            _, title, price_tjs, diamonds, desc = prod
            price = price_tjs if price_tjs else 0
            lines.append(f"{title} x{qty} — {price} TJS each")
            total += price * qty
    lines.append(f"\nҶамъ: {total} TJS")
    return "\n".join(lines)

# ---------- Handlers ----------
@bot.message_handler(commands=['start'])
def handle_start(message):
    add_user_if_not_exists(message.from_user)
    tg_id = message.from_user.id
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📱 Фиристони рақам", request_contact=True))
    kb.add("Ворид кардан бо рақам (фаришта)")
    kb.add("❌ Бекор")
    bot.send_message(tg_id, "Салом! Лутфан рақами телефон ё рақамро ворид кунед. (Формат: танҳо рақамҳо, бе ҳарф)", reply_markup=kb)
    set_state(tg_id, "await_phone")

@bot.message_handler(content_types=['contact', 'text'])
def handle_contact_or_text(message):
    tg_id = message.from_user.id
    state = get_state(tg_id)
    text = message.text or ""

    if message.content_type == 'contact':
        phone = message.contact.phone_number
        phone_digits = re.sub(r'\D', '', phone)
        set_user_phone(tg_id, phone_digits, verified=0)
        total = sum(int(d) for d in phone_digits) + 7
        expected = str(total)
        set_state(tg_id, "await_verification", expected=expected, tmp={"phone": phone_digits})
        bot.send_message(tg_id, f"Барои амният, натиҷаи санҷиши хурдро ворид кунед: ҷамъ(ҳар рақам) + 7 = ?\n(Натиҷа танҳо рақам бошад)")
        return

    # state: await_phone
    if state['step'] == "await_phone":
        phone_digits = re.sub(r'\D', '', text)
        if not phone_digits:
            bot.send_message(tg_id, "Рақам ё контакт дохил нашуд. Лутфан танҳо рақам ворид кунед.")
            return
        if len(phone_digits) < 10 or len(phone_digits) > 12:
            bot.send_message(tg_id, "Рақами шумо бояд танҳо рақам бошад ва дарозӣ байни 10 ва 12 рақам бошад. Лутфан дубора ворид кунед.")
            return
        set_user_phone(tg_id, phone_digits, verified=0)
        total = sum(int(d) for d in phone_digits) + 7
        expected = str(total)
        set_state(tg_id, "await_verification", expected=expected, tmp={"phone": phone_digits})
        bot.send_message(tg_id, "Санҷиш: суммияи рақамҳо + 7 = ?\nЛутфан натиҷаро ҳамчун рақам ворид кунед.")
        return

    # state: await_verification
    if state['step'] == "await_verification":
        answer = re.sub(r'\D', '', text)
        if not answer:
            bot.send_message(tg_id, "Лутфан танҳо рақам ворид кунед (бе ҳарф).")
            return
        if answer == state['expected']:
            set_user_verified(tg_id, 1)
            add_user_if_not_exists(message.from_user)
            bot.send_message(tg_id, "Шуморо тафтиш кардем — хуб! Хуш омадед ба менюи асосӣ.", reply_markup=main_menu_keyboard(tg_id))
            clear_state(tg_id)
            return
        else:
            bot.send_message(tg_id, "Натиҷаи санҷиш нодуруст. Лутфан дубора кӯшиш кунед ё бо занг/контакт фиристед.")
            return

    # main menu text handlers
    if text == "🛒 Мағоза" or text.lower() == "мағоза":
        bot.send_message(tg_id, "Мағоза — интихоб кунед:", reply_markup=shop_menu_kb())
        return

    if text == "🧺 Сабад" or text.lower() == "сабад":
        summary = cart_summary_text(tg_id)
        bot.send_message(tg_id, f"Сабад:\n\n{summary}", reply_markup=types.ReplyKeyboardRemove())
        bot.send_message(tg_id, "Амалиётҳо:", reply_markup=cart_item_kb())
        return

    if text == "💖 Дилхоҳо" or text.lower() == "дилхоҳо":
        items = get_wishlist_items(tg_id)
        if not items:
            bot.send_message(tg_id, "Дилҳо холӣ аст.", reply_markup=main_menu_keyboard(tg_id))
            return
        for (code,) in items:
            prod = get_product_by_code(code)
            if prod:
                _, title, price_tjs, diamonds, desc = prod
                bot.send_message(tg_id, f"{title}\n{desc}", reply_markup=wishlist_item_kb(code))
        return

    if text == "ℹ️ Маълумот" or text.lower() == "маълумот":
        bot.send_message(tg_id, "Ин бот барои фурӯши алмаз ва воучерҳо сохта шудааст.\nAdmin: " + ADMIN_INSTAGRAM, reply_markup=main_menu_keyboard(tg_id))
        return

    if text == "👤 Профили админ" or text.lower() == "профили админ":
        u = get_user_by_tg(tg_id)
        phone = u['phone'] if u else None
        verified = u['verified'] if u else 0
        txt = f"Профил:\nID Telegram: {tg_id}\nНом: {message.from_user.first_name or '-'}\nUsername: @{message.from_user.username or '-'}\nPhone: {phone or '-'}\nVerified: {'Ҳа' if verified else 'Не'}\n\nИнстаграми админ: {ADMIN_INSTAGRAM}"
        bot.send_message(tg_id, txt, reply_markup=main_menu_keyboard(tg_id))
        return

    if text == "🛠️ Панели админ" or text.lower() == "панели админ":
        is_admin = (tg_id == ADMIN_ID)
        bot.send_message(tg_id, "Панели админ:", reply_markup=admin_panel_kb(is_admin))
        return

    # catch-all
    bot.send_message(tg_id, "Номуайян — лутфан менюеро интихоб кунед ё /start фишоред.", reply_markup=main_menu_keyboard(tg_id))

# ---------- Callbacks ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    tg_id = call.from_user.id
    data = call.data

    if data in ("back_to_main", "shop_menu_back"):
        try:
            bot.edit_message_text("Баргашт ба менюи асосӣ.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(tg_id, "Менюи асосӣ:", reply_markup=main_menu_keyboard(tg_id))
        return

    if data == "shop_diamond":
        try:
            bot.edit_message_text("Алмаз — интихоб кунед:", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(tg_id, "Пакетҳоро интихоб кунед:", reply_markup=diamonds_kb())
        return

    if data == "shop_voucher":
        try:
            bot.edit_message_text("Воучер — интихоб кунед:", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(tg_id, "Воучерҳоро интихоб кунед:", reply_markup=vouchers_kb())
        return

    if data.startswith("prod_select:"):
        code = data.split(":", 1)[1]
        prod = get_product_by_code(code)
        if prod:
            _, title, price_tjs, diamonds, desc = prod
            txt = f"{title}\n{desc}\n\nНарх: {price_tjs} TJS\n{diamonds}💎"
            try:
                bot.edit_message_text(txt, chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception:
                bot.send_message(tg_id, txt)
            bot.send_message(tg_id, "Интихоб кунед:", reply_markup=product_action_kb(code))
        else:
            bot.answer_callback_query(call.id, "Маҳсулот ёфт нашуд.")
        return

    if data.startswith("add_cart:"):
        code = data.split(":", 1)[1]
        add_to_cart_db(tg_id, code)
        bot.answer_callback_query(call.id, "Илова шуд ба сабад.")
        bot.send_message(tg_id, "Маҳсулот ба сабад илова шуд.", reply_markup=main_menu_keyboard(tg_id))
        return

    if data.startswith("add_wish:"):
        code = data.split(":", 1)[1]
        add_to_wishlist_db(tg_id, code)
        bot.answer_callback_query(call.id, "Илова шуд ба дилхоҳо.")
        bot.send_message(tg_id, "Маҳсулот ба дилхоҳо илова шуд.", reply_markup=main_menu_keyboard(tg_id))
        return

    if data.startswith("wish_to_cart:"):
        code = data.split(":", 1)[1]
        add_to_cart_db(tg_id, code)
        remove_from_wishlist_db(tg_id, code)
        bot.answer_callback_query(call.id, "Аз дилхоҳо ба сабад илова шуд.")
        bot.send_message(tg_id, "Аз дилхоҳо ба сабад илова шуд.", reply_markup=main_menu_keyboard(tg_id))
        return

    if data.startswith("wish_clear_item:"):
        code = data.split(":", 1)[1]
        remove_from_wishlist_db(tg_id, code)
        bot.answer_callback_query(call.id, "Пок карда шуд.")
        bot.send_message(tg_id, "Маҳсулот аз дилхоҳо пок карда шуд.", reply_markup=main_menu_keyboard(tg_id))
        return

    if data == "cart_clear":
        remove_from_cart_db(tg_id)
        bot.answer_callback_query(call.id, "Сабад пок шуд.")
        bot.send_message(tg_id, "Сабад пок карда шуд.", reply_markup=main_menu_keyboard(tg_id))
        return

    if data == "order_start":
        items = get_cart_items(tg_id)
        if not items:
            bot.answer_callback_query(call.id, "Сабад холӣ аст.")
            bot.send_message(tg_id, "Сабад холӣ аст.", reply_markup=main_menu_keyboard(tg_id))
            return
        set_state(tg_id, "await_game_id", tmp={"cart": items})
        bot.send_message(tg_id, "Лутфан ID-и бозиро ворид кунед (танҳо рақам; 10-12 рақам):", reply_markup=types.ReplyKeyboardRemove())
        return

    if data == "admin_users":
        if tg_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Фақат админ.")
            return
        users = get_all_users()
        txt = "Рӯйхати корбарон:\n\n"
        for u in users:
            uid, phone, verified, first, last, username = u
            txt += f"TG ID: {uid} — {first or ''} @{username or ''} — phone: {phone or '-'} — verified: {'Ҳа' if verified else 'Не'}\n"
        bot.send_message(tg_id, txt)
        return

    if data == "admin_orders":
        if tg_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Фақат админ.")
            return
        orders = get_all_orders()
        if not orders:
            bot.send_message(tg_id, "Фармоишҳо вуҷуд надоранд.")
            return
        for ord_row in orders:
            oid, u_tg, order_text, game_id, status, created_at, receipt = ord_row
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))
            txt = f"Order #{oid}\nUser: {u_tg}\nGameID: {game_id}\nStatus: {status}\nTime: {t}\n\n{order_text}\nReceipt: {'Ҳаст' if receipt else 'Не'}"
            bot.send_message(tg_id, txt, reply_markup=admin_order_action_kb(oid))
        return

    if data == "admin_broadcast":
        if tg_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Фақат админ.")
            return
        set_state(tg_id, "admin_broadcast_prepare")
        bot.send_message(tg_id, "Лутфан матни паём барои фиристодан ба ҳамаи корбаронро нависед.")
        return

    if data.startswith("admin_accept:"):
        if tg_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Фақат админ.")
            return
        oid = int(data.split(":",1)[1])
        order = get_order(oid)
        if not order:
            bot.answer_callback_query(call.id, "Order not found.")
            return
        user_tg = order[1]
        set_order_status(oid, "accepted")
        bot.send_message(user_tg, "✅ Маълумот: маҳсулот ба ҳисоби шумо фиристода шуд.")
        bot.answer_callback_query(call.id, f"Order #{oid} қабул шуд.")
        return

    if data.startswith("admin_reject:"):
        if tg_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Фақат админ.")
            return
        oid = int(data.split(":",1)[1])
        order = get_order(oid)
        if not order:
            bot.answer_callback_query(call.id, "Order not found.")
            return
        user_tg = order[1]
        set_order_status(oid, "rejected")
        bot.send_message(user_tg, "❌ Фармоиш рад карда шуд. Пардохт анҷом дода нашудааст. Агар мушкилот пеш омада бошад ба админ тамос гиред.")
        bot.answer_callback_query(call.id, f"Order #{oid} рад карда шуд.")
        return

    bot.answer_callback_query(call.id, "Амалиёт иҷро шуд.")

# ---------- Game ID / Order flow ----------
@bot.message_handler(func=lambda m: get_state(m.from_user.id)['step'] == "await_game_id", content_types=['text'])
def handle_game_id(message):
    tg_id = message.from_user.id
    text = message.text or ""
    digits = re.sub(r'\D', '', text)
    if not digits:
        bot.send_message(tg_id, "Лутфан фақат рақам ворид кунед (бе ҳарф).")
        return
    if len(digits) < 10 or len(digits) > 12:
        bot.send_message(tg_id, "ID бояд 10-12 рақам дошта бошад. Лутфан дубора ворид кунед.")
        return
    cart_items = get_cart_items(tg_id)
    if not cart_items:
        bot.send_message(tg_id, "Сабад холӣ аст.")
        clear_state(tg_id)
        return
    lines = []
    total = 0
    for code, qty in cart_items:
        prod = get_product_by_code(code)
        if prod:
            _, title, price_tjs, diamonds, desc = prod
            lines.append(f"{title} x{qty}")
            total += (price_tjs if price_tjs else 0) * qty
    order_text = ";\n".join(lines) + f"\nTotal: {total} TJS"
    order_id = create_order_db(tg_id, order_text, digits)
    remove_from_cart_db(tg_id)
    clear_state(tg_id)
    set_state(tg_id, "await_receipt", tmp={"order_id": order_id})
    pay_msg = ("Лутфан барои пардохт маблағро ба рақами корт: <b>577726627</b> пардохт кунед.\n"
               "Баъд аз пардохт як скриншот ё файлро ҳамчун квитансия фиристед.\n"
               f"Order ID: {order_id}\nGame ID: {digits}")
    bot.send_message(tg_id, pay_msg)
    bot.send_message(tg_id, "Ҳоло лутфан файл ё расм (скриншот) барои квитансия фиристед.")
    return

# ---------- Handle receipt ----------
@bot.message_handler(content_types=['photo', 'document'])
def handle_receipt(message):
    tg_id = message.from_user.id
    st = get_state(tg_id)
    if st['step'] != "await_receipt":
        bot.send_message(tg_id, "Ман интизор нестам, лутфан аз меню истифода кунед.")
        return
    order_id = st['tmp'].get("order_id")
    if not order_id:
        bot.send_message(tg_id, "Order маълум нест.")
        clear_state(tg_id)
        return
    file_id = None
    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
    else:
        file_id = message.document.file_id
    set_order_receipt(order_id, file_id)
    set_order_status(order_id, "waiting_admin")
    clear_state(tg_id)
    order = get_order(order_id)
    if order:
        oid, user_tg, order_text, game_id, status, created_at, receipt = order
        u = get_user_by_tg(user_tg)
        phone = u['phone'] if u else '-'
        profile_info = f"User: {user_tg}\nPhone: {phone}\nOrder: #{oid}\nGame ID: {game_id}\n\n{order_text}"
        if message.content_type == 'photo':
            bot.send_photo(ADMIN_ID, file_id, caption=profile_info, reply_markup=admin_order_action_kb(oid))
        else:
            bot.send_document(ADMIN_ID, file_id, caption=profile_info, reply_markup=admin_order_action_kb(oid))
        bot.send_message(tg_id, "Квитансия фиристода шуд ва ба админ равон гардид. Пас аз тасдиқиш шумо хабар мегиред.")
    else:
        bot.send_message(tg_id, "Хатогӣ дар эҷоди фармоиш. Лутфан бо админ тамос гиред.")
    return

# ---------- Admin broadcast ----------
@bot.message_handler(func=lambda m: get_state(m.from_user.id)['step'] == "admin_broadcast_prepare", content_types=['text', 'photo', 'document'])
def handle_admin_broadcast(message):
    tg_id = message.from_user.id
    if tg_id != ADMIN_ID:
        bot.send_message(tg_id, "Фақат админ.")
        clear_state(tg_id)
        return
    users = get_all_users()
    successes = 0
    fails = 0
    for u in users:
        user_tg = u[0]
        try:
            if message.content_type == 'text':
                bot.send_message(user_tg, f"Админ: {message.text}")
            elif message.content_type == 'photo':
                bot.send_photo(user_tg, message.photo[-1].file_id, caption=message.caption or "")
            elif message.content_type == 'document':
                bot.send_document(user_tg, message.document.file_id, caption=message.caption or "")
            successes += 1
            time.sleep(0.05)
        except Exception:
            fails += 1
    bot.send_message(tg_id, f"Фиристодам: success={successes}, fail={fails}")
    clear_state(tg_id)
    return

print("Bot is running...")

if __name__ == "__main__":
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("Stopped by user")
