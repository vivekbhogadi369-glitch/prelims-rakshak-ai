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

IMPORTANT SOURCE PRIORITY:

1️⃣ First priority → NCERT History textbooks (Class 6–12)  
2️⃣ Second priority → Faculty history notes  
3️⃣ Third priority → Other uploaded history documents  

Use the uploaded documents as the PRIMARY source.

Rules:
- Prefer NCERT explanations whenever available.
- Use faculty notes to enrich explanations.
- Only use general model knowledge if documents lack information.

Student query:
{user_message}

Answer strictly in this structure:

A. UPSC PRELIMS PYQs (Past 15 years)

B. QUICK REVISION NOTES (minimum 500 words)

Notes must include:
• Clear concept explanation  
• Timeline / chronology  
• Key exam keywords  
• UPSC trap areas  
• Mini mindmap structure  

C. PRACTICE MCQs

Generate exactly **10 UPSC standard MCQs**

Pattern:
5 Statement based questions  
3 Match the following  
2 Factual questions  

Difficulty distribution:
3 Easy  
5 Moderate  
2 Tough  

For EACH MCQ include:

Correct Answer  
Elimination Logic  
Why other options are wrong  
Trap Zone
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
