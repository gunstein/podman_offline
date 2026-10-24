"""Focused item 65 lab path: execute the canonical manual over administrator/runtime SSH."""

import gzip
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "docs/PRODUCTION-INSTALL.md"
# The manifest is also a drift gate: required operator steps cannot disappear.
STEPS = (
    "values",
    "upload-directory",
    "admin-login",
    "transfer",
    "tool-bootstrap",
    "setup",
    "cache-remedy",
    "login",
    "init-layout",
    "gateway-config",
    "credentials-transfer",
    "gateway-credentials",
    "gateway-install",
    "gateway-check",
    "identity-config",
    "identity-install",
    "identity-check",
    "status",
    "boot-check",
)


def blocks(text=None):
    text = MANUAL.read_text() if text is None else text
    matches = re.findall(
        r"<!-- operator: ([a-z-]+) -->\n```sh\n(.*?)\n```", text, re.DOTALL
    )
    result = dict(matches)
    if len(result) != len(matches) or set(result) != set(STEPS):
        raise ValueError(
            "Operator manual step IDs changed; update/review the executable mapping"
        )
    return result


def assignments(values):
    return (
        "set -eu\n"
        + "\n".join(
            key + "=" + shlex.quote(str(value)) for key, value in values.items()
        )
        + "\n"
    )


def script(step, values):
    return assignments(values) + blocks()[step] + "\n"


def operator(run, step, values, runtime=False):
    code = script(step, values)
    if runtime:
        return run.command(run.operator_ssh + ["bash -se"], code)
    return run.ssh("PROD", code)


def infrastructure(run, values):
    """Only declared account baseline and disposable SSH access, never product setup."""
    key = run.private / "operator-key"
    run.command(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key])
    public = Path(str(key) + ".pub").read_text().strip()
    account = values["runtime"]
    run.ssh(
        "PROD",
        "set -eu\ngetent passwd "
        + shlex.quote(account)
        + " >/dev/null || sudo -n useradd -m -s /bin/bash "
        + shlex.quote(account)
        + "\n"
        + "sudo -n -H -u "
        + shlex.quote(account)
        + " bash -c "
        + shlex.quote(
            'umask 077; mkdir -p "$HOME/.ssh"; cat >> "$HOME/.ssh/authorized_keys"'
        )
        + " <<'LAB_PUBLIC_KEY'\n"
        + public
        + "\nLAB_PUBLIC_KEY\n",
    )
    run.operator_ssh = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=8",
        "-i",
        str(key),
        account + "@" + run.cfg["PROD_IP"],
    ]
    run.operator_values = values
    run.operator_public_key = public


def cleanup(run):
    if not getattr(run, "operator_public_key", None):
        return
    values = run.operator_values
    incoming = values.get("credentials")
    if incoming:
        if not re.fullmatch(r"/var/tmp/host65-creds-[A-Za-z0-9_-]+", incoming):
            raise ValueError("Unexpected disposable credential-input path")
        names = (
            "web.crt",
            "web.key",
            "ca.crt",
            "identity.crt",
            "identity.key",
            "alice-password",
            "bob-password",
        )
        target = shlex.quote(incoming)
        cleanup_script = (
            "if [ -d "
            + target
            + " ]; then rm -f -- "
            + " ".join(shlex.quote(incoming + "/" + name) for name in names)
            + "; rmdir -- "
            + target
            + "; fi"
        )
        run.command(run.operator_ssh + ["bash -se"], cleanup_script)
    # Remote key cleanup is an infrastructure action, executed as its owner.
    code = r"""from pathlib import Path
import sys
p = Path.home() / '.ssh/authorized_keys'
key = sys.argv[1]
lines = p.read_text().splitlines()
p.write_text(''.join(line + '\n' for line in lines if line != key))
"""
    run.ssh(
        "PROD",
        "sudo -n -H -u "
        + shlex.quote(values["runtime"])
        + " python3 -I -B - "
        + shlex.quote(run.operator_public_key)
        + " <<'CLEAN_KEY'\n"
        + code
        + "\nCLEAN_KEY\n",
    )
    run.operator_public_key = None


