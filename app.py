import logging
import sqlite3
import asyncio
import threading
import os
import io
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, send_file
from PIL import Image, ImageDraw, ImageFont
import requests as req

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─────────────────────────────────────
# ΡΥΘΜΙΣΕΙΣ
# ─────────────────────────────────────
TOKEN = "8800151694:AAH3L3xHMI2JtXgbrTjzyoONgY-p89yBCnc"
ADMIN_ID = 7287706699
CHANNEL_ID = "-1004477491962"
BOT_USERNAME = "vamosprive_bot"
WEBAPP_URL = "https://vamosbot-production.up.railway.app"

DB_PATH = "/app/bot_database.db"
WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")

# ─────────────────────────────────────
# LOGGING
# ─────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────
flask_app = Flask(__name__, static_folder=WEBAPP_DIR)

# ─────────────────────────────────────
# DATABASE
# ─────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            photo_id    TEXT PRIMARY KEY,
            file_id     TEXT NOT NULL,
            caption     TEXT,
            created_at  TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS views (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id    TEXT NOT NULL,
            user_id     INTEGER NOT NULL,
            username    TEXT,
            first_name  TEXT,
            viewed_at   TEXT NOT NULL,
            UNIQUE(photo_id, user_id)
        )
    """)
    conn.commit()
    conn.close()

def save_photo(photo_id, file_id, caption=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO photos (photo_id, file_id, caption, created_at) VALUES (?, ?, ?, ?)",
        (photo_id, file_id, caption, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def get_photo(photo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM photos WHERE photo_id = ?", (photo_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def save_view(photo_id, user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO views (photo_id, user_id, username, first_name, viewed_at) VALUES (?, ?, ?, ?, ?)",
            (photo_id, user_id, username or "Κανένα", first_name or "Άγνωστος",
             datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        )
        conn.commit()
        is_new = True
    except sqlite3.IntegrityError:
        is_new = False
    conn.close()
    return is_new

def get_views(photo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, first_name, viewed_at FROM views WHERE photo_id = ?", (photo_id,))
    results = cursor.fetchall()
    conn.close()
    return results

def get_total_views(photo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM views WHERE photo_id = ?", (photo_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_photos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT photo_id, caption, created_at FROM photos ORDER BY created_at DESC")
    results = cursor.fetchall()
    conn.close()
    return results

def get_next_photo_id():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    count = cursor.fetchone()[0]
    conn.close()
    return f"photo_{count + 1}"

def is_admin(user_id):
    return user_id == ADMIN_ID

# ─────────────────────────────────────
# WATERMARK
# ─────────────────────────────────────
def add_watermark(image_bytes, username, user_id):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    watermark_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark_layer)

    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    watermark_text = f"@{username}  |  ID: {user_id}  |  {date_str}"

    font_size = max(20, int(width / 30))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding = 15
    x = width - text_width - padding
    y = height - text_height - padding

    draw.text((x + 2, y + 2), watermark_text, font=font, fill=(0, 0, 0, 180))
    draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 210))

    # Diagonal watermark
    txt_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_layer)
    diag_font_size = max(30, int(width / 15))
    try:
        diag_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", diag_font_size)
    except:
        diag_font = ImageFont.load_default()

    diag_text = f"@{username}"
    diag_bbox = txt_draw.textbbox((0, 0), diag_text, font=diag_font)
    diag_w = diag_bbox[2] - diag_bbox[0]
    diag_h = diag_bbox[3] - diag_bbox[1]
    txt_draw.text(((width - diag_w) // 2, (height - diag_h) // 2), diag_text, font=diag_font, fill=(255, 255, 255, 60))
    txt_layer = txt_layer.rotate(25, expand=False)

    combined = Image.alpha_composite(img, watermark_layer)
    combined = Image.alpha_composite(combined, txt_layer)

    output = io.BytesIO()
    combined.convert("RGB").save(output, format="JPEG", quality=90)
    output.seek(0)
    return output.read()

# ─────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────
@flask_app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")

@flask_app.route("/api/photo/<photo_id>")
def get_photo_api(photo_id):
    photo = get_photo(photo_id)
    if not photo:
        return jsonify({"error": "Φωτογραφία δεν βρέθηκε"}), 404
    return jsonify({
        "photo_id": photo[0],
        "caption": photo[2],
        "created_at": photo[3],
        "total_views": get_total_views(photo_id)
    })

@flask_app.route("/api/photo/<photo_id>/image")
def get_watermarked_photo(photo_id):
    photo = get_photo(photo_id)
    if not photo:
        return jsonify({"error": "Φωτογραφία δεν βρέθηκε"}), 404

    username = request.args.get("username", "unknown")
    user_id = request.args.get("user_id", "0")
    first_name = request.args.get("first_name", "Άγνωστος")

    save_view(photo_id, int(user_id), username, first_name)

    file_id = photo[1]
    try:
        file_info = req.get(f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}").json()
        file_path = file_info["result"]["file_path"]
        image_bytes = req.get(f"https://api.telegram.org/file/bot{TOKEN}/{file_path}").content
        watermarked = add_watermark(image_bytes, username, user_id)
        return send_file(io.BytesIO(watermarked), mimetype="image/jpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────
# TELEGRAM BOT HANDLERS
# ─────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if context.args:
        photo_id = context.args[0]
        photo = get_photo(photo_id)

        if photo:
            is_new = save_view(photo_id, user.id, user.username, user.first_name)
            total = get_total_views(photo_id)

            if is_new:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"👁️ *Νέα Θέαση!*\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"📸 Φωτό: `{photo_id}`\n"
                        f"👤 Όνομα: {user.first_name}\n"
                        f"🔖 Username: @{user.username or 'Κανένα'}\n"
                        f"🆔 User ID: `{user.id}`\n"
                        f"🕐 Ώρα: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                        f"👥 Σύνολο θεάσεων: *{total}*"
                    ),
                    parse_mode="Markdown"
                )

            # Κουμπί Mini App
            webapp_url = f"{WEBAPP_URL}/?photo_id={photo_id}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🖼️ Άνοιξε τη Φωτογραφία",
                    web_app=WebAppInfo(url=webapp_url)
                )]
            ])

            caption = photo[2] or "🔒 Πάτα το κουμπί για να δεις τη φωτογραφία!"
            await update.message.reply_text(
                f"*{caption}*\n\n👁️ Θεάσεις: {total}\n\n⬇️ Πάτα για να ανοίξεις:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Η φωτογραφία δεν βρέθηκε!")
    else:
        await update.message.reply_text(
            f"👋 Γεια σου *{user.first_name}*!\n\n📢 Πήγαινε στο κανάλι!\n👉 {CHANNEL_ID}",
            parse_mode="Markdown"
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Δεν έχεις δικαίωμα!")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id
    caption = update.message.caption or None
    photo_id = get_next_photo_id()

    save_photo(photo_id, file_id, caption)

    # Κουμπί στο κανάλι → πάει στο bot → bot ανοίγει Mini App
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔓 Δες τη φωτογραφία!",
            url=f"https://t.me/{BOT_USERNAME}?start={photo_id}"
        )]
    ])

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=(f"🖼️ *Νέα Φωτογραφία!*\n\n{caption or '🔒 Πάτα το κουμπί για να τη δεις!'}"),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    await update.message.reply_text(
        f"✅ *Στάλθηκε!*\n🆔 ID: `{photo_id}`\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Μόνο για admin!")
        return

    photos = get_all_photos()
    if not photos:
        await update.message.reply_text("📊 Δεν υπάρχουν φωτογραφίες ακόμα!")
        return

    msg = "📊 *ΣΤΑΤΙΣΤΙΚΑ*\n━━━━━━━━━━━━━━\n\n"
    total_all = 0
    for photo in photos:
        photo_id, caption, created_at = photo
        views = get_total_views(photo_id)
        total_all += views
        msg += f"📸 `{photo_id}`\n📝 {caption or 'Χωρίς caption'}\n📅 {created_at}\n👁️ *{views}*\n\n"
    msg += f"━━━━━━━━━━━━━━\n👁️ Σύνολο: *{total_all}*"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def viewers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Μόνο για admin!")
        return
    if not context.args:
        await update.message.reply_text("📌 Χρήση: `/viewers photo_1`", parse_mode="Markdown")
        return

    photo_id = context.args[0]
    photo = get_photo(photo_id)
    if not photo:
        await update.message.reply_text("❌ Δεν βρέθηκε!")
        return

    views = get_views(photo_id)
    if not views:
        await update.message.reply_text(f"👁️ Κανείς δεν έχει δει ακόμα!")
        return

    msg = f"👥 *{photo_id}* — {len(views)} θεάσεις\n━━━━━━━━━━━━━━\n\n"
    for v in views:
        user_id, username, first_name, viewed_at = v
        msg += f"👤 {first_name} | @{username or 'Κανένα'} | `{user_id}`\n🕐 {viewed_at}\n─────────\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def photos_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Μόνο για admin!")
        return

    photos = get_all_photos()
    if not photos:
        await update.message.reply_text("📸 Δεν υπάρχουν φωτογραφίες!")
        return

    msg = "📸 *ΛΙΣΤΑ ΦΩΤΟΓΡΑΦΙΩΝ*\n━━━━━━━━━━━━━━\n\n"
    for photo in photos:
        photo_id, caption, created_at = photo
        views = get_total_views(photo_id)
        msg += f"🆔 `{photo_id}` | 📅 {created_at} | 👁️ {views}\n📝 {caption or 'Χωρίς caption'}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text(f"ℹ️ Πήγαινε στο κανάλι!\n👉 {CHANNEL_ID}")
        return
    msg = (
        "🤖 *ΕΝΤΟΛΕΣ ADMIN*\n━━━━━━━━━━━━━━\n\n"
        "📸 Στείλε φωτό για να δημοσιευτεί\n"
        "📊 /stats\n👥 /viewers photo_1\n📋 /photos\n❓ /help"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ─────────────────────────────────────
# ΕΚΚΙΝΗΣΗ BOT ΣΕ THREAD
# ─────────────────────────────────────
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("viewers", viewers))
    app.add_handler(CommandHandler("photos", photos_list))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))

    logger.info("🤖 Bot ξεκίνησε!")
    app.run_polling()

# ─────────────────────────────────────
# MAIN
# ─────────────────────────────────────
if __name__ == "__main__":
    init_db()
    logger.info("✅ Database αρχικοποιήθηκε!")

    # Bot σε ξεχωριστό thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Flask server
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Web server στο port {port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False)
