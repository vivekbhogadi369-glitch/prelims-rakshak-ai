import os
import json
import re
import html
import urllib.request
from datetime import date
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from openai import OpenAI  # still used only for clean formatting (optional)
from PyPDF2 import PdfReader

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

# ===================== PYQ Fetch + Cache =====================
CACHE_DIR = Path("pyq_cache")
CACHE_DIR.mkdir(exist_ok=True)

def fetch_url(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")

def download_file(url: str, out_path: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out_path.write_bytes(r.read())

def find_gs1_pdf_url_from_upsc_year_page(year: int) -> str | None:
    """
    Official UPSC year page example:
    https://upsc.gov.in/examinations/question-papers/question-papers-year-2015

    We parse HTML and find the PDF link for:
    "Civil Services (Preliminary) Examination, <year>" -> "General Studies Paper - I"
    """
    year_url = f"https://upsc.gov.in/examinations/question-papers/question-papers-year-{year}"
    try:
        page = fetch_url(year_url)
    except Exception:
        return None

    # Narrow down near the Civil Services (Preliminary) block for that year
    # We then find the first PDF link near "General Studies Paper - I"
    # UPSC pages typically contain href="/sites/default/files/....pdf"
    page_l = page.lower()

    # Try to locate section
    idx = page_l.find(f"civil services (preliminary) examination, {year}".lower())
    snippet = page if idx == -1 else page[idx: idx + 20000]

    # Find link text occurrences around "General Studies Paper - I"
    # We'll extract candidate PDF hrefs and pick the one closest after that text.
    # Pattern: href="...pdf"
    hrefs = [(m.start(), html.unescape(m.group(1))) for m in re.finditer(r'href="([^"]+\.pdf)"', snippet, flags=re.IGNORECASE)]
    if not hrefs:
        return None

    # Find position of "General Studies Paper - I"
    gs_pos = snippet.lower().find("general studies paper - i")
    if gs_pos == -1:
        # fallback: "general studies paper-i"
        gs_pos = snippet.lower().find("general studies paper-i")
    if gs_pos == -1:
        return None

    # Pick first pdf link that appears after the gs_pos
    for pos, href in hrefs:
        if pos > gs_pos:
            if href.startswith("/"):
                return "https://upsc.gov.in" + href
            return href

    return None

def pdf_text_cached(year: int) -> str | None:
    """
    Downloads GS Paper-1 PDF for that year from official UPSC page,
    caches it locally, extracts text using PyPDF2, and caches extracted text.
    """
    txt_path = CACHE_DIR / f"csp_prelims_gs1_{year}.txt"
    pdf_path = CACHE_DIR / f"csp_prelims_gs1_{year}.pdf"

    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8", errors="ignore")

    pdf_url = find_gs1_pdf_url_from_upsc_year_page(year)
    if not pdf_url:
        return None

    if not pdf_path.exists():
        try:
            download_file(pdf_url, pdf_path)
        except Exception:
            return None

    try:
        reader = PdfReader(str(pdf_path))
        text_parts = []
        for p in reader.pages:
            t = p.extract_text() or ""
            text_parts.append(t)
        full_text = "\n".join(text_parts)
        txt_path.write_text(full_text, encoding="utf-8", errors="ignore")
        return full_text
    except Exception:
        return None

def split_questions(text: str) -> list[str]:
    """
    Best-effort split of UPSC PDF text into individual question blocks.
    UPSC PDFs vary, so we keep it robust and simple.
    """
    if not text:
        return []

    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)

    # Split on patterns like:
    # 1.  / 1 ) / 1) / 1 -
    parts = re.split(r"\n\s*(\d{1,3})\s*[\.\)\-]\s+", cleaned)

    # If split didn't work, fallback to returning whole text
    if len(parts) < 3:
        return []

    # parts format: [preamble, qno1, qtext1, qno2, qtext2, ...]
    questions = []
    for i in range(1, len(parts) - 1, 2):
        qno = parts[i].strip()
        qtext = parts[i + 1].strip()
        if qtext and len(qtext) > 20:
            questions.append(f"{qno}. {qtext}")
    return questions

def keyword_list(topic: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", topic.lower())
    # remove ultra-common words
    stop = {"the", "and", "from", "with", "into", "about", "india", "indian", "paper", "prelims"}
    words = [w for w in words if w not in stop]
    # keep unique order
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:6]  # keep small

def match_questions(questions: list[str], topic: str) -> list[str]:
    keys = keyword_list(topic)
    if not keys:
        return []

    matched = []
    for q in questions:
        ql = q.lower()
        score = sum(1 for k in keys if k in ql)
        # require at least 1 keyword match; for multi-word topics this works well
        if score >= 1:
            matched.append(q)

    return matched

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
    parts = text.split(" from ", 1)
    topic = parts[0].strip()
    subject = parts[1].strip()
    if not topic or not subject:
        return None, None
    return topic, subject

def user_requested_telugu(text: str) -> bool:
    if not text:
        return False
    # Telugu script range OR explicit keywords
    if re.search(r"[\u0C00-\u0C7F]", text):
        return True
    if "telugu" in text.lower() or "తెలుగు" in text:
        return True
    return False

# ===================== Handlers =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Hello 👋 Prelims Rakshak AI is live.\n"
        "Which PYQs you want?\n\n"
        "✅ Format:\n"
        "<Topic> from <Subject>\n\n"
        "Example:\n"
        "Indus town planning from Indian history\n\n"
        "📌 Current mode: UPSC Prelims GS Paper-1 PYQs (last 15 years) from official UPSC website."
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

    # Telugu ONLY if user asked
    telugu = user_requested_telugu(text)

    await update.message.reply_text("Searching official UPSC PYQs (last 15 years)…")

    current_year = date.today().year
    years = list(range(current_year, current_year - 15, -1))

    results = []
    scanned_years = 0

    for y in years:
        t = pdf_text_cached(y)
        if not t:
            continue
        scanned_years += 1
        qs = split_questions(t)
        if not qs:
            continue
        matched = match_questions(qs, topic)
        if matched:
            # keep first 25 per year to avoid Telegram wall-of-text
            matched = matched[:25]
            results.append((y, matched))

    if not results:
        if telugu:
            await update.message.reply_text(
                f"ఈ టాపిక్‌పై గత 15 సంవత్సరాల UPSC Prelims GS1 ప్రశ్నాపత్రాల్లో స్పష్టమైన మ్యాచ్ కనిపించలేదు.\n"
                f"టిప్: టాపిక్‌ను మరింత specific keyword‌తో ఇవ్వండి (ఉదా: 'GDP deflator', 'GVA', 'NDP')."
            )
        else:
            await update.message.reply_text(
                "No clear match found in last 15 years UPSC Prelims GS1 papers.\n"
                "Tip: Use a more specific keyword (e.g., 'GDP deflator', 'GVA', 'NDP')."
            )
        return

    # Build final response
    lines = []
    if telugu:
        lines.append(f"✅ టాపిక్: {topic} | సబ్జెక్ట్: {subject}")
        lines.append(f"🔎 UPSC అధికారిక ప్రశ్నాపత్రాల నుంచి (గత 15 సంవత్సరాలు) మ్యాచ్ అయిన PYQs:\n")
    else:
        lines.append(f"✅ Topic: {topic} | Subject: {subject}")
        lines.append(f"🔎 Matching PYQs from official UPSC papers (last 15 years):\n")

    for (y, qs) in sorted(results, key=lambda x: x[0], reverse=True):
        lines.append(f"📌 {y} (GS Paper 1):")
        for q in qs:
            # shorten very long lines
            q2 = q.strip()
            if len(q2) > 450:
                q2 = q2[:450] + "…"
            lines.append(f"- {q2}")
        lines.append("")

    # Telegram message size limit protection
    final = "\n".join(lines)
    if len(final) > 3500:
        final = final[:3500] + "\n\n[Output trimmed due to Telegram limit. Use more specific keyword to narrow results.]"

    await update.message.reply_text(final)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
