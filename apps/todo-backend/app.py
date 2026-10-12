"""Small Todo BFF: OIDC tokens stay on the server; browser uses a signed cookie."""

import os
import secrets
import time
from datetime import timedelta
from pathlib import Path

import psycopg
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from authlib.oauth2.rfc7523 import PrivateKeyJWT
from flask import Flask, abort, jsonify, redirect, request, session
from psycopg.rows import DictRow, dict_row

ORIGIN = os.environ["PUBLIC_ORIGIN"].rstrip("/")
ISSUER = ORIGIN + "/identity"
CERTIFICATES = Path(os.getenv("CERTIFICATES_DIR", "/certificates"))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=(CERTIFICATES / "session-key").read_text().strip(),
    SESSION_COOKIE_NAME="todo-session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    MAX_CONTENT_LENGTH=16384,
)
oauth = OAuth(app)
identity = oauth.register(
    "identity",
    client_id="todo",
    client_secret=(CERTIFICATES / "todo-client.key").read_text(),
    server_metadata_url=ISSUER + "/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid profile todo",
        "code_challenge_method": "S256",
        "token_endpoint_auth_method": "private_key_jwt",
    },
    client_auth_methods=[PrivateKeyJWT(ISSUER + "/connect/token", alg="RS256")],
)


def connect():
    return psycopg.Connection[DictRow].connect(
        host=os.environ["DATABASE_HOST"],
        dbname="todo",
        user="todo",
        password=Path(
            os.getenv("DATABASE_PASSWORD_FILE", "/run/secrets/database/password")
        )
        .read_text()
        .strip(),
        row_factory=dict_row,
        connect_timeout=5,
    )


def initialize():
    for attempt in range(60):
        try:
            with connect() as db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS todos (
                        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        owner text NOT NULL,
                        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
                        done boolean NOT NULL DEFAULT false
                    )
                """)
            return
        except psycopg.OperationalError:
            if attempt == 59:
                raise
            time.sleep(1)


@app.before_request
def authenticate():
    if session.get("expires", 0) <= time.time() and "user" in session:
        session.clear()
    protected = request.path.startswith("/api/") and request.path != "/api/health"
    if protected or request.path == "/auth/logout":
        if "user" not in session:
            abort(401)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = session.get("csrf", "")
            actual = request.headers.get("X-CSRF-Token", "")
            if not expected or not secrets.compare_digest(expected, actual):
                abort(403)
            if request.headers.get("Origin") != ORIGIN:
                abort(403)


@app.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/auth/login")
def login():
    # Require credentials again after local logout for this small demo.
    return identity.authorize_redirect(ORIGIN + "/auth/callback", prompt="login")


@app.get("/auth/callback")
def callback():
    # Authlib validates state, nonce, issuer, audience, expiry and ID-token signature.
    token = identity.authorize_access_token()
    claims = token["userinfo"]
    session.clear()
    session.permanent = True
    session["user"] = {"sub": claims["sub"], "name": claims.get("name", claims["sub"])}
    session["expires"] = min(claims["exp"], int(time.time()) + 3600)
    session["csrf"] = secrets.token_urlsafe(32)
    return redirect("/")


@app.errorhandler(OAuthError)
def oauth_error(error):
    app.logger.warning("OIDC rejected: %s", error.error)
    return "Innlogging feilet. Gå tilbake og prøv igjen.", 400


@app.get("/auth/me")
def me():
    return jsonify(user=session.get("user"), csrf=session.get("csrf", ""))


@app.post("/auth/logout")
def logout():
    session.clear()
    return "", 204


@app.get("/api/health")
def health():
    with connect() as db:
        db.execute("SELECT 1")
    return jsonify(status="ok")


@app.get("/api/todos")
def list_todos():
    with connect() as db:
        rows = db.execute(
            "SELECT id, title, done FROM todos WHERE owner = %s ORDER BY id",
            (session["user"]["sub"],),
        ).fetchall()
    return jsonify(rows)


@app.post("/api/todos")
def create_todo():
    data = request.get_json()
    title = data.get("title") if isinstance(data, dict) else None
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        abort(400)
    with connect() as db:
        row = db.execute(
            "INSERT INTO todos (owner, title) VALUES (%s, %s) RETURNING id, title, done",
            (session["user"]["sub"], title.strip()),
        ).fetchone()
    return jsonify(row), 201


@app.patch("/api/todos/<int:todo_id>")
def update_todo(todo_id):
    data = request.get_json()
    if not isinstance(data, dict) or not isinstance(data.get("done"), bool):
        abort(400)
    with connect() as db:
        row = db.execute(
            "UPDATE todos SET done = %s WHERE id = %s AND owner = %s RETURNING id, title, done",
            (data["done"], todo_id, session["user"]["sub"]),
        ).fetchone()
    if row is None:
        abort(404)
    return jsonify(row)


@app.delete("/api/todos/<int:todo_id>")
def delete_todo(todo_id):
    with connect() as db:
        row = db.execute(
            "DELETE FROM todos WHERE id = %s AND owner = %s RETURNING id",
            (todo_id, session["user"]["sub"]),
        ).fetchone()
    if row is None:
        abort(404)
    return "", 204


initialize()
