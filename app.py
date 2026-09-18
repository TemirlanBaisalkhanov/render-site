import os
from flask import Flask
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()  # для локального теста; на Render переменные берутся из Environment

app = Flask(__name__)

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

@app.route("/")
def home():
    response = supabase.table("notes").select("*").execute()
    notes = response.data

    html = "<h1>Заметки</h1><ul>"
    for note in notes:
        html += f'<li>{note["text"]}</li>'
    html += "</ul>"
    return html

@app.route("/add/<text>")
def add(text):
    supabase.table("notes").insert({"text": text}).execute()
    return f"Добавлено: {text}"

if __name__ == "__main__":
    app.run(debug=True)
