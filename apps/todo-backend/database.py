"""PostgreSQL file-secret interface; no defaults and no connection strings on disk."""

import os
from pathlib import Path

import psycopg
from psycopg.rows import DictRow, dict_row


def parameters():
    """Read ordinary config and the same LF convention as postgres file_env."""
    values = {}
    for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
        value = os.environ.get(key)
        if not value or "\x00" in value:
            raise RuntimeError("Missing or invalid " + key)
        values[key] = value
    port = values["DB_PORT"]
    if (
        len(port) > 5
        or any(character not in "0123456789" for character in port)
        or not 1 <= int(port) <= 65535
    ):
        raise RuntimeError("Invalid DB_PORT (expected 1-65535)")
    try:
        password = (
            Path("/run/secrets/database/password")
            .read_bytes()
            .decode("utf-8")
            .rstrip("\n")
        )
    except (OSError, UnicodeError):
        raise RuntimeError("Cannot read database password file") from None
    if not password or any(c in password for c in ("\x00", "\r", "\n")):
        raise RuntimeError("Empty or invalid database password file")
    return {
        "host": values["DB_HOST"],
        "port": int(port),
        "user": values["DB_USER"],
        "dbname": values["DB_NAME"],
        "password": password,
    }


def connect(timeout=5):
    """Use libpq keyword parameters, avoiding connection-string interpolation."""
    return psycopg.Connection[DictRow].connect(
        **parameters(), row_factory=dict_row, connect_timeout=timeout
    )


def authentication_failed(error):
    """libpq handshake failures lack a result/SQLSTATE; classify its FATAL reply.

    PostgreSQL 17's image uses English lc_messages. Never expose this private
    driver diagnostic: return only whether password authentication was rejected.
    DNS, routing, timeout and refused connections do not match this server reply.
    """
    if getattr(error, "sqlstate", None) == "28P01":
        return True
    connection = getattr(error, "pgconn", None)
    message = getattr(connection, "error_message", b"")
    signature = "FATAL:  password authentication failed for user "
    # Psycopg may discard PGconn after a failed handshake but retains its reply
    # in the exception. Inspect privately; never propagate that diagnostic.
    return signature.encode() in message or signature in str(error)
