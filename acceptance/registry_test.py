#!/usr/bin/env python3
"""Prove TLS registry-only bundling and expected failures with a temporary dev registry."""

# ruff: noqa: UP021, UP022 - retain the Python 3.6 subprocess API on the guest

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "docker.io/library/busybox:1.37.0"
SERVER = "docker.io/library/registry:3.0.0"
# Distribution's HTTP handler emits Combined access records even with a JSON app logger.
COMBINED_ACCESS = re.compile(
    r"\S+ - \S+ \[[0-9]{2}/[A-Za-z]{3}/[0-9]{4}:[0-9]{2}:[0-9]{2}:[0-9]{2} [+-][0-9]{4}\] "
    r'"(?P<method>[A-Z]+) (?P<path>(?:[^"\\ ]|\\.)+) HTTP/[0-9]+\.[0-9]+" '
    r'(?P<status>[1-5][0-9]{2}) [0-9]+ "(?:[^"\\]|\\.)*" "(?:[^"\\]|\\.)*"'
)


def command(arguments, cwd=None, env=None, expected_failure=False):
    """Log controlled test commands with separate streams and enforce their expected exit."""
    print("+ " + " ".join(map(str, arguments)), flush=True)
    result = subprocess.run(
        list(map(str, arguments)),
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=300,
    )
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    expected = 1 if expected_failure else 0
    if result.returncode != expected:
        raise RuntimeError(
            f"Registry test command exit {result.returncode} (expected {expected})"
        )
    return result.stdout, result.stderr


def image_exists(image):
    """Distinguish a missing image from a Podman command failure."""
    result = subprocess.run(
        ["podman", "image", "exists", image],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=10,
    )
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode not in (0, 1):
        raise RuntimeError("Cannot check registry fixture image cache")
    return result.returncode == 0


def write_manifest(fixture, image):
    """Write an offline Pod fixture with one exact registry image reference."""
    (fixture / "manifests/app.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "registry-test"},
                "spec": {
                    "restartPolicy": "Always",
                    "containers": [
                        {
                            "name": "app",
                            "image": image,
                            "imagePullPolicy": "Never",
                            "command": ["sh", "-c", "sleep 600"],
                        }
                    ],
                },
            }
        )
    )


def check_operations(path, expected):
    """Require the exact Podman operation sequence without logging credential arguments."""
    operations = path.read_text().splitlines() if path.exists() else []
    print("REGISTRY_OPERATIONS " + json.dumps(operations))
    if operations != expected:
        raise RuntimeError(
            "Registry-only phase invoked unexpected operations or a build"
        )


def access_requests(output):
    """Project public request fields from JSON or Combined logs; reject unknown formats."""
    requests = []
    for line in output.splitlines():
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise TypeError("Expected a log object")
        except (TypeError, ValueError):
            match = COMBINED_ACCESS.fullmatch(line)
            if not match:
                raise RuntimeError("Invalid registry JSON or Combined log") from None
            method, path, status = match.group("method", "path", "status")
            status = int(status)
        else:
            method, path, status = (
                row.get("http.request.method"),
                row.get("http.request.uri"),
                row.get("http.response.status"),
            )
        if (
            method == "GET"
            and isinstance(path, str)
            and re.fullmatch(
                r"/v2/acceptance/busybox/(?:manifests/(?:1\.37\.0|sha256:[0-9a-f]{64})|blobs/sha256:[0-9a-f]{64})",
                path,
            )
        ):
            if type(status) is not int:
                continue
            requests.append({"method": method, "path": path, "status": status})
    return requests


def registry_requests(container, since):
    """Read both registry log streams privately and require successful manifest and blob GETs."""
    result = subprocess.run(
        ["podman", "logs", "--since", since, container],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Cannot read registry access logs")
    requests = access_requests(result.stdout) + access_requests(result.stderr)
    for request in requests:
        print("REGISTRY_REQUEST " + json.dumps(request, sort_keys=True))
    for kind in ("manifests", "blobs"):
        if not any(
            "/" + kind + "/" in row["path"] and row["status"] == 200 for row in requests
        ):
            raise RuntimeError(
                f"No successful registry {kind} GET; download not proven"
            )


def negative_bundle(fixture, image, env, log, label):
    """Require a pull failure with the image/login hint and no save or build fallback."""
    write_manifest(fixture, image)
    log.write_text("")
    _out, err = command(
        ["python3", "bundle.py"], cwd=fixture, env=env, expected_failure=True
    )
    if image not in err or "podman login" not in err or len(err.splitlines()) != 1:
        raise RuntimeError("Wrong diagnostic for the expected registry pull failure")
    check_operations(log, ["pull"])
    print(f"PASS: expected {label} failure; no save/build fallback")


def main(base, run):
    """Seed a loopback TLS registry, test uncached/cached pulls and retain only public bundle evidence."""
    fixture = base / "registry-fixture"
    fixture.mkdir(mode=0o700)
    (fixture / "manifests").mkdir()
    (fixture / "dev").mkdir()
    for name in (
        "deploy.sh",
        "bundle.py",
        "README.md",
        "dev/build-images.sh",
        "dev/pull-images.sh",
    ):
        shutil.copy2(ROOT / name, fixture / name)
    for name in ("deployment", "scripts", "quadlet"):
        shutil.copytree(ROOT / name, fixture / name)
    (fixture / "VERSION").write_text("0.0.0\n")
    (fixture / "config.defaults.yaml").write_text("HTTPS_PORT: 8443\n")
    private = Path(
        tempfile.mkdtemp(prefix="registry-test-", dir=os.environ["XDG_RUNTIME_DIR"])
    )
    container = "offline-registry-" + run
    cert_dir, created = None, False
    try:
        tls = private / "tls"
        tls.mkdir(mode=0o700)
        command(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=offline-registry",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
                "-keyout",
                tls / "server.key",
                "-out",
                tls / "server.crt",
            ]
        )
        command(["podman", "pull", "--policy=always", SERVER])
        command(
            [
                "podman",
                "create",
                "--name",
                container,
                "-p",
                "127.0.0.1::5000",
                "-e",
                "REGISTRY_HTTP_TLS_CERTIFICATE=/tls/server.crt",
                "-e",
                "REGISTRY_HTTP_TLS_KEY=/tls/server.key",
                "-e",
                "REGISTRY_LOG_FORMATTER=json",
                "-e",
                "REGISTRY_LOG_LEVEL=info",
                "-e",
                "OTEL_TRACES_EXPORTER=none",
                SERVER,
            ]
        )
        created = True
        command(["podman", "cp", tls, container + ":/tls"])
        command(["podman", "start", container])
        binding, _ = command(["podman", "port", container, "5000/tcp"])
        if not re.fullmatch(r"127\.0\.0\.1:[0-9]+\n?", binding):
            raise RuntimeError("Unexpected registry port binding")
        registry = binding.strip()
        image = registry + "/acceptance/busybox:1.37.0"
        directory = Path.home() / ".config/containers/certs.d" / registry
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        cert_dir = directory
        shutil.copy2(tls / "server.crt", cert_dir / "ca.crt")
        for _ in range(30):
            ready = subprocess.run(
                [
                    "curl",
                    "--noproxy",
                    "*",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "3",
                    "--cacert",
                    str(tls / "server.crt"),
                    "https://" + registry + "/v2/",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("TLS registry did not become ready")
        command(["podman", "pull", "--policy=always", SOURCE])
        image_id, _ = command(
            ["podman", "image", "inspect", "--format", "{{.Id}}", SOURCE]
        )
        image_id = image_id.strip()
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", image_id):
            raise RuntimeError("Invalid source image ID")
        command(["podman", "tag", SOURCE, image])
        command(["podman", "push", image])
        for name in (image, SOURCE, "localhost/offline-example:1"):
            if image_exists(name):
                command(["podman", "image", "rm", name])
        if image_exists(image_id):
            raise RuntimeError(
                "Registry test image still cached; fresh download not proven"
            )
        write_manifest(fixture, image)
        wrapper = private / "bin"
        wrapper.mkdir()
        executable = wrapper / "podman"
        executable.write_text(
            "#!/bin/sh\n# Record operations and forbid builds in the registry-only phase.\n"
            'printf "%s\\n" "$1" >> "$REGISTRY_COMMAND_LOG"\n'
            'if [ "$1" = build ]; then echo "Registry-only build forbidden" >&2; exit 91; fi\n'
            'exec "$REGISTRY_PODMAN" "$@"\n'
        )
        executable.chmod(0o755)
        log = fixture / "operations.txt"
        env = dict(
            os.environ,
            PATH=str(wrapper) + os.pathsep + os.environ["PATH"],
            REGISTRY_PODMAN=shutil.which("podman"),
            REGISTRY_COMMAND_LOG=str(log),
        )
        command(["bash", "dev/build-images.sh"], cwd=fixture, env=env)
        check_operations(log, [])
        since, _ = command(["date", "-u", "+%Y-%m-%dT%H:%M:%S.%NZ"])
        command(["python3", "bundle.py"], cwd=fixture, env=env)
        check_operations(log, ["pull", "save"])
        registry_requests(container, since.strip())
        image_names = (
            fixture / "build/bundle/myproduct-0.0.0/images/images.txt"
        ).read_text()
        if image_names != image + "\n" or not image_exists(image):
            raise RuntimeError("Registry name not preserved after download/save")
        log.write_text("")
        command(["bash", "dev/pull-images.sh"], cwd=fixture, env=env)
        check_operations(log, ["pull"])
        missing = registry + "/acceptance/missing:1"
        command(["podman", "tag", image, missing])
        negative_bundle(
            fixture, missing, env, log, "missing registry tag with cached alias"
        )
        command(["podman", "image", "rm", missing])
        command(["podman", "stop", container])
        negative_bundle(
            fixture, image, env, log, "unavailable registry with cached image"
        )
        (fixture / "image.txt").write_text(image + "\n")
        print(
            "PASS: registry download/save and helper pull; zero builds; cached failures have no fallback"
        )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print("Registry test failed: " + str(error), file=sys.stderr)
        raise
    finally:
        try:
            if created:
                command(["podman", "rm", "--force", "--volumes", container])
        finally:
            try:
                if cert_dir is not None:
                    shutil.rmtree(str(cert_dir))
            finally:
                shutil.rmtree(str(private))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main(Path(sys.argv[1]), sys.argv[2])
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit("FAIL: " + str(error))
