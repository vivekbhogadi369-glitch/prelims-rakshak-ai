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


# ===================== Input parsing =====================
def parse_topic_subject(text: str):
    if not text:
        return None, None

    if " from " not in text.lower():
        return None, None

    parts = re.split(r"\s+from\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None

    topic = parts[0].strip()
    subject = parts[1].strip()

    if not topic or not subject:
        return None, None

    return topic, subject


def user_requested_telugu(text: str) -> bool:
    if not text:
        return False
    if re.search(r"[\u0C00-\u0C7F]", text):
        return True
    if "telugu" in text.lower() or "తెలుగు" in text:
        return True
    return False


def normalize_subject(subject: str) -> str:
    s = (subject or "").strip().lower()

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
        "sci-tech": "science and technology",
        "environment": "environment",
        "ecology": "environment",
        "climate change": "environment",
        "pollution": "environment",
        "biodiversity": "environment",
        "disaster management": "disaster management",
    }

    return mapping.get(s, s)


def is_allowed_subject(subject: str) -> bool:
    s = normalize_subject(subject)
    return s in [normalize_subject(x) for x in ALLOWED_SUBJECTS]


# ===================== AI Generation =====================
def build_prompt(topic: str, subject: str, telugu: bool) -> str:
    language_line = (
        "Write the full response in Telugu."
        if telugu
        else "Write the full response in English only."
    )

    return f"""
You are Prelims Rakshak AI, a UPSC mentor.

Student topic: {topic}
Subject: {subject}

{language_line}

Strict rules:
1. Use ONLY information retrieved from the uploaded faculty documents in file search.
2. Do NOT use outside knowledge.
3. Do NOT guess, assume, or add facts not found in the retrieved documents.
4. If the documents do not contain enough relevant information, reply exactly:
Answer not found in the uploaded faculty document.
5. Do not mention AI, prompt, model, backend, training data, retrieval, vector store, or file search.
6. Keep the topic strictly limited to: {topic}
7. Generate exam-oriented content only if supported by the documents.
8. If exact PYQ frequency is not available in the documents, give only a cautious estimate such as Low / Medium / High based on the retrieved material, without claiming official data.
9. MCQs and mains answer must be based only on the retrieved documents.

Now generate the response in this format:

1️⃣ QUICK REVISION NOTES
- Around 120 to 180 words
- Crisp, exam-oriented
- Only from the documents
- Add:
PYQ Frequency: Low / Medium / High
Mindmap: in short text form

2️⃣ UPSC PRELIMS MCQs
- Create 3 genuinely UPSC-standard MCQs only
- They must be based only on the documents
- At least 2 out of 3 must be statement-based
- Use UPSC-style formats such as:
  • Consider the following statements
  • With reference to...
  • Which of the statements given above is/are correct?
- Avoid direct one-line factual questions unless absolutely unavoidable
- Make options close and confusing, suitable for elimination
- Include conceptual traps wherever possible, but only from the documents
- Do not ask very easy questions like dates or names directly unless mixed with other statements
- After each MCQ give:
Correct Answer:
Elimination Logic:
Why other options are wrong:

3️⃣ UPSC MAINS SAMPLE ANSWER
- One short mains answer
- Structure:
Introduction:
Body:
Conclusion:
- Keep it around 120 to 150 words
- Only from the documents
"""


def generate_ai_answer(topic: str, subject: str, telugu: bool) -> str:
    prompt = build_prompt(topic, subject, telugu)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [VECTOR_STORE_ID],
                "max_num_results": 8,
            }
        ],
        max_output_tokens=1400,
    )

    text = (response.output_text or "").strip()
    if not text:
        return "Answer not found in the uploaded faculty document."
    return text


def split_long_message(text: str, limit: int = 3500):
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
        await update.message.reply_text("You are Admin ✅ Unlimited usage.")
        return
    used = used_today(user_id)
    await update.message.reply_text(f"Daily usage: {used}/{DAILY_LIMIT}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    if not can_use_today(user_id):
        await update.message.reply_text(
            f"Daily limit reached ({DAILY_LIMIT}/day). Please try tomorrow or upgrade."
        )
        return

    topic, subject = parse_topic_subject(text)
    if not topic or not subject:
        await update.message.reply_text(
            "Please use this format:\n"
            "<Topic> from <Subject>\n\n"
            "Example:\n"
            "Indus town planning from history"
        )
        return

    subject_normalized = normalize_subject(subject)
    if not is_allowed_subject(subject_normalized):
        await update.message.reply_text(
            "Allowed subjects only:\n"
            "History, Polity, Economy, Geography, Science and Technology, Environment, Disaster Management"
        )
        return

    telugu = user_requested_telugu(text)

    inc_today(user_id)

    await update.message.reply_text("Searching faculty documents...")

    try:
        final = generate_ai_answer(topic, subject_normalized, telugu)
    except Exception:
        await update.message.reply_text(
            "Something went wrong while reading the faculty document. Please try again."
        )
        return

    chunks = split_long_message(final, limit=3500)
    for chunk in chunks:
        await update.message.reply_text(chunk)


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
