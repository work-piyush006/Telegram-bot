import os
import uuid
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from PyPDF2 import PdfMerger

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = "YOUR_BOT_TOKEN"
ADMIN_ID = 123456789

QR_PATH = "assets/qr.png"
UPI_ID = "work.piyush006@Fam"
PAYMENT_LINK = "https://tinyurl.com/Thanks-for-Supporting"

MAX_PAGES = 15

# ================= USER STATE =================
user_state = {}
pending_donations = {}

def init_user(uid):
    if uid not in user_state:
        user_state[uid] = {
            "supporter": False,
            "scan_images": [],
            "mode": None,
        }

def cleanup_files(files):
    for f in files:
        if os.path.exists(f):
            os.remove(f)

# ================= IMAGE ENHANCEMENT =================
def enhance_image(input_path, output_path):
    img = Image.open(input_path)
    img.thumbnail((1400, 1400))
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = ImageEnhance.Brightness(img).enhance(1.1)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=3))
    img = img.convert("RGB")
    img.save(output_path, quality=95)

def images_to_pdf(images, pdf_path):
    imgs = [Image.open(p).convert("RGB") for p in images]
    imgs[0].save(pdf_path, save_all=True, append_images=imgs[1:], resolution=300)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_user(uid)

    keyboard = [
        [InlineKeyboardButton("📸 Image → PDF (Scan)", callback_data="SCAN")],
        [InlineKeyboardButton("📎 PDF Joiner", callback_data="JOIN")],
    ]

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Turn photos into clean, scanner-style PDFs 📄\n"
        "Perfect for notes, documents & forms.\n\n"
        "Choose an option 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ================= MENU =================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    init_user(uid)

    if q.data == "SCAN":
        user_state[uid]["mode"] = "SCAN"
        user_state[uid]["scan_images"] = []
        await q.message.reply_text(
            "📸 Scanner Mode selected\n\n"
            "You can send up to 15 images.\n"
            "Send images one by one OR multiple at once.\n\n"
            "Tap “Finish Scan” when done."
        )

        keyboard = [
            [InlineKeyboardButton("🔚 Finish Scan", callback_data="FINISH_SCAN")],
            [InlineKeyboardButton("❌ Cancel", callback_data="RESTART")],
        ]
        await q.message.reply_text("Ready to receive images 👇", reply_markup=InlineKeyboardMarkup(keyboard))

    elif q.data == "JOIN":
        user_state[uid]["mode"] = "JOIN"
        user_state[uid]["join_pdfs"] = []
        await q.message.reply_text("📎 PDF Joiner selected\n\nSend the first PDF.")

    elif q.data == "SUPPORT":
        await show_payment(q)

    elif q.data == "RESTART":
        await start(q.message, context)

# ================= PHOTO HANDLER =================
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_user(uid)

    if user_state[uid]["mode"] != "SCAN":
        return

    photos = update.message.photo
    current = user_state[uid]["scan_images"]

    if len(current) + len(photos) > MAX_PAGES:
        await update.message.reply_text(
            f"⚠️ Maximum {MAX_PAGES} images allowed.\n"
            "Please tap “Finish Scan”."
        )
        return

    for p in photos:
        fid = str(uuid.uuid4())
        raw = f"{fid}.jpg"
        enhanced = f"{fid}_scan.jpg"
        tg = await p.get_file()
        await tg.download_to_drive(raw)
        enhance_image(raw, enhanced)
        cleanup_files([raw])
        current.append(enhanced)

    await update.message.reply_text(
        f"📄 {len(photos)} page(s) added ({len(current)}/{MAX_PAGES})\n"
        "Send more images or tap “Finish Scan”."
    )

# ================= FINISH SCAN =================
async def finish_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    images = user_state[uid]["scan_images"]
    if not images:
        await q.message.reply_text("No images received.")
        return

    pdf_path = f"{uuid.uuid4()}.pdf"
    await q.message.reply_text("🪄 Enhancing & creating multi-page PDF…")
    images_to_pdf(images, pdf_path)

    await q.message.reply_document(
        document=InputFile(pdf_path),
        caption="✅ Scan complete!\nHere’s your scanned PDF 👇"
    )

    cleanup_files(images + [pdf_path])
    user_state[uid]["scan_images"] = []

    await post_action(update, context)

