"""Keep one app3 (whoami, backlog 71) session across PROD restarts and a reboot.

    python acceptance/whoami_session.py create|check|logout FILE

`create` signs in as alice through dev/whoami-smoke-test.py's flow and saves
the session cookies to FILE, a new 0600 file in the run's private runtime
directory. `check` requires the same cookies to still be signed in, which needs
app3's persisted Data Protection keys. `logout` checks once more, then signs
out with the CSRF token and requires the cookies to be rejected afterwards.
"""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "whoami_smoke", str(ROOT / "dev/whoami-smoke-test.py")
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def save(session, path):
    """Write the cookies to a new private file; an existing file is refused."""
    cookies = [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
        for c in session.cookies
    ]
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(cookies, stream)


def load(path):
    """Return a fresh HTTPS session that carries the saved cookies."""
    session = smoke.client()
    for cookie in json.loads(path.read_text()):
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie["domain"],
            path=cookie["path"],
        )
    return session


def signed_in(session):
    """Require alice's session and claims; return the current CSRF token.

    Just after a restart the proxy may briefly answer through a stale route, so
    this waits up to 60 seconds; a lost session never recovers, so waiting
    cannot hide one.
    """
    state = {}
    for _ in range(60):
        try:
            response = smoke.get(session, "/auth/me")
            state = response.json() if response.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            state = {}
        if (state.get("user") or {}).get("sub") == "alice":
            break
        time.sleep(1)
    else:
        raise AssertionError("Session not signed in within 60 seconds")
    assert smoke.claims(session)["sub"] == ["alice"], "Unexpected claims"
    return state["csrf"]


def main(operation, path):
    if operation == "create":
        session, _ = smoke.login("alice")
        signed_in(session)
        save(session, path)
        print("PASS: alice signed in to app3; session saved for later checks")
    elif operation == "check":
        signed_in(load(path))
        print("PASS: the saved app3 session is still signed in")
    elif operation == "logout":
        session = load(path)
        csrf = signed_in(session)
        logout = smoke.ORIGIN + smoke.BASE_PATH + "/auth/logout"
        headers = {"Origin": smoke.ORIGIN, "X-CSRF-Token": csrf}
        response = session.post(logout, headers=headers, timeout=15)
        assert response.status_code == 204, "Logout refused"
        assert smoke.get(session, "/api/claims").status_code == 401, "Still signed in"
        print("PASS: the saved app3 session was still signed in; local logout")
    else:
        raise SystemExit("Usage: whoami_session.py create|check|logout FILE")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: whoami_session.py create|check|logout FILE")
    try:
        main(sys.argv[1], Path(sys.argv[2]))
    except AssertionError as error:
        # Only the fixed messages above; never response URLs or bodies.
        print("FAIL: app3 session: " + str(error), file=sys.stderr)
        raise SystemExit(1)
    except (requests.RequestException, RuntimeError, KeyError, OSError):
        print(
            "FAIL: app3 session check failed; response URLs and bodies are withheld",
            file=sys.stderr,
        )
        raise SystemExit(1)
