# -*- coding: utf-8 -*-
"""
ربات پشتیبانی تلگرام
BOT_TOKEN  → توکنی که BotFather می‌دهد
ADMIN_ID   → آیدی عددی شما (از @userinfobot)
"""

import os
import json
import time
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from html import escape

from telegram import Update, ReactionTypeEmoji
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────── تنظیمات ───────────────────────────
BOT_TOKEN = os.environ.get("8784120583:AAHftJDUue1gYvCPRfKeC7fMuDfT9PMhk2E", "").strip()
ADMIN_ID_RAW = os.environ.get("71031452", "").strip()
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.lstrip("-").isdigit() else 0

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
MAX_REMEMBERED = 5000

# ─────────────────── ذخیره‌سازی ساده (JSON) ───────────────────
def load_db():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        db = {}
    db.setdefault("users", {})    # user_id -> {name, username, time}
    db.setdefault("msg_map", {})  # message_id (در چت مدیر) -> user_id
    db.setdefault("blocked", [])  # کاربران مسدودشده
    return db


DB = load_db()


def save_db():
    try:
        if len(DB["msg_map"]) > MAX_REMEMBERED:
            items = sorted(DB["msg_map"].items(), key=lambda kv: int(kv[0]))[-MAX_REMEMBERED:]
            DB["msg_map"] = dict(items)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DB, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        logger.warning("save failed: %s", exc)


def remember(admin_msg_id: int, user_id: int):
    DB["msg_map"][str(admin_msg_id)] = user_id
    save_db()


def who_is(admin_msg_id: int):
    v = DB["msg_map"].get(str(admin_msg_id))
    return int(v) if v is not None else None


def register_user(user):
    DB["users"][str(user.id)] = {
        "name": user.full_name,
        "username": user.username or "",
        "time": int(time.time()),
    }
    save_db()


# ─────────────────────── متن‌های ربات ───────────────────────
WELCOME = (
    "سلام! 👋\n"
    "به ربات ارتباط با مدیریت خوش آمدید.\n\n"
    "پیام خود را بنویسید یا عکس/فایل/ویس بفرستید تا برای مدیر ارسال شود؛ "
    "پاسخ از همین‌جا به شما می‌رسد. ✉️"
)

ADMIN_HELP = (
    "🛠 <b>راهنمای مدیر</b>\n\n"
    "پیام هر کاربر به صورت «کارت اطلاعات + خودِ پیام» برایتان می‌آید.\n"
    "برای پاسخ دادن فقط روی کارت یا روی پیامِ کاربر <b>Reply</b> کنید و جواب را بفرستید.\n\n"
    "<b>دستورات:</b>\n"
    "▫️ ریپلای + <code>/block</code> ← مسدود کردن کاربر\n"
    "▫️ ریپلای + <code>/unblock</code> ← رفع مسدودیت\n"
    "▫️ <code>/block 123456</code> ← مسدود با آیدی عددی\n"
    "▫️ ریپلای روی یک پیام + <code>/broadcast</code> ← ارسال آن به همه\n"
    "▫️ <code>/broadcast متن...</code> ← ارسال متن به همه\n"
    "▫️ <code>/stats</code> ← آمار کاربران"
)


async def react(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, emoji: str = "✅"):
    try:
        await context.bot.set_message_reaction(chat_id, message_id, ReactionTypeEmoji(emoji))
    except TelegramError:
        pass


# ───────────────────────── هندلرها ─────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(ADMIN_HELP, parse_mode="HTML")
    else:
        register_user(update.effective_user)
        await update.message.reply_text(WELCOME)


async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, msg = update.effective_user, update.message
    register_user(user)

    if user.id in DB["blocked"]:
        await msg.reply_text("⛔ متأسفانه حساب شما در این ربات مسدود است.")
        return

    uname = f"@{user.username}" if user.username else "—"
    info = (
        "📩 <b>پیام جدید از کاربر</b>\n"
        f"👤 نام: {escape(user.full_name)}\n"
        f"🆔 آیدی عددی: <code>{user.id}</code>\n"
        f"🔗 یوزرنیم: {escape(uname)}\n"
        f"💬 <a href=\"tg://user?id={user.id}\">باز کردن پروفایل</a>\n\n"
        "↩️ برای پاسخ، روی همین پیام یا پیامِ زیر Reply کنید."
    )
    try:
        card = await context.bot.send_message(ADMIN_ID, info, parse_mode="HTML")
        copied = await context.bot.copy_message(
            chat_id=ADMIN_ID, from_chat_id=user.id, message_id=msg.message_id
        )
        remember(card.message_id, user.id)
        remember(copied.message_id, user.id)
        await react(context, user.id, msg.message_id, "✅")
    except TelegramError as exc:
        logger.error("forward to admin failed: %s", exc)
        await msg.reply_text("⚠️ خطایی رخ داد؛ لطفاً کمی بعد دوباره تلاش کنید.")


