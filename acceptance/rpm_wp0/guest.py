"""Fixed OL9 probe actions sent over SSH stdin. No action runs on import."""

import json
import os
import pwd
import re
import subprocess
import time
from pathlib import Path

import contracts
import mechanisms as mech
import operations as op
from contracts import (
    ACCOUNT,
    APPROVED_FINGERPRINT,
    TOOLS_VERSION,
    require,
)

PREDICATES = []
OBSERVATIONS = []
SIGNATURE_CASES = (
    "product",
    "unsigned",
    "foreign",
    "tampered-header",
    "tampered-payload",
    "product-subkey",
    "foreign-subkey",
)


def check(name, condition):
    require(condition, "Predicate failed: " + name)
    PREDICATES.append(name)
    return True


def policy():
    rules = op.command(["fapolicyd-cli", "--list"]).stdout
    filters = sorted(Path("/etc/fapolicyd").glob("*filter*"))
    plugin = op.command(["rpm", "--eval", "%{__transaction_fapolicyd}"]).stdout.strip()
    require(Path(plugin).is_file(), "RPM fapolicyd plugin is missing")
    return {
        "plugin_package": op.command(
            ["rpm", "-q", "rpm-plugin-fapolicyd"]
        ).stdout.strip(),
        "rules": rules,
        "config": Path("/etc/fapolicyd/fapolicyd.conf").read_text(),
        "filter": "\n".join(p.read_text().rstrip() for p in filters if p.is_file()),
        "languages": [line for line in rules.splitlines() if line.startswith("-> ")],
        "plugin": plugin,
    }


def baseline():
    artifacts = []
    for pattern in (
        "/root/pkg",
        "/root/wp0*",
        "/var/tmp/wp0*",
        "/run/wp0*",
        "/var/lib/myproduct",
        "/var/lib/wp0-probe",
        "/etc/podman-offline-isolation.nft",
        "/etc/systemd/system/podman-offline-isolation.service",
    ):
        import glob

        artifacts.extend(glob.glob(pattern))
    if op.command(["getent", "passwd", ACCOUNT], allowed=(0, 2)).returncode == 0:
        artifacts.append("runtime account already exists")
    keys = op.command(["rpm", "-qa", "gpg-pubkey", "--qf", "%{DESCRIPTION}\\n"]).stdout
    # Inspect public certificates, never key IDs, and never reject ordinary OS keys.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="wp0-gpg-") as home:
        key_result = op.command(
            ["gpg", "--homedir", home, "--batch", "--with-colons", "--show-keys"],
            input=keys,
            allowed=(0, 2),
        )
    require(
        not keys.strip() or key_result.returncode == 0,
        "Cannot inspect installed public keys",
    )
    key_lines = [
        line
        for line in key_result.stdout.splitlines()
        if APPROVED_FINGERPRINT in line
        or (
            "uid:" in line
            and re.search(r"WP0|podman-offline lab RPM", line, re.IGNORECASE)
        )
    ]
    return {
        "os": Path("/etc/oracle-release").read_text(),
        "selinux": op.command(["getenforce"]).stdout,
        "services": [
            op.command(["systemctl", "is-active", service]).stdout.strip()
            for service in ("fapolicyd", "firewalld")
        ],
        "packages": op.command(
            ["rpm", "-qa", "myproduct*", "wp0-*"]
        ).stdout.splitlines(),
        "keys": key_lines,
        "artifacts": sorted(artifacts),
        "policy": policy(),
    }


def apply_p2():
    directory = Path("/etc/fapolicyd/rules.d")
    path = Path("/etc/fapolicyd/fapolicyd.conf")
    files = {item: item.read_text() for item in directory.glob("*.rules")}
    changed, config = contracts.derive_p2_sources(files, path.read_text())
    for item, text in changed.items():
        if text != files[item]:
            item.write_text(text)
    path.write_text(config)
    op.command(["fagenrules", "--load"])
    op.command(["systemctl", "restart", "fapolicyd"])
    return policy()


