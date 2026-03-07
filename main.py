import os
import re
from datetime import date
from PyPDF2 import PdfReader
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

if not TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# ===================== Faculty PDF =====================
PDF_PATH = "docs/Class 6 History Our Pasts 1.pdf"


def load_pdf_text():
    try:
        reader = PdfReader(PDF_PATH)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception:
        return ""


PDF_TEXT = load_pdf_text()

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
    """
    Expected:
    <Topic> from <Subject>
    Example:
    Indus town planning from history
    """
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


def keyword_list(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    stop = {
        "the", "and", "from", "with", "into", "about", "paper", "prelims",
        "topic", "subject", "history", "polity", "economy", "geography",
        "science", "technology", "environment", "disaster", "management",
        "indian", "india"
    }
    out = []
    seen = set()
    for w in words:
        if w not in stop and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:10]


# ===================== Simple document retrieval =====================
def split_text_into_chunks(text: str, chunk_size: int = 1800):
    if not text:
        return []

    cleaned = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    n = len(cleaned)

    while start < n:
        end = min(start + chunk_size, n)
        chunk = cleaned[start:end]

        if end < n:
            last_period = chunk.rfind(". ")
            last_space = chunk.rfind(" ")
            if last_period > 800:
                end = start + last_period + 1
                chunk = cleaned[start:end]
            elif last_space > 1200:
                end = start + last_space
                chunk = cleaned[start:end]

        chunks.append(chunk.strip())
        start = end

    return chunks


DOC_CHUNKS = split_text_into_chunks(PDF_TEXT)


def get_relevant_context(topic: str, subject: str, max_chunks: int = 4) -> str:
    if not DOC_CHUNKS:
        return ""

    keys = keyword_list(topic + " " + subject)
    if not keys:
        return ""

    scored = []
    for chunk in DOC_CHUNKS:
        chunk_lower = chunk.lower()
        score = sum(1 for k in keys if k in chunk_lower)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_chunks = [chunk for _, chunk in scored[:max_chunks]]

    return "\n\n".join(top_chunks).strip()


# ===================== AI Generation =====================
def build_prompt(topic: str, subject: str, telugu: bool, context_text: str) -> str:
    language_line = (
        "Write the entire response in Telugu."
        if telugu
        else "Write the entire response in English only."
    )

    return f"""
You are Prelims Rakshak AI.

Student topic: {topic}
Subject: {subject}

Relevant faculty document excerpts:
{context_text}

{language_line}

Strict rules:
1. Answer ONLY from the faculty document excerpts given above.
2. Do NOT use outside knowledge.
3. Do NOT guess, assume, or add facts not present in the excerpts.
4. If the excerpts are insufficient, reply exactly:
Answer not found in the uploaded faculty document.
5. Keep the answer short, clear, and exam-oriented.
6. Do not mention AI, prompt, model, backend, training data, or document retrieval.
7. Do not generate MCQs, mains answers, PYQ frequency, or mindmaps unless clearly supported by the excerpt.
8. Do not change the topic.

Now answer the student's topic using only the faculty document excerpts.
"""


def generate_ai_answer(topic: str, subject: str, telugu: bool, context_text: str) -> str:
    prompt = build_prompt(topic, subject, telugu, context_text)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You must answer strictly from provided document excerpts only. "
                    "If the answer is not supported by the excerpts, say exactly: "
                    "'Answer not found in the uploaded faculty document.'"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.1,
        max_tokens=700,
    )

    return response.choices[0].message.content.strip()


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
        "Current mode: Answering from uploaded faculty document only.\n\n"
        "Send your topic in this format:\n"
        "<Topic> from <Subject>\n\n"
        "Example:\n"
        "Harappan civilization from history\n\n"
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
            "Harappan civilization from history"
        )
        return

    subject_normalized = normalize_subject(subject)
    if not is_allowed_subject(subject_normalized):
        await update.message.reply_text(
            "Allowed subjects only:\n"
            "History, Polity, Economy, Geography, Science and Technology, Environment, Disaster Management"
        )
        return

    if not PDF_TEXT:
        await update.message.reply_text(
            "No readable faculty document found. Please upload a valid PDF."
        )
        return

    telugu = user_requested_telugu(text)
    context_text = get_relevant_context(topic, subject_normalized)

    if not context_text:
        await update.message.reply_text(
            "Answer not found in the uploaded faculty document."
        )
        return

    inc_today(user_id)

    await update.message.reply_text("Searching faculty document...")

    try:
        final = generate_ai_answer(topic, subject_normalized, telugu, context_text)
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
    app.run_polling()


if __name__ == "__main__":
    main()
