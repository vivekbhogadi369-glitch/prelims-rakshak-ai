import os
import re
from datetime import date
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===================== ENV =====================
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY")

if not VECTOR_STORE_ID:
    raise ValueError("Missing VECTOR_STORE_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

# ===================== Daily Limit =====================
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "10"))

ADMIN_USER_IDS = set()
_raw_admin = (os.getenv("ADMIN_USER_IDS") or "").strip()

if _raw_admin:
    for x in _raw_admin.split(","):
        if x.strip().isdigit():
            ADMIN_USER_IDS.add(int(x.strip()))

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


# ===================== Allowed Subjects =====================
ALLOWED_SUBJECTS = [
    "history",
    "polity",
    "economy",
    "geography",
    "science and technology",
    "science & technology",
    "environment",
    "ecology",
    "climate change",
    "pollution",
    "biodiversity",
    "disaster management",
]


# ===================== Input Parsing =====================
def parse_topic_subject(text: str):

    if not text or " from " not in text.lower():
        return None, None

    parts = re.split(r"\s+from\s+", text, maxsplit=1, flags=re.IGNORECASE)

    if len(parts) != 2:
        return None, None

    topic = parts[0].strip()
    subject = parts[1].strip()

    if not topic or not subject:
        return None, None

    return topic, subject


def normalize_subject(subject: str):

    s = subject.strip().lower()

    mapping = {
        "indian history": "history",
        "ancient history": "history",
        "medieval history": "history",
        "modern history": "history",
        "history": "history",
        "polity": "polity",
        "indian polity": "polity",
        "economy": "economy",
        "indian economy": "economy",
        "geography": "geography",
        "indian geography": "geography",
        "science and technology": "science and technology",
        "science & technology": "science and technology",
        "environment": "environment",
        "ecology": "environment",
        "climate change": "environment",
        "pollution": "environment",
        "biodiversity": "environment",
        "disaster management": "disaster management",
    }

    return mapping.get(s, s)


def is_allowed_subject(subject: str):

    s = normalize_subject(subject)

    allowed = [normalize_subject(x) for x in ALLOWED_SUBJECTS]

    return s in allowed


def user_requested_telugu(text: str):

    if not text:
        return False

    if re.search(r"[\u0C00-\u0C7F]", text):
        return True

    if "telugu" in text.lower():
        return True

    return False


# ===================== Vector Search =====================
def get_relevant_context(topic: str, subject: str) -> str:

    query = f"{topic} {subject} UPSC concept explanation"

    try:

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=query,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 5
                }
            ],
        )

    except Exception:
        return ""

    text_parts = []

    if hasattr(response, "output"):
        for item in response.output:
            if hasattr(item, "content"):
                for c in item.content:
                    if hasattr(c, "text"):
                        text_parts.append(c.text)

    return "\n".join(text_parts).strip()


# ===================== AI Generation =====================
def build_prompt(topic, subject, telugu, context):

    language = "Telugu" if telugu else "English"

    return f"""
You are Prelims Rakshak AI.

Student Topic: {topic}
Subject: {subject}

Faculty document excerpts:
{context}

Answer only using the excerpts.

Language: {language}

Generate:

1. Quick Revision Notes
2. 3 UPSC standard MCQs with elimination logic
3. One 150 word UPSC mains answer

If excerpts are insufficient reply exactly:

Answer not found in the uploaded faculty document.
"""


def generate_ai_answer(topic, subject, telugu, context):

    prompt = build_prompt(topic, subject, telugu, context)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        max_output_tokens=1400
    )

    return response.output_text.strip()


# ===================== Split Long Messages =====================
def split_long_message(text, limit=3500):

    parts = []

    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)

        if cut == -1:
            cut = limit

        parts.append(text[:cut].strip())

        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts


# ===================== Handlers =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = (
        "Hello 👋 Prelims Rakshak AI is live.\n\n"
        "Current mode: Mentor output from uploaded faculty document only.\n\n"
        "Send your topic in this format:\n"
        "<Topic> from <Subject>\n\n"
        "Example:\n"
        "Indus town planning from history\n\n"
        "Default language: English\n"
        "Telugu only if asked."
    )

    await update.message.reply_text(msg)


async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id in ADMIN_USER_IDS:
        await update.message.reply_text("Admin account. Unlimited usage.")
        return

    used = used_today(user_id)

    await update.message.reply_text(f"Daily usage: {used}/{DAILY_LIMIT}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    if not can_use_today(user_id):

        await update.message.reply_text(
            f"Daily limit reached ({DAILY_LIMIT}). Try tomorrow."
        )

        return

    topic, subject = parse_topic_subject(text)

    if not topic:

        await update.message.reply_text(
            "Use format:\n\nTopic from Subject\n\nExample:\nIndus town planning from history"
        )

        return

    subject = normalize_subject(subject)

    if not is_allowed_subject(subject):

        await update.message.reply_text(
            "Allowed subjects:\nHistory, Polity, Economy, Geography, Science & Tech, Environment, Disaster Management"
        )

        return

    telugu = user_requested_telugu(text)

    context = get_relevant_context(topic, subject)

    if not context:

        await update.message.reply_text(
            "Answer not found in the uploaded faculty document."
        )

        return

    inc_today(user_id)

    await update.message.reply_text("Searching faculty documents...")

    try:

        final = generate_ai_answer(topic, subject, telugu, context)

    except Exception:

        await update.message.reply_text(
            "Error reading faculty documents. Try again."
        )

        return

    chunks = split_long_message(final)

    for chunk in chunks:
        await update.message.reply_text(chunk)


# ===================== MAIN =====================
def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
