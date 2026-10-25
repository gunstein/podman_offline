"""WP0 constants and predicates. No transport, lab configuration or side effects."""

import re
import time

# Independently pinned from RPM-PROTOTYPE.md's recorded paper lab fingerprint.
APPROVED_FINGERPRINT = "425584C83A44FFC9F7E5E1A4E2021B0CC1DD70E3"
# Explicitly approved by the product owner after plan revision 3.2.
TRUST_TIMEOUT = 30
LOCK_TIMEOUT = 5
# ausearch parses %x in its own LC_ALL=C environment, including a two-digit year.
AUDIT_START_COMMAND = "LC_ALL=C date '+%x %X'"
TOOLS_VERSION = "2.0"
ACCOUNT = "myproduct-ops"
GROUPS = ("A", "B", "C1", "C2", "R1", "R2", "R3", "R4", "R5", "D", "E", "F", "G", "H")
POSITIVE = frozenset(("A", "B", "E"))
P1_RULES = (
    "allow perm=any uid=0 : dir=/var/tmp/",
    "allow perm=any uid=0 trust=1 : all",
    "allow perm=open exe=/usr/bin/rpm : all",
    "allow perm=open exe=/usr/bin/python3.9 comm=dnf : all",
    "deny_audit perm=any pattern=ld_so : all",
    "deny_audit perm=any all : ftype=application/x-bad-elf",
    "allow perm=open all : ftype=application/x-sharedlib trust=1",
    "deny_audit perm=open all : ftype=application/x-sharedlib",
    "allow perm=execute all : trust=1",
    "allow perm=open all : ftype=%languages trust=1",
    "deny_audit perm=any all : ftype=%languages",
    "allow perm=any all : ftype=text/x-shellscript",
    "deny_audit perm=execute all : all",
    "allow perm=open all : all",
)
REMOVED_RULES = frozenset(P1_RULES[i - 1] for i in (1, 2, 12))


def require(condition, message):
    if condition is not True:
        raise RuntimeError(message)
    return True


def matrix(group="all", profile="all"):
    require(group == "all" or group in GROUPS, "Unknown case group")
    require(profile in ("all", "P1", "P2"), "Unknown profile")
    result = []
    for name in GROUPS:
        profiles = (
            ("P2",)
            if name == "B"
            else (("P1",) if name in ("D", "G", "H") else ("P1", "P2"))
        )
        for selected in profiles:
            if group in ("all", name) and profile in ("all", selected):
                result.append((name, selected))
    require(bool(result), "Case group does not support this profile")
    return result


def signature_ok(status, output):
    lines = output.splitlines()
    return (
        status == 0 and len(lines) == 1 and lines[0].endswith(": digests signatures OK")
    )


def primary_fingerprints(colons):
    fingerprints = []
    waiting = False
    for line in colons.splitlines():
        fields = line.split(":")
        if fields[0] == "pub":
            require(not waiting, "Missing primary fingerprint")
            waiting = True
        elif fields[0] == "fpr" and waiting:
            require(
                len(fields) > 9 and bool(re.fullmatch(r"[A-F0-9]{40}", fields[9])),
                "Invalid primary fingerprint",
            )
            fingerprints.append(fields[9])
            waiting = False
        elif fields[0] == "sub":
            require(not waiting, "Missing primary fingerprint")
    require(not waiting, "Missing primary fingerprint")
    return fingerprints


def authorize_key(colons, expected=APPROVED_FINGERPRINT):
    fingerprints = primary_fingerprints(colons)
    require(len(fingerprints) == 1, "STOP: expected exactly one primary key")
    require(fingerprints[0] == expected, "STOP: primary fingerprint differs from paper")
    return True


def authorize_paper_key(output, expected=APPROVED_FINGERPRINT):
    """Read the ordinary gpg --show-keys output named by the paper procedure."""
    lines = output.splitlines()
    primaries = [i for i, line in enumerate(lines) if line.startswith("pub ")]
    require(len(primaries) == 1, "STOP: expected exactly one primary key")
    index = primaries[0] + 1
    require(index < len(lines), "STOP: missing primary fingerprint")
    fingerprint = "".join(lines[index].split())
    require(
        bool(re.fullmatch(r"[A-F0-9]{40}", fingerprint)),
        "STOP: missing primary fingerprint",
    )
    require(fingerprint == expected, "STOP: primary fingerprint differs from paper")
    return True


def audit_start_fields(start):
    require(
        isinstance(start, str)
        and bool(re.fullmatch(r"\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", start)),
        "Invalid C-locale audit start",
    )
    time.strptime(start, "%m/%d/%y %H:%M:%S")
    return start.split()


def repair_decision(installed, delivered=TOOLS_VERSION):
    """Select the paper repair from observed rpmdb state, not the test case name."""

    def version(value):
        require(
            bool(re.fullmatch(r"\d+(?:\.\d+)*", value)), "Unsupported probe version"
        )
        return tuple(int(part) for part in value.split("."))

    expected = version(delivered)
    values = [version(item) for item in installed]
    if any(value > expected for value in values):
        return "stop-newer"
    if len(values) > 1:
        require(
            len(values) == 2 and len(set(values)) == 2 and expected in values,
            "Unclear duplicate tools state",
        )
        return "deduplicate"
    if values == [expected]:
        return "reinstall"
    return "install"


def derive_p2_sources(files, config):
    found = [
        line.strip()
        for text in files.values()
        for line in text.splitlines()
        if line.strip() in REMOVED_RULES
    ]
    require(
        len(found) == 3 and set(found) == REMOVED_RULES,
        "P2 must remove exactly three source rules",
    )
    changed = {}
    for path, text in files.items():
        changed[path] = "".join(
            line
            for line in text.splitlines(keepends=True)
            if line.strip() not in REMOVED_RULES
        )
    for key, value in (("trust", "rpmdb"), ("integrity", "sha256")):
        config, count = re.subn(
            r"(?m)^" + key + r"\s*=.*$", key + " = " + value, config
        )
        require(count == 1, "Ambiguous policy setting")
    return changed, config


