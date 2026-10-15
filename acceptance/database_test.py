#!/usr/bin/env python3
"""Disposable real PostgreSQL/runtime tests on the dev VM; never print credentials."""

import base64
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import deploy


def podman(arguments, expected=0):
    """Withhold subprocess diagnostics: only controlled checks may reach evidence."""
    result = subprocess.run(
        ["podman"] + arguments, capture_output=True, text=True, check=False, timeout=180
    )
    if result.returncode != expected:
        interface = "Python" if "python" in arguments else "Identity/PostgreSQL"
        raise RuntimeError(
            f"Database runtime check failed at {arguments[0]} ({interface}, expected {expected}, exit {result.returncode})"
        )
    return result


def image(component, container_name):
    """Use the release manifest rather than hardcoded test image versions."""
    for path in (ROOT / "components" / component / "manifests").glob("*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc.get("kind") == "Pod":
                for container in doc["spec"]["containers"]:
                    if container["name"] == container_name:
                        return container["image"]
    raise RuntimeError("Missing database test image")


PYTHON_CHECK = """
import sys
from database import authentication_failed, connect
try:
    with connect() as connection:
        assert connection.execute("SELECT 1").fetchone()["?column?"] == 1
except Exception as error:
    if authentication_failed(error):
        print("Database password authentication failed")
        sys.exit(2)
    print("Database verification failed")
    sys.exit(3)
print("Database connection verified")
"""


def volume_guard(base, secret, claim):
    """Exercise the lifecycle guard against this actual initialized test volume."""
    path = base / "guard/config.yaml"
    config = {
        deploy.SECRET_FILES: {secret: ["lost/password"]},
        deploy.GENERATED_SECRETS: ["lost/password"],
    }
    try:
        deploy.database_preflight(config, path, base)
    except deploy.DeployError as error:
        if "existing volume " + claim not in str(error) or "restore" not in str(error):
            raise RuntimeError("Unexpected database volume guard failure") from None
    else:
        raise RuntimeError(
            "Existing initialized database permitted missing-password generation"
        )
    if (path.parent / "lost/password").exists():
        raise RuntimeError("Database volume guard changed private state")
    print("PASS: actual initialized volume refuses lost-password generation")


def run():
    """Test quoting and LF semantics using kube Secrets, actual initdb and clients."""
    os.umask(0o077)
    prefix = "db-check-" + uuid.uuid4().hex[:12]
    network, claim, secret = prefix + "-network", prefix + "-data", prefix + "-password"
    host = prefix + "-postgres"
    passwords = [
        " space;single' double\" dollar$ equals= end ",
        "unicode-ø;=\"'$",
        "0123456789abcdef" * 3 + "\n\n",
    ]
    with tempfile.TemporaryDirectory(prefix=prefix + "-") as directory:
        base = Path(directory)
        password_path = base / "password"
        manifest = base / "database.yaml"
        podman(["network", "create", network])
        try:
            for password in passwords:
                password_path.write_bytes(password.encode("utf-8"))
                password_path.chmod(0o600)
                docs = [
                    {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "metadata": {"name": secret},
                        "data": {
                            "password": base64.b64encode(password.encode()).decode()
                        },
                    },
                    {
                        "apiVersion": "v1",
                        "kind": "PersistentVolumeClaim",
                        "metadata": {"name": claim},
                        "spec": {
                            "accessModes": ["ReadWriteOnce"],
                            "resources": {"requests": {"storage": "1Gi"}},
                        },
                    },
                    {
                        "apiVersion": "v1",
                        "kind": "Pod",
                        "metadata": {"name": host},
                        "spec": {
                            "containers": [
                                {
                                    "name": "db",
                                    "image": image("app1", "db"),
                                    "imagePullPolicy": "Never",
                                    "env": [
                                        {
                                            "name": "POSTGRES_USER",
                                            "value": "configured-user",
                                        },
                                        {
                                            "name": "POSTGRES_DB",
                                            "value": "configured-database",
                                        },
                                        {"name": "PGPORT", "value": "5544"},
                                        {
                                            "name": "PGDATA",
                                            "value": "/var/lib/postgresql/data/pgdata",
                                        },
                                        {
                                            "name": "POSTGRES_PASSWORD_FILE",
                                            "value": "/run/secrets/database/password",
                                        },
                                    ],
                                    "volumeMounts": [
                                        {
                                            "name": "data",
                                            "mountPath": "/var/lib/postgresql/data",
                                        },
                                        {
                                            "name": "password",
                                            "mountPath": "/run/secrets/database",
                                            "readOnly": True,
                                        },
                                    ],
                                }
                            ],
                            "volumes": [
                                {
                                    "name": "data",
                                    "persistentVolumeClaim": {"claimName": claim},
                                },
                                {
                                    "name": "password",
                                    "secret": {
                                        "secretName": secret,
                                        "items": [
                                            {"key": "password", "path": "password"}
                                        ],
                                    },
                                },
                            ],
                        },
                    },
                ]
                manifest.write_text(yaml.safe_dump_all(docs))
                manifest.chmod(0o600)
                podman(["kube", "play", "--network", network, str(manifest)])
                deadline = time.monotonic() + 90
                while True:
                    result = subprocess.run(
                        [
                            "podman",
                            "exec",
                            host + "-db",
                            "pg_isready",
                            "-h",
                            "127.0.0.1",
                            "-p",
                            "5544",
                            "-U",
                            "configured-user",
                            "-d",
                            "configured-database",
                        ],
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode == 0:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError(
                            "Disposable PostgreSQL initialization timed out"
                        )
                    time.sleep(1)
                retained = password_path.read_bytes()
                config = {
                    deploy.SECRET_FILES: {secret: ["password"]},
                    deploy.GENERATED_SECRETS: ["password"],
                }
                deploy.database_preflight(config, base / "config.yaml", base)
                deploy.generate_secrets(config, base)
                if password_path.read_bytes() != retained:
                    raise RuntimeError(
                        "Existing database password changed during generation transition"
                    )
                volume_guard(base, secret, claim)
                # Client gets the exact same Secret through Kubernetes mounting.
                client_name = prefix + "-identity"
                client = {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {"name": client_name},
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "app",
                                "image": image("identity", "app"),
                                "imagePullPolicy": "Never",
                                "args": ["--database-check"],
                                "env": [
                                    {"name": key, "value": value}
                                    for key, value in {
                                        "DB_HOST": host,
                                        "DB_PORT": "5544",
                                        "DB_USER": "configured-user",
                                        "DB_NAME": "configured-database",
                                    }.items()
                                ],
                                "volumeMounts": [
                                    {
                                        "name": "password",
                                        "mountPath": "/run/secrets/database",
                                        "readOnly": True,
                                    }
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "password",
                                "secret": {
                                    "secretName": secret,
                                    "items": [{"key": "password", "path": "password"}],
                                },
                            }
                        ],
                    },
                }
                client_manifest = base / "client.yaml"
                client_manifest.write_text(yaml.safe_dump(client))
                client_manifest.chmod(0o600)
                podman(["kube", "play", "--network", network, str(client_manifest)])
                status = podman(["wait", client_name + "-app"]).stdout.strip()
                if status != "0":
                    raise RuntimeError("Identity environment connection failed")
                output = podman(["logs", client_name + "-app"]).stdout
                if (
                    "verified via ConnectionStrings__Default" not in output
                    or password.rstrip("\n") in output
                    or ("password=" in output.lower() and "host=" in output.lower())
                ):
                    raise RuntimeError("Identity runtime evidence invalid")
                podman(["kube", "down", str(client_manifest)])
                client_dir = base / "client-input"
                client_dir.mkdir(mode=0o700, exist_ok=True)
                client_password = client_dir / "password"
                client_password.write_bytes(retained)
                client_password.chmod(0o600)
                common = [
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network",
                    network,
                    "-v",
                    str(client_dir) + ":/run/secrets/database:ro,Z",
                    "-e",
                    "DB_HOST=" + host,
                    "-e",
                    "DB_PORT=5544",
                    "-e",
                    "DB_USER=configured-user",
                    "-e",
                    "DB_NAME=configured-database",
                ]
                podman(
                    common
                    + [
                        "--entrypoint",
                        "python",
                        image("app1", "backend"),
                        "-c",
                        PYTHON_CHECK,
                    ]
                )
                # Change only disposable input; never an installed persistent password.
                client_password.write_bytes(b"deliberately-wrong-secret")
                negative = podman(
                    common + [image("identity", "app"), "--database-check"], expected=2
                )
                if "28P01" not in negative.stderr:
                    raise RuntimeError(
                        "Expected Identity authentication error, not network failure"
                    )
                negative = podman(
                    common
                    + [
                        "--entrypoint",
                        "python",
                        image("app1", "backend"),
                        "-c",
                        PYTHON_CHECK,
                    ],
                    expected=2,
                )
                if "Database password authentication failed" not in negative.stdout:
                    raise RuntimeError(
                        "Expected Python authentication error, not network failure"
                    )
                for invalid in ("0", "65536", "invalid"):
                    result = podman(
                        common
                        + [
                            "-e",
                            "DB_PORT=" + invalid,
                            image("identity", "app"),
                            "--database-check",
                        ],
                        expected=1,
                    )
                    if (
                        "Invalid DB_PORT" not in result.stderr
                        or "deliberately-wrong-secret" in result.stderr
                    ):
                        raise RuntimeError("Unsafe invalid-parameter diagnostics")
                if password == passwords[0]:
                    for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
                        result = podman(
                            common
                            + [
                                "-e",
                                key + "=",
                                image("identity", "app"),
                                "--database-check",
                            ],
                            expected=1,
                        )
                        if (
                            key not in result.stderr
                            or "deliberately-wrong-secret" in result.stderr
                        ):
                            raise RuntimeError("Unsafe missing-parameter diagnostics")
                    for invalid_password in (
                        b"",
                        b"\n\n",
                        b"invalid\r\n",
                        b"\xff",
                        b"invalid\x00value",
                    ):
                        client_password.write_bytes(invalid_password)
                        result = podman(
                            common + [image("identity", "app"), "--database-check"],
                            expected=1,
                        )
                        if (
                            "password file" not in result.stderr
                            or "invalid\r" in result.stderr
                        ):
                            raise RuntimeError("Unsafe invalid-password diagnostics")
                if password_path.read_bytes() != retained:
                    raise RuntimeError(
                        "Negative database checks changed original credentials"
                    )
                server_log = podman(["logs", host + "-db"])
                if password.rstrip("\n") in server_log.stdout + server_log.stderr:
                    raise RuntimeError("Database server log contains credentials")
                podman(["kube", "down", str(manifest)])
                podman(["volume", "rm", claim])
                if (
                    secret
                    in podman(
                        ["secret", "ls", "--format", "{{.Name}}"]
                    ).stdout.splitlines()
                ):
                    podman(["secret", "rm", secret])
                print(
                    "PASS: PostgreSQL initialization, environment/file clients, special credentials and authentication refusal"
                )
        finally:
            # Only UUID-scoped disposable resources; fail if cleanup itself fails.
            for name in (prefix + "-identity", host):
                result = subprocess.run(
                    ["podman", "pod", "exists", name], capture_output=True, check=False
                )
                if result.returncode == 0:
                    podman(["pod", "rm", "-f", name])
                elif result.returncode != 1:
                    raise RuntimeError(
                        "Cannot check disposable database pod during cleanup"
                    )
            exists = subprocess.run(
                ["podman", "volume", "exists", claim], capture_output=True, check=False
            )
            if exists.returncode == 0:
                podman(["volume", "rm", claim])
            elif exists.returncode != 1:
                raise RuntimeError(
                    "Cannot check disposable database volume during cleanup"
                )
            if (
                secret
                in podman(["secret", "ls", "--format", "{{.Name}}"]).stdout.splitlines()
            ):
                podman(["secret", "rm", secret])
            podman(["network", "rm", network])
    print("PASS: database runtime verification complete; disposable resources removed")


if __name__ == "__main__":
    try:
        run()
    except RuntimeError as error:
        raise SystemExit("FAIL: " + str(error)) from None
    except (OSError, subprocess.TimeoutExpired):
        raise SystemExit(
            "FAIL: database runtime verification (diagnostics withheld)"
        ) from None
