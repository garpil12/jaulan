import sqlite3
import logging
from datetime import datetime
import pytz
from cryptography.fernet import Fernet
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ================= CONFIG =================
TOKEN = "8493844166:AAEN5c-Pu2jxzsuk8Di056hStdZixIjk1iY"
OWNER_IDS = [6361374151, 8209644174]
SECRET_KEY = b'0mBl7VBelC7fPvZsjj0l6RGxHDwrjlHZixYWUC68gPU='
WIB = pytz.timezone("Asia/Jakarta")
LOGS_CHAT_ID = -1003724444499  # grup logs
PAYMENT_INFO = """💳 PAYMENT INFO 💳
- QR: https://ibb.co.com/7t54RddV
- Shopeepay: 081219623569 A/n rifkxxx
"""

cipher = Fernet(SECRET_KEY)
logging.basicConfig(level=logging.INFO)

def now_wib():
    return datetime.now(WIB).strftime("%d-%m-%Y %H:%M:%S WIB")

def encrypt(text):
    return cipher.encrypt(text.encode()).decode()

def decrypt(text):
    return cipher.decrypt(text.encode()).decode()

# ================= DATABASE =================
conn = sqlite3.connect("store.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
cursor.execute("""CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT,
    harga INTEGER,
    stok INTEGER,
    kategori_id INTEGER,
    file TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_id INTEGER,
    status TEXT,
    tanggal TEXT
)""")
conn.commit()

# Tambah kategori awal A/B/C/D jika belum ada
for cat in ["A", "B", "C", "D"]:
    cursor.execute("INSERT OR IGNORE INTO categories (nama) VALUES (?)", (cat,))
conn.commit()

# ================= ROLE =================
def is_owner(uid):
    return uid in OWNER_IDS

def is_admin(uid):
    cursor.execute("SELECT * FROM admins WHERE user_id=?", (uid,))
    return cursor.fetchone() or is_owner(uid)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (uid,))
    conn.commit()

    cursor.execute("SELECT * FROM categories")
    cats = cursor.fetchall()
    keyboard = [[InlineKeyboardButton(c[1], callback_data=f"cat_{c[0]}")] for c in cats]

    await update.message.reply_text(
        "🔥 WELCOME TO GARFIELD STORE 🔥\nPilih kategori:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= ADD PRODUK =================
async def addproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Khusus owner.")
        return
    try:
        data = update.message.text.split(" ", 1)[1]
        nama, harga, stok, kategori = data.split("|")
        harga = harga.replace(".", "").replace(",", "").strip()
        stok = stok.strip()
        cursor.execute(
            "INSERT INTO products (nama, harga, stok, kategori_id, file) VALUES (?, ?, ?, ?, ?)",
            (nama.strip(), int(harga), int(stok), int(kategori), encrypt(""))
        )
        conn.commit()
        await update.message.reply_text("Produk berhasil ditambahkan.")
    except:
        await update.message.reply_text(
            "Format salah.\nContoh:\n/addproduk Nama|Harga|Stok|KategoriID"
        )

# ================= LIST PRODUK =================
async def list_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("cat_"):
        cat_id = int(query.data.split("_")[1])
        cursor.execute("SELECT * FROM products WHERE kategori_id=?", (cat_id,))
    else:
        cursor.execute("SELECT * FROM products")

    data = cursor.fetchall()
    if not data:
        await query.edit_message_text("Produk kosong.")
        return

    keyboard = [[InlineKeyboardButton(f"{p[1]} | Rp{p[2]} | Stok:{p[3]}", callback_data=f"detail_{p[0]}")] for p in data]
    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="start")])

    await query.edit_message_text("📦 LIST PRODUK:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= DETAIL PRODUK =================
async def detail_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pid = int(query.data.split("_")[1])
    cursor.execute("SELECT * FROM products WHERE id=?", (pid,))
    p = cursor.fetchone()

    keyboard = [
        [InlineKeyboardButton("🛒 BELI", callback_data=f"buy_{pid}")],
        [InlineKeyboardButton("🔙 Kembali", callback_data=f"cat_{p[4]}")]
    ]

    await query.edit_message_text(f"📦 {p[1]}\nHarga: Rp{p[2]}\nStok: {p[3]}\n\n{PAYMENT_INFO}", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= BUY =================
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    pid = int(query.data.split("_")[1])

    cursor.execute("SELECT * FROM transactions WHERE user_id=? AND status='PENDING'", (uid,))
    if cursor.fetchone():
        await query.answer("Masih ada transaksi pending!", show_alert=True)
        return

    cursor.execute("SELECT stok FROM products WHERE id=?", (pid,))
    stok = cursor.fetchone()[0]
    if stok <= 0:
        await query.answer("Stok habis!", show_alert=True)
        return

    cursor.execute("INSERT INTO transactions (user_id,product_id,status,tanggal) VALUES (?,?,?,?)",
                   (uid, pid, "PENDING", now_wib()))
    conn.commit()
    await query.edit_message_text("Silakan transfer & kirim foto bukti.\nStatus: PENDING")

# ================= FOTO BUKTI =================
async def bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    cursor.execute("SELECT * FROM transactions WHERE user_id=? AND status='PENDING'", (uid,))
    trx = cursor.fetchone()
    if not trx:
        return

    keyboard = [[
        InlineKeyboardButton("✅ ACC", callback_data=f"acc_{trx[0]}"),
        InlineKeyboardButton("❌ CANCEL", callback_data=f"cancel_{trx[0]}")
    ]]

    await context.bot.send_photo(
        LOGS_CHAT_ID,
        photo=update.message.photo[-1].file_id,
        caption=f"User: {uid}\nTRX ID: {trx[0]}\n{now_wib()}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Bukti dikirim ke admin.")

# ================= ACC / CANCEL =================
async def acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    trx_id = int(query.data.split("_")[1])
    cursor.execute("SELECT user_id, product_id FROM transactions WHERE id=?", (trx_id,))
    uid, pid = cursor.fetchone()
    cursor.execute("SELECT file FROM products WHERE id=?", (pid,))
    encrypted_file = cursor.fetchone()[0]
    decrypted = decrypt(encrypted_file)
    lines = decrypted.split("\n")
    if not lines or lines[0] == "":
        await query.answer("Stok file kosong!")
        return

    item = lines[0]
    remaining = "\n".join(lines[1:])

    cursor.execute("UPDATE products SET file=?, stok=stok-1 WHERE id=?",
                   (encrypt(remaining), pid))
    cursor.execute("UPDATE transactions SET status='SUCCESS' WHERE id=?", (trx_id,))
    conn.commit()

    await context.bot.send_message(uid, f"✅ Transaksi berhasil!\nProduk: {item}\nStatus: SUCCESS\nTerima kasih sudah membeli.")
    await query.edit_message_caption("SUCCESS")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trx_id = int(query.data.split("_")[1])
    cursor.execute("SELECT user_id FROM transactions WHERE id=?", (trx_id,))
    uid = cursor.fetchone()[0]
    cursor.execute("UPDATE transactions SET status='CANCEL' WHERE id=?", (trx_id,))
    conn.commit()
    await context.bot.send_message(uid, f"❌ Transaksi dibatalkan.\nTRX ID: {trx_id}")
    await query.edit_message_caption("CANCELLED")

# ================= BROADCAST =================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.message.from_user.id):
        return
    text = " ".join(context.args)
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    for u in users:
        try:
            await context.bot.send_message(u[0], text)
        except:
            pass
    await update.message.reply_text("Broadcast selesai.")

# ================= HELP =================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
🔥 GARFIELD STORE BOT 🔥

📌 Commands:
/start - Menu awal kategori
/addproduk Nama|Harga|Stok|KategoriID - Tambah produk (Owner)
/broadcast Pesan - Broadcast ke semua user (Owner)
/help - Tampilkan panduan

💳 Payment Info:
{PAYMENT_INFO}
"""
    await update.message.reply_text(text)

# ================= MAIN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addproduk", addproduk))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CallbackQueryHandler(list_produk, pattern="list|cat_"))
app.add_handler(CallbackQueryHandler(detail_produk, pattern="detail_"))
app.add_handler(CallbackQueryHandler(buy, pattern="buy_"))
app.add_handler(CallbackQueryHandler(acc, pattern="acc_"))
app.add_handler(CallbackQueryHandler(cancel, pattern="cancel_"))
app.add_handler(MessageHandler(filters.PHOTO, bukti))

app.run_polling()
