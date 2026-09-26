import os
from flask import Flask, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv
import json

load_dotenv()

DOMAIN = "https://anymynote.vercel.app/"
EMAIL = "https://mail.google.com/"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-please")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def get_embedding(text):
    response = get_client().functions.invoke(
        "generate-embedding",
        invoke_options={"body": {"text": text}}
    )
    if isinstance(response, bytes):
        response = response.decode("utf-8")
    data = json.loads(response)
    if "embedding" not in data:
        raise Exception(f"Функция вернула: {data}")
    return data["embedding"]

def get_client():
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if "access_token" in session:
        client.postgrest.auth(session["access_token"])
    return client

@app.route("/add", methods=["POST"])
def add():
    if "access_token" not in session:
        return redirect(url_for("login"))

    headline = request.form["headline"]
    text = request.form["text"]
    client = get_client()

    try:
        embedding = get_embedding(text)
        result = client.table("notes").insert({
            "headline": headline,
            "text": text,
            "id_user": session["user_id"],
            "embedding": embedding
        }).execute()

        new_note_id = result.data[0]["id_note"]

        matches = client.rpc("match_notes", {
            "query_embedding": embedding,
            "match_user_id": session["user_id"],
            "match_note_id": new_note_id,
            "match_count": 5
        }).execute()

        for match in matches.data:
            client.table("note_edges").insert({
                "note_id": new_note_id,
                "related_note_id": match["id_note"],
                "similarity": match["similarity"]
            }).execute()

    except Exception as e:
        return f"Ошибка при добавлении: {e}"

    return redirect(url_for("home"))

@app.route("/edit", methods=["POST"])
def edit():
    if "access_token" not in session:
        return redirect(url_for("login"))
    
    id_note = request.form["id_note"]
    headline = request.form["headline"]
    text = request.form["text"]

    client = get_client()
    
    client.table("notes")\
        .update({"headline": headline, "text": text})\
        .eq("id_note", id_note)\
        .eq("id_user", session["user_id"])\
        .execute()

    return redirect(url_for("home"))

#В разработке
@app.route("/reset-password", methods=["POST"])
def reset_password_submit():
    data = request.get_json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    password = data.get("password")

    if not access_token:
        return "Ошибка: токен не найден. Откройте ссылку из письма заново.", 400

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        client.auth.set_session(access_token, refresh_token)
        client.auth.update_user({"password": password})
        return "Пароль изменён! Сейчас перекинем на вход."
    except Exception as e:
        return f"Ошибка: {e}", 400

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        try:
            client.auth.sign_up({"email": email, "password": password})
            return f"Регистрация успешна! Теперь подтвердите почту. <a href='{EMAIL}'>Открыть почту</a>"
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
            session["email"] = result.user.email
            return redirect(url_for("home"))
        except Exception as e:
            return f"Ошибка входа: {e}"
    return '''
        <a href="/signup">Или зарегистрироваться?</a>
        <form method="post">
            Email: <input name="email" type="email" required><br>
            Пароль: <input name="password" type="password" required><br>
            <a href="/forgot">Забыли пароль?</a>
            <button type="submit">Войти</button>
        </form>
    '''

@app.route("/")
def home():
    if "access_token" not in session:
        return redirect(url_for("login"))

    client = get_client()
    response = client.table("notes").select("*").execute()
    notes = response.data

    html = f"<a href='/create'>Создать</a><p>{session.get('email')}</p><a href='/logout'>Выйти</a><ul>"
    for note in notes:
        html += f"""<li><a href='/change?id={note["id_note"]}'>{note["headline"]}: {note["text"]} (Создано:  <span class='date' data-date='{note["created_at"]}'></span>)</a></li>"""
    html += "</ul>"

    html += '''
        <script>
            document.querySelectorAll(".date").forEach(element => {
                let utcString = element.dataset.date;
                utcString = utcString.replace(" ", "T");

                const date = new Date(utcString);

                element.textContent = date.toLocaleString("ru-RU");
            });
        </script>
    '''
    return html

@app.route("/create")
def create():
    if "access_token" not in session:
        return redirect(url_for("login"))

    html = f"<button onclick='window.history.back()'>Назад</button><p>{session.get('email')}</p><a href='/logout'>Выйти</a>"
    html += '''
        <form method="post" action="/add">
            <input name="headline" placeholder="Заголовок" required>
            <input name="text" placeholder="Новая заметка" required>
            <button type="submit">Создать</button>
        </form>
    '''
    return html

@app.route("/change")
def change():
    if "access_token" not in session:
        return redirect(url_for("login"))
    
    id_note = request.args.get("id")

    client = get_client()
    response = client.table("notes").select("*").eq("id_note", id_note).execute()
    if not response.data:
        return "Заметка не найдена", 404
    note = response.data[0]

    html = f"<button onclick='window.history.back()'>Назад</button><p>{session.get('email')}</p><a href='/logout'>Выйти</a>"
    html += f"Создано:  <span class='date' data-date='{note["created_at"]}'></span>"
    
    html += f'''
        <form method="post" action="/edit">
            <input type="hidden" name="id_note" value="{id_note}">
            <input name="headline" value='{note["headline"]}' required>
            <input name="text" value='{note["text"]}' required>
            <button type="submit">Изменить</button>
        </form>
    '''
    html += '''
        <script>
            document.querySelectorAll(".date").forEach(element => {
                let utcString = element.dataset.date;
                utcString = utcString.replace(" ", "T");

                const date = new Date(utcString);

                element.textContent = date.toLocaleString("ru-RU");
            });
        </script>
    '''
    return html

#В разработке
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form["email"]
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        try:
            client.auth.reset_password_email(
                email,
                {"redirect_to": DOMAIN + "//reset-password"}
            )
            return "Письмо для сброса пароля отправлено, проверьте почту."
        except Exception as e:
            return f"Ошибка: {e}"
    return '''
        <button onclick='window.history.back()'>Назад</button>
        <form method="post">
            Email: <input name="email" type="email" required><br>
            <button type="submit">Отправить ссылку для сброса</button>
        </form>
    '''

@app.route("/reset-password", methods=["GET"])
def reset_password_page():
    return '''
        <button onclick='window.history.back()'>Назад</button>
        <form id="resetForm">
            <input type="password" id="password" placeholder="Новый пароль" required minlength="6">
            <button type="submit">Сохранить</button>
        </form>
        <p id="msg"></p>
        <script>
            const hash = window.location.hash.substring(1);
            const params = new URLSearchParams(hash);
            const access_token = params.get("access_token");
            const refresh_token = params.get("refresh_token");

            document.getElementById("resetForm").addEventListener("submit", async (e) => {
                e.preventDefault();
                const password = document.getElementById("password").value;

                const res = await fetch("/reset-password", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({access_token, refresh_token, password})
                });
                const text = await res.text();
                document.getElementById("msg").textContent = text;
                if (res.ok) {
                    setTimeout(() => window.location.href = "/login", 1500);
                }
            });
        </script>
    '''

if __name__ == "__main__":
    app.run(debug=True)