def settings(text):
    result = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, sep, value = line.partition("=")
            require(
                bool(sep) and key.strip() not in result,
                "Invalid or duplicate policy setting",
            )
            result[key.strip()] = value.strip()
    return result


def policy_rules(text):
    require(
        all(
            not line.strip()
            or line.startswith("-> ")
            or re.match(r"^\d+\.\s", line) is not None
            for line in text.splitlines()
        ),
        "Unexpected effective-rule output",
    )
    return tuple(
        re.sub(r"^\d+\.\s*", "", line)
        for line in text.splitlines()
        if re.match(r"^\d+\.\s", line)
    )


def check_profile(observed, baseline, profile):
    require(profile in ("P1", "P2"), "Unknown policy profile")
    expected_rules = (
        P1_RULES
        if profile == "P1"
        else tuple(r for r in P1_RULES if r not in REMOVED_RULES)
    )
    require(
        policy_rules(observed["rules"]) == expected_rules,
        "Effective rules differ from profile",
    )
    expected = settings(baseline["config"])
    require(
        expected.get("trust") == "rpmdb,file"
        and expected.get("integrity") == "none"
        and expected.get("permissive") == "0",
        "Invalid recorded P1 configuration",
    )
    if profile == "P2":
        expected.update(trust="rpmdb", integrity="sha256")
    require(
        settings(observed["config"]) == expected,
        "Effective configuration differs from profile",
    )
    for key in ("filter", "plugin", "plugin_package", "languages"):
        actual, reference = observed[key], baseline[key]
        if key == "filter":
            # Historical policy copies trimmed trailing whitespace, which has
            # no filter meaning. Keep all significant indentation/content.
            actual = "\n".join(line.rstrip() for line in actual.splitlines()).rstrip()
            reference = "\n".join(
                line.rstrip() for line in reference.splitlines()
            ).rstrip()
        require(actual == reference, "Effective " + key + " differs from baseline")
    return True


def check_baseline(facts):
    require(facts["os"].strip() == "Oracle Linux Server release 9.8", "Expected OL9.8")
    require(facts["selinux"].strip() == "Enforcing", "SELinux must be Enforcing")
    require(facts["services"] == ["active", "active"], "Policy services must be active")
    require(
        facts["artifacts"] == [] and facts["packages"] == [] and facts["keys"] == [],
        "Baseline contains product/probe state",
    )
    return True


def runtime_health(status, containers):
    require(
        status.get("product") == "myproduct" and status.get("pending") is None,
        "Unexpected product or pending work",
    )
    components = {row["name"]: row for row in status["components"]}
    require(set(components) == {"platform", "identity"}, "Missing installed components")
    for row in components.values():
        require(
            row["version"] == "0.4.12"
            and row["complete"] is True
            and row["state"] == "active",
            "Incomplete installed status",
        )
    application = []
    for row in containers:
        require(
            type(row["IsInfra"]) is bool and type(row["IsService"]) is bool,
            "Invalid container kind",
        )
        if not row["IsInfra"] and not row["IsService"]:
            application.append(row)
    require(len(application) == 3, "Expected three application containers")
    for row in application:
        state = row["State"]
        require(
            state["Running"] is True
            and state["Status"] == "running"
            and state["Health"]["Status"] == "healthy",
            "Application container is not healthy",
        )
    return True


def bounded_poll(predicate, timeout, clock=time.monotonic, sleep=time.sleep):
    start = clock()
    while True:
        remaining = timeout - (clock() - start)
        require(remaining > 0, "Timed out waiting for trust")
        if predicate(remaining) is True:
            require(
                clock() - start <= timeout, "Trust appeared after the poll deadline"
            )
            return True
        sleep(min(0.1, max(0, timeout - (clock() - start))))


def disks(config):
    result = {}
    for key, value in config.items():
        if re.fullmatch(r"(?:scsi|sata|ide|virtio)\d+|efidisk0|tpmstate0", key):
            if "media=cdrom" in value:
                continue
            require(
                "snapshot=0" not in value and ":" in value.split(",")[0],
                "Disk cannot be attested for rollback",
            )
            result[key] = value.split(",")[0]
    require(bool(result), "No PROD disks found")
    return result


def snapshot_preflight(config, status, snapshots, configurations):
    require(
        status.get("ha", {}).get("managed") in (False, 0), "HA state missing or managed"
    )
    rows = {row["name"]: row for row in snapshots if row["name"] != "current"}
    require("clean-agent" in rows, "Missing clean-agent snapshot")
    anchor = rows["clean-agent"]
    require(isinstance(anchor.get("snaptime"), int), "Missing snapshot time")
    current = disks(config)
    require(
        disks(configurations["clean-agent"]) == current,
        "clean-agent does not cover every current PROD disk",
    )
    for name, row in rows.items():
        if name == "clean-agent":
            continue
        require(isinstance(row.get("snaptime"), int), "Missing snapshot time")
        captured = disks(configurations[name])
        for volume in current.values():
            require(
                volume not in captured.values() or row["snaptime"] < anchor["snaptime"],
                "clean-agent is not the newest snapshot on every PROD disk",
            )
        require(
            row.get("parent") != "clean-agent", "clean-agent has a newer child snapshot"
        )
    require(
        config.get("parent") == "clean-agent",
        "Current snapshot parent is not clean-agent",
    )
    return True
