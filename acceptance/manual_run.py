"""Backlog 69 WP6: run the production manual's own commands on the lab hosts.

Each operator block of docs/PRODUCTION-INSTALL.md carries a step ID
(<!-- operator: <id> -->). STEPS maps every ID to how the lab runs it: as the
administrator over SSH, as the runtime user through a real SSH login with a
lab-only key, or as a declared substitute. A manual block is run literally;
only the manual's example values (EXAMPLE) are replaced by this lab's values.
Prompts are answered through a pseudo-terminal, as an operator types them;
an unexpected prompt fails the step.

Checks of printed lines are here (check_*), with expected values from the
scenario's inputs; checks of host state are remote.sh actions that never run
the commands themselves.
"""

import json
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "docs/PRODUCTION-INSTALL.md"

# How the lab runs each operator step of the manual. A new or removed step ID
# fails blocks(): the mapping must be reviewed with the manual.
STEPS = {
    "find-medium": "substitute",  # the lab delivers a copied directory, not a medium
    "mount": "substitute",  # ... which the manual allows: "use that directory"
    "tools": "admin",
    "admin": "admin",
    "credentials": "admin",
    "umount": "substitute",  # nothing is mounted
    "credentials-scp": "laptop",  # the controller is the runtime user's laptop
    "runtime": "runtime",
    "tools-version": "admin",
    "tools-reinstall": "admin",
    "help-journal": "admin",
}

# The manual's example values ("The example used in this manual") and the
# lab value each one stands for. /dev/sdb1 only appears in a substituted step.
EXAMPLE = {
    "/mnt": "delivery",
    "produser": "account",
    "server1.example.org": "host",
    "192.0.2.10": "ip",
    "8443": "port",
    "myproduct": "product",
    "/dev/sdb1": None,
}

# Runs in a pseudo-terminal on the host: python3 -I - <command> <answers> <stop>.
# answers is a JSON list of [question, answer]; each answer is typed only once
# its question is the last thing printed. stop, if not empty, closes the
# terminal (SIGHUP to the command's process group) once that text was printed,
# as a dropped SSH session would. Exit: the command's status, 129 after a stop,
# 3 for a missing or unexpected prompt, 124 after the time limit.
DRIVER = r"""
import json, os, pty, select, signal, sys, time
command, answers, stop = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
pid, fd = pty.fork()
if pid == 0:
    os.execvp("bash", ["bash", "-c", command])
printed, tail, given = b"", b"", 0
IDLE = 30  # seconds a prompt may wait before it counts as unexpected
deadline = time.monotonic() + 3600
idle = time.monotonic()


def finish(code, message=""):
    if message:
        print("\n" + message, flush=True)
    sys.exit(code)


while True:
    ready, _, _ = select.select([fd], [], [], 1)
    if ready:
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
        printed += data
        tail += data
        idle = time.monotonic()
        if stop and stop.encode() in printed:
            os.killpg(pid, signal.SIGHUP)
            os.waitpid(pid, 0)
            finish(129, "INTERRUPTED: terminal closed after " + stop)
    waiting = tail.rstrip(b" ").endswith(b":") and not tail.endswith(b"\n")
    if waiting and given < len(answers) and answers[given][0].encode() in tail:
        os.write(fd, answers[given][1].encode() + b"\r")
        given, tail = given + 1, b""
    elif waiting and time.monotonic() - idle > IDLE:
        os.killpg(pid, signal.SIGTERM)
        finish(3, "FAIL: unexpected prompt: " + tail.decode(errors="replace").splitlines()[-1])
    if time.monotonic() > deadline:
        os.killpg(pid, signal.SIGTERM)
        finish(124, "FAIL: time limit")
_, status = os.waitpid(pid, 0)
if given < len(answers):
    finish(3, "FAIL: prompt not shown: " + answers[given][0])
finish(os.WEXITSTATUS(status) if os.WIFEXITED(status) else 128 + os.WTERMSIG(status))
"""


def blocks(text=None):
    """{step ID: command block} of the manual; the IDs must be exactly STEPS."""
    text = MANUAL.read_text() if text is None else text
    found = re.findall(
        r"<!-- operator: ([a-z-]+) -->\n```sh\n(.*?)\n```", text, re.DOTALL
    )
    result = dict(found)
    if len(result) != len(found) or set(result) != set(STEPS):
        raise ValueError(
            "Manual step IDs changed; review STEPS in acceptance/manual_run.py"
        )
    return result


