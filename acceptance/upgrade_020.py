"""Focused historical upgrade; shares the existing runner's lab, logs and cleanup."""

import shlex
from pathlib import Path

LEGACY_REVISION = "86e8e27ed38d6e209eecf018299fd48ec2ce0b1b"
ROOT = Path(__file__).resolve().parent.parent


def guest(run, action):
    """Run fixed checks as the service user, without exposing private snapshots."""
    code = (ROOT / "acceptance/upgrade_020_guest.py").read_text()
    args = [action, run.meta["version"]]
    prefix = (
        "sudo -n -H -u myproduct bash -c "
        + shlex.quote(
            'cd "$HOME" || exit; export XDG_RUNTIME_DIR="/run/user/$(id -u)"; exec python3 - "$@"'
        )
        + " bash "
        + " ".join(map(shlex.quote, args))
        + " <<'UPGRADE_020'\n"
    )
    return run.ssh("PROD", prefix + code + "\nUPGRADE_020\n")


def execute(run):
    """Reset only the configured lab and upgrade genuine old bundles in two stages."""
    run.step("00-readiness", run.readiness)
    run.meta["legacy_revision"] = LEGACY_REVISION
    run.meta["upgrade_revision"] = run.revision
    if run.meta["version"] == "0.2.0" or run.meta["core_version"] == "0.2.0":
        raise RuntimeError("Historical upgrade requires newer app and core versions")
    for role in ("DEV", "PROD"):
        run.step("01-reset-" + role.lower(), lambda r=role: run.reset(r))
    run.step("02-isolate-prod", lambda: run.guest("PROD", "isolate"))
    run.step("03-source", run.source)
    # Keep current source for the smoke/marker clients; old images and archives
    # are built first in a separate worktree, before building any current images.
    run.step("03-legacy-build", lambda: run.guest("DEV", "legacy-build"))
    run.step("03-venv", lambda: run.guest("DEV", "venv"))
    for bundle in ("app1", "app2"):
        run.step(
            "04-transfer-" + bundle, lambda b=bundle: run.transfer("0.2.0", bundle=b)
        )
    run.step("05-prepare-host", lambda: run.guest("PROD", "prepare-host", "0.2.0"))
    for bundle in ("app1", "app2"):
        run.step(
            "05-install-" + bundle,
            lambda b=bundle: run.guest("PROD", "install", "0.2.0", bundle=b),
        )
        run.step("05-health-" + bundle, lambda: run.guest("PROD", "health"))
    run.step("06-credentials", run.credentials)
    run.step("06-e2e-old", lambda: run.guest("DEV", "prod-e2e"))
    run.step("06-markers", lambda: run.guest("DEV", "markers-create"))
    run.step("06-observe-old", lambda: guest(run, "baseline"))
    run.step("07-current-images", lambda: run.guest("DEV", "build-images"))
    run.step("07-current-bundle", lambda: run.guest("DEV", "bundle"))
    for bundle in ("app1", "app2"):
        run.step("08-transfer-" + bundle, lambda b=bundle: run.transfer(bundle=b))
        migration = "migrate-app1" if bundle == "app1" else "migrate-app2"
        run.step("08-" + migration, lambda a=migration: guest(run, a))
        run.step(
            "08-install-" + bundle,
            lambda b=bundle: run.guest("PROD", "legacy-install", bundle=b),
        )
        run.step("08-health-" + bundle, lambda: run.guest("PROD", "health"))
        run.step("08-e2e-" + bundle, lambda: run.guest("DEV", "prod-e2e"))
        run.step("08-markers-" + bundle, lambda: run.guest("DEV", "markers-check"))
        run.step("08-observe-" + bundle, lambda b=bundle: guest(run, "check-" + b))
        if bundle == "app2":
            run.step("08-database-auth", lambda: run.guest("PROD", "database-auth"))
        # Retire only after the independent HTTPS, user data and state checks.
        run.step(
            "08-retire-" + bundle,
            lambda b=bundle: run.guest(
                "PROD", "legacy-retire", old_version="0.2.0", bundle=b
            ),
        )
        run.step("08-trust-" + bundle, lambda b=bundle: guest(run, "trust-" + b))
    run.finished = True
