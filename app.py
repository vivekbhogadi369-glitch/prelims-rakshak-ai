from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os
import traceback

app = Flask(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=120
)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"answer": "Error: Please enter topic, subject."})

        prompt = f"""
You are Prelims Rakshak AI created by Vivek Sir for UPSC aspirants.

Student question:
{user_message}

Answer strictly in this format:

A. UPSC PRELIMS PYQs (Past 15 years)

B. QUICK REVISION NOTES (500 words with timeline, mindmap and map pointers)

C. PRACTICE MCQs (10 UPSC standard MCQs with elimination explanation and trap zones)

If PYQs are not available say exactly:
No PYQs came from this subtopic so far.
"""

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt,
            max_output_tokens=1200
        )

        answer = response.output[0].content[0].text

    except Exception as e:
        answer = "Error: " + str(e) + "\n\n" + traceback.format_exc()

    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
