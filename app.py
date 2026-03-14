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
- If exact PYQs are not available, include PYQs from closely related subtopics.
- For every PYQ, mention the year first in this style:
  2019 - UPSC Prelims
- Then write the question and answer.
- If none exist, write exactly:
No PYQs came from this subtopic so far.

B. QUICK REVISION NOTES (Minimum 500 words)

The notes must look like high-quality UPSC coaching material.

Include the following:

1. **Core Concept Explanation**
   - Explain the topic clearly and concisely.

2. **Chronology / Timeline**
   - If the topic has historical development, provide timeline points.

3. **Key Terms / Exam Keywords**
   - Highlight terms UPSC frequently tests.

4. **UPSC Trap Areas**
   - Mention common conceptual confusions asked in exams.

5. **Mini Mindmap Structure**
   Example format:
   Topic
   ├ Key feature 1
   ├ Key feature 2
   ├ Related concept
   └ Important fact

6. **Map or Location references**
   - Mention geographical locations if relevant.

C. PRACTICE MCQs

Generate **10 UPSC standard MCQs**.

Each MCQ must follow this format:

Question

A. Option  
B. Option  
C. Option  
D. Option  

Correct Answer

Elimination Logic  
- Explain how a student can eliminate wrong options step-by-step.

Why Other Options Are Wrong  
- Brief explanation for each incorrect option.

Trap Zone  
- Mention where UPSC usually confuses aspirants.

Rules:
- Default language: English
- Do not ask the student to paste anything
- Keep the output structured and exam-oriented
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
