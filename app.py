from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"answer": "Please enter topic, subject."})

        prompt = f"""
You are Prelims Rakshak AI created by Vivek Sir for UPSC aspirants.

Use uploaded documents as the primary source.

GLOBAL RULES:
- Do NOT include references
- Do NOT include citations
- Do NOT include source names
- Do NOT include follow-up questions
- Do NOT include supplementary questions
- Do NOT print divider lines
- Do NOT print separator lines like --- or ____ or ===
- Do NOT add any extra section beyond A, B and C
- End the full answer with exactly this sentence:
All the best for your preparation.

Student query:
{user_message}

Answer strictly in this structure only:

A. UPSC PRELIMS PYQs (Past 10 Years)

Rules:
- Search uploaded PYQ PDFs first
- Use exact topic match first
- If exact PYQs are limited, include closely related PYQs from the same chapter/topic family
- Do NOT invent PYQs
- Do NOT invent years
- Do NOT copy explanation text from the PDF
- Extract only the question, options and answer from the uploaded PYQ PDFs
- Generate your own fresh short analysis

For every PYQ use this exact format:

2019 - UPSC Prelims
Question:
Correct Answer:
PYQ INSIGHT:
PYQ TAG:

Under PYQ INSIGHT, include only:
- Concept Tested
- Why UPSC asked this
- Elimination Hint
- One-line Takeaway

Under PYQ TAG, include only:
- Topic Frequency
- Last Asked Year
- Nature
- Difficulty

For Topic Frequency use only:
High / Medium / Low

For Nature use only:
Factual / Conceptual / Analytical

For Difficulty use only:
Easy / Moderate / Tough

If no exact or closely related PYQs are found, write exactly:
No PYQs came from this subtopic so far.

B. QUICK REVISION NOTES

At the beginning of this section, write exactly:
Here are your quick revision notes on {user_message} for your exam.

At the end of this section, write exactly:
Best wishes for your preparation.

Rules:
- Minimum around 700 words
- Prefer short, crisp bullet points
- Avoid long dull paragraphs
- Use clean headings only
- Include:
Introduction
Background
Core Features
Important Sites
Chronology
UPSC Trap Zone
Revision Takeaway
- Include one small table wherever useful
- Include one short chronology block wherever relevant
- Include one plain-text flowchart or hierarchy wherever useful
- Mention important sites, rivers, capitals, regions, or geographic references wherever relevant
- Include one UPSC Trap Zone
- Include one one-line revision takeaway
- Make it look like polished coaching notes, not AI output
- Keep it visually organized and revision-friendly

C. PRACTICE MCQs

Generate exactly 10 UPSC Prelims standard MCQs.

Distribution:
- 5 statement-based questions
- 3 match-the-following questions
- 2 factual but tricky questions

Difficulty:
- 3 easy
- 5 moderate
- 2 tough

Strict format for every MCQ:
Question:
Options:
Correct Answer:
Elimination Logic:
Why other options are wrong:
Trap Zone:

Rules:
- Do NOT repeat PYQs directly unless absolutely necessary
- Keep MCQs linked to the same concept family as the user query
- Make them UPSC-style, not school-style
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 30
                }
            ]
        )

        answer = "Error: No answer generated."

        for item in response.output:
            if getattr(item, "type", "") == "message":
                contents = getattr(item, "content", [])
                for content in contents:
                    if getattr(content, "type", "") in ["output_text", "text"]:
                        answer = getattr(content, "text", "Error: No answer generated.")
                        break
                if answer != "Error: No answer generated.":
                    break

        return jsonify({"answer": answer})

    except Exception as e:
        return jsonify({"answer": f"Error: {str(e)}"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
