import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─────────────────────────────────────
# ΡΥΘΜΙΣΕΙΣ - ΑΛΛΑΞΕ ΤΑ ΠΑΡΑΚΑΤΩ
# ─────────────────────────────────────
TOKEN = "8800151694:AAH3L3xHMI2JtXgbrTjzyoONgY-p89yBCnc"
ADMIN_ID = 7287706699
CHANNEL_ID = "-1004477491962"
BOT_USERNAME = "vamosprive_bot"

# ⚠️ Βάλε εδώ το δημόσιο HTTPS URL του server σου (π.χ. από ngrok ή VPS)
# Παράδειγμα ngrok: "https://abc123.ngrok.io"
# Παράδειγμα VPS:   "https://yourdomain.com"
WEBAPP_URL = "https://YOUR_DOMAIN_HERE"

# ─────────────────────────────────────
# LOGGING
# ─────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────
def init_db():
    conn = sqlite3.connect("bot_database.db")
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

# ─────────────────────────────────────
# DATABASE FUNCTIONS
# ─────────────────────────────────────
def save_photo(photo_id: str, file_id: str, caption: str = None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO photos (photo_id, file_id, caption, created_at) VALUES (?, ?, ?, ?)",
        (photo_id, file_id, caption, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def get_photo(photo_id: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM photos WHERE photo_id = ?", (photo_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def save_view(photo_id: str, user_id: int, username: str, first_name: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO views (photo_id, user_id, username, first_name, viewed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                photo_id,
                user_id,
                username or "Κανένα",
                first_name or "Άγνωστος",
                datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            )
        )
        conn.commit()
        is_new = True
    except sqlite3.IntegrityError:
        is_new = False
    conn.close()
    return is_new

def get_views(photo_id: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, first_name, viewed_at FROM views WHERE photo_id = ?",
        (photo_id,)
    )
    results = cursor.fetchall()
    conn.close()
    return results

def get_total_views(photo_id: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM views WHERE photo_id = ?", (photo_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_photos():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT photo_id, caption, created_at FROM photos ORDER BY created_at DESC")
    results = cursor.fetchall()
    conn.close()
    return results

def get_next_photo_id():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    count = cursor.fetchone()[0]
    conn.close()
    return f"photo_{count + 1}"

# ─────────────────────────────────────
# ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ
# ─────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ─────────────────────────────────────
# /start
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

            # Κουμπί που ανοίγει Mini App μέσα στο Telegram
            webapp_url = f"{WEBAPP_URL}/?photo_id={photo_id}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🖼️ Άνοιξε τη Φωτογραφία",
                    web_app=WebAppInfo(url=webapp_url)
                )]
            ])

            caption = photo[2] or "🔒 Πάτα το κουμπί για να δεις τη φωτογραφία!"

            await update.message.reply_text(
                f"*{caption}*\n\n"
                f"👁️ Συνολικές θεάσεις: {total}\n\n"
                f"⬇️ Πάτα το κουμπί για να ανοίξεις τη φωτογραφία:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❌ Η φωτογραφία δεν βρέθηκε ή έχει διαγραφεί!"
            )
    else:
        await update.message.reply_text(
            f"👋 Γεια σου *{user.first_name}*!\n\n"
            f"📢 Πήγαινε στο κανάλι για να δεις τις φωτογραφίες!\n"
            f"👉 {CHANNEL_ID}",
            parse_mode="Markdown"
        )

