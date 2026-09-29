import os
from flask import Flask, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv
from flask_babel import Babel, gettext as _
import json

load_dotenv()

DOMAIN = "https://anymynote.vercel.app/"
EMAIL = "https://mail.google.com/"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-please")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase_admin = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)

# --- Flask-Babel: настройка многоязычности ---
LANGUAGES = ["ru", "kk", "en"]

app.config["BABEL_DEFAULT_LOCALE"] = "ru"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"


def get_locale():
    # 1) если пользователь сам выбрал язык — используем его
    if "lang" in session and session["lang"] in LANGUAGES:
        return session["lang"]
    # 2) иначе смотрим язык браузера
    return request.accept_languages.best_match(LANGUAGES) or "ru"


babel = Babel(app, locale_selector=get_locale)


@app.route("/set-language/<lang>")
def set_language(lang):
    if lang in LANGUAGES:
        session["lang"] = lang
    return redirect(request.referrer or url_for("home"))


def language_switcher():
    return '''
        <div>
            <a href="/set-language/ru">RU</a> |
            <a href="/set-language/kk">KK</a> |
            <a href="/set-language/en">EN</a>
        </div>
    '''


def truncate(text, length):
    return text[:length] + "..." if len(text) > length else text


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
    updated_at = request.form["updated_at"]

    client = get_client()

    try:
        embedding = get_embedding(text)
        result = client.table("notes").insert({
            "headline": headline,
            "text": text,
            "id_user": session["user_id"],
            "embedding": embedding,
            "updated_at": updated_at
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
        return f"{_('Ошибка при добавлении')}: {e}"

    return redirect(url_for("home"))


@app.route("/edit", methods=["POST"])
def edit():
    if "access_token" not in session:
        return redirect(url_for("login"))

    id_note = request.form["id_note"]
    headline = request.form["headline"]
    text = request.form["text"]
    updated_at = request.form["updated_at"]

    client = get_client()

    try:
        old = client.table("notes").select("embedding").eq("id_note", id_note).execute()
        old_embedding = old.data[0]["embedding"]

        if isinstance(old_embedding, str):
            old_embedding = json.loads(old_embedding)

        new_embedding = get_embedding(text)

        similarity = sum(a * b for a, b in zip(old_embedding, new_embedding))

        client.table("notes")\
            .update({"headline": headline, "text": text, "embedding": new_embedding, "updated_at": updated_at})\
            .eq("id_note", id_note)\
            .eq("id_user", session["user_id"])\
            .execute()

        THRESHOLD = 0.92

        if similarity < THRESHOLD:
            client.table("note_edges").delete().eq("note_id", id_note).execute()
            client.table("note_edges").delete().eq("related_note_id", id_note).execute()

            matches = client.rpc("match_notes", {
                "query_embedding": new_embedding,
                "match_user_id": session["user_id"],
                "match_note_id": id_note,
                "match_count": 5
            }).execute()

            for match in matches.data:
                client.table("note_edges").insert({
                    "note_id": id_note,
                    "related_note_id": match["id_note"],
                    "similarity": match["similarity"]
                }).execute()

    except Exception as e:
        return f"{_('Ошибка при изменении')}: {e}"

    return redirect(url_for("home"))


@app.route("/delete", methods=["POST"])
def delete():
    if "access_token" not in session:
        return redirect(url_for("login"))

    id_note = request.form["id_note"]
    client = get_client()

    try:
        client.table("note_edges").delete().eq("note_id", id_note).execute()
        client.table("note_edges").delete().eq("related_note_id", id_note).execute()

        client.table("notes")\
            .delete()\
            .eq("id_note", id_note)\
            .eq("id_user", session["user_id"])\
            .execute()
    except Exception as e:
        return f"{_('Ошибка при удалении')}: {e}"

    return redirect(url_for("home"))


@app.route("/reset-password", methods=["POST"])
def reset_password_submit():
    data = request.get_json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    password = data.get("password")

    if not access_token:
        return f"{_('Ошибка: токен не найден. Откройте ссылку из письма заново.')}", 400

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        client.auth.set_session(access_token, refresh_token)
        client.auth.update_user({"password": password})
        return _("Пароль изменён! Сейчас перекинем на вход.")
    except Exception as e:
        return f"{_('Ошибка')}: {e}", 400


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
            return f"{_('Регистрация успешна! Теперь подтвердите почту.')} <a href='{EMAIL}'>{_('Открыть почту')}</a>"
        except Exception as e:
            return f"{_('Ошибка')}: {e}"
    return f'''
        {language_switcher()}
        <a href="/login">{_('Или войти?')}</a>
        <form method="post">
            {_('Email')}: <input name="email" type="email" required><br>
            {_('Пароль')}: <input name="password" type="password" required><br>
            <button type="submit">{_('Зарегистрироваться')}</button>
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
            return f"{_('Ошибка входа')}: {e}"
    return f'''
        {language_switcher()}
        <a href="/signup">{_('Или зарегистрироваться?')}</a>
        <form method="post">
            {_('Email')}: <input name="email" type="email" required><br>
            {_('Пароль')}: <input name="password" type="password" required><br>
            <a href="/forgot">{_('Забыли пароль?')}</a>
            <button type="submit">{_('Войти')}</button>
        </form>
    '''


@app.route("/")
def home():
    if "access_token" not in session:
        return redirect(url_for("login"))

    client = get_client()
    response = client.table("notes").select("*").execute()
    notes = response.data

    html = f"{language_switcher()}<a href='/create'>{_('Создать')}</a><p>{session.get('email')}</p><a href='/logout'>{_('Выйти')}</a><ul>"
    for note in notes:
        html += f"""<li>
            <a href='/change?id={note["id_note"]}'>
                {truncate(note["headline"], 20)}:
                {truncate(note["text"], 80)}
                ({_('Последнее изменение')}: {note["updated_at"]})
            </a>
                <form method="post" action="/delete" onsubmit="return confirm('{_('Удалить заметку?')}')">
                <input type="hidden" name="id_note" value="{note["id_note"]}">
                <button type="submit">{_('Удалить')}</button>
            </form>
        </li>"""
    html += "</ul>"

    return html


@app.route("/create")
def create():
    if "access_token" not in session:
        return redirect(url_for("login"))

    html = f"{language_switcher()}<button onclick='window.history.back()'>{_('Назад')}</button><p>{session.get('email')}</p><a href='/logout'>{_('Выйти')}</a>"
    html += f'''
        <form method="post" action="/add" onsubmit="setUtcTime(this)">
            <input type="hidden" name="updated_at">
            <input name="headline" placeholder="{_('Заголовок')}" required>
            <textarea name="text" placeholder="{_('Новая заметка')}" required></textarea>
            <button type="submit">{_('Создать')}</button>
        </form>

        <script>
            function setUtcTime(form) {{
                form.querySelector('input[name="updated_at"]').value = new Date().toISOString();
            }}
        </script>
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
        return _("Заметка не найдена"), 404
    note = response.data[0]

    html = f"{language_switcher()}<button onclick='window.history.back()'>{_('Назад')}</button><p>{session.get('email')}</p><a href='/logout'>{_('Выйти')}</a>"
    html += f"<p>{_('Последнее изменение')}: {note['updated_at']}</p>"

    html += f'''
        <form method="post" action="/edit" onsubmit="setUtcTime(this)">
            <input type="hidden" name="id_note" value="{id_note}">
            <input type="hidden" name="updated_at">
            <input name="headline" value='{note["headline"]}' required>
            <textarea name="text" required>{note["text"]}</textarea>
            <button type="submit">{_('Изменить')}</button>
        </form>
        <form method="post" action="/delete" onsubmit="return confirm('{_('Удалить заметку?')}')">
            <input type="hidden" name="id_note" value="{id_note}">
            <button type="submit">{_('Удалить')}</button>
        </form>

        <script>
            function setUtcTime(form) {{
                form.querySelector('input[name="updated_at"]').value = new Date().toISOString();
            }}
        </script>
    '''

    return html


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
            return _("Письмо для сброса пароля отправлено, проверьте почту.")
        except Exception as e:
            return f"{_('Ошибка')}: {e}"
    return f'''
        {language_switcher()}
        <button onclick='window.history.back()'>{_('Назад')}</button>
        <form method="post">
            {_('Email')}: <input name="email" type="email" required><br>
            <button type="submit">{_('Отправить ссылку для сброса')}</button>
        </form>
    '''


@app.route("/reset-password", methods=["GET"])
def reset_password_page():
    return f'''
        {language_switcher()}
        <button onclick='window.history.back()'>{_('Назад')}</button>
        <form id="resetForm">
            <input type="password" id="password" placeholder="{_('Новый пароль')}" required minlength="6">
            <button type="submit">{_('Сохранить')}</button>
        </form>
        <p id="msg"></p>
        <script>
            const hash = window.location.hash.substring(1);
            const params = new URLSearchParams(hash);
            const access_token = params.get("access_token");
            const refresh_token = params.get("refresh_token");

            document.getElementById("resetForm").addEventListener("submit", async (e) => {{
                e.preventDefault();
                const password = document.getElementById("password").value;

                const res = await fetch("/reset-password", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{access_token, refresh_token, password}})
                }});
                const text = await res.text();
                document.getElementById("msg").textContent = text;
                if (res.ok) {{
                    setTimeout(() => window.location.href = "/login", 1500);
                }}
            }});
        </script>
    '''


@app.route("/api/keep-alive")
def keep_alive():
    supabase_admin.table("notes").select("text").limit(1).execute()
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True)
