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

# ===================== Helpers =====================

def parse_topic_subject(text: str):
    """
    Expected format:
    <Topic> from <Subject>

    Example:
    Indus town planning from Indian history
    """
    if not text:
        return None, None
    lower = text.lower()
    if " from " not in lower:
        return None, None

    parts = text.split(" from ", 1)
    if len(parts) != 2:
        return None, None

    topic = parts[0].strip()
    subject = parts[1].strip()

    if not topic or not subject:
        return None, None

    return topic, subject

# ===================== Handlers =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Hello 👋 Prelims Rakshak AI is live.\n"
        "Tell me how can I help you?\n\n"
        "✅ How to ask:\n"
        "Type: <Topic> from <Subject>\n\n"
        "Example:\n"
        "Indus town planning from Indian history\n\n"
        "⚠️ Current mode: UPSC Prelims PYQ-only (No hallucinations).\n"
        "To get an answer, paste the exact PYQ question text (or UPSC PDF question text) after you give topic+subject."
    )
    await update.message.reply_text(msg)

async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_USER_IDS:
        await update.message.reply_text("You are Admin ✅ Unlimited usage.")
        return

    used = used_today(user_id)
    await update.message.reply_text(f"Daily usage: {used}/{DAILY_LIMIT}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not can_use_today(user_id):
        await update.message.reply_text(
            f"Daily limit reached ({DAILY_LIMIT}/day). Please try tomorrow or upgrade."
        )
        return

    user_text = (update.message.text or "").strip()

    # Step-2: Force format Topic from Subject
    topic, subject = parse_topic_subject(user_text)
    if not topic:
        await update.message.reply_text(
            "Please type in this format:\n"
            "<Topic> from <Subject>\n\n"
            "Example:\n"
            "Indus town planning from Indian history"
        )
        return

    inc_today(user_id)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Prelims Rakshak AI (UPSC Prelims PYQ mode).\n"
                        "RULES:\n"
                        "1) Do NOT hallucinate. Do NOT guess.\n"
                        "2) You may answer ONLY if the user provides the exact PYQ question text (verbatim) from UPSC Prelims.\n"
                        "3) If the user only gives a topic/subject (without the actual PYQ question), ask them to paste the exact PYQ question text.\n"
                        "4) If they paste the question, answer in exam-oriented manner: "
                        "give final answer first, then short explanation, then key terms.\n"
                        "5) Keep it concise.\n"
                        "6) If user asks in Telugu, respond in Telugu."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User provided Topic: {topic}\n"
                        f"Subject: {subject}\n\n"
                        f"User message:\n{user_text}\n\n"
                        "If the PYQ question text is NOT present, ask them to paste the exact question text from UPSC (verbatim)."
                    ),
                },
            ],
            max_tokens=500,
        )

        reply = response.choices[0].message.content or "Please try again."
    except Exception:
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