# ─────────────────────────────────────
# ADMIN: ΛΑΜΒΑΝΕΙ ΦΩΤΟ ΚΑΙ ΤΗΝ ΣΤΕΛΝΕΙ
# ─────────────────────────────────────
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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔓 Δες τη φωτογραφία!",
            url=f"https://t.me/{BOT_USERNAME}?start={photo_id}"
        )]
    ])

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=(
            f"🖼️ *Νέα Φωτογραφία!*\n\n"
            f"{caption or '🔒 Πάτα το κουμπί για να τη δεις!'}"
        ),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    await update.message.reply_text(
        f"✅ *Η φωτογραφία στάλθηκε στο κανάλι!*\n"
        f"🆔 ID: `{photo_id}`\n"
        f"📅 Ώρα: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────
# /stats
# ─────────────────────────────────────
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Μόνο για admin!")
        return

    photos = get_all_photos()

    if not photos:
        await update.message.reply_text("📊 Δεν υπάρχουν φωτογραφίες ακόμα!")
        return

    msg = "📊 *ΣΤΑΤΙΣΤΙΚΑ*\n━━━━━━━━━━━━━━\n\n"
    total_views_all = 0

    for photo in photos:
        photo_id, caption, created_at = photo
        views = get_total_views(photo_id)
        total_views_all += views
        msg += (
            f"📸 `{photo_id}`\n"
            f"📝 {caption or 'Χωρίς caption'}\n"
            f"📅 {created_at}\n"
            f"👁️ Θεάσεις: *{views}*\n\n"
        )

    msg += f"━━━━━━━━━━━━━━\n👁️ Σύνολο θεάσεων: *{total_views_all}*"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ─────────────────────────────────────
# /viewers
# ─────────────────────────────────────
async def viewers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Μόνο για admin!")
        return

    if not context.args:
        await update.message.reply_text(
            "📌 Χρήση: `/viewers photo_1`",
            parse_mode="Markdown"
        )
        return

    photo_id = context.args[0]
    photo = get_photo(photo_id)

    if not photo:
        await update.message.reply_text("❌ Δεν βρέθηκε αυτή η φωτογραφία!")
        return

    views = get_views(photo_id)

    if not views:
        await update.message.reply_text(f"👁️ Κανείς δεν έχει δει ακόμα την {photo_id}!")
        return

    msg = f"👥 *Θεάσεις για {photo_id}*\nΣύνολο: *{len(views)}*\n━━━━━━━━━━━━━━\n\n"

    for v in views:
        user_id, username, first_name, viewed_at = v
        msg += (
            f"👤 {first_name}\n"
            f"🔖 @{username or 'Κανένα'}\n"
            f"🆔 `{user_id}`\n"
            f"🕐 {viewed_at}\n"
            f"─────────\n"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")

# ─────────────────────────────────────
# /photos
# ─────────────────────────────────────
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
        msg += (
            f"🆔 `{photo_id}`\n"
            f"📝 {caption or 'Χωρίς caption'}\n"
            f"📅 {created_at}\n"
            f"👁️ {views} θεάσεις\n\n"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")

# ─────────────────────────────────────
# /help
# ─────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text(
            "ℹ️ Πήγαινε στο κανάλι για να δεις φωτογραφίες!\n"
            f"👉 {CHANNEL_ID}"
        )
        return

    msg = (
        "🤖 *ΕΝΤΟΛΕΣ ADMIN*\n"
        "━━━━━━━━━━━━━━\n\n"
        "📸 *Αποστολή φωτό:*\n"
        "Απλά στείλε μια φωτογραφία στο bot!\n\n"
        "📊 /stats - Γενικά στατιστικά\n"
        "👥 /viewers photo_1 - Ποιοι είδαν φωτό\n"
        "📋 /photos - Λίστα φωτογραφιών\n"
        "❓ /help - Αυτό το μήνυμα\n\n"
        f"🌐 WebApp: `{WEBAPP_URL}`\n"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")

# ─────────────────────────────────────
# ΕΚΚΙΝΗΣΗ BOT
# ─────────────────────────────────────
def main():
    init_db()
    logger.info("✅ Database αρχικοποιήθηκε!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("viewers", viewers))
    app.add_handler(CommandHandler("photos", photos_list))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        handle_photo
    ))

    logger.info("🤖 Bot ξεκίνησε!")
    print("🤖 Bot τρέχει... Πάτα Ctrl+C για να σταματήσει.")

    app.run_polling()

if __name__ == "__main__":
    main()
