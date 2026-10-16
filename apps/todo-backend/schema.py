"""Idempotent Todo schema preparation, without importing the web application."""

import signal
import sys
import time

import psycopg
from database import authentication_failed, connect, parameters

CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS todos (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        owner text NOT NULL,
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        done boolean NOT NULL DEFAULT false
    )
"""


def prepare():
    """Wait up to 60 seconds for a separate database pod, then create the table."""
    parameters()  # Validate input before retrying; the reader sanitizes errors.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with connect(timeout=2) as db:
                db.execute("SET statement_timeout = '5s'")
                db.execute("SET lock_timeout = '5s'")
                db.execute(CREATE_TABLE)
            return
        except psycopg.Error as error:
            if authentication_failed(error):
                raise RuntimeError("Database password authentication failed") from None
            # Retry only connection establishment/availability errors. SQL/schema
            # errors must fail immediately rather than masquerade as startup delay.
            if getattr(error, "sqlstate", None) not in (
                None,
                "57P03",
                "08001",
                "08006",
            ):
                raise RuntimeError("Database schema preparation failed") from None
            time.sleep(1)
    raise RuntimeError("Database preparation timed out")


def verify_ready():
    """App1 must never silently substitute backend DDL for a failed/missing init."""
    try:
        with connect() as db:
            db.execute("SET statement_timeout = '5s'")
            db.execute("SELECT id, owner, title, done FROM todos LIMIT 0")
    except psycopg.Error:
        raise RuntimeError(
            "Todo schema is not ready; database init must succeed"
        ) from None


def timed_out(signum, frame):
    """Hard process limit also covers DNS, SQL and other blocking driver work."""
    raise RuntimeError("Database preparation timed out")


def main():
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(75)
    try:
        prepare()
    except Exception:  # noqa: BLE001 - Keep every driver/config diagnostic private at the CLI boundary.
        # Never print driver errors, supplied config, passwords or a traceback.
        print(
            "ERROR: Todo database preparation failed (75s limit); check database availability, schema and matching credentials",
            file=sys.stderr,
        )
        return 1
    finally:
        signal.alarm(0)
    print("Todo database schema is ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
