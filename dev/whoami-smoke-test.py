"""Exercise the .NET/TypeScript whoami demo (backlog 71) through the real proxy.

Checks HTTPS, the OIDC handler's https redirect URI on the client protocol's
callback path, sign-in through Duende (code, PKCE, private_key_jwt), the claims
API, CSRF and local logout, and last sends an OIDC error response whose text the
backend must not log (the harness checks the log). With SMOKE_RESTART_COMMAND (for example
`podman pod restart app3-whoami`, or `systemctl --user restart myproduct-app3`
on a target) it restarts the app after sign-in and requires the same session
cookie to still work, which needs the persisted Data Protection keys.
Run with the Todo backend dependencies installed (requests).
"""

import os
import shlex
import socket
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = os.getenv("PUBLIC_ORIGIN", "https://myproduct-proxy:8443").rstrip("/")
HOSTNAME = urlparse(ORIGIN).hostname
CONNECT_IP = os.getenv("CONNECT_IP", "127.0.0.1")
BASE_PATH = os.getenv("APP_BASE_PATH", "/app3").rstrip("/")
RESTART = os.getenv("SMOKE_RESTART_COMMAND", "")
# Sent as an Identity error's description and URI; the harness requires that it
# never appears in the backend log (acceptance/remote.sh whoami_marker).
LOG_MARKER = "whoami-log-marker-7f3c"
original_getaddrinfo = socket.getaddrinfo


def local_dns(host, *args, **kwargs):
    """Point the app host name at the test IP and keep other DNS lookups."""
    return original_getaddrinfo(
        CONNECT_IP if host == HOSTNAME else host, *args, **kwargs
    )


socket.getaddrinfo = local_dns


class Form(HTMLParser):
    """Collect the action and hidden fields of a page's form."""

    def __init__(self):
        """Create the parser with no action and an empty set of hidden fields."""
        super().__init__()
        self.action = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        """Collect the form action and name/value of hidden input fields."""
        attrs = dict(attrs)
        if tag == "form":
            self.action = attrs.get("action")
        elif tag == "input" and attrs.get("type") == "hidden":
            self.fields[attrs["name"]] = attrs.get("value", "")


def client():
    """Create an HTTPS session with the test CA and no environment proxy."""
    result = requests.Session()
    result.trust_env = False
    result.verify = os.getenv(
        "SMOKE_CA_FILE", str(ROOT / "build/dev/PKI/private/ca.crt")
    )
    return result


def get(session, path, **options):
    """Fetch a path below the app's base path with the test session."""
    return session.get(ORIGIN + BASE_PATH + path, timeout=15, **options)


def require_success(response, context):
    """Report an HTTP failure without its potentially secret-bearing URL or body."""
    if response.status_code >= 400:
        raise RuntimeError(f"{context} failed with HTTP {response.status_code}")


def wait_ready(session):
    """Wait until the backend answers through the proxy."""
    for _ in range(90):
        try:
            if get(session, "/auth/me").status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("Backend did not become ready")