def interrupted_setup(run, values):
    """Instrument a separately authenticated helper in memory; production files stay intact."""
    # This is extra fault-injection infrastructure. Initial and successful
    # repeat/retry runs below execute the exact unmodified manual command.
    launcher = """import gzip, hashlib, os, signal, sys
path = '/usr/local/libexec/podman-offline-release.py.gz'
with open(path, 'rb') as stream:
    data = stream.read()
if hashlib.sha256(data).hexdigest() != sys.argv[1]:
    raise SystemExit('FAIL: unexpected protected helper')
namespace = {'__name__': 'interrupted_setup'}
exec(compile(gzip.decompress(data), path, 'exec'), namespace)
original = namespace['command']
def command(arguments, allowed=(0,)):
    if arguments[0] == 'systemd-tmpfiles':
        print('PROBE: publications authenticated; interrupt before journal flush', flush=True)
        os.kill(os.getpid(), signal.SIGKILL)
    return original(arguments, allowed)
namespace['command'] = command
sys.argv = ['release.py'] + sys.argv[2:]
namespace['main']()
"""
    setup = blocks()["setup"]
    # Keep the same selection logic and CLI argv. Replace only the interpreter
    # transport for this explicitly labelled injected attempt.
    original = "gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - setup"
    replacement = 'sudo python3 -I -B - "$helper_sha256" setup'
    if original not in setup:
        raise ValueError(
            "Manual setup transport changed; review fault-injection mapping"
        )
    prefix, invocation = setup.split(original, 1)
    # Put the heredoc redirection on the final continued command line.
    command = (
        replacement
        + invocation.rstrip()
        + " <<'INJECTED_SETUP'\n"
        + launcher
        + "INJECTED_SETUP\n"
    )
    code = assignments(values) + prefix + command
    # Expected SIGKILL is checked explicitly, never hidden by Run.command's
    # general failure handling. Raw output is bounded by the helper's redaction.
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            run.host("PROD"),
            "bash -se",
        ],
        input=code,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    run.log_streams(result.stdout, result.stderr)
    if (
        result.returncode not in (137, 9)
        or "PROBE: publications authenticated; interrupt before journal flush"
        not in result.stdout
    ):
        raise RuntimeError("Wrong setup interruption; no successful injected boundary")


def initial_setup(run, values):
    """Only the exact documented, sole cache preflight failure permits a remedy."""
    code = script("setup", values)
    run.write("# manual setup first attempt\n" + code + "\n")
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            run.host("PROD"),
            "bash -se",
        ],
        input=code,
        capture_output=True,
        text=True,
        check=False,
        timeout=3600,
    )
    run.log_streams(result.stdout, result.stderr)
    if result.returncode == 0 and "PASS: host setup" in result.stdout:
        return
    errors = re.findall(r"(?m)^- (.*)$", result.stdout + result.stderr)
    if (
        result.returncode != 1
        or "preflight failed before changes" not in result.stdout + result.stderr
        or len(errors) != 1
        or not errors[0].startswith(
            "set subj_cache_size = 16381 in /etc/fapolicyd/fapolicyd.conf"
        )
    ):
        raise RuntimeError(
            "Manual setup failed; no automatic repair or retry for an unexpected failure"
        )
    run.write(
        "EXPECTED: sole cache preflight failure; execute manual cache-remedy then setup\n"
    )
    run.meta["setup_preflight_remedy"] = "cache-remedy"
    operator(run, "cache-remedy", values)
    operator(run, "setup", values)


def checked_runtime(run, step, values):
    output = operator(run, step, values, True)
    expected = {"gateway-check": "204", "identity-check": "200"}.get(step)
    if expected is not None and output.strip() != expected:
        raise RuntimeError("Manual " + step + " returned an unexpected HTTP result")
    return output


