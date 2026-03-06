import os
import json
import re
from datetime import date

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

if not TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")

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

# ===================== PYQ BANK =====================
PYQ_FILE = "pyq_bank.json"

def load_pyq_bank():
    try:
        with open(PYQ_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []

PYQ_BANK = load_pyq_bank()

# ===================== Input parsing =====================

def parse_topic_subject(text: str):
    """
    Expected:
    <Topic> from <Subject>
    Example:
    Indus town planning from Indian history
    """
    if not text:
        return None, None
    if " from " not in text.lower():
        return None, None

    match = re.split(r"\s+from\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(match) != 2:
        return None, None

    topic = match[0].strip()
    subject = match[1].strip()

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

def keyword_list(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    stop = {
        "the", "and", "from", "with", "into", "about", "paper", "prelims",
        "indian", "india", "general", "studies", "topic", "subject"
    }
    out = []
    seen = set()
    for w in words:
        if w not in stop and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:8]

def search_pyq_bank(topic: str, subject: str):
    topic_keys = keyword_list(topic)
    subject_l = subject.lower().strip()

    results = []

    for item in PYQ_BANK:
        item_subject = str(item.get("subject", "")).strip()
        item_topic = str(item.get("topic", "")).strip()
        item_question = str(item.get("question_text", "")).strip()

        combined = f"{item_subject} {item_topic} {item_question}".lower()

        subject_match = subject_l in item_subject.lower() or item_subject.lower() in subject_l

        topic_score = sum(1 for k in topic_keys if k in combined)

        if subject_match and topic_score >= 1:
            results.append(item)

    results.sort(key=lambda x: x.get("year", 0), reverse=True)
    return results

# ===================== Handlers =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Hello 👋 Prelims Rakshak AI is live.\n"
        "Which PYQs you want?\n\n"
        "✅ Format:\n"
        "<Topic> from <Subject>\n\n"
        "Example:\n"
        "Indus town planning from Indian history\n\n"
        "📌 Current mode: UPSC Prelims GS Paper-1 PYQs (from PYQ bank compiled from official UPSC papers)."
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
    if not topic:
        await update.message.reply_text(
            "Please use this format:\n"
            "<Topic> from <Subject>\n\n"
            "Example:\n"
            "Indus town planning from Indian history"
        )
        return

    inc_today(user_id)

    telugu = user_requested_telugu(text)

    await update.message.reply_text("Searching PYQ bank...")

    results = search_pyq_bank(topic, subject)

    if not results:
        if telugu:
            await update.message.reply_text(
                "ఈ టాపిక్‌పై స్పష్టమైన మ్యాచ్ కనిపించలేదు.\n"
                "టిప్: మరింత specific keyword వాడండి."
            )
        else:
            await update.message.reply_text(
                "No clear match found in the PYQ bank.\n"
                "Tip: Use a more specific keyword."
            )
        return

    lines = []
    if telugu:
        lines.append(f"✅ టాపిక్: {topic} | సబ్జెక్ట్: {subject}")
        lines.append("🔎 మ్యాచ్ అయిన PYQs:\n")
    else:
        lines.append(f"✅ Topic: {topic} | Subject: {subject}")
        lines.append("🔎 Matching PYQs:\n")

    for item in results[:20]:
        year = item.get("year", "Unknown")
        paper = item.get("paper", "GS1")
        qtext = str(item.get("question_text", "")).strip()
        source = item.get("source", "")
        source_url = item.get("source_url", "")

        if len(qtext) > 450:
            qtext = qtext[:450] + "…"

        lines.append(f"📌 {year} ({paper})")
        lines.append(f"- {qtext}")
        if source:
            lines.append(f"Source: {source}")
        if source_url:
            lines.append(f"Link: {source_url}")
        lines.append("")

    final = "\n".join(lines)

    if len(final) > 3500:
        final = final[:3500] + "\n\n[Output trimmed due to Telegram limit.]"

    await update.message.reply_text(final)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