def examples(text=None):
    """The first column of the manual's example table."""
    text = MANUAL.read_text() if text is None else text
    section = text.split("## The example used in this manual", 1)[1].split("\n## ", 1)[
        0
    ]
    return re.findall(r"(?m)^\| `([^`]+)` \|", section)


def substitute(block, values):
    """The block with each example value replaced by the lab's value."""
    if set(examples()) != set(EXAMPLE):
        raise ValueError("Manual example values changed; review EXAMPLE")
    result = block
    for example, key in sorted(EXAMPLE.items(), key=lambda item: -len(item[0])):
        if example in result:
            if key is None:
                raise ValueError(example + " appears in an executed step")
            result = result.replace(example, str(values[key]))
    return result


def command(step, values):
    """The manual's block for one executed step, with the lab's values."""
    if STEPS[step] == "substitute":
        raise ValueError(step + " is substituted, not executed")
    return substitute(blocks()[step], values)


def driver_script(line, answers=(), stop=""):
    """A bash script that runs one manual line in a pseudo-terminal."""
    arguments = " ".join(
        shlex.quote(a) for a in (line, json.dumps(list(answers)), stop)
    )
    return (
        "python3 -I - "
        + arguments
        + " <<'MANUAL_DRIVER'\n"
        + DRIVER
        + "\nMANUAL_DRIVER\n"
    )


