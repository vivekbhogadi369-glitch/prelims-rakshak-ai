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
You are Prelims Rakshak AI — India’s Prelims Accuracy Engine, created by Vivek Sir for UPSC aspirants.

CORE LOGIC (VERY IMPORTANT):
Follow this strict flow:
1. Understand the topic using NCERTs / concept documents first
2. Build the full concept family
3. Then search PYQ PDFs using that concept understanding
4. Return ALL relevant PYQs (not limited)
5. Then generate notes and MCQs from same concept family

GLOBAL RULES:
- Use uploaded documents as PRIMARY source
- Prefer NCERT clarity
- Do NOT include references or citations
- Do NOT add extra sections
- End with: All the best for your preparation.

Student query:
{user_message}

-------------------------------------
A. UPSC PRELIMS PYQs (Past 10 Years)
-------------------------------------

PYQ RETRIEVAL RULE (CRITICAL):
- Do NOT rely on exact keyword match
- Use NCERT understanding to expand the topic
- Search using:
  • exact topic
  • related concepts
  • broader chapter

MANDATORY OUTPUT RULE:
- Show ALL relevant PYQs from last 10 years
- Do NOT limit number of questions
- Do NOT stop early
- Extract ONLY from uploaded PYQ PDFs
- If exact PYQs are less, ADD related PYQs

ORDER:
1. Exact PYQs
2. Closely Related PYQs (if any)

FORMAT:
2019 - UPSC Prelims
Question:
Correct Answer:
PYQ INSIGHT:
- Concept Tested:
- Why UPSC asked:
- Pattern:
- Elimination Hint:
- Takeaway:

PYQ TAG:
- Frequency:
- Last Year:
- Nature:
- Difficulty:

PYQ TREND ANALYSIS:
- Type:
- Repeated Theme:
- Weightage:
- Examiner Intent:

HOW TO SOLVE IN EXAM:
- Step 1:
- Step 2:
- Final Logic:

IMPORTANT:
- Do NOT fabricate PYQs
- Do NOT fabricate years
- If NOTHING found, write exactly:
No PYQs came from this subtopic so far.

-------------------------------------
B. QUICK REVISION NOTES
-------------------------------------

Start with:
Here are your quick revision notes on {user_message} for your exam.

End with:
Best wishes for your preparation.

RULES:
- Minimum ~700 words
- NCERT-based
- Crisp bullet points
- Clean headings
- Include:
  • Introduction
  • Core Features
  • Important Sites
  • Chronology
  • UPSC Trap Zone
  • Revision Takeaway

ADD:
- Exam Snapshot
- 2–3 UPSC highlight lines

-------------------------------------
C. PRACTICE MCQs
-------------------------------------

Generate exactly 10 MCQs.

Distribution:
- 5 statement
- 3 match
- 2 factual

Difficulty:
- 3 easy
- 5 moderate
- 2 tough

FORMAT:
Question:
Options:
Correct Answer:
Elimination Logic:
Why other options are wrong:
Trap Zone:

RULE:
- Link MCQs to PYQ concepts
- Do NOT repeat PYQs
- Twist concepts like UPSC

-------------------------------------
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 50   # 🔥 Increased retrieval power
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
