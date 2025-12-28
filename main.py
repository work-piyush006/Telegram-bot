import os
import uuid
import cv2
from PIL import Image

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
BOT_TOKEN = "8431204935:AAF3hoRDAhANjYlb4iWNz52-n1TsNfSYr50"

ADMIN_ID = 8189463964  # <-- apna Telegram user ID yahan daalo

QR_PATH = "assets/qr.png"
UPI_ID = "work.piyush006@Fam"
PAYMENT_LINK = "https://tinyurl.com/Thanks-for-Supporting"

# ================= USER STATE =================
user_state = {}
pending_donations = {}  # key: user_id, value: info

def init_user(uid):
    if uid not in user_state:
        user_state[uid] = {
            "scans": 0,
            "supporter": False
        }

def cleanup(*files):
    for f in files:
        if f and os.path.exists(f):
            os.remove(f)

# ================= IMAGE ENHANCEMENT =================
def enhance_image(input_path, output_image_path):
    img = cv2.imread(input_path)

    # resize for performance
    target_h = 1000
    ratio = target_h / img.shape[0]
    img = cv2.resize(img, None, fx=ratio, fy=ratio)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    thresh = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2
    )

    cv2.imwrite(output_image_path, thresh)

def image_to_pdf(image_path, pdf_path):
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(pdf_path, "PDF", resolution=300)

# ================= /start =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_user(uid)

    keyboard = [
        [InlineKeyboardButton("📸 Image → PDF (Scan)", callback_data="SCAN")]
    ]

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Turn photos into clean, scanner-style PDFs 📄\n"
        "Perfect for notes, documents & forms.\n\n"
        "Tap below to start 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ================= MODE / MENU =================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "SCAN":
        await query.message.reply_text(
            "📸 Scanner Mode selected\n\n"
            "Send a clear photo of your document.\n"
            "Good lighting gives best results."
        )

    elif query.data == "SUPPORT":
        await show_payment(query)

    elif query.data == "RESTART":
        await start(query.message, context)

# ================= IMAGE HANDLER =================
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_user(uid)

    await update.message.reply_text(
        "⏳ Image received\n🪄 Enhancing & scanning…"
    )

    file_id = str(uuid.uuid4())
    raw_img = f"{file_id}.jpg"
    enhanced_img = f"{file_id}_scan.jpg"
    pdf_file = f"{file_id}.pdf"

    try:
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        await tg_file.download_to_drive(raw_img)

        enhance_image(raw_img, enhanced_img)
        image_to_pdf(enhanced_img, pdf_file)

        await update.message.reply_document(
            document=InputFile(pdf_file),
            caption="✅ Scan complete!\nHere’s your enhanced PDF 👇"
        )

        user_state[uid]["scans"] += 1

        # ----- POST SCAN CTA (EVERY USE) -----
        if user_state[uid]["supporter"]:
            text = (
                "💙 Thanks for supporting!\n"
                "Your help keeps this bot running smoothly.\n\n"
                "What would you like to do next?"
            )
            keyboard = [
                [InlineKeyboardButton("🔁 Scan another image", callback_data="RESTART")],
                [InlineKeyboardButton("🏠 Back to main menu", callback_data="RESTART")],
            ]
        else:
            text = (
                "If this bot helped you,\n"
                "supporting it keeps the scans free & fast 💙\n\n"
                "What would you like to do next?"
            )
            keyboard = [
                [InlineKeyboardButton("🔁 Scan another image", callback_data="RESTART")],
                [InlineKeyboardButton("⭐ Support this bot", callback_data="SUPPORT")],
            ]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception:
        await update.message.reply_text(
            "⚠️ Scan failed. Please send a clear image and try again."
        )

    finally:
        cleanup(raw_img, enhanced_img, pdf_file)

# ================= PAYMENT =================
async def show_payment(query):
    keyboard = [
        [InlineKeyboardButton("💖 I’ve Paid", callback_data="PAID")],
        [InlineKeyboardButton("❌ Maybe later", callback_data="RESTART")],
    ]

    with open(QR_PATH, "rb") as qr:
        await query.message.reply_photo(
            photo=InputFile(qr),
            caption=(
                "💖 Support This Bot\n\n"
                f"UPI ID:\n`{UPI_ID}`\n\n"
                f"Payment Link:\n{PAYMENT_LINK}\n\n"
                "After payment, tap *I’ve Paid* 👇"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

# ================= USER CLAIMS PAYMENT =================
async def user_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    user = query.from_user

    pending_donations[uid] = {
        "username": user.username,
        "name": user.first_name,
        "scans": user_state.get(uid, {}).get("scans", 0)
    }

    await query.message.reply_text(
        "🙏 Thanks!\n\n"
        "Your payment request has been sent for verification.\n"
        "Once confirmed, you’ll get a thank-you message."
    )

    # Notify admin
    admin_keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"APPROVE_{uid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"REJECT_{uid}")
        ]
    ]

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "💰 Donation Request\n\n"
            f"User: @{user.username}\n"
            f"Name: {user.first_name}\n"
            f"User ID: {uid}\n"
            f"Scans done: {pending_donations[uid]['scans']}\n\n"
            "Approve this donation?"
        ),
        reply_markup=InlineKeyboardMarkup(admin_keyboard),
    )

# ================= ADMIN ACTION =================
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    action, uid_str = query.data.split("_")
    uid = int(uid_str)

    if uid not in pending_donations:
        await query.message.reply_text("Request not found.")
        return

    if action == "APPROVE":
        user_state.setdefault(uid, {"scans": 0, "supporter": False})
        user_state[uid]["supporter"] = True

        await context.bot.send_message(
            chat_id=uid,
            text=(
                "💙 Donation confirmed!\n\n"
                "Thank you for supporting this bot 🙏\n"
                "You’re now a Supporter 🎉"
            )
        )

        await query.message.reply_text("✅ Donation approved.")
        pending_donations.pop(uid, None)

    elif action == "REJECT":
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "❌ Payment not found.\n\n"
                "If this is a mistake, please contact admin."
            )
        )
        await query.message.reply_text("❌ Donation rejected.")
        pending_donations.pop(uid, None)

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(SCAN|SUPPORT|RESTART)$"))
    app.add_handler(CallbackQueryHandler(user_paid, pattern="^PAID$"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(APPROVE_|REJECT_)"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()