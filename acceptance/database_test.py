#!/usr/bin/env python3
"""Disposable real PostgreSQL/runtime tests on the dev VM; never print credentials."""

import base64
import copy
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
from deployment import common as deployment_common
from deployment import deploy
from deployment import render as rendering


def podman(arguments, expected=0):
    """Withhold subprocess diagnostics: only controlled checks may reach evidence."""
    result = subprocess.run(
        ["podman"] + arguments, capture_output=True, text=True, check=False, timeout=180
    )
    if result.returncode != expected:
        operation = arguments[0]
        if arguments[:2] in (["kube", "play"], ["kube", "down"]):
            operation = " ".join(arguments[:2] + [Path(arguments[-1]).name])
        raise RuntimeError(
            f"Database runtime check failed at {operation} (expected {expected}, exit {result.returncode})"
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


def volume_guard(base, secret, claim, documents):
    """Exercise the lifecycle guard against this actual initialized test volume.

    documents are the manifests that started the database; the preflight reads
    the volume and Secret from them as it would from effective_documents().
    """
    path = base / "guard/config.yaml"
    config = {
        deployment_common.SECRET_FILES: {
            secret: [{"path": "lost", "generate": ["password"]}]
        },
    }
    try:
        deploy.database_preflight(config, path, documents)
    except deployment_common.DeployError as error:
        if "existing volume " + claim not in str(error) or "restore" not in str(error):
            raise RuntimeError("Unexpected database volume guard failure") from None
    else:
        raise RuntimeError(
            "Existing initialized database permitted missing-password generation"
        )
    if (path.parent / "lost/password").exists():
        raise RuntimeError("Database volume guard changed private state")
    print("PASS: actual initialized volume refuses lost-password generation")


def init_schema_check(base, network, client):
    """Run the actual app1 init twice against the disposable, already started DB."""
    probe = copy.deepcopy(client)
    probe["metadata"]["name"] += "-schema"
    probe["metadata"]["annotations"] = {
        "io.podman.annotations.init.container.type": "always"
    }
    source = rendering.load_yaml_all(ROOT / "components/app1/manifests/60-todo.yaml")[
        0
    ]["spec"]["initContainers"][0]
    init = copy.deepcopy(source)
    init["env"] = copy.deepcopy(client["spec"]["containers"][0]["env"])
    probe["spec"]["initContainers"] = [init]
    check = probe["spec"]["containers"][0]
    check.pop("args", None)
    check["name"] = "check"
    check["image"] = init["image"]
    manifest = base / "schema-init.yaml"
    for repeated in (False, True):
        expected_rows = (
            [{"owner": "init-check", "title": "retained todo", "done": False}]
            if repeated
            else []
        )
        # Podman 5.8.2 reserializes YAML before parsing it again. Multiline
        # command scalars can fail that round trip; keep this fixed probe on one line.
        statements = [
            "from database import connect",
            "from schema import verify_ready",
            "verify_ready()",
            "db = connect()",
            'rows = db.execute("SELECT owner, title, done FROM todos ORDER BY id").fetchall()',
            "assert rows == " + repr(expected_rows),
        ]
        if not repeated:
            statements.append(
                "db.execute(\"INSERT INTO todos(owner, title) VALUES ('init-check', 'retained todo')\")"
            )
        statements += [
            "db.commit()",
            "db.close()",
            'print("Todo init and retained data verified")',
        ]
        check["command"] = ["python", "-c", "; ".join(statements)]
        manifest.write_text(yaml.safe_dump(probe))
        manifest.chmod(0o600)
        try:
            podman(["kube", "play", "--network", network, str(manifest)])
            name = probe["metadata"]["name"] + "-check"
            if podman(["wait", name]).stdout.strip() != "0":
                raise RuntimeError("Todo init ordering or retained-data check failed")
        finally:
            podman(["kube", "down", str(manifest)])
    print(
        "PASS: actual Todo init creates schema before client and retains rows on replay"
    )


def seed_retry_check(base, network, client):
    """Fail the actual SQL init after a committed step, then repair/reimport/replay."""
    source = rendering.load_yaml_all(ROOT / "components/app1/manifests/60-todo.yaml")[0]
    probe = copy.deepcopy(client)
    name = client["metadata"]["name"] + "-seed"
    claim = name + "-input"
    probe["metadata"] = {
        "name": name,
        "annotations": {"io.podman.annotations.init.container.type": "always"},
    }
    init = copy.deepcopy(
        next(
            item
            for item in source["spec"]["initContainers"]
            if item["name"] == "seed-database"
        )
    )
    init["env"] = copy.deepcopy(client["spec"]["containers"][0]["env"])
    probe["spec"]["initContainers"] = [init]
    probe["spec"]["volumes"].append(
        {"name": "seed", "persistentVolumeClaim": {"claimName": claim}}
    )
    check = probe["spec"]["containers"][0]
    check.pop("args", None)
    check["name"] = "check"
    check["image"] = image("app1", "backend")
    check["command"] = [
        "python",
        "-c",
        'from database import connect; db=connect(); assert db.execute("SELECT name, value FROM demo_seed ORDER BY name").fetchall() == [{"name":"reference","value":"release-v1"}]; assert db.execute("SELECT title FROM todos WHERE owner=\'init-check\'").fetchall() == [{"title":"retained todo"}]; db.close()',
    ]
    inputs = base / "seed-input"
    inputs.mkdir(exist_ok=True)
    reference = inputs / "010-reference.sql"
    reference.write_bytes(
        (ROOT / "components/app1/files/sql/010-reference.sql").read_bytes()
    )
    broken = inputs / "050-failure.sql"
    broken.write_text("SELECT 1 / 0;\n")
    volumes = {claim: [reference, broken]}
    archives = base / "seed-archives"
    manifest = base / "seed-retry.yaml"
    host = next(item["value"] for item in init["env"] if item["name"] == "DB_HOST")
    try:
        for attempt in range(3):
            rendering.write_file_archives(volumes, archives)
            docs = rendering.volume_claims(volumes, archives) + [probe]
            manifest.write_text(yaml.safe_dump_all(docs))
            manifest.chmod(0o600)
            try:
                play = subprocess.run(
                    ["podman", "kube", "play", "--network", network, str(manifest)],
                    capture_output=True,
                    check=False,
                    timeout=180,
                )
                code = podman(["wait", name + "-seed-database"]).stdout.strip()
                if not code.isdigit() or not 0 <= int(code) <= 255:
                    raise RuntimeError("Invalid SQL init exit status")
                if attempt == 0:
                    if code == "0":
                        raise RuntimeError("Broken SQL init was reported successful")
                    statuses = podman(
                        [
                            "ps",
                            "-a",
                            "--filter",
                            "name=" + name + "-check",
                            "--format",
                            "{{.Status}}",
                        ]
                    )
                    if any(
                        not row.startswith(("Created", "Configured"))
                        for row in statuses.stdout.splitlines()
                    ):
                        raise RuntimeError("Consumer started despite failed SQL init")
                    query = 'export PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"; exec psql -XAt -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "SELECT value FROM demo_seed WHERE name=\'reference\'"'
                    if (
                        podman(
                            ["exec", host + "-db", "sh", "-ec", query]
                        ).stdout.strip()
                        != "release-v1"
                    ):
                        raise RuntimeError(
                            "Expected earlier committed SQL step was not observed"
                        )
                    broken.write_text("SELECT 1;\n")
                elif (
                    play.returncode
                    or code != "0"
                    or podman(["wait", name + "-check"]).stdout.strip() != "0"
                ):
                    raise RuntimeError("SQL retry/replay or retained Todo check failed")
            finally:
                podman(["kube", "down", str(manifest)])
    finally:
        present = subprocess.run(
            ["podman", "volume", "exists", claim],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if present.returncode == 0:
            podman(["volume", "rm", claim])
        elif present.returncode != 1:
            raise RuntimeError("Cannot inspect disposable seed volume for cleanup")
    print(
        "PASS: failed SQL init refused startup; repaired import and replay retained Todo data"
    )


def database_documents(secret, claim, host, password):
    """The disposable PostgreSQL Secret, volume and Pod in the supported layout."""
    return [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": secret},
            "data": {"password": base64.b64encode(password.encode()).decode()},
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
                            "items": [{"key": "password", "path": "password"}],
                        },
                    },
                ],
            },
        },
    ]


