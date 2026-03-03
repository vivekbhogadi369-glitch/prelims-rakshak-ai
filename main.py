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

TOKEN = os.getenv("TELEGRAM_TOKEN")

# ===================== Daily Limit Config =====================
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "10"))

ADMIN_USER_IDS = set()
_raw_admin = (os.getenv("ADMIN_USER_IDS") or "").strip()
if _raw_admin:
    for x in _raw_admin.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_USER_IDS.add(int(x))

# In-memory daily usage (resets if Railway worker restarts; we’ll make it permanent later)
DAILY_USAGE = {}  # key: f"{user_id}:{YYYY-MM-DD}" -> count


def _today_key(user_id: int) -> str:
    return f"{user_id}:{date.today().isoformat()}"


def used_today(user_id: int) -> int:
    if user_id in ADMIN_USER_IDS:
        return 0
    return DAILY_USAGE.get(_today_key(user_id), 0)


def remaining_today(user_id: int) -> int:
    if user_id in ADMIN_USER_IDS:
        return 999999  # effectively unlimited
    return max(0, DAILY_LIMIT - used_today(user_id))


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
    left = remaining_today(user_id)
    await update.message.reply_text(
        f"Daily usage: {used}/{DAILY_LIMIT}\nRemaining today: {left}"
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Enforce limit
    if not can_use_today(user_id):
        await update.message.reply_text(
            f"Daily limit reached ({DAILY_LIMIT}/day).\nPlease try tomorrow or upgrade."
        )
        return

    # Count this message
    inc_today(user_id)

    # Your current simple reply
    await update.message.reply_text("You said: " + (update.message.text or ""))


def main():
    if not TOKEN:
        raise ValueError("Missing TELEGRAM_TOKEN in Railway Variables")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    app.run_polling()


if __name__ == "__main__":
    main()
