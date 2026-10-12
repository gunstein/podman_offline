"""Authenticated persistence checks, executed only in VM-1's smoke-test venv."""

import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "smoke", Path(__file__).resolve().parent.parent / "dev/smoke-test.py"
)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def main():
    action, filename, run_id = sys.argv[1:]
    path = Path(filename)
    if action == "create":
        if path.exists():
            raise RuntimeError("Markers already created")
        markers = {}
        for user in ("alice", "bob"):
            session = smoke.login(user)
            title = f"Acceptance {run_id} {user}"
            response = session.post(
                smoke.ORIGIN + "/api/todos", json={"title": title}, timeout=10
            )
            response.raise_for_status()
            row = response.json()
            markers[user] = {"id": row["id"], "title": title}
        path.write_text(json.dumps(markers))
    else:
        markers = json.loads(path.read_text())
    for user, marker in markers.items():
        session = smoke.login(user)
        response = smoke.get(session, "/api/todos")
        response.raise_for_status()
        rows = response.json()
        assert any(
            r["id"] == marker["id"] and r["title"] == marker["title"] for r in rows
        )
        for other, other_marker in markers.items():
            if other != user:
                assert not any(r["id"] == other_marker["id"] for r in rows)
        print(
            "PASS marker {} id={} title={}".format(user, marker["id"], marker["title"])
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - never expose auth response bodies
        print(
            "FAIL: authenticated marker operation; see preceding step", file=sys.stderr
        )
        raise SystemExit(1)
