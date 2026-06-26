import os
import io
import sqlite3
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file
from PIL import Image, ImageDraw, ImageFont
import requests

# ─────────────────────────────────────
# ΡΥΘΜΙΣΕΙΣ
# ─────────────────────────────────────
TOKEN = "8800151694:AAH3L3xHMI2JtXgbrTjzyoONgY-p89yBCnc"
BOT_TOKEN = TOKEN
WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")

app = Flask(__name__, static_folder=WEBAPP_DIR)

# ─────────────────────────────────────
# DATABASE
# ─────────────────────────────────────
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

def get_total_views(photo_id: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM views WHERE photo_id = ?", (photo_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ─────────────────────────────────────
# WATERMARK FUNCTION
# ─────────────────────────────────────
def add_watermark(image_bytes: bytes, username: str, user_id: int) -> bytes:
    """Προσθέτει watermark με username + ημερομηνία + user_id στη φωτογραφία."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    # Φτιάχνουμε το watermark layer
    watermark_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark_layer)

    # Κείμενο watermark
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    watermark_text = f"@{username}  |  ID: {user_id}  |  {date_str}"

    # Font size ανάλογα με το μέγεθος της εικόνας
    font_size = max(20, int(width / 30))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # Μέγεθος κειμένου
    bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Θέση: κάτω δεξιά με padding
    padding = 15
    x = width - text_width - padding
    y = height - text_height - padding

    # Shadow για καλύτερη ορατότητα
    shadow_offset = 2
    draw.text((x + shadow_offset, y + shadow_offset), watermark_text, font=font, fill=(0, 0, 0, 180))

    # Κυρίως κείμενο (λευκό με διαφάνεια)
    draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 210))

    # Επίσης diagonal watermark στη μέση (πιο διαφανές)
    diagonal_text = f"@{username}"
    diag_font_size = max(30, int(width / 15))
    try:
        diag_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", diag_font_size)
    except:
        diag_font = ImageFont.load_default()

    # Φτιάχνουμε το diagonal text σε ξεχωριστό layer
    txt_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_layer)
    diag_bbox = txt_draw.textbbox((0, 0), diagonal_text, font=diag_font)
    diag_w = diag_bbox[2] - diag_bbox[0]
    diag_h = diag_bbox[3] - diag_bbox[1]
    diag_x = (width - diag_w) // 2
    diag_y = (height - diag_h) // 2
    txt_draw.text((diag_x, diag_y), diagonal_text, font=diag_font, fill=(255, 255, 255, 60))

    # Rotate diagonal
    txt_layer = txt_layer.rotate(25, expand=False)

    # Συνδυασμός layers
    combined = Image.alpha_composite(img, watermark_layer)
    combined = Image.alpha_composite(combined, txt_layer)

    # Μετατροπή σε JPEG
    output = io.BytesIO()
    combined.convert("RGB").save(output, format="JPEG", quality=90)
    output.seek(0)
    return output.read()

# ─────────────────────────────────────
# ROUTES
# ─────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")

@app.route("/webapp/<path:filename>")
def serve_webapp(filename):
    return send_from_directory(WEBAPP_DIR, filename)

@app.route("/api/photo/<photo_id>")
def get_photo_api(photo_id):
    """Επιστρέφει πληροφορίες φωτογραφίας."""
    photo = get_photo(photo_id)
    if not photo:
        return jsonify({"error": "Φωτογραφία δεν βρέθηκε"}), 404

    return jsonify({
        "photo_id": photo[0],
        "caption": photo[2],
        "created_at": photo[3],
        "total_views": get_total_views(photo_id)
    })

@app.route("/api/photo/<photo_id>/image")
def get_watermarked_photo(photo_id):
    """Κατεβάζει τη φωτογραφία από το Telegram και προσθέτει watermark."""
    photo = get_photo(photo_id)
    if not photo:
        return jsonify({"error": "Φωτογραφία δεν βρέθηκε"}), 404

    # User στοιχεία από query params (στάλθηκαν από το Mini App)
    username = request.args.get("username", "unknown")
    user_id = request.args.get("user_id", "0")
    first_name = request.args.get("first_name", "Άγνωστος")

    # Καταγραφή θέασης
    save_view(photo_id, int(user_id), username, first_name)

    # Κατέβασμα φωτογραφίας από Telegram
    file_id = photo[1]
    try:
        # Παίρνουμε το file path από Telegram
        file_info_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        file_info = requests.get(file_info_url).json()
        file_path = file_info["result"]["file_path"]

        # Κατεβάζουμε το αρχείο
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        image_response = requests.get(file_url)
        image_bytes = image_response.content

        # Προσθέτουμε watermark
        watermarked = add_watermark(image_bytes, username, user_id)

        return send_file(
            io.BytesIO(watermarked),
            mimetype="image/jpeg",
            as_attachment=False
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────
# ΕΚΚΙΝΗΣΗ SERVER
# ─────────────────────────────────────
if __name__ == "__main__":
    print("🌐 Web server τρέχει στο http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
