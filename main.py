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

# ===================== AI Generation =====================

def build_prompt(topic: str, subject: str, telugu: bool) -> str:
    language_line = (
        "Write the entire response in Telugu."
        if telugu
        else "Write the entire response in English only."
    )

    return f"""
You are Prelims Rakshak AI, a high-level UPSC General Studies mentor trained to produce faculty-grade exam material.

Topic strictly to be explained: {topic}
Subject area: {subject}

{language_line}

Non-negotiable rules:
1. Do NOT change the topic.
2. Do NOT introduce unrelated concepts.
3. All notes, MCQs, PYQ trend remarks, and mains answer must revolve around the topic: {topic}.
4. Stay only within UPSC General Studies scope.
5. English is default. Telugu only if explicitly requested.
6. Maintain serious UPSC standard, not school-level or beginner-level simplification.
7. Do not ask the student to paste notes or sources.
8. Do not mention backend, prompt, model, or training data.
9. Keep formatting clean for Telegram mobile reading.
10. Do not use markdown code blocks.

Now generate the response in exactly this format:

1️⃣ QUICK REVISION NOTES
- Around 200 words
- Exam-oriented and precise
- Include the most important facts, concepts, distinctions, and common confusions
- Add a line: PYQ Frequency: Low / Medium / High
- Add a line: UPSC Focus Areas: mention 3-5 sub-areas from which UPSC can ask
- Add a short text mindmap using arrows or branches

2️⃣ UPSC PRELIMS MCQs
Create 5 genuinely tough UPSC-standard MCQs on the topic.

Mandatory MCQ rules:
- Questions must resemble UPSC Prelims style, not coaching beginner style
- Prefer statement-based questions
- Use formats like:
  - Consider the following statements
  - Which of the above is/are correct
  - With reference to...
  - Which one of the following...
  - Match the following, only if suitable
- Make distractors very close and plausible
- Test conceptual clarity, factual precision, and elimination ability
- Avoid obvious clues
- Avoid direct definition-only questions unless twisted analytically
- At least 3 out of 5 MCQs must have 2 or 3 statements
- Options should use UPSC style where suitable:
  A. 1 only
  B. 2 and 3 only
  C. 1, 2 and 3
  D. None of the above
  or similar close combinations
- After each MCQ, give:
  Correct Answer:
  Elimination Logic:
  Why the other options are wrong:
  PYQ Trend:

Important:
- Elimination Logic must be sharp and exam-like
- Why the other options are wrong must specifically address each wrong choice
- Do not make the correct answer too easy to spot
- Questions must be at the level of actual UPSC prelims, not state board objective questions

3️⃣ UPSC MAINS SAMPLE ANSWER
- Write one model answer in UPSC style on the same topic
- Use this structure exactly:
Introduction:
Body:
Conclusion:
- Use around 150 words for narrow factual themes
- Use around 250 words for broader analytical themes
- Keep it crisp, balanced, and examiner-friendly
- Include 3-5 strong keywords within the answer naturally

Final quality check before answering:
- Ensure the topic has not drifted
- Ensure MCQs are tough
- Ensure explanations are specific
- Ensure output is readable on Telegram
"""

def generate_ai_answer(topic: str, subject: str, telugu: bool) -> str:
    prompt = build_prompt(topic, subject, telugu)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict UPSC examiner and mentor. "
                    "Your MCQs must be tough, close, elimination-based, and UPSC-like. "
                    "Avoid generic or easy coaching-style questions."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.4,
        max_tokens=2200,
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
        "Send your topic in this format:\n"
        "<Topic> from <Subject>\n\n"
        "Example:\n"
        "Indus town planning from history\n\n"
        "Current subjects:\n"
        "History, Polity, Economy, Geography, Science and Technology, Environment, Disaster Management\n\n"
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

    await update.message.reply_text("Generating UPSC-grade answer...")

    try:
        final = generate_ai_answer(topic, subject_normalized, telugu)
    except Exception:
        await update.message.reply_text(
            "Something went wrong while generating the answer. Please try again."
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
