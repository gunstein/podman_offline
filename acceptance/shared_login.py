"""Verify cross-app SSO and separate Todo data without exposing OIDC responses."""

import importlib.util
import sys
from pathlib import Path
from urllib.parse import urlparse

spec = importlib.util.spec_from_file_location(
    "smoke", Path(__file__).resolve().parent.parent / "dev/smoke-test.py"
)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def main():
    """Reuse one browser identity session across scoped app cookies and isolated databases."""
    for first, second in (("app1", "app2"), ("app2", "app1")):
        smoke.__dict__["BASE_PATH"] = "/" + first
        session = smoke.login("alice")
        response = session.post(
            smoke.app_url("/api/todos"),
            json={"title": "Scoped data " + first},
            timeout=10,
        )
        smoke.require_success(response, "Cross-app fixture creation")
        marker = response.json()
        smoke.__dict__["BASE_PATH"] = "/" + second
        response = smoke.get(session, "/auth/login")
        smoke.require_success(response, "Shared sign-in")
        if urlparse(response.url).path != smoke.BASE_PATH + "/":
            raise RuntimeError("The second app required a new password form")
        state = smoke.get(session, "/auth/me").json()
        if state["user"]["sub"] != "alice":
            raise RuntimeError("Shared sign-in returned the wrong user")
        rows = smoke.get(session, "/api/todos").json()
        if any(row["title"] == marker["title"] for row in rows):
            raise RuntimeError("Todo data crossed app database boundaries")
        cookie_names = {cookie.name: cookie.path for cookie in session.cookies}
        for app in (first, second):
            if cookie_names.get(app + "-session") != "/" + app + "/":
                raise RuntimeError("App cookie path or name is not isolated")
        smoke.__dict__["BASE_PATH"] = "/" + first
        smoke.login("alice", session)
        response = session.delete(
            smoke.app_url("/api/todos/" + str(marker["id"])), timeout=10
        )
        smoke.require_success(response, "Cross-app fixture cleanup")
        print(
            f"PASS: {first} -> {second} shared sign-in, separate data and scoped cookies"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - callback URLs and bodies may contain credentials
        print(
            "FAIL: cross-app SSO/data check; response content withheld", file=sys.stderr
        )
        raise SystemExit(1)
