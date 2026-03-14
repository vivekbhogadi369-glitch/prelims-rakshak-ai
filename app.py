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

The answers MUST come from the faculty uploaded history documents.

Student query:
{user_message}

Answer strictly in this structure:

A. UPSC PRELIMS PYQs (Past 15 years)

B. QUICK REVISION NOTES (minimum 500 words)
Include:
- concept explanation
- timeline
- key exam terms
- UPSC trap areas
- mini mindmap structure

C. PRACTICE MCQs

Generate exactly 10 UPSC standard MCQs:

Pattern:
5 Statement based
3 Match the following
2 Factual

Difficulty:
3 Easy
5 Moderate
2 Tough

For each MCQ include:
- Correct answer
- Elimination logic
- Why other options are wrong
- Trap zone
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID]
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