# ================= PDF JOINER =================
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_user(uid)

    if user_state[uid].get("mode") != "JOIN":
        return

    pdfs = user_state[uid].setdefault("join_pdfs", [])
    file = update.message.document
    fid = f"{uuid.uuid4()}.pdf"
    tg = await file.get_file()
    await tg.download_to_drive(fid)
    pdfs.append(fid)

    if len(pdfs) == 1:
        await update.message.reply_text("📄 First PDF received\nSend second PDF.")
    elif len(pdfs) == 2:
        await update.message.reply_text("🔗 Joining PDFs…")
        out = f"{uuid.uuid4()}.pdf"
        merger = PdfMerger()
        for p in pdfs:
            merger.append(p)
        with open(out, "wb") as f:
            merger.write(f)

        await update.message.reply_document(
            document=InputFile(out),
            caption="✅ PDFs merged successfully!"
        )

        cleanup_files(pdfs + [out])
        user_state[uid]["join_pdfs"] = []
        await post_action(update, context)

# ================= POST ACTION CTA =================
async def post_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_user(uid)

    if user_state[uid]["supporter"]:
        text = (
            "💙 Thanks for supporting!\n"
            "Your help keeps this bot running smoothly.\n\n"
            "What would you like to do next?"
        )
        buttons = [
            [InlineKeyboardButton("🔁 Scan another document", callback_data="SCAN")],
            [InlineKeyboardButton("🏠 Back to main menu", callback_data="RESTART")],
        ]
    else:
        text = (
            "If this bot helped you,\n"
            "supporting it keeps the scans free & fast 💙\n\n"
            "What would you like to do next?"
        )
        buttons = [
            [InlineKeyboardButton("🔁 Scan another document", callback_data="SCAN")],
            [InlineKeyboardButton("⭐ Support this bot", callback_data="SUPPORT")],
            [InlineKeyboardButton("🏠 Back to main menu", callback_data="RESTART")],
        ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ================= PAYMENT =================
async def show_payment(q):
    keyboard = [
        [InlineKeyboardButton("💖 I’ve Paid", callback_data="PAID")],
        [InlineKeyboardButton("❌ Maybe later", callback_data="RESTART")],
    ]

    with open(QR_PATH, "rb") as qr:
        await q.message.reply_photo(
            photo=InputFile(qr),
            caption=(
                "💖 Support Scanify Bot\n\n"
                f"UPI ID:\n`{UPI_ID}`\n\n"
                f"Payment Link:\n{PAYMENT_LINK}\n\n"
                "After payment, tap *I’ve Paid* 👇"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

async def user_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = q.from_user

    pending_donations[uid] = True

    await q.message.reply_text(
        "🙏 Thanks!\n\nYour payment request has been sent for verification."
    )

    admin_kb = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"APPROVE_{uid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"REJECT_{uid}"),
        ]
    ]

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💰 Donation Request\n\nUser: {user.first_name}\nID: {uid}",
        reply_markup=InlineKeyboardMarkup(admin_kb),
    )

# ================= ADMIN ACTION =================
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id != ADMIN_ID:
        return

    action, uid = q.data.split("_")
    uid = int(uid)

    if action == "APPROVE":
        user_state.setdefault(uid, {})["supporter"] = True
        await context.bot.send_message(
            chat_id=uid,
            text="💙 Donation confirmed!\nThank you for supporting 🙏"
        )
        await q.message.reply_text("Approved ✅")
    else:
        kb = [
            [InlineKeyboardButton("📩 Contact Admin", callback_data="CONTACT_ADMIN")],
            [InlineKeyboardButton("🏠 Back to main menu", callback_data="RESTART")],
        ]
        await context.bot.send_message(
            chat_id=uid,
            text="❌ Payment not found.\n\nIf this is a mistake, please contact admin.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        await q.message.reply_text("Rejected ❌")

    pending_donations.pop(uid, None)

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "📩 User Contacted Admin\n\n"
            f"Name: {user.first_name}\n"
            f"Username: @{user.username}\n"
            f"User ID: {user.id}\n\n"
            "Issue: Payment marked as not found."
        )
    )

    await q.message.reply_text(
        "📩 Your message has been sent to admin.\nThey’ll get back to you shortly."
    )

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(SCAN|JOIN|SUPPORT|RESTART)$"))
    app.add_handler(CallbackQueryHandler(finish_scan, pattern="^FINISH_SCAN$"))
    app.add_handler(CallbackQueryHandler(user_paid, pattern="^PAID$"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(APPROVE_|REJECT_)"))
    app.add_handler(CallbackQueryHandler(contact_admin, pattern="^CONTACT_ADMIN$"))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photos))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()