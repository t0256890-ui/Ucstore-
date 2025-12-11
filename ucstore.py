#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram shop bot — пурра:
- Python + python-telegram-bot v20+
- SQLite барои нигоҳдорӣ (файли local: bot_data.db)
- Администратор: 5808918857 (аз шумо гирифта шудааст)
- Instagram админ дар профил нишон дода мешавад
"""

import logging
import sqlite3
import random
import time
from datetime import datetime

from telegram import (
    __version__ as pg_version,
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

# ==========================
# CONFIG
# ==========================
BOT_TOKEN = "8394642029:AAH50ltfmxyRRBnPm3QTa3LAtx8MeDSqBU0"
ADMIN_ID = 5808918857  # аз шумо гирифта шуд
ADMIN_INSTAGRAM = "https://www.instagram.com/garant_alestr?igsh=cTE4bnA3NW5ycHFs"
DB_FILE = "bot_data.db"

# card number for payment instruction
PAYMENT_CARD = "577726627"
PAYMENT_CONTACT = "+722773727"  # рақами барои паём ба админ дар паём барои фармоиш

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ==========================
# DATABASE HELPERS
# ==========================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # users: id (tg id), phone (text), first_name, last_name, created_at
    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            phone TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at INTEGER
        )"""
    )
    # products: id, category, code, title, price, meta (like diamonds count)
    c.execute(
        """CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            code TEXT,
            title TEXT,
            price INTEGER,
            meta TEXT
        )"""
    )
    # cart items: id, tg_id, product_id, added_at
    c.execute(
        """CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            product_id INTEGER,
            added_at INTEGER
        )"""
    )
    # hearts (wishlist)
    c.execute(
        """CREATE TABLE IF NOT EXISTS hearts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            product_id INTEGER,
            added_at INTEGER
        )"""
    )
    # orders
    c.execute(
        """CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            product_id INTEGER,
            game_id TEXT,
            status TEXT,
            created_at INTEGER,
            payment_file_id TEXT,
            payment_file_type TEXT
        )"""
    )
    conn.commit()
    # seed products if empty
    c.execute("SELECT COUNT(*) FROM products")
    count = c.fetchone()[0]
    if count == 0:
        seed_products = [
            # Almaz products (category 'almaz')
            ("almaz", "A1", "💎100+5", 10, "100+5"),
            ("almaz", "A2", "💎310+16", 28, "310+16"),
            ("almaz", "A3", "💎510+26", 45, "510+26"),
            ("almaz", "A4", "💎1060+53", 92, "1060+53"),
            ("almaz", "A5", "💎2180+216", 185, "2180+216"),
            ("almaz", "A6", "💎5600+560", 460, "5600+560"),
            # Voucher products (category 'voucher'), meta holds diamonds-cost mapping
            ("voucher", "V1", "Неделю - 450💎-17 см", 0, "week-450-17"),
            ("voucher", "V2", "Месяц-2600💎-97 см", 0, "month-2600-97"),
            ("voucher", "V3", "Лайт-90💎-7 см", 0, "lite-90-7"),
        ]
        c.executemany(
            "INSERT INTO products (category,code,title,price,meta) VALUES (?,?,?,?,?)",
            seed_products,
        )
        conn.commit()
    conn.close()


def db_execute(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    data = None
    if fetchone:
        data = c.fetchone()
    elif fetchall:
        data = c.fetchall()
    conn.commit()
    conn.close()
    return data


# ==========================
# UTIL
# ==========================
def main_menu_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("🛍️ Мағоза", callback_data="shop")],
        [InlineKeyboardButton("🧺 Сабад", callback_data="cart")],
        [InlineKeyboardButton("💖 Дилхоҳо", callback_data="hearts")],
        [InlineKeyboardButton("ℹ️ Маълумот", callback_data="info")],
        [InlineKeyboardButton("👤 Профили админ", callback_data="admin_profile")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("⚙️ Панели админ", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)


def shop_keyboard():
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Алмаз", callback_data="cat_almaz")],
            [InlineKeyboardButton("Воучер", callback_data="cat_voucher")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
        ]
    )
    return kb