def check_redirect(session):
    """The handler must send the browser to the public authorize endpoint with
    the registered https callback, not ASP.NET's default /signin-oidc."""
    response = get(session, "/auth/login", allow_redirects=False)
    assert response.status_code == 302, response.status_code
    target = urlparse(response.headers["Location"])
    assert f"{target.scheme}://{target.netloc}" == ORIGIN, "Authorize origin"
    assert target.path == "/identity/connect/authorize", "Authorize path"
    query = parse_qs(target.query)
    assert query["redirect_uri"] == [ORIGIN + BASE_PATH + "/auth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) >= {"openid", "profile"}


def check_error_response(session):
    """Answer a real sign-in start with an OIDC error carrying LOG_MARKER.

    The handler must refuse it with the fixed message; the caller checks the
    backend log.
    """
    response = get(session, "/auth/login", allow_redirects=False)
    state = parse_qs(urlparse(response.headers["Location"]).query)["state"][0]
    response = session.post(
        ORIGIN + BASE_PATH + "/auth/callback",
        data={
            "state": state,
            "error": "access_denied",
            "error_description": "Synthetic " + LOG_MARKER,
            "error_uri": "https://example.invalid/" + LOG_MARKER,
        },
        timeout=15,
    )
    assert response.status_code == 400, "OIDC error response not refused"
    assert LOG_MARKER not in response.text, "Error text echoed to the browser"


def login(username):
    """Sign in with the local demo password; return the session and CSRF token."""
    session = client()
    response = get(session, "/auth/login")
    require_success(response, "Sign-in page")
    assert urlparse(response.url).path == "/identity/account/login"
    form = Form()
    form.feed(response.text)
    form.fields.update(
        username=username,
        password=(
            Path(
                os.getenv(
                    "SMOKE_PASSWORD_DIR",
                    str(ROOT / "build/dev/identity/credentials/users"),
                )
            )
            / (username + "-password")
        )
        .read_text()
        .strip(),
    )
    response = session.post(response.url, data=form.fields, timeout=15)
    require_success(response, "Duende sign-in")
    # ASP.NET's default response_mode=form_post: Duende answers with a form that
    # a browser posts to the callback automatically.
    callback = Form()
    callback.feed(response.text)
    assert callback.action == ORIGIN + BASE_PATH + "/auth/callback", "form_post"
    response = session.post(callback.action, data=callback.fields, timeout=15)
    require_success(response, "OIDC callback")
    assert urlparse(response.url).path == BASE_PATH + "/", "Callback destination"
    state = get(session, "/auth/me").json()
    assert state["user"]["sub"] == username, "Unexpected signed-in user"
    return session, state["csrf"]


def claims(session):
    """Return the claims API result as a type -> values mapping."""
    response = get(session, "/api/claims")
    require_success(response, "Claims API")
    result = {}
    for claim in response.json():
        result.setdefault(claim["type"], []).append(claim["value"])
    return result


def main():
    """Test anonymous access, sign-in, claims, restart, CSRF and logout."""
    anonymous = client()
    wait_ready(anonymous)
    assert get(anonymous, "/auth/me").json()["user"] is None
    assert get(anonymous, "/api/claims").status_code == 401
    page = get(anonymous, "/")
    assert "<title>Who am I</title>" in page.text, "Frontend page"
    script = get(anonymous, "/app.js")
    assert script.status_code == 200 and "/api/claims" in script.text, "Compiled app.js"
    check_redirect(anonymous)
    print("PASS: HTTPS, routes, compiled frontend, anonymous 401, https callback URI")

    alice, csrf = login("alice")
    values = claims(alice)
    # The demo Identity issues no name claim; sid shows a Duende session.
    assert values["sub"] == ["alice"] and values.get("sid"), "Unexpected claims"
    print("PASS: alice signed in through Duende (PKCE, private_key_jwt); claims API")

    if RESTART:
        subprocess.run(shlex.split(RESTART), check=True, stdout=subprocess.DEVNULL)
        time.sleep(2)
        wait_ready(anonymous)
        assert get(alice, "/auth/me").json()["user"]["sub"] == "alice"
        assert claims(alice)["sub"] == ["alice"]
        csrf = get(alice, "/auth/me").json()["csrf"]
        print("PASS: the session cookie still works after restarting the app")
    else:
        print("SKIP: restart check (set SMOKE_RESTART_COMMAND)")

    logout = ORIGIN + BASE_PATH + "/auth/logout"
    headers = {"Origin": ORIGIN}
    assert alice.post(logout, headers=headers, timeout=15).status_code == 403
    bad = dict(headers, **{"X-CSRF-Token": "invalid"})
    assert alice.post(logout, headers=bad, timeout=15).status_code == 403
    cross = {"Origin": "https://attacker.example", "X-CSRF-Token": csrf}
    assert alice.post(logout, headers=cross, timeout=15).status_code == 403
    good = dict(headers, **{"X-CSRF-Token": csrf})
    assert alice.post(logout, headers=good, timeout=15).status_code == 204
    assert get(alice, "/api/claims").status_code == 401
    print("PASS: CSRF and origin checks; local logout")
    check_error_response(client())
    print("PASS: an OIDC error response is refused without echoing its text")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, requests.RequestException, RuntimeError, KeyError):
        print(
            "FAIL: whoami smoke test failed; response URLs and bodies are withheld",
            file=sys.stderr,
        )
        raise SystemExit(1)
