from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

Student query:
{user_message}

Answer strictly in the following structure:

A. UPSC PRELIMS PYQs (Past 15 years)
- List all relevant PYQs from the past 15 years related to the topic.
- For every PYQ, mention the year first in this style:
  2019 - UPSC Prelims
- Then write the question and answer.
- If none exist, write exactly:
No PYQs came from this subtopic so far.

B. QUICK REVISION NOTES (Minimum 500 words)
Include:
- Key concepts
- Timeline if applicable
- Map/location references if relevant
- Mindmap-style bullet structure

C. PRACTICE MCQs
Generate 10 UPSC standard MCQs.

For each MCQ include:
- Correct answer
- Elimination logic
- Why other options are wrong
- Trap zone where aspirants usually get confused

Rules:
- Default language: English
- Do not ask the student to paste anything
- Keep the output clean, exam-oriented, and structured
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        answer = response.output[0].content[0].text

        return jsonify({"answer": answer})

    except Exception as e:
        return jsonify({"answer": f"Error: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