def provision(public):
    op.command(["useradd", "-m", "-s", "/bin/bash", ACCOUNT])
    account = pwd.getpwnam(ACCOUNT)
    groups = op.command(["id", "-G", ACCOUNT]).stdout.split()
    require(groups == [str(account.pw_gid)], "Runtime account has supplementary groups")
    sudo = op.command(["sudo", "-n", "-l", "-U", ACCOUNT], allowed=tuple(range(256)))
    require(
        "is not allowed to run sudo" in sudo.stdout + sudo.stderr,
        "Runtime account sudo policy is not an explicit refusal",
    )
    directory = Path(account.pw_dir) / ".ssh"
    directory.mkdir(mode=0o700)
    os.chown(directory, account.pw_uid, account.pw_gid)
    key = directory / "authorized_keys"
    require(
        public.startswith("ssh-ed25519 ") and "\n" not in public.strip(),
        "Invalid lab public key",
    )
    key.write_text(public.strip() + "\n")
    key.chmod(0o600)
    os.chown(key, account.pw_uid, account.pw_gid)
    op.command(["restorecon", "-RF", directory])
    return True


def setup_mechanisms():
    op.install_verified(
        [
            op.DELIVERED,
            "wp0-release-base-1.0-1.noarch.rpm",
            "wp0-release-sibling-1.0-1.noarch.rpm",
        ]
    )
    op.wait_trust([op.TOOLS, "wp0-release-base", "wp0-release-sibling"])
    mech.RUN.mkdir(mode=0o700, exist_ok=True)
    mech.STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    account = pwd.getpwnam(ACCOUNT)
    os.chown(mech.STATE, account.pw_uid, account.pw_gid)
    for package in ("wp0-release-base", "wp0-release-sibling"):
        mech.record_identity(package)
    return True


def import_foreign_observation(database):
    # This import cannot authorize a product: it is deliberately outside every
    # bootstrap/candidate database. Check one primary before this setup import.
    colons = op.key_text(op.INPUT / "foreign.asc")
    fingerprints = contracts.primary_fingerprints(colons)
    require(
        len(fingerprints) == 1 and fingerprints[0] != APPROVED_FINGERPRINT,
        "Invalid foreign fixture",
    )
    op.command(["rpmkeys", "--dbpath", database, "--import", op.INPUT / "foreign.asc"])


def signature_matrix(repository=False):
    if repository:
        op.install_verified([op.DELIVERED])
        op.wait_trust([op.TOOLS])
    # C1 intentionally imports a foreign key globally, proving that global RPM
    # trust does not authorize candidates in the isolated product database.
    colons = op.key_text(op.INPUT / "foreign.asc")
    require(
        len(contracts.primary_fingerprints(colons)) == 1
        and contracts.primary_fingerprints(colons)[0] != APPROVED_FINGERPRINT,
        "Foreign setup key must have one distinct primary",
    )
    op.command(["rpm", "--import", op.INPUT / "foreign.asc"])
    global_check = op.command(
        ["rpmkeys", "--define", "_pkgverify_level all", "-K", op.INPUT / "foreign.rpm"],
        allowed=tuple(range(256)),
    )
    require(
        contracts.signature_ok(
            global_check.returncode, global_check.stdout + global_check.stderr
        ),
        "Foreign fixture is not signed by the globally imported key",
    )
    names = (*SIGNATURE_CASES, "repository-download") if repository else SIGNATURE_CASES
    for name in names:
        key_name = (
            "product-subkey.asc"
            if name == "product-subkey"
            else "RPM-GPG-KEY-myproduct"
        )
        package = (
            op.DELIVERED
            if name in ("product", "repository-download")
            else name + ".rpm"
        )
        if repository:
            # Use installed probe tools code for all C1 candidates, plus a
            # positive file-repository download through exactly the same gate.
            code = """import sys, json; sys.path.insert(0,"/usr/libexec/wp0")
import operations as op
op.fresh_directory()
key = op.copy_candidate(sys.argv[1])
op.import_product(key, op.PKG / "db")
if sys.argv[3] == "download":
    op.dnf("download", "--repofrompath=wp0,file:///var/tmp/wp0-input/repositories/product", "--enablerepo=wp0", "--destdir=" + str(op.PKG), "myproduct-tools")
    packages = list(op.PKG.glob("*.rpm"))
    if len(packages) != 1: raise SystemExit(4)
    candidate = packages[0]
else:
    candidate = op.copy_candidate(sys.argv[2])
print(json.dumps({"accepted": op.verify(candidate, op.PKG / "db"), "commands": op.TRANSCRIPT}))
"""
            result = op.command(
                [
                    "python3",
                    "-B",
                    "-c",
                    code,
                    key_name,
                    package,
                    "download" if name == "repository-download" else "copy",
                ]
            )
            verdict = json.loads(result.stdout)
            accepted = verdict["accepted"]
            require(
                type(accepted) is bool and bool(verdict["commands"]),
                "Missing tools verdict",
            )
        else:
            accepted = op.verify_paper_delivery(key_name, package)
        check(
            ("" if name == "repository-download" else "signature-") + name,
            accepted == (name in ("product", "product-subkey", "repository-download")),
        )
    return True