def back_keyboard(callback="back_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Бозгашт", callback_data=callback)]])


def product_options_keyboard(product_id):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Илова ба сабад", callback_data=f"addcart:{product_id}"),
                InlineKeyboardButton("💖 Илова ба дилхоҳо", callback_data=f"addheart:{product_id}"),
            ],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="cat_back")],
        ]
    )


def cart_item_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 Фармоиш додан", callback_data="order_start")],
            [InlineKeyboardButton("🗑️ Пок кардан", callback_data="cart_clear")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
        ]
    )


def heart_item_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Илова ба сабад", callback_data="heart_to_cart")],
            [InlineKeyboardButton("🗑️ Пок кардан", callback_data="heart_clear")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
        ]
    )


def admin_panel_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Рӯйхати корбарон", callback_data="admin_users")],
            [InlineKeyboardButton("🧾 Фармоишҳо", callback_data="admin_orders")],
            [InlineKeyboardButton("✉️ Паём ба корбарон", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
        ]
    )


# ==========================
# HANDLERS
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id
    first = user.first_name or ""
    last = user.last_name or ""
    now = int(time.time())
    # save user if not exists
    row = db_execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,), fetchone=True)
    if not row:
        db_execute(
            "INSERT INTO users (tg_id, phone, first_name, last_name, created_at) VALUES (?,?,?,?,?)",
            (tg_id, None, first, last, now),
        )

    # Request contact (keyboard) — but also accept manual phone input
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("Расонам рақами телефон (Send contact)", request_contact=True)], ["Ворид кардани рақам дастӣ"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "Салом! Барои идома, лутфан рақами телефонатонро фиристед.\nШумо метавонед тугмаи 'Send contact'-ро пахш кунед ё рақамро дастӣ ворид кунед.",
        reply_markup=kb,
    )
    # set state expecting phone (we'll track with context.user_data)
    context.user_data["expect"] = "phone"


async def contact_or_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    text = None
    phone = None
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        text = update.message.text and update.message.text.strip()
        # try to extract digits
        if text:
            digits = "".join(ch for ch in text if ch.isdigit() or ch == "+")
            if len(digits) >= 5:
                phone = digits
    if not phone:
        await update.message.reply_text("Рақам ё контакт нодуруст аст. Лутфан дубора кӯшиш кунед.")
        return

    # store phone in DB
    db_execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, tg_id))
    # now create a simple math captcha: add/sub two numbers
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    op = random.choice(["+", "-"])
    if op == "+":
        answer = a + b
        qtext = f"Барои санҷиш, лутфан {a} + {b} = ? (фақат рақамҳо)"
    else:
        # ensure non-negative
        if a < b:
            a, b = b, a
        answer = a - b
        qtext = f"Барои санҷиш, лутфан {a} - {b} = ? (фақат рақамҳо)"
    context.user_data["captcha_answer"] = str(answer)
    await update.message.reply_text(qtext, reply_markup=ReplyKeyboardMarkup([["Бекор"]], resize_keyboard=True))