def run_step(run, step, values, answers=(), stop="", expect=0, component=None):
    """Run one manual step as its role; return the printed output.

    expect is the exit status the scenario requires (0, or 1 for a documented
    stop, 129 for a deliberate interruption). component runs the documented
    `myproduct <component>` form of the runtime step for that component.
    """
    line = command(step, values)
    if component is not None:
        documented = "`" + blocks()[step] + " <component>`"
        if step != "runtime" or documented not in MANUAL.read_text():
            raise ValueError("The manual does not document " + documented)
        line += " " + component
    role = STEPS[step]
    if role == "runtime":
        target = run.operator_ssh
    elif role == "admin":
        target = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                  "-o", "ConnectTimeout=8", run.host("PROD")]  # fmt: skip
    else:
        raise ValueError(step + " does not run on the server")
    script = driver_script(line, answers, stop)
    run.write("# manual step " + step + ": " + line + "\n")
    result = subprocess.run(
        target + ["bash -s"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
        timeout=3700,
    )
    run.log_streams(result.stdout, result.stderr)
    run.write(f"exit={result.returncode}\n")
    if result.returncode != expect:
        raise RuntimeError(
            f"Manual step {step} exited {result.returncode}, expected {expect}"
        )
    return result.stdout.replace("\r\n", "\n")


def lines(output):
    return [line.rstrip() for line in output.splitlines()]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


# Checks of printed lines; each names the defect it catches.


def check_preflight_stop(output, account):
    """The missing account stops admin before any change, naming the remedy."""
    require("Preflight stopped before any change:" in output, "no preflight stop")
    require(
        f"- Account {account} does not exist; create it" in output,
        "the stop does not name the missing account",
    )
    require("[OK] installed" not in output, "a package was installed before the stop")


def check_admin_first(output, values, components):
    """First admin run: preflight, each release installed and runnable, the next line."""
    printed = lines(output)
    require("[OK] preflight" in printed, "no preflight line")
    for component in components:
        require(
            any(re.fullmatch(rf"\[OK\] installed {values['product']}-{component}-[0-9.]+", line)
                for line in printed),
            f"{component} was not installed",
        )  # fmt: skip
        require(
            any(re.fullmatch(rf"\[OK\] {values['account']} can run {values['product']}-{component}-[0-9.]+", line)
                for line in printed),
            f"{values['account']} cannot run {component}",
        )  # fmt: skip
    require(
        f"[OK] next: log in as {values['account']} (at the console, or ssh "
        f"{values['account']}@<server>) and run {values['product']}" in printed,
        "the next line differs from the manual",
    )
    require(printed[-1] == f"PASS: {values['product']}-admin completed", "no PASS line")


def check_admin_repeat(output, values, components):
    """An unchanged admin repeat installs and removes nothing and asks nothing."""
    printed = lines(output)
    require(not any(line.startswith(("[OK] installed", "[OK] removed")) for line in printed),
            "a repeat installed or removed a package")  # fmt: skip
    for component in components:
        require(
            any(re.fullmatch(rf"\[OK\] {values['product']}-{component}-[0-9.]+ [0-9.]+ is installed", line)
                for line in printed),
            f"{component} is not reported as installed",
        )  # fmt: skip
    require(printed[-1] == f"PASS: {values['product']}-admin completed", "no PASS line")


def check_runtime_missing_credential(output, values):
    """Before the credentials are delivered, the gateway's install stops on them."""
    require(
        any("ERROR:" in line and "credentials/web" in line for line in lines(output)),
        "the stop does not name the missing web credentials",
    )
    require(
        "deploy.sh install stopped; fix what it names, then run the same command again"
        in output,
        "the runtime command did not stop at the install",
    )
    require(f"PASS: {values['product']} completed" not in output, "the run passed")


def check_credentials(output, files, repeat=False):
    """Every delivered file reported (copied, or kept on a repeat), contents never."""
    for path in files:
        expected = f"[OK] incoming/{path}" + (" is already there" if repeat else "")
        require(expected in lines(output), f"no line for {path}")
    require(
        "PRIVATE KEY" not in output and "BEGIN " not in output,
        "credential content printed",
    )


def check_runtime(output, values, installed, asked=False):
    """<product>: the components installed now, status complete, PASS; prompts only first."""
    printed = lines(output)
    for component, version in installed.items():
        require(f"[OK] {component} {version} installed" in printed,
                f"{component} {version} was not installed")  # fmt: skip
    others = [line for line in printed
              if re.fullmatch(r"\[OK\] [a-z0-9-]+ [0-9.]+ installed", line)
              and line.split()[1] not in installed]  # fmt: skip
    require(not others, "other components were installed: " + ", ".join(others))
    require("Pending: none" in printed, "status shows pending work")
    require(("Public address" in output) == asked, "the prompts were not as expected")
    require(printed[-1] == f"PASS: {values['product']} completed", "no PASS line")


def check_admin_upgrade(output, values, new, old):
    printed = lines(output)
    require(
        f"[OK] installed {values['product']}-help-{new}" in printed,
        f"help {new} was not installed",
    )
    require(
        f"[OK] {values['product']}-help-{old} kept: help {old} is the installed version"
        in printed,
        f"help {old} was not kept as the installed version",
    )


def check_admin_retire(output, values, old):
    require(
        f"[OK] removed {values['product']}-help-{old}, which {values['account']} no longer uses"
        in lines(output),
        f"help {old} was not removed",
    )


def check_tools_version(output, values, version):
    """rpm -q names exactly the delivered tools version (the repair table's row)."""
    require(
        lines(output)[-1] == f"{values['product']}-tools-{version}-1.noarch",
        "rpm -q does not name the delivered tools version",
    )


def check_journal(output, values):
    """The shareable journal lines: the commands' start and result, nothing else."""
    require(f"{values['product']}-admin" in output and ": completed" in output,
            "no start/result lines in the journal")  # fmt: skip
    require("PRIVATE KEY" not in output, "credential content in the journal")


# The scenario -----------------------------------------------------------


SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=8"]  # fmt: skip


def runtime_login(run, values):
    """Lab infrastructure: a lab-only SSH key for the runtime user's real login.

    The account itself is the declared prerequisite (created by the baseline,
    as the account administrator would); no product state is created here.
    """
    key = run.private / "runtime-key"
    run.command(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key])
    public = Path(str(key) + ".pub").read_text().strip()
    run.ssh(
        "PROD",
        "sudo -n -H -u " + shlex.quote(values["account"]) + " bash -c "
        + shlex.quote('umask 077; mkdir -p "$HOME/.ssh"; cat >> "$HOME/.ssh/authorized_keys"')
        + " <<'LAB_PUBLIC_KEY'\n" + public + "\nLAB_PUBLIC_KEY\n",
    )  # fmt: skip
    run.operator_ssh = (
        ["ssh"] + SSH_OPTIONS + ["-i", str(key), values["account"] + "@" + values["ip"]]
    )
    # The laptop's ssh configuration for scp: the server's name, this key.
    config = run.private / "laptop-ssh-config"
    config.write_text(
        f"Host {values['host']}\n  HostName {values['ip']}\n  User {values['account']}\n"
        f"  IdentityFile {key}\n  IdentitiesOnly yes\n  BatchMode yes\n"
        "  StrictHostKeyChecking yes\n  ConnectTimeout 8\n"
    )
    run.write("runtime login key installed for " + values["account"] + "\n")