async def on_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    replied = msg.reply_to_message

    if not replied:
        await msg.reply_text(ADMIN_HELP, parse_mode="HTML")
        return

    target = who_is(replied.message_id)
    if target is None:
        await msg.reply_text(
            "⚠️ این پیام به هیچ کاربری مرتبط نیست.\n"
            "روی کارت اطلاعات یا خودِ پیامِ کاربر Reply کنید."
        )
        return

    try:
        await context.bot.copy_message(
            chat_id=target, from_chat_id=ADMIN_ID, message_id=msg.message_id
        )
        await react(context, ADMIN_ID, msg.message_id, "✅")
    except TelegramError as exc:
        await msg.reply_text(f"❌ ارسال نشد: {exc.message}\n(شاید کاربر ربات را بلاک کرده است)")


def _target_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        t = who_is(msg.reply_to_message.message_id)
        if t:
            return t
    if context.args and context.args[0].lstrip("-").isdigit():
        return int(context.args[0])
    return None


async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    target = _target_from(update, context)
    if target is None:
        await update.message.reply_text(
            "روش استفاده:\n• ریپلای روی پیام کاربر + /block\n• /block 123456"
        )
        return
    if target == ADMIN_ID:
        await update.message.reply_text("😄 نمی‌توانید خودتان را مسدود کنید.")
        return
    if target not in DB["blocked"]:
        DB["blocked"].append(target)
        save_db()
    await update.message.reply_text(f"⛔ کاربر <code>{target}</code> مسدود شد.", parse_mode="HTML")


async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    target = _target_from(update, context)
    if target is None:
        await update.message.reply_text(
            "روش استفاده:\n• ریپلای روی پیام کاربر + /unblock\n• /unblock 123456"
        )
        return
    if target in DB["blocked"]:
        DB["blocked"].remove(target)
        save_db()
        await update.message.reply_text(f"✅ کاربر <code>{target}</code> رفع‌مسدودی شد.", parse_mode="HTML")
    else:
        await update.message.reply_text("این کاربر مسدود نبود.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"👥 کاربران: <b>{len(DB['users'])}</b>\n"
        f"⛔ مسدودشده: <b>{len(DB['blocked'])}</b>\n"
        f"🧠 پیام‌های به‌یادمانده: <b>{len(DB['msg_map'])}</b>",
        parse_mode="HTML",
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = update.message
    text = msg.text.partition(" ")[2].strip() if msg.text else ""

    if not msg.reply_to_message and not text:
        await msg.reply_text(
            "روش استفاده:\n• ریپلای روی یک پیام + /broadcast\n• /broadcast متن پیام"
        )
        return

    sent = failed = 0
    for uid in list(DB["users"].keys()):
        try:
            if msg.reply_to_message:
                await context.bot.copy_message(
                    chat_id=int(uid), from_chat_id=ADMIN_ID,
                    message_id=msg.reply_to_message.message_id,
                )
            else:
                await context.bot.send_message(
                    int(uid),
                    f"📢 <b>پیام همگانی مدیر:</b>\n\n{escape(text)}",
                    parse_mode="HTML",
                )
            sent += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.05)

    await msg.reply_text(f"📊 نتیجه ارسال همگانی:\n✅ موفق: {sent}\n❌ ناموفق: {failed}")


async def on_other_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(ADMIN_HELP, parse_mode="HTML")
    else:
        register_user(update.effective_user)
        await update.message.reply_text("پیامتان را به صورت متن، عکس، فایل یا ویس بفرستید ✉️")


# ─────────────── وب‌سرور کوچک برای Render (۲۴ ساعته آنلاین) ───────────────
def run_health_server():
    port = int(os.environ.get("PORT", "8080"))

    class Handler(BaseHTTPRequestHandler):
        def _ok(self):
            body = "Bot is running".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command == "GET":
                self.wfile.write(body)

        do_GET = _ok
        do_HEAD = _ok

        def log_message(self, *args):
            return

    logger.info("health server on port %s", port)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


# ─────────────────────────── اجرا ───────────────────────────
def main():
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("❌ متغیرهای محیطی BOT_TOKEN و ADMIN_ID را تنظیم کنید.")

    if os.environ.get("RENDER") or os.environ.get("PORT"):
        threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("block", cmd_block))
    app.add_handler(CommandHandler("unblock", cmd_unblock))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    base = filters.ChatType.PRIVATE & ~filters.COMMAND & ~filters.StatusUpdate.ALL
    app.add_handler(MessageHandler(base & filters.User(ADMIN_ID), on_admin_message))
    app.add_handler(MessageHandler(base & ~filters.User(ADMIN_ID), on_user_message))
    app.add_handler(MessageHandler(filters.COMMAND, on_other_command))

    logger.info("bot started (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()