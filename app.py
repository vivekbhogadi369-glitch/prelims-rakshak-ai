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

SOURCE PRIORITY:
1. First priority -> NCERT History textbooks (Class 6 to 12)
2. Second priority -> Uploaded History textbook
3. Third priority -> Other uploaded history documents

Use the uploaded documents as the PRIMARY source.

General Rules:
- Prefer NCERT explanations whenever available.
- Use the additional textbook to enrich explanations.
- Use general model knowledge only if the documents do not contain enough information.
- Do NOT include references.
- Do NOT include citations.
- Do NOT include source names.
- Do NOT include supplementary questions.
- Do NOT include follow-up questions.
- Do NOT include "Would you like..." style endings.
- Do NOT add any extra section beyond A, B and C.
- End the full answer with exactly this sentence:
All the best for your preparation.

Student query:
{user_message}

Answer strictly in this structure only:

A. UPSC PRELIMS PYQs (Past 15 years)

- List relevant PYQs if available.
- If exact PYQs are not available, include closely related PYQs.
- For every PYQ mention the year like:
2019 - UPSC Prelims
- Then write the question and answer.
- If none exist, write exactly:
No PYQs came from this subtopic so far.

B. QUICK REVISION NOTES

At the beginning of this section, write exactly:
Here are your quick revision notes on {user_message} for your exam.

At the end of this section, write exactly:
Best wishes for your preparation.

Important:
- Do NOT write phrases like "UPSC Coaching Style", "Quick Revision Notes (UPSC Coaching Style)", or any bracketed heading.
- Do NOT show template labels or meta-headings.
- Do NOT show numbering like "1. Topic Title" or "2. Brief Introduction".

Use natural, attractive headings such as:
Introduction
Background
Core Features
Administrative Structure
Important Sites
Chronology
UPSC Trap Zone
Revision Takeaway

Formatting rules for Quick Revision Notes:
- Minimum around 700 words
- Prefer short, crisp bullet points
- Avoid long dull paragraphs
- Use clean headings
- Include one small table wherever useful
- Include one short chronology block wherever relevant
- Include one plain-text flowchart or hierarchy wherever useful
- Mention important sites, rivers, capitals, regions, or geographic references wherever relevant
- Include one UPSC Trap Zone
- Include one one-line revision takeaway
- Make it look like polished coaching notes, not AI output
- Make it visually organized and revision-friendly

C. PRACTICE MCQs

Generate exactly 10 UPSC Prelims standard MCQs.

STRICT DISTRIBUTION:
- 5 statement-based questions
- 3 match-the-following questions
- 2 factual but tricky questions

STRICT DIFFICULTY:
- 3 easy
- 5 moderate
- 2 tough

ADVANCED UPSC RULES:
1. Questions must resemble real UPSC PYQs.
2. Avoid direct/static questions.
3. Use chronology, location, administration, economy, culture, and terminology.
4. At least 3 questions should interlink topics.
5. At least 2 statement questions should have close/confusing options.
6. Use negative statements occasionally.
7. Include assertion-reason style in at least 1 question.
8. Include chronology-based arrangement in at least 1 question.
9. Include map/location logic in at least 1 question.
10. Include at least 1 question based on a small NCERT fact.

FOR EACH MCQ GIVE:
1. Question
2. Options
3. Correct Answer
4. Elimination Logic
5. Why other options are wrong
6. Trap Zone
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 10
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