def stop_rules():
    original_keys = op.global_keys()
    for key_name, message in (
        ("two-primary.asc", "exactly one primary"),
        ("foreign.asc", "fingerprint differs"),
    ):
        error = ""
        try:
            op.bootstrap(key_name)
        except RuntimeError as failure:
            error = str(failure)
        check(
            "stop-" + key_name,
            message in error
            and not (op.PKG / "db").exists()
            and op.global_keys() == original_keys
            and op.versions() == [],
        )
    op.fresh_directory()
    import_foreign_observation(op.PKG / "db")
    op.copy_candidate("foreign.rpm")
    check(
        "leftover-setup", (op.PKG / "foreign.rpm").exists() and (op.PKG / "db").exists()
    )
    op.bootstrap()
    actual_keys = op.command(
        [
            "rpm",
            "--dbpath",
            op.PKG / "db",
            "-qa",
            "gpg-pubkey",
            "--qf",
            "%{DESCRIPTION}\\n",
        ]
    ).stdout
    import tempfile

    with tempfile.TemporaryDirectory(prefix="wp0-gpg-") as home:
        colons = op.command(
            ["gpg", "--homedir", home, "--batch", "--with-colons", "--show-keys"],
            input=actual_keys,
        ).stdout
    check(
        "leftover-replaced",
        not (op.PKG / "foreign.rpm").exists()
        and len(list(op.PKG.glob("*.rpm"))) == 1
        and contracts.primary_fingerprints(colons) == [APPROVED_FINGERPRINT]
        and op.versions() == [TOOLS_VERSION],
    )
    observation = Path("/root/wp0-import-observation")
    require(not observation.exists(), "Observation database must be fresh")
    result = op.command(
        ["rpmkeys", "--dbpath", observation, "--import", op.INPUT / "two-primary.asc"],
        allowed=tuple(range(256)),
    )
    keys = op.command(
        [
            "rpm",
            "--dbpath",
            observation,
            "-qa",
            "gpg-pubkey",
            "--qf",
            "%{DESCRIPTION}\\n",
        ],
        allowed=(0, 1),
    ).stdout
    with tempfile.TemporaryDirectory(prefix="wp0-gpg-") as home:
        observed = op.command(
            ["gpg", "--homedir", home, "--batch", "--with-colons", "--show-keys"],
            input=keys,
            allowed=(0, 2),
        ).stdout
    OBSERVATIONS.append(
        {
            "kind": "two-primary-rpm-import-NOT-A-GATE",
            "exit": result.returncode,
            "messages": result.stdout + result.stderr,
            "primary_fingerprints": contracts.primary_fingerprints(observed),
        }
    )
    return True


