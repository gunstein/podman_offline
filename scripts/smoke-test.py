"""Exercise actual HTTPS, OIDC code/PKCE/private_key_jwt and per-user Todo CRUD.

Run with the Todo backend dependencies installed. No hosts-file change needed.
"""

import os
import socket
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = os.getenv("PUBLIC_ORIGIN", "https://myproduct-proxy:8443").rstrip("/")
HOSTNAME = urlparse(ORIGIN).hostname
CONNECT_IP = os.getenv("CONNECT_IP", "127.0.0.1")
original_getaddrinfo = socket.getaddrinfo


def local_dns(host, *args, **kwargs):
    return original_getaddrinfo(
        CONNECT_IP if host == HOSTNAME else host, *args, **kwargs
    )


socket.getaddrinfo = local_dns


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden":
            self.fields[attrs["name"]] = attrs.get("value", "")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = set()

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.add(href)


def check_help(session):
    expected = {
        "/help/": "Hjelp til Todo",
        "/help/innlogging.html": "Logge inn og ut",
        "/help/oppgaver.html": "Bruke oppgavelisten",
        "/help/feilsoking.html": "Når noe ikke virker",
    }
    links = Links()
    links.feed(get(session, "/").text)
    assert set(expected).issubset(links.hrefs), links.hrefs
    for path, heading in expected.items():
        response = get(session, path)
        assert response.status_code == 200, (path, response.status_code)
        assert "<h1>" + heading + "</h1>" in response.text, path
        navigation = Links()
        navigation.feed(response.text)
        assert "/" in navigation.hrefs, path
        assert navigation.hrefs.issubset(set(expected) | {"/"}), navigation.hrefs
    stylesheet = get(session, "/help/help.css")
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["Content-Type"]
    redirect = session.get(ORIGIN + "/help", allow_redirects=False, timeout=10)
    assert redirect.status_code == 308
    assert urlparse(redirect.headers["Location"]).path == "/help/"
    response = get(session, "/help")
    assert response.status_code == 200
    assert response.url == ORIGIN + "/help/", response.url
    assert get(session, "/help/does-not-exist.html").status_code == 404
    print("PASS: Todo help links, public help pages, navigation, CSS, redirect and 404")


def client():
    result = requests.Session()
    result.trust_env = False
    result.verify = str(ROOT / "PKI/private/ca.crt")
    return result


def get(session, path):
    return session.get(ORIGIN + path, timeout=10)


def login(username):
    session = client()
    response = get(session, "/auth/login")
    response.raise_for_status()
    assert urlparse(response.url).path == "/identity/account/login", response.url
    form = LoginForm()
    form.feed(response.text)
    assert "__RequestVerificationToken" in form.fields
    form.fields.update(
        username=username,
        password=(ROOT / "generated-certificates/users" / (username + "-password"))
        .read_text()
        .strip(),
    )
    response = session.post(response.url, data=form.fields, timeout=15)
    response.raise_for_status()
    assert urlparse(response.url).path == "/", response.url
    state = get(session, "/auth/me").json()
    assert state["user"]["sub"] == username, state
    session.headers.update({"X-CSRF-Token": state["csrf"], "Origin": ORIGIN})
    return session


def main():
    anonymous = client()
    for attempt in range(60):
        try:
            response = get(anonymous, "/api/health")
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Backend did not become ready")
    assert get(anonymous, "/api/todos").status_code == 401
    discovery = get(anonymous, "/identity/.well-known/openid-configuration")
    discovery.raise_for_status()
    assert discovery.json()["issuer"] == ORIGIN + "/identity"
    assert (
        "private_key_jwt" in discovery.json()["token_endpoint_auth_methods_supported"]
    )
    assert "<title>Todo</title>" in get(anonymous, "/").text
    assert get(anonymous, "/app.js").status_code == 200
    print("PASS: verified HTTPS, proxy routes, discovery and anonymous rejection")

    check_help(anonymous)

    alice, bob = login("alice"), login("bob")
    print("PASS: alice and bob signed in through Duende, PKCE and private_key_jwt")
    created = alice.post(
        ORIGIN + "/api/todos", json={"title": "OIDC smoke test"}, timeout=10
    )
    assert created.status_code == 201, created.text
    item = created.json()
    path = "/api/todos/" + str(item["id"])
    try:
        assert any(row["id"] == item["id"] for row in get(alice, "/api/todos").json())
        assert not any(row["id"] == item["id"] for row in get(bob, "/api/todos").json())
        assert (
            bob.patch(ORIGIN + path, json={"done": True}, timeout=10).status_code == 404
        )
        assert bob.delete(ORIGIN + path, timeout=10).status_code == 404
        bad_csrf = alice.post(
            ORIGIN + "/api/todos",
            json={"title": "must not exist"},
            headers={"X-CSRF-Token": "invalid"},
            timeout=10,
        )
        assert bad_csrf.status_code == 403
        assert (
            alice.post(
                ORIGIN + "/api/todos", json={"title": "   "}, timeout=10
            ).status_code
            == 400
        )
        updated = alice.patch(ORIGIN + path, json={"done": True}, timeout=10)
        assert updated.status_code == 200 and updated.json()["done"] is True
    finally:
        deleted = alice.delete(ORIGIN + path, timeout=10)
        assert deleted.status_code == 204, deleted.text
    assert alice.post(ORIGIN + "/auth/logout", timeout=10).status_code == 204
    assert get(alice, "/api/todos").status_code == 401
    print("PASS: create/read/update/delete, user isolation, CSRF and local logout")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, requests.RequestException, RuntimeError) as error:
        print("FAIL:", error, file=sys.stderr)
        raise SystemExit(1)