async def captcha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expect = context.user_data.get("expect")
    if expect != "phone":
        # ignore unless expecting captcha
        pass
    text = update.message.text.strip() if update.message.text else ""
    if text == "Бекор":
        await update.message.reply_text("Операсия бекор карда шуд. Нав оғоз кунед /start")
        return
    correct = context.user_data.get("captcha_answer")
    if not correct:
        await update.message.reply_text("Навсозӣ зарур аст. Лутфан /start занед.")
        return
    if text == correct:
        # success, show main menu
        tg_id = update.effective_user.id
        is_admin = tg_id == ADMIN_ID
        await update.message.reply_text(
            "Санҷиш бомуваффақият гузашт. Хуш омадед!",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
        # clear expect
        context.user_data.pop("expect", None)
        context.user_data.pop("captcha_answer", None)
    else:
        await update.message.reply_text("Ҷавоб нодуруст. Лутфан дубора /start кунед ва рақамро такрор фиристед.")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    tg_id = user.id

    if data == "back_main":
        await query.edit_message_text("Менюи асосӣ:", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
        return

    if data == "shop":
        await query.edit_message_text("Мағоза — интихоб кунед:", reply_markup=shop_keyboard())
        return

    if data == "cat_almaz":
        # list almaz products
        rows = db_execute("SELECT id,title,price,meta FROM products WHERE category = 'almaz'", fetchall=True)
        text = "Алмаз — интихоб кунед маҳсулот:\n\n"
        kb = InlineKeyboardMarkup([])
        for r in rows:
            pid, title, price, meta = r[0], r[1], r[2], r[3]
            text += f"{title} — {price} TJS\n"
            kb.add(InlineKeyboardButton(title + f" — {price}TJS", callback_data=f"product:{pid}"))
        kb.add(InlineKeyboardButton("⬅️ Бозгашт", callback_data="shop"))
        await query.edit_message_text(text, reply_markup=kb)
        return

    if data == "cat_voucher":
        rows = db_execute("SELECT id,title,price,meta FROM products WHERE category = 'voucher'", fetchall=True)
        text = "Воучер — интихоб кунед:\n\n"
        kb = InlineKeyboardMarkup([])
        for r in rows:
            pid, title = r[0], r[1], r[2]
            text += f"{title}\n"
            kb.add(InlineKeyboardButton(title, callback_data=f"product:{pid}"))
        kb.add(InlineKeyboardButton("⬅️ Бозгашт", callback_data="shop"))
        await query.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("product:"):
        pid = int(data.split(":", 1)[1])
        p = db_execute("SELECT title,price,meta FROM products WHERE id = ?", (pid,), fetchone=True)
        if not p:
            await query.edit_message_text("Маҳсулот ёфт нашуд.", reply_markup=shop_keyboard())
            return
        title, price, meta = p
        await query.edit_message_text(f"{title}\nНархи: {price} TJS\n\nИнтихоби амал:", reply_markup=product_options_keyboard(pid))
        return

    if data.startswith("addcart:"):
        pid = int(data.split(":", 1)[1])
        db_execute("INSERT INTO cart (tg_id, product_id, added_at) VALUES (?,?,?)", (tg_id, pid, int(time.time())))
        await query.edit_message_text("Маҳсулот ба сабад илова шуд.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
        return

    if data.startswith("addheart:"):
        pid = int(data.split(":", 1)[1])
        db_execute("INSERT INTO hearts (tg_id, product_id, added_at) VALUES (?,?,?)", (tg_id, pid, int(time.time())))
        await query.edit_message_text("Маҳсулот ба дилхоҳо (wishlist) илова шуд.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
        return

    if data == "cart":
        rows = db_execute("SELECT c.id,p.title,p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.tg_id = ?", (tg_id,), fetchall=True)
        if not rows:
            await query.edit_message_text("Сабад холӣ аст.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
            return
        text = "Маҳсулотҳои дар сабад:\n\n"
        total = 0
        for r in rows:
            cid, title, price = r
            text += f"- {title} — {price} TJS\n"
            total += price
        text += f"\nҲамагӣ: {total} TJS"
        await query.edit_message_text(text, reply_markup=cart_item_keyboard())
        return

    if data == "hearts":
        rows = db_execute("SELECT h.id,p.title,p.price FROM hearts h JOIN products p ON h.product_id=p.id WHERE h.tg_id = ?", (tg_id,), fetchall=True)
        if not rows:
            await query.edit_message_text("Дилхоҳо холӣ аст.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
            return
        text = "Маҳсулотҳои дар дилхоҳо:\n\n"
        for r in rows:
            hid, title, price = r
            text += f"- {title} — {price} TJS\n"
        await query.edit_message_text(text, reply_markup=heart_item_keyboard())
        return

    if data == "cat_back":
        await query.edit_message_text("Мағоза — интихоб кунед:", reply_markup=shop_keyboard())
        return

    if data == "cart_clear":
        db_execute("DELETE FROM cart WHERE tg_id = ?", (tg_id,))
        await query.edit_message_text("Сабад пок карда шуд.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
        return

    if data == "heart_clear":
        db_execute("DELETE FROM hearts WHERE tg_id = ?", (tg_id,))
        await query.edit_message_text("Дилхоҳо пок карда шуд.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
        return

    if data == "heart_to_cart":
        # move all hearts to cart
        items = db_execute("SELECT product_id FROM hearts WHERE tg_id = ?", (tg_id,), fetchall=True)
        if not items:
            await query.edit_message_text("Дилхоҳо холӣ.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
            return
        for it in items:
            pid = it[0]
            db_execute("INSERT INTO cart (tg_id, product_id, added_at) VALUES (?,?,?)", (tg_id, pid, int(time.time())))
        db_execute("DELETE FROM hearts WHERE tg_id = ?", (tg_id,))
        await query.edit_message_text("Ҳамаи маҳсулотҳо ба сабад интиқол ёфтанд.", reply_markup=main_menu_keyboard(is_admin=(tg_id == ADMIN_ID)))
        return

    if data == "order_start":
        # Expect Game/ID from user — ask for numeric ID
        await query.edit_message_text("Лутфан ID-и бозиро ворид кунед (фаqat рақамҳо):", reply_markup=back_keyboard("cart"))
        # set state
        context.user_data["expect_order_game_id"] = True
        return

    if data == "admin_profile":
        rows = db_execute("SELECT first_name, last_name, phone FROM users WHERE tg_id = ?", (ADMIN_ID,), fetchone=True)
        admin_info = f"Admin: {ADMIN_ID}\nInstagram: {ADMIN_INSTAGRAM}"
        await query.edit_message_text(admin_info, reply_markup=back_keyboard())
        return

    if data == "info":
        info_text = "Ин бот барои харид ва идораи фармоишҳо сохта шудааст.\n\nДастур: /start барои оғоз."
        await query.edit_message_text(info_text, reply_markup=back_keyboard())
        return

    if data == "admin_panel":
        if tg_id != ADMIN_ID:
            await query.edit_message_text("Шумо админ нестед.")
            return
        await query.edit_message_text("Панели админ:", reply_markup=admin_panel_keyboard())
        return

    # Admin panel callbacks
    if data == "admin_users":
        if tg_id != ADMIN_ID:
            await query.edit_message_text("Рузӣ нест.")
            return
        users = db_execute("SELECT tg_id,first_name,last_name,phone,created_at FROM users ORDER BY created_at DESC", fetchall=True)
        text = "Рӯйхати корбарон:\n\n"
        for u in users:
            uid, fn, ln, phone, created = u
            created_s = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
            text += f"ID: {uid} — {fn or ''} {ln or ''} — {phone or '-'} — {created_s}\n"
        await query.edit_message_text(text or "Корбарон вуҷуд надоранд.", reply_markup=back_keyboard("admin_panel"))
        return

    if data == "admin_orders":
        if tg_id != ADMIN_ID:
            await query.edit_message_text("Дастрасӣ нест.")
            return
        orders = db_execute(
            "SELECT o.id,o.tg_id,o.product_id,o.status,o.created_at,p.title FROM orders o LEFT JOIN products p ON o.product_id=p.id ORDER BY o.created_at DESC",
            fetchall=True,
        )
        if not orders:
            await query.edit_message_text("Фармоишҳо вуҷуд надоранд.", reply_markup=back_keyboard("admin_panel"))
            return
        text = "Фармоишҳо:\n\n"
        for o in orders:
            oid, uid, pid, status, created, title = o
            created_s = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
            text += f"#{oid} — User:{uid} — {title} — {status} — {created_s}\n"
        await query.edit_message_text(text, reply_markup=back_keyboard("admin_panel"))
        return

    if data == "admin_broadcast":
        if tg_id != ADMIN_ID:
            await query.edit_message_text("Дастрасӣ нест.")
            return
        await query.edit_message_text("Лутфан матни паём ба ҳамаи корбаронро фиристед. (Матни оддӣ)", reply_markup=back_keyboard("admin_panel"))
        context.user_data["expect_broadcast"] = True
        return

    # Accept/Reject order callbacks (admin action forwarded when payment file is sent)
    if data.startswith("admin_accept:") or data.startswith("admin_reject:"):
        if tg_id != ADMIN_ID:
            await query.edit_message_text("Дастрасӣ нест.")
            return
        parts = data.split(":")
        action = parts[0].split("_")[1] if "_" in parts[0] else parts[0].split("admin_")[1]
        order_id = int(parts[1])
        order = db_execute("SELECT tg_id, product_id FROM orders WHERE id = ?", (order_id,), fetchone=True)
        if not order:
            await query.edit_message_text("Фармоиш ёфт нашуд.", reply_markup=back_keyboard("admin_panel"))
            return
        user_id, product_id = order
        product = db_execute("SELECT title FROM products WHERE id = ?", (product_id,), fetchone=True)
        product_title = product[0] if product else "Маҳсулот"
        if data.startswith("admin_accept:"):
            # mark accepted
            db_execute("UPDATE orders SET status = ? WHERE id = ?", ("accepted", order_id))
            try:
                await context.bot.send_message(user_id, f"Маҳсулот ({product_title}) ба ҳисоби шумо фиристода шуд.")
            except Exception as e:
                logger.exception("Failed to send accept msg to user")
            await query.edit_message_text(f"Фармоиш #{order_id} қабул шуд.", reply_markup=back_keyboard("admin_panel"))
        else:
            db_execute("UPDATE orders SET status = ? WHERE id = ?", ("rejected", order_id))
            try:
                await context.bot.send_message(user_id, "Фармоиш рад карда шуд — пардохт анҷом дода нашуд. Агар савол бошад, ба админ муроҷиат кунед.")
            except Exception as e:
                logger.exception("Failed to send reject msg to user")
            await query.edit_message_text(f"Фармоиш #{order_id} рад шуд.", reply_markup=back_keyboard("admin_panel"))
        return

    # Fallback
    await query.edit_message_text("Амалиёт маълум нест.", reply_markup=back_keyboard())


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id
    text = update.message.text.strip() if update.message.text else ""

    # Admin broadcast flow
    if context.user_data.get("expect_broadcast") and tg_id == ADMIN_ID:
        # send to all users
        users = db_execute("SELECT tg_id FROM users", fetchall=True)
        count = 0
        for u in users:
            uid = u[0]
            try:
                await context.bot.send_message(uid, f"🔔 Хабар аз админ:\n\n{text}")
                count += 1
            except Exception:
                pass
        await update.message.reply_text(f"Паём ба {count} корбар фиристода шуд.", reply_markup=admin_panel_keyboard())
        context.user_data.pop("expect_broadcast", None)
        return

    # Expecting order game ID
    if context.user_data.get("expect_order_game_id"):
        # verify digits only
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            await update.message.reply_text("ID нодуруст аст. Танҳо рақамҳоро ворид кунед.")
            return
        game_id = digits
        # create order(s) for all items in cart
        cart_items = db_execute("SELECT product_id FROM cart WHERE tg_id = ?", (tg_id,), fetchall=True)
        if not cart_items:
            await update.message.reply_text("Сабад холӣ аст.", reply_markup=main_menu_keyboard(is_admin=(tg_id==ADMIN_ID)))
            context.user_data.pop("expect_order_game_id", None)
            return
        created = int(time.time())
        for item in cart_items:
            pid = item[0]
            db_execute(
                "INSERT INTO orders (tg_id,product_id,game_id,status,created_at) VALUES (?,?,?,?,?)",
                (tg_id, pid, game_id, "pending_payment", created),
            )
        # clear cart after creating orders
        db_execute("DELETE FROM cart WHERE tg_id = ?", (tg_id,))
        await update.message.reply_text(
            f"Ҳоло тасвири квитансия ё файлро ҳамчун исботи пардохт бор кунед.\n\nРақами корт: {PAYMENT_CARD}\nБа ин рақам пардохт карда, файл/скриншот фиристед.\n(Ҳамин паём ба админ фиристонида мешавад.)",
            reply_markup=back_keyboard(),
        )
        # set state to expect payment file
        context.user_data["expect_payment_file"] = True
        context.user_data.pop("expect_order_game_id", None)
        return

    # If expecting phone captcha answer, handle like captcha (we set expect earlier in start flow)
    if context.user_data.get("captcha_answer"):
        # reuse captcha handler style
        if text == context.user_data.get("captcha_answer"):
            is_admin = tg_id == ADMIN_ID
            await update.message.reply_text("Санҷиш бомуваффақият гузашт.", reply_markup=main_menu_keyboard(is_admin=is_admin))
            context.user_data.pop("captcha_answer", None)
            context.user_data.pop("expect", None)
        else:
            await update.message.reply_text("Ҷавоб нодуруст. Лутфан /start ро боз занед ва такрор кунед.")
        return

    # If expecting broadcast or others handled above, else general help
    await update.message.reply_text("Ман ин паёмро фаҳмидам, аммо барои идома аз меню истифода кунед. /start")


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle photo or document uploaded as payment proof.
    Forward to admin with buttons Accept/Reject.
    """
    user = update.effective_user
    tg_id = user.id

    if not context.user_data.get("expect_payment_file"):
        await update.message.reply_text("Ман дар ҳолати интизори файли пардохт нестам. Агар фармоиш доред - иваз /start.")
        return

    # find the latest pending orders of this user (we created them earlier)
    orders = db_execute("SELECT id,product_id FROM orders WHERE tg_id = ? AND status = 'pending_payment' ORDER BY created_at DESC", (tg_id,), fetchall=True)
    if not orders:
        await update.message.reply_text("Фармоишҳо ёфт нашуд. Лутфан дубора санҷед.", reply_markup=main_menu_keyboard(is_admin=(tg_id==ADMIN_ID)))
        context.user_data.pop("expect_payment_file", None)
        return

    # forward file to admin + send order info and inline accept/reject buttons
    # handle photo vs document
    file_caption = f"Фармоиш: User: {tg_id}\n"
    # We'll attach order ids and game id
    order_ids = [str(o[0]) for o in orders]
    first_order_id = order_ids[0]
    game_id = db_execute("SELECT game_id FROM orders WHERE id = ?", (orders[0][0],), fetchone=True)[0]
    file_caption += f"Order IDs: {', '.join(order_ids)}\nGame ID: {game_id}\nПрофил: @{user.username if user.username else '-'}\n"
    # when user sends photo
    if update.message.photo:
        ph = update.message.photo[-1]  # best quality
        file_id = ph.file_id
        # forward to admin
        msg = await context.bot.send_photo(
            ADMIN_ID,
            photo=file_id,
            caption=file_caption,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✔️ Қабул", callback_data=f"admin_accept:{first_order_id}"),
                        InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject:{first_order_id}"),
                    ]
                ]
            ),
        )
    elif update.message.document:
        doc = update.message.document
        file_id = doc.file_id
        msg = await context.bot.send_document(
            ADMIN_ID,
            document=file_id,
            caption=file_caption,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✔️ Қабул", callback_data=f"admin_accept:{first_order_id}"),
                        InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject:{first_order_id}"),
                    ]
                ]
            ),
        )
    else:
        await update.message.reply_text("Файлро тасдиқ карда натавонистам. Лутфан тасвир ё ҳуҷҷат фиристед.")
        return

    # update orders with file info (store file_id in payment_file_id)
    for oid in order_ids:
        db_execute("UPDATE orders SET payment_file_id = ?, payment_file_type = ? WHERE id = ?", (file_id, "photo" if update.message.photo else "document", int(oid)))

    await update.message.reply_text("Файл гирифта шуд ва ба админ фиристода шуд. Ҳангоми тасдиқ админ ба шумо хабар медиҳад.")
    context.user_data.pop("expect_payment_file", None)


# error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


# ==========================
# MAIN
# ==========================
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    # contact / phone text or captcha
    app.add_handler(MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), contact_or_phone_handler), group=0)
    # Captcha answer (we'll allow text handler to process)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, captcha_handler), group=1)

    # CallbackQuery router
    app.add_handler(CallbackQueryHandler(callback_router))

    # File handler (photos/documents)
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, file_handler))

    # Admin broadcast and order flow messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler), group=2)

    app.add_error_handler(error_handler)

    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