def repair(state):
    delivered = op.DELIVERED
    old, new = "myproduct-tools-1.0-1.noarch.rpm", "myproduct-tools-3.0-1.noarch.rpm"
    if state in ("R1", "R2"):
        op.install_verified([delivered])
        if state == "R1":
            Path("/usr/bin/wp0-selfcheck").unlink()
            Path("/usr/libexec/wp0/probe_module.py").unlink()
            result = op.command(["rpm", "-V", op.TOOLS], allowed=tuple(range(256)))
            check(
                "diagnosis",
                result.returncode != 0
                and "missing" in result.stdout
                and "wp0-selfcheck" in result.stdout
                and "probe_module.py" in result.stdout
                and op.versions() == [TOOLS_VERSION],
            )
        else:
            op.command(["rpm", "-e", "--justdb", "--noscripts", op.TOOLS])
            check(
                "diagnosis",
                op.versions() == []
                and Path("/usr/bin/wp0-selfcheck").is_file()
                and Path("/usr/libexec/wp0/probe_module.py").is_file(),
            )
    elif state == "R3":
        op.install_verified([old, "wp0-release-sibling-1.0-1.noarch.rpm"])
        mech.RUN.mkdir(mode=0o700, exist_ok=True)
        mech.record_identity("wp0-release-sibling")
        op.fresh_directory()
        key = op.copy_candidate("RPM-GPG-KEY-myproduct")
        op.import_product(key, op.PKG / "db")
        target = op.copy_candidate(delivered)
        require(
            op.verify(target, op.PKG / "db"), "Delivered fixture failed verification"
        )
        op.command(["rpm", "-i", "--replacefiles", target])
        check("diagnosis", op.versions() == ["1.0", TOOLS_VERSION])
    elif state in ("R4", "R5"):
        op.install_verified([old if state == "R4" else new])
        check("diagnosis", op.versions() == (["1.0"] if state == "R4" else ["3.0"]))
    require(op.verify_paper_delivery(), "Paper verification failed before repair")
    before = op.versions()
    if state == "R5":
        identity = mech.package_identity(op.TOOLS)
        checks = {
            str(p): op.file_digest(p) for p in Path("/usr/libexec/wp0").glob("*.py")
        }
        check("newer-stop", contracts.repair_decision(before) == "stop-newer")
        OBSERVATIONS.append(
            {"diagnosis": "STOP: contact the supplier for the current tools package"}
        )
        check(
            "unchanged",
            op.versions() == before
            and mech.package_identity(op.TOOLS) == identity
            and all(op.file_digest(Path(p)) == digest for p, digest in checks.items())
            and op.rpm_clean(op.TOOLS),
        )
        return True
    if contracts.repair_decision(before) == "deduplicate":
        op.dnf("remove", "--duplicates")
        check(
            "duplicate-cleanup",
            op.versions() == [TOOLS_VERSION] and op.rpm_clean("wp0-release-sibling"),
        )
    action = contracts.repair_decision(op.versions())
    require(
        action in ("install", "reinstall"),
        "Repair diagnosis does not permit installation",
    )
    op.paper_install(action)
    check("repair-version", op.versions() == [TOOLS_VERSION])
    check("repair-integrity", op.rpm_clean(op.TOOLS))
    check("repair-trust", op.wait_trust([op.TOOLS]))
    result = op.command(["/usr/bin/wp0-selfcheck"])
    check("repair-execution", result.stdout.strip() == "WP0 trusted module")
    if state == "R3":
        check(
            "release-retained",
            op.versions("wp0-release-sibling") == ["1.0"]
            and op.rpm_clean("wp0-release-sibling"),
        )
    return True


def refusal(args, token="wp0-admin"):
    result = op.command(args, allowed=tuple(range(256)))
    # dnf may return 0 even after an RPM scriptlet failure; inspect diagnostics
    # AND the installed package/file state, not dnf's exit alone.
    require(token in result.stdout + result.stderr, "Missing expected guard diagnostic")
    for package in ("wp0-release-base", "wp0-release-sibling", op.TOOLS):
        require(
            op.versions(package) == (["2.0"] if package == op.TOOLS else ["1.0"])
            and op.rpm_clean(package),
            "Refused erase changed a package",
        )
    return True


