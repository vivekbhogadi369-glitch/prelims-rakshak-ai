import os
from datetime import date
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

# ===================== ENV =====================
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# ===================== Daily Limit =====================
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "10"))

ADMIN_USER_IDS = set()
_raw_admin = (os.getenv("ADMIN_USER_IDS") or "").strip()
if _raw_admin:
    for x in _raw_admin.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_USER_IDS.add(int(x))

DAILY_USAGE = {}

def _today_key(user_id: int) -> str:
    return f"{user_id}:{date.today().isoformat()}"

def used_today(user_id: int) -> int:
    if user_id in ADMIN_USER_IDS:
        return 0
    return DAILY_USAGE.get(_today_key(user_id), 0)

def can_use_today(user_id: int) -> bool:
    if user_id in ADMIN_USER_IDS:
        return True
    return used_today(user_id) < DAILY_LIMIT

def inc_today(user_id: int) -> None:
    if user_id in ADMIN_USER_IDS:
        return
    k = _today_key(user_id)
    DAILY_USAGE[k] = DAILY_USAGE.get(k, 0) + 1

# ===================== Handlers =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Prelims Rakshak AI is Live 🚀")

async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_USER_IDS:
        await update.message.reply_text("You are Admin ✅ Unlimited usage.")
        return

    used = used_today(user_id)
    await update.message.reply_text(
        f"Daily usage: {used}/{DAILY_LIMIT}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not can_use_today(user_id):
        await update.message.reply_text(
            f"Daily limit reached ({DAILY_LIMIT}/day). Please try tomorrow or upgrade."
        )
        return

    user_text = update.message.text

    inc_today(user_id)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Prelims Rakshak AI. "
                        "You are a UPSC General Studies expert. "
                        "Give structured answers. "
                        "For MCQs include elimination logic. "
                        "Be concise but high quality."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
            max_tokens=500,
        )

        reply = response.choices[0].message.content

    except Exception as e:
        reply = "Error generating response. Please try again."

    await update.message.reply_text(reply)


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