def identity_check(base, network, name, host, password, expected):
    """Deliver the complete value through secretKeyRef; never put it in argv."""
    secret = name + "-connection"
    # Test-only .NET quoting keeps the existing special-password DB coverage.
    # The product templates deliberately reject these characters instead.
    connection = (
        None
        if password is None
        else (
            "Host="
            + host
            + ';Port=5544;Database=configured-database;Username=configured-user;Password="'
            + password.replace('"', '""')
            + '";Timeout=5;Include Error Detail=false'
        )
    )
    container = {
        "name": "app",
        "image": image("identity", "app"),
        "imagePullPolicy": "Never",
        "args": ["--database-check"],
    }
    docs = []
    if connection is not None:
        docs.append(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": secret},
                "data": {"connection": base64.b64encode(connection.encode()).decode()},
            }
        )
        container["env"] = [
            {
                "name": "ConnectionStrings__Default",
                "valueFrom": {"secretKeyRef": {"name": secret, "key": "connection"}},
            }
        ]
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name},
            "spec": {"restartPolicy": "Never", "containers": [container]},
        }
    )
    manifest = base / "identity-client.yaml"
    manifest.write_text(yaml.safe_dump_all(docs))
    manifest.chmod(0o600)
    try:
        podman(["kube", "play", "--network", network, str(manifest)])
        if podman(["wait", name + "-app"]).stdout.strip() != str(expected):
            raise RuntimeError("Identity complete connection-string result mismatch")
        result = podman(["logs", name + "-app"])
        output = result.stdout + result.stderr
        message = {
            0: "verified via ConnectionStrings__Default",
            1: "Missing ConnectionStrings__Default",
            2: "28P01",
        }[expected]
        if (
            message not in output
            or (password and password in output)
            or (connection and connection in output)
        ):
            raise RuntimeError("Identity connection-string diagnostics invalid")
    finally:
        podman(["kube", "down", str(manifest)])
    print("PASS: Identity complete connection string; expected exit " + str(expected))


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
                docs = database_documents(secret, claim, host, password)
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
                    deployment_common.SECRET_FILES: {
                        secret: [{"path": ".", "generate": ["password"]}]
                    },
                }
                deploy.database_preflight(config, base / "config.yaml", docs)
                rendering.generate_secrets(config, base)
                if password_path.read_bytes() != retained:
                    raise RuntimeError(
                        "Existing database password changed during generation transition"
                    )
                volume_guard(base, secret, claim, docs)
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
                # The Python/init examples keep their file interface. Identity reads
                # only a complete string from a kube Secret, like an unchanged image.
                init_schema_check(base, network, client)
                seed_retry_check(base, network, client)
                identity_check(
                    base, network, client_name, host, password.rstrip("\n"), 0
                )
                identity_check(
                    base, network, client_name, host, "deliberately-wrong-secret", 2
                )
                identity_check(base, network, client_name, host, None, 1)
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
            for name in (prefix + "-identity-schema", prefix + "-identity", host):
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
