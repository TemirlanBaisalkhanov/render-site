import os
from flask import Flask, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-please")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_client():
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if "access_token" in session:
        client.postgrest.auth(session["access_token"])
    return client

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        try:
            client.auth.sign_up({"email": email, "password": password})
            return "Регистрация успешна! Теперь войдите. <a href='/login'>Войти</a>"
        except Exception as e:
            return f"Ошибка: {e}"
    return '''
        <h1>Регистрация</h1>
        <form method="post">
            Email: <input name="email" type="email" required><br>
            Пароль: <input name="password" type="password" required><br>
            <button type="submit">Зарегистрироваться</button>
        </form>
        <a href="/login">Уже есть аккаунт? Войти</a>
    '''

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        try:
            result = client.auth.sign_in_with_password({"email": email, "password": password})
            session["access_token"] = result.session.access_token
            session["user_id"] = result.user.id
            return redirect(url_for("home"))
        except Exception as e:
            return f"Ошибка входа: {e}"
    return '''
        <h1>Вход</h1>
        <form method="post">
            Email: <input name="email" type="email" required><br>
            Пароль: <input name="password" type="password" required><br>
            <button type="submit">Войти</button>
        </form>
        <a href="/signup">Нет аккаунта? Зарегистрироваться</a>
    '''

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def home():
    if "access_token" not in session:
        return redirect(url_for("login"))

    client = get_client()
    response = client.table("notes").select("*").execute()
    notes = response.data

    html = "<h1>Мои заметки</h1><p><a href='/logout'>Выйти</a></p><ul>"
    for note in notes:
        html += f'<li>{note["text"]}</li>'
    html += "</ul>"
    html += '''
        <form method="post" action="/add">
            <input name="text" placeholder="Новая заметка" required>
            <button type="submit">Добавить</button>
        </form>
    '''
    return html

@app.route("/add", methods=["POST"])
def add():
    if "access_token" not in session:
        return redirect(url_for("login"))

    text = request.form["text"]
    client = get_client()
    client.table("notes").insert({"text": text, "user_id": session["user_id"]}).execute()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