def laptop_step(run, step, values, directory):
    """Run a manual line on the controller as the runtime user's laptop, in directory."""
    line = command(step, values)
    script = (
        "set -e\ncd " + shlex.quote(str(directory)) + "\n"
        + "scp() { command scp -F " + shlex.quote(str(run.private / "laptop-ssh-config"))
        + " -o UserKnownHostsFile=" + shlex.quote(str(Path.home() / ".ssh/known_hosts"))
        + " -o HostKeyAlias=" + shlex.quote(values["ip"]) + ' "$@"; }\n'
        + line + "\n"
    )  # fmt: skip
    run.write("# manual step " + step + " on the laptop: " + line + "\n")
    return run.command(["bash", "-c", script])


def execute(run, strict=False):
    """The --rpm-manual scenario (backlog 69 WP6), on fapolicyd P1 or, strict, P2."""
    product = run.product
    old = (ROOT / "components/help/VERSION").read_text().strip()
    major, minor, patch = old.split(".")
    new = f"{major}.{minor}.{int(patch) + 1}"
    base = "podman-offline-acceptance/" + run.id
    values = {
        "delivery": "$HOME/" + base + "/delivery",
        "account": product[:27] + "-ops",  # as remote.sh: not named after the product
        "host": run.cfg["PROD_HOST"],
        "ip": run.cfg["PROD_IP"],
        "port": run.cfg["HTTPS_PORT"],
        "product": product,
    }
    tools = (ROOT / "tools/VERSION").read_text().strip()
    credentials = [
        "platform/credentials/web/web.crt",
        "platform/credentials/web/web.key",
    ]
    run.meta.update(rpm_manual=True, strict_fapolicyd=strict, help_versions=[old, new])
    port_answer = "" if values["port"] == "8443" else values["port"]
    origin = f"https://{values['host']}:{values['port']}"

    def admin(name, check=None, answers=(), expect=0, step="admin"):
        def action():
            output = run_step(run, step, values, answers, expect=expect)
            if check:
                check(output)

        run.step(name, action)

    def runtime(name, check=None, answers=(), expect=0, stop="", component=None):
        def action():
            output = run_step(run, "runtime", values, answers, stop, expect, component)
            if check:
                check(output)

        run.step(name, action)

    for action in ("build-images", "pull-images"):
        run.step("03-" + action, lambda a=action: run.guest("DEV", a))
    run.step("04-bundle", lambda: run.guest("DEV", "bundle"))
    run.step("04-rpms", lambda: run.guest("DEV", "rpms"))
    run.step("04-medium", lambda: run.guest("DEV", "admin-medium"))
    run.step("05-transfer-rpms", run.transfer_rpms)
    run.step("05-transfer-medium", run.transfer_medium)
    if strict:
        # Lab infrastructure: the WP0 P2 policy, applied after the reset.
        strict_policy = (ROOT / "acceptance/rpm_wp0/strict.sh").read_text()
        run.step("06-fapolicyd-p2", lambda: run.command(
            ["ssh"] + SSH_OPTIONS + [run.host("PROD"), "sudo -n bash -s"], strict_policy))  # fmt: skip
    # Step 2 of the manual; dnf asks before it installs.
    admin("06-manual-tools", lambda out: require("Complete!" in out, "dnf did not complete"),
          answers=[("Is this ok", "y")], step="tools")  # fmt: skip
    # The runtime account is missing: the documented stop, then its remedy.
    admin("06-manual-admin-no-account",
          lambda out: check_preflight_stop(out, values["account"]),
          answers=[("Runtime account", values["account"]), ("HTTPS port", port_answer)],
          expect=1)  # fmt: skip
    run.step("06-nothing-changed", lambda: run.guest("PROD", "rpm-nothing-changed"))
    run.step("06-account-created", lambda: run.guest("PROD", "admin-baseline"))
    run.step("06-runtime-login-key", lambda: runtime_login(run, values))
    admin("06-manual-admin", lambda out: check_admin_first(out, values, ["platform", "help"]),
          answers=[("Runtime account", values["account"]), ("HTTPS port", port_answer)])  # fmt: skip
    run.step("06-host-prepared", lambda: run.guest("PROD", "rpm-host-check"))
    admin(
        "06-manual-admin-repeat",
        lambda out: check_admin_repeat(out, values, ["platform", "help"]),
    )
    run.step("06-erase-guard", lambda: run.guest("PROD", "admin-erase-guard"))
    # The runtime user before the credentials arrive: the documented stop.
    runtime("07-manual-runtime-no-credentials",
            lambda out: check_runtime_missing_credential(out, values),
            answers=[("Public address", origin), ("IP address", values["ip"])], expect=1)  # fmt: skip
    admin("07-manual-credentials", lambda out: check_credentials(out, credentials),
          step="credentials")  # fmt: skip
    admin("07-manual-credentials-repeat", lambda out: check_credentials(out, credentials, True),
          step="credentials")  # fmt: skip
    # Another medium whose key differs: the documented stop, nothing copied.
    run.step("07-other-medium", lambda: run.guest("PROD", "rpm-other-medium"))
    other = dict(values, delivery="$HOME/" + base + "/other-medium")
    run.step("07-manual-credentials-other", lambda: require(
        "already exist with other content; nothing was copied"
        in run_step(run, "credentials", other, expect=1),
        "a different credential was not refused"))  # fmt: skip
    run.step(
        "07-credentials-delivered", lambda: run.guest("PROD", "rpm-credentials-check")
    )
    platform = (ROOT / "components/platform/VERSION").read_text().strip()
    runtime("07-manual-runtime",
            lambda out: check_runtime(out, values, {"platform": platform, "help": old}))  # fmt: skip
    run.step("07-runtime-installed", lambda: run.guest("PROD", "rpm-runtime-check"))
    runtime("07-manual-runtime-repeat", lambda out: check_runtime(out, values, {}))
    run.step("07-nothing-restarted", lambda: run.guest("PROD", "rpm-no-restart"))
    runtime("07-manual-runtime-help", lambda out: check_runtime(out, values, {"help": old}),
            component="help")  # fmt: skip
    run.step("07-help-restarted-only", lambda: run.guest("PROD", "rpm-reinstall-check"))
    # A new delivery: the newer help release, credentials through scp.
    run.step(
        "08-help-build",
        lambda: run.guest("DEV", "help-upgrade-bundle", new, bundle="help"),
    )
    run.step("08-help-rpm", lambda: run.guest("DEV", "rpm-upgrade", new, bundle="help"))
    run.step("08-transfer-rpms", run.transfer_rpms)
    run.step("08-manual-credentials-scp",
             lambda: laptop_step(run, "credentials-scp", values, run.private / "medium"))  # fmt: skip
    admin(
        "09-manual-admin-upgrade",
        lambda out: check_admin_upgrade(out, values, new, old),
    )
    # The terminal closes once podman has loaded the new help image, before
    # the new version is completed; a fresh login then completes it.
    runtime("09-manual-runtime-interrupted", stop="Loaded image:", expect=129)
    run.step("09-left-unfinished",
             lambda: run.guest("PROD", "rpm-interrupted-check", new, old_version=old))  # fmt: skip
    runtime("09-manual-runtime-resumed",
            lambda out: check_runtime(out, values, {"help": new}))  # fmt: skip
    run.step(
        "09-upgraded",
        lambda: run.guest("PROD", "rpm-upgrade-check", new, old_version=old),
    )
    admin("09-manual-admin-retire", lambda out: check_admin_retire(out, values, old))
    run.step(
        "09-retired",
        lambda: run.guest("PROD", "rpm-retire-check", new, old_version=old),
    )
    admin("09-manual-admin-retire-repeat",
          lambda out: check_admin_repeat(out, values, ["platform", "help"]))  # fmt: skip
    # Tools repair: damaged tools (fault injection), the documented repair.
    run.step("10-tools-damaged", lambda: run.guest("PROD", "rpm-tools-damage"))
    # The manual's symptom: a Python error instead of an ERROR: line.
    admin("10-manual-admin-broken",
          lambda out: require("ERROR:" not in out and "admin.py" in out
                              and "No such file or directory" in out,
                              "not the documented symptom of damaged tools"),
          expect=2)  # fmt: skip
    admin("10-manual-tools-version", lambda out: check_tools_version(out, values, tools),
          step="tools-version")  # fmt: skip
    admin("10-manual-tools-reinstall", lambda out: require("Complete!" in out, "no reinstall"),
          answers=[("Is this ok", "y")], step="tools-reinstall")  # fmt: skip
    admin("10-manual-admin-repaired",
          lambda out: check_admin_repeat(out, values, ["platform", "help"]))  # fmt: skip
    run.step("10-tools-intact", lambda: run.guest("PROD", "rpm-tools-intact"))
    admin(
        "10-manual-help-journal",
        lambda out: check_journal(out, values),
        step="help-journal",
    )
    run.finished = True
