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
        data = request.get_json()
        user_message = data.get("message", "")

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=user_message
        )

        answer = response.output[0].content[0].text

        return jsonify({"answer": answer})

    except Exception as e:
        return jsonify({"answer": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
