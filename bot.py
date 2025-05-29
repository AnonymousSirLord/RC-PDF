import os
import logging
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

def extract_rate_details(text: str) -> str:
    data = {}
    patterns = {
        "Carrier": r"Carrier:\s*(SIMPLE 1 GROUP LLC.*)",
        "Dispatcher": r"Contact:\s*(ALEX MOOZ)",
        "Pickup Address": r"Pickup\s+\d+\s+([^\n]+)\n([A-Z].+?\d{5})",
        "Pickup Time": r"Pickup\s+\d+\s+[A-Z\s]+\n.*?(\d{2}/\d{2}/\d{2}\s+\d{1,2}:\d{2}\s+[AP]M)",
        "Delivery Address": r"Delivery\s+\d+\s+([^\n]+)\n([A-Z].+?\d{5})",
        "Delivery Time": r"Delivery\s+\d+\s+[A-Z\s]+\n.*?(\d{2}/\d{2}/\d{2}\s+\d{1,2}:\d{2}\s+[AP]M)",
        "Rate": r"Freight Pay:\s*\$([\d,]+\.\d{2})",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            data[key] = match.group(1).strip()
    return "\n".join([f"{k}: {v}" for k, v in data.items()]) or "No structured data found."

async def send_key_fields(update: Update, extracted: str):
    fields = ["Carrier", "Pickup Address", "Pickup Time", "Delivery Address", "Delivery Time", "Rate"]
    lines = []
    for field in fields:
        match = re.search(rf"{field}:\s*(.*)", extracted)
        if match:
            lines.append(f"{field}: {match.group(1)}")
    response = "\n".join(lines) or "No key fields found."
    await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Send a rate confirmation PDF (scanned or regular). I'll extract the key info.")

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    if not file.mime_type.endswith("pdf"):
        await update.message.reply_text("Please send a PDF.")
        return
    telegram_file = await file.get_file()
    pdf_path = await telegram_file.download_to_drive()
    print(f"📥 Downloaded PDF to {pdf_path.name}")

    try:
        with pdfplumber.open(pdf_path.name) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        print("📄 Extracted text from pdfplumber:")
        print(full_text)
        if not full_text.strip():
            raise ValueError("No text found, fallback to OCR")
        extracted = extract_rate_details(full_text)
    except Exception as e:
        logging.warning(f"Text extraction failed: {e}. Trying OCR...")
        try:
            images = convert_from_path(pdf_path.name)
            ocr_text = "\n".join(pytesseract.image_to_string(img, lang="eng", config="--psm 6") for img in images)
            print("🖼️ OCR text extracted:")
            print(ocr_text)
            extracted = extract_rate_details(ocr_text)
        except Exception as ocr_err:
            logging.error(f"OCR failed: {ocr_err}")
            extracted = "❌ Failed to extract text from PDF."

    await send_key_fields(update, extracted)

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("❌ BOT_TOKEN not found in environment.")
    else:
        print("✅ BOT_TOKEN loaded. Starting bot...")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    print("🚀 Bot is running with date/time extraction...")
    app.run_polling()
