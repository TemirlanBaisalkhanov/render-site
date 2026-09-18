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
            return "Регистрация успешна! Теперь подтвердите почту. <a href='https://mail.google.com/'>Открыть почту</a>"
        except Exception as e:
            return f"Ошибка: {e}"
    return '''
        <a href="/login">Или войти?</a>
        <form method="post">
            Email: <input name="email" type="email" required><br>
            Пароль: <input name="password" type="password" required><br>
            <button type="submit">Зарегистрироваться</button>
        </form>
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
        <a href="/signup">Или зарегистрироваться?</a>
        <form method="post">
            Email: <input name="email" type="email" required><br>
            Пароль: <input name="password" type="password" required><br>
            <a href="/#">Забыли пароль?</a>
            <button type="submit">Войти</button>
        </form>
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

    html = "<a href='/create'>Создать</a><a href='/logout'>Выйти</a><ul>"
    for note in notes:
        html += f'<li>{note["headline"]}: {note["text"]}</li>'
    html += "</ul>"

    return html

@app.route("/create")
def create():
    if "access_token" not in session:
        return redirect(url_for("login"))

    html = "<button onclick='window.history.back()'>Назад</button><a href='/logout'>Выйти</a>"
    html += '''
        <form method="post" action="/add">
            <input name="headline" placeholder="Заголовок" required>
            <input name="text" placeholder="Новая заметка" required>
            <button type="submit">Создать</button>
        </form>
    '''
    return html

@app.route("/add", methods=["POST"])
def add():
    if "access_token" not in session:
        return redirect(url_for("login"))

    headline = request.form["headline"]
    text = request.form["text"]
    client = get_client()
    client.table("notes").insert({"headline": headline,"text": text, "id_user": session["id_user"]}).execute()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