def clear_events():
    for name in (
        "holding",
        "release-hold",
        "approved",
        "pause-erase",
        "continue-erase",
        "transaction-pid",
        "transaction-result",
    ):
        (mech.RUN / name).unlink(missing_ok=True)


def wait_file(path):
    return contracts.bounded_poll(lambda remaining: path.exists(), 30)


def guards():
    setup_mechanisms()
    uid = pwd.getpwnam(ACCOUNT).pw_uid
    unit = "user@" + str(uid) + ".service"
    op.command(["systemctl", "start", unit])
    check(
        "manager-running",
        op.command(["systemctl", "is-active", unit]).stdout.strip() == "active",
    )
    base = "wp0-release-base"
    check(
        "plain-dnf-release", refusal(["dnf", "--disablerepo=*", "-y", "remove", base])
    )
    check("plain-rpm-release", refusal(["rpm", "-e", base]))
    check(
        "plain-dnf-tools", refusal(["dnf", "--disablerepo=*", "-y", "remove", op.TOOLS])
    )
    for fault, reason in (
        ("package", "another package"),
        ("boot", "another boot"),
        ("dead", "dead"),
        ("reused", "reused"),
    ):
        clear_events()
        op.command([mech.ADMIN, "erase", base, fault], allowed=(3,))
        transaction = json.loads((mech.RUN / "transaction-result").read_text())
        check(
            "record-" + fault,
            reason in transaction["stdout"] + transaction["stderr"]
            and op.rpm_clean(base)
            and op.versions(base) == ["1.0"]
            and not (mech.RUN / "erase-authorization").exists(),
        )
    clear_events()
    admin = subprocess.Popen(
        [mech.ADMIN, "hold", base], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        wait_file(mech.RUN / "holding")
        check(
            "not-ancestor",
            refusal(
                ["dnf", "--disablerepo=*", "-y", "remove", base], "not an ancestor"
            ),
        )
        (mech.RUN / "release-hold").touch()
        require(admin.wait(timeout=10) == 0, "Hold admin failed")
    finally:
        if admin.poll() is None:
            admin.kill()
            admin.wait(timeout=10)
    uid = pwd.getpwnam(ACCOUNT).pw_uid
    op.command(["systemctl", "stop", "user@" + str(uid) + ".service"])
    inactive = op.command(
        ["systemctl", "is-active", "user@" + str(uid) + ".service"], allowed=(0, 3)
    ).stdout.strip()
    check(
        "manager-independent", inactive == "inactive" and refusal(["rpm", "-e", base])
    )
    clear_events()
    op.command([mech.ADMIN, "erase", base])
    check(
        "authorized-one",
        op.versions(base) == []
        and not (mech.RELEASES / base).exists()
        and op.versions("wp0-release-sibling") == ["1.0"]
        and op.rpm_clean("wp0-release-sibling")
        and not (mech.IDENTITIES / (base + ".json")).exists()
        and not (mech.RUN / "erase-authorization").exists(),
    )
    return True


def locks():
    setup_mechanisms()
    clear_events()
    admin = subprocess.Popen(
        [mech.ADMIN, "hold", "wp0-release-base"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_file(mech.RUN / "holding")
        start = time.monotonic()
        result = op.command(
            mech.dropped("python3", "-B", mech.SOURCE, "runtime"), allowed=(3,)
        )
        check(
            "bounded-runtime",
            "operation lock busy" in result.stderr
            and 5 <= time.monotonic() - start < 10,
        )
        (mech.RUN / "release-hold").touch()
        require(admin.wait(timeout=10) == 0, "Hold admin failed")
    finally:
        if admin.poll() is None:
            admin.kill()
            admin.wait(timeout=10)
    fd = mech.locked_check()
    try:
        result = op.command(
            mech.dropped("python3", "-B", mech.SOURCE, "runtime", str(fd)),
            pass_fds=(fd,),
        )
        check("inherited-accepted", result.returncode == 0)
    finally:
        os.close(fd)
    forged = os.open(str(mech.STATE / ".operation.lock"), os.O_RDWR)
    try:
        result = op.command(
            mech.dropped("python3", "-B", mech.SOURCE, "runtime", str(forged)),
            pass_fds=(forged,),
            allowed=(3,),
        )
        check("forged-refused", "did not inherit" in result.stderr)
    finally:
        os.close(forged)
    clear_events()
    (mech.RUN / "pause-erase").touch()
    admin = subprocess.Popen(
        [mech.ADMIN, "erase", "wp0-release-base"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_file(mech.RUN / "approved")
        # locked_check waited for the check child to exit before dnf was started.
        result = op.command(
            mech.dropped("python3", "-B", mech.SOURCE, "runtime"), allowed=(3,)
        )
        check("check-exit-lock-held", "operation lock busy" in result.stderr)
        admin.kill()
        admin.wait(timeout=10)
        result = op.command(
            mech.dropped("python3", "-B", mech.SOURCE, "runtime"), allowed=(3,)
        )
        check(
            "admin-exit-lock-held",
            "operation lock busy" in result.stderr
            and op.versions("wp0-release-base") == ["1.0"],
        )
        (mech.RUN / "continue-erase").touch()
        wait_file(mech.RUN / "transaction-result")
        result = json.loads((mech.RUN / "transaction-result").read_text())
        check(
            "preun-and-dnf-complete",
            result["exit"] == 0
            and op.versions("wp0-release-base") == []
            and not (mech.RELEASES / "wp0-release-base").exists()
            and op.rpm_clean("wp0-release-sibling"),
        )
        # The killed admin cannot do its normal authorization/identity cleanup;
        # these artifacts are recorded and discarded only by the next rollback.
        check(
            "lock-released",
            op.command(mech.dropped("python3", "-B", mech.SOURCE, "runtime")).returncode
            == 0,
        )
    finally:
        (mech.RUN / "continue-erase").touch()
        if admin.poll() is None:
            admin.kill()
            admin.wait(timeout=10)
    return True


def identities():
    setup_mechanisms()
    base = "wp0-release-base"
    marker = mech.STATE / "executed"
    # Positive control proves these entry points really attempt init-layout
    # when verification succeeds; later marker absence is not vacuous.
    op.command(mech.dropped("/usr/bin/wp0-runtime", base))
    require(
        marker.read_text().strip() == "release-code-ran",
        "Missing release execution control",
    )
    marker.unlink()
    before = (mech.IDENTITIES / (base + ".json")).read_bytes()
    op.install_verified(["wp0-release-base-2.0-1.noarch.rpm"])
    check(
        "bypass-upgrade",
        op.versions(base) == ["2.0"]
        and (mech.RUN / "upgrade-observed").read_text().strip() == "2.0"
        and (mech.IDENTITIES / (base + ".json")).read_bytes() == before,
    )
    for account in ("admin", "runtime"):
        args = [mech.ADMIN, "use", base]
        if account == "runtime":
            args = mech.dropped("/usr/bin/wp0-runtime", base)
        result = op.command(args, allowed=(3,))
        check(
            "mismatch-" + account,
            "mismatching identity" in result.stderr and not marker.exists(),
        )
    sibling = "wp0-release-sibling"
    (mech.IDENTITIES / (sibling + ".json")).unlink()
    # Reinstall via plain dnf after removing the reference: no admin recording.
    op.install_verified(["wp0-release-sibling-2.0-1.noarch.rpm"])
    for account in ("admin", "runtime"):
        args = [mech.ADMIN, "use", sibling]
        if account == "runtime":
            args = mech.dropped("/usr/bin/wp0-runtime", sibling)
        result = op.command(args, allowed=(3,))
        check(
            "missing-" + account,
            "missing identity" in result.stderr and not marker.exists(),
        )
    return True


def audit(start):
    result = op.command(
        [
            "ausearch",
            "--input-logs",
            "-m",
            "FANOTIFY,AVC",
            "-ts",
            *contracts.audit_start_fields(start),
        ],
        allowed=(0, 1),
        stdin=subprocess.DEVNULL,
    )
    output = result.stdout + result.stderr
    lines = [line for line in output.splitlines() if line.startswith("type=")]
    if result.returncode == 1:
        require(
            output.strip() == "<no matches>",
            "Audit query failed or had ambiguous output",
        )
    else:
        require(
            any(line.startswith(("type=FANOTIFY ", "type=AVC ")) for line in lines),
            "Malformed audit result",
        )
    return {"lines": lines, "no_events": result.returncode == 1, "output": output}


def account_python_prepared(root, uid):
    # Root creates only state/config/storage. These descendants and the lock
    # are created by prepare-host's embedded Python after the privilege drop.
    return all(
        (root / name).is_dir() and (root / name).stat().st_uid == uid
        for name in (
            "config/cni/net.d",
            "config/containers/systemd",
            "storage/containers/storage",
        )
    ) and (
        (root / "config/cni/net.d/cni.lock").is_file()
        and (root / "config/cni/net.d/cni.lock").stat().st_uid == uid
    )


def main(action, arguments):
    if action == "baseline":
        return baseline()
    if action == "profile":
        return policy()
    if action == "p2":
        return apply_p2()
    if action == "provision":
        return {"ok": provision(arguments["public"])}
    if action == "audit":
        return audit(arguments["start"])
    if action == "install-prototype":
        names = [p.name for p in op.INPUT.glob("myproduct-host-tools-*.rpm")]
        require(len(names) == 1, "Exactly one prototype host-tools RPM required")
        names += [
            "myproduct-platform-0.4.12-0.4.12-1.noarch.rpm",
            "myproduct-identity-0.4.12-0.4.12-1.noarch.rpm",
        ]
        op.install_verified(names)
        packages = [
            "myproduct-host-tools",
            "myproduct-platform-0.4.12",
            "myproduct-identity-0.4.12",
        ]
        check("prototype-trust", op.wait_trust(packages, code_only=True))
        op.command(
            ["myproduct-host-setup", "--user", ACCOUNT, "--port", arguments["port"]]
        )
    elif action == "B":
        main("install-prototype", arguments)
        result = op.command(["python3", "-B", "-"], input='print("WP0 root stdin")\n')
        check("root-stdin", result.stdout.strip() == "WP0 root stdin")
        # prepare-host's embedded Python ran under its real numeric privilege drop.
        account = pwd.getpwnam(ACCOUNT)
        check(
            "account-python",
            account_python_prepared(Path("/var/lib/myproduct"), account.pw_uid),
        )
    elif action == "C1":
        signature_matrix()
    elif action == "C2":
        stop_rules()
    elif action in ("R1", "R2", "R3", "R4", "R5"):
        repair(action)
    elif action == "D":
        signature_matrix(repository=True)
    elif action == "E":
        op.install_verified([op.DELIVERED])
        check("trust-visible", op.wait_trust([op.TOOLS]))
        # The controller performs the first execution over the runtime account's
        # real SSH session only after receiving this trust predicate.
    elif action == "F":
        guards()
    elif action == "G":
        locks()
    elif action == "H":
        identities()
    else:
        raise RuntimeError("Unknown probe action")
    return {"ok": True, "predicates": PREDICATES, "observations": OBSERVATIONS}


def entry(action, arguments):
    try:
        value = main(action, arguments)
        return {"success": True, "value": value, "commands": op.TRANSCRIPT}
    except Exception as error:  # noqa: BLE001 - retain all failed probe evidence
        return {
            "success": False,
            "error": type(error).__name__ + ": " + str(error),
            "predicates": PREDICATES,
            "commands": op.TRANSCRIPT,
        }
