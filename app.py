from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return "Prelims Rakshak AI is Live 🚀"

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_message = data.get("message", "")

    response = client.responses.create(
        model="gpt-5-mini",
        input=f"You are Prelims Rakshak AI. Reply briefly. User: {user_message}"
    )

    return jsonify({
        "answer": response.output_text
    })