def execute(run):
    """One focused preparation/manual scenario, not the future complete item 67 matrix."""
    SCP = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
    ]

    minimal = run.platform_help_only
    for action in ("build-images", "pull-images"):
        run.step("03-" + action, lambda a=action: run.guest("DEV", a))
    tree = "src"
    if run.renamed_product:
        run.step("03-renamed-generate", lambda: run.guest("DEV", "renamed-generate"))
        tree = "renamed"
    action = "renamed-bundle" if run.renamed_product else "bundle"
    run.step("04-bundle", lambda: run.guest("DEV", action))
    run.step(
        "04-bundle-list",
        lambda: run.record_bundles(
            "renamed-bundle-list" if run.renamed_product else "bundle-list"
        ),
    )
    gateway = "gateway" if run.renamed_product else "platform"
    identity = "login-service" if run.renamed_product else "identity"
    chosen = [gateway] if minimal else [gateway, identity]
    for name in chosen:
        run.step(
            "05-transfer-" + name,
            lambda n=name: run.transfer(bundle=n, tree=tree, publish=False),
        )
    base = "podman-offline-acceptance/" + run.id
    keyring = run.folder / "bundle-signing.gpg"
    helper = run.folder / "release.py.gz"
    helper.write_bytes(
        gzip.compress((ROOT / "scripts/release.py").read_bytes(), mtime=0)
    )
    values = {
        "server": run.cfg["PROD_IP"],
        "admin": run.cfg["SSH_USER"],
        "runtime": run.product[:27] + "-ops",
        "product": run.product,
        "gateway": gateway,
        "login_component": identity,
        "gateway_version": run.meta["bundles_built"][gateway],
        "login_version": run.meta["bundles_built"][identity],
        "port": run.cfg["HTTPS_PORT"],
        "public_origin": "https://"
        + run.cfg["PROD_HOST"]
        + ":"
        + run.cfg["HTTPS_PORT"],
        "bind_ip": run.cfg["PROD_IP"],
        "upload": "/var/tmp/host65-" + run.id,
        "credentials": "/var/tmp/host65-creds-" + run.id,
        "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "key_sha256": hashlib.sha256(keyring.read_bytes()).hexdigest(),
        "with_identity": "no" if minimal else "yes",
        "credential_format": "pem",
        "discovery_path": "/identity/.well-known/openid-configuration",
    }
    run.step(
        "05-fresh-host-baseline",
        lambda: run.ssh(
            "PROD",
            "sudo -n test ! -e /var/log/journal && sudo -n test ! -e /var/lib/"
            + shlex.quote(run.product),
        ),
    )
    run.step("05-runtime-ssh-infrastructure", lambda: infrastructure(run, values))
    run.step(
        "05-manual-upload-directory", lambda: operator(run, "upload-directory", values)
    )

    def delivery():
        files = [helper, keyring]
        for name in chosen:
            archive = (
                run.product
                + "-"
                + name
                + "-"
                + run.meta["bundles_built"][name]
                + "-offline.tar.gz"
            )
            files += [run.folder / archive, run.folder / (archive + ".asc")]
        run.command(SCP + files + [run.host("PROD") + ":" + values["upload"] + "/"])

    run.step("05-delivery", delivery)
    run.step(
        "06-manual-tool-bootstrap", lambda: operator(run, "tool-bootstrap", values)
    )

    run.step("06-manual-setup-first", lambda: initial_setup(run, values))
    public_records = ["/var/lib/" + run.product + "/keyring.gpg"] + [
        "/var/lib/"
        + run.product
        + "/releases/"
        + run.product
        + "-"
        + name
        + "-"
        + run.meta["bundles_built"][name]
        + "/.release.json"
        for name in chosen
    ]

    def retained_records():
        return run.ssh(
            "PROD",
            "sudo -n sha256sum " + " ".join(map(shlex.quote, public_records)),
            log_stdout=False,
        )

    before = retained_records()
    run.step("06-manual-setup-repeat", lambda: operator(run, "setup", values))
    run.step("06-setup-interruption", lambda: interrupted_setup(run, values))
    run.step("06-manual-setup-retry", lambda: operator(run, "setup", values))

    def retained():
        if retained_records() != before:
            raise RuntimeError(
                "Pinned key or release provenance changed across repeat/interruption/retry"
            )
        run.meta["host_setup_retained_records"] = True

    run.step("06-retained-publications", retained)
    run.step(
        "06-runtime-init-layout", lambda: operator(run, "init-layout", values, True)
    )
    run.step(
        "06-runtime-init-layout-repeat",
        lambda: operator(run, "init-layout", values, True),
    )
    run.step(
        "06-runtime-gateway-config",
        lambda: operator(run, "gateway-config", values, True),
    )
    # External credential delivery is an explicitly demo-only DEV fixture;
    # production does not run any demo provisioning code.
    run.step("06-credential-fixture", lambda: run.guest("DEV", "host65-credentials"))

    def credentials():
        paths = {
            "web.crt": "platform/credentials/web/web.crt",
            "web.key": "platform/credentials/web/web.key",
            "ca.crt": "PKI/private/ca.crt",
        }
        if not minimal:
            paths.update(
                {
                    "identity.crt": "identity/credentials/identity/identity.crt",
                    "identity.key": "identity/credentials/identity/identity.key",
                    "alice-password": "identity/credentials/users/alice-password",
                    "bob-password": "identity/credentials/users/bob-password",
                }
            )
        for name, relative in paths.items():
            local = run.private / name
            run.command(
                SCP
                + [
                    run.host("DEV") + ":" + base + "/host65-credentials/" + relative,
                    local,
                ]
            )
            local.chmod(0o600)
            if name.endswith("-password"):
                run.redactions.append(local.read_text().strip())
            run.command(
                SCP
                + [
                    "-i",
                    str(run.private / "operator-key"),
                    "-o",
                    "IdentitiesOnly=yes",
                    local,
                    values["runtime"]
                    + "@"
                    + values["server"]
                    + ":"
                    + values["credentials"]
                    + "/",
                ]
            )

    run.step("06-credential-delivery", credentials)
    runtime_steps = ["gateway-credentials", "gateway-install", "gateway-check"]
    if not minimal:
        runtime_steps += ["identity-config", "identity-install", "identity-check"]
    for name in runtime_steps:
        run.step("07-manual-" + name, lambda n=name: checked_runtime(run, n, values))

    def logs():
        output = operator(run, "status", values, True)
        entries = [
            json.loads(line) for line in output.splitlines() if line.startswith("{")
        ]
        unit = run.product + "-" + gateway + ".service"
        if not entries or not any(
            (entry.get("_SYSTEMD_USER_UNIT") == unit or entry.get("USER_UNIT") == unit)
            for entry in entries
        ):
            raise RuntimeError("No service journal entries from real runtime SSH")

    run.step("08-runtime-status-journal", logs)
    run.finished = True
