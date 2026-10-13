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
APP_ID = os.getenv("APP_ID", "todo")
BASE_PATH = os.getenv("BASE_PATH", "").rstrip("/")
CERTIFICATES = Path(os.getenv("CERTIFICATES_DIR", "/certificates"))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=(CERTIFICATES / "session-key").read_text().strip(),
    SESSION_COOKIE_NAME=APP_ID + "-session",
    SESSION_COOKIE_PATH=BASE_PATH + "/",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    MAX_CONTENT_LENGTH=16384,
)
oauth = OAuth(app)
identity = oauth.register(
    "identity",
    client_id=APP_ID,
    client_secret=(CERTIFICATES / "todo-client.key").read_text(),
    server_metadata_url=ISSUER + "/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid profile " + APP_ID,
        "code_challenge_method": "S256",
        "token_endpoint_auth_method": "private_key_jwt",
    },
    client_auth_methods=[PrivateKeyJWT(ISSUER + "/connect/token", alg="RS256")],
)


def connect():
    """Open this instance's PostgreSQL connection with its private password."""
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
    """Create the instance's Todo table, retrying while PostgreSQL starts."""
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
    """Protect only this instance's API and logout with session and CSRF checks."""
    if session.get("expires", 0) <= time.time() and "user" in session:
        session.clear()
    protected = (
        request.path.startswith(BASE_PATH + "/api/")
        and request.path != BASE_PATH + "/api/health"
    )
    if protected or request.path == BASE_PATH + "/auth/logout":
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
    """Prevent caching and MIME sniffing of backend responses."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get(BASE_PATH + "/auth/login")
def login():
    """Start OIDC for this instance; the shared identity cookie permits SSO."""
    return identity.authorize_redirect(ORIGIN + BASE_PATH + "/auth/callback")


@app.get(BASE_PATH + "/auth/callback")
def callback():
    """Validate OIDC and issue a session cookie scoped to this app path."""
    # Authlib validates state, nonce, issuer, audience, expiry and ID-token signature.
    token = identity.authorize_access_token()
    claims = token["userinfo"]
    session.clear()
    session.permanent = True
    session["user"] = {"sub": claims["sub"], "name": claims.get("name", claims["sub"])}
    session["expires"] = min(claims["exp"], int(time.time()) + 3600)
    session["csrf"] = secrets.token_urlsafe(32)
    return redirect(BASE_PATH + "/")


@app.errorhandler(OAuthError)
def oauth_error(error):
    """Return a safe sign-in failure without logging callback URLs or tokens."""
    app.logger.warning("OIDC rejected: %s", error.error)
    return "Sign-in failed. Go back and try again.", 400


@app.get(BASE_PATH + "/auth/me")
def me():
    """Return this instance's current user and CSRF token."""
    return jsonify(user=session.get("user"), csrf=session.get("csrf", ""))


@app.post(BASE_PATH + "/auth/logout")
def logout():
    """Clear only this app's local session."""
    session.clear()
    return "", 204


@app.get("/livez")
def livez():
    """Answer locally, without database or sign-in, for the container liveness probe."""
    return "", 204


@app.get(BASE_PATH + "/api/health")
def health():
    """Check this app's database for integration tests, not liveness."""
    with connect() as db:
        db.execute("SELECT 1")
    return jsonify(status="ok")


@app.get(BASE_PATH + "/api/todos")
def list_todos():
    """List only the current user's tasks in this app database."""
    with connect() as db:
        rows = db.execute(
            "SELECT id, title, done FROM todos WHERE owner = %s ORDER BY id",
            (session["user"]["sub"],),
        ).fetchall()
    return jsonify(rows)


@app.post(BASE_PATH + "/api/todos")
def create_todo():
    """Validate and store a new task for the current user."""
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


@app.patch(BASE_PATH + "/api/todos/<int:todo_id>")
def update_todo(todo_id):
    """Update a task owned by the current user in this app database."""
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


@app.delete(BASE_PATH + "/api/todos/<int:todo_id>")
def delete_todo(todo_id):
    """Delete a task owned by the current user in this app database."""
    with connect() as db:
        row = db.execute(
            "DELETE FROM todos WHERE id = %s AND owner = %s RETURNING id",
            (todo_id, session["user"]["sub"]),
        ).fetchone()
    if row is None:
        abort(404)
    return "", 204


initialize()
