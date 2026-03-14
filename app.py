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

--------------------------------------------------

A. UPSC PRELIMS PYQs (Past 15 years)

- List all relevant PYQs from the past 15 years related to the topic.
- If exact PYQs are not available, include PYQs from closely related subtopics.
- For every PYQ mention the year like:

2019 - UPSC Prelims

- Then write the question and answer.

If none exist write exactly:
No PYQs came from this subtopic so far.

--------------------------------------------------

B. QUICK REVISION NOTES (Minimum 500 words)

The notes must look like high quality UPSC coaching material.

Include:

1. Core Concept Explanation
2. Chronology / Timeline if relevant
3. Key Terms / Exam Keywords
4. UPSC Trap Areas
5. Mini Mindmap structure
6. Map or location references if relevant

--------------------------------------------------

C. PRACTICE MCQs

Generate exactly **10 UPSC standard MCQs**.

MCQ Pattern Distribution:

• 5 Statement based questions  
• 3 Match the Following questions  
• 2 Factual questions  

Difficulty Distribution:

• 3 Easy questions  
• 5 Moderately difficult questions  
• 2 Tough questions  

Follow real UPSC style.

Statement based example format:

Consider the following statements:

1. Statement  
2. Statement  
3. Statement  

Which of the above is/are correct?

(a) 1 only  
(b) 1 and 2 only  
(c) 2 and 3 only  
(d) 1, 2 and 3  

Match the following example format:

Match List I with List II.

List I | List II

Choose the correct answer using codes below.

Factual questions should test precise knowledge.

For EACH MCQ include:

Correct Answer

Elimination Logic  
Explain how aspirants can eliminate options.

Why Other Options Are Wrong

Trap Zone  
Mention typical UPSC confusion area.

--------------------------------------------------

Rules:

Default language: English  
Do not ask students to paste anything  
Keep the output clean, exam-oriented and structured
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
