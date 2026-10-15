"""Install genuine historical core state, then prove the platform boundary refuses it."""

import shlex

import upgrade_020

HISTORICAL_HARNESS = "511099e7e056d0d18c4ade95067c30a54c48bec4"


def execute(run):
    """Use old helpers for old state; never rename historical fixtures to platform."""
    run.step("00-readiness", run.readiness)
    run.meta["legacy_revision"] = upgrade_020.LEGACY_REVISION
    run.meta["historical_harness"] = HISTORICAL_HARNESS
    old_remote = run.command(
        ["git", "show", HISTORICAL_HARNESS + ":acceptance/remote.sh"]
    )

    def old_guest(role, action, bundle="app1"):
        args = [
            action,
            run.id,
            run.cfg["LAB_CIDR"],
            run.cfg["PROD_IP"],
            run.cfg["PROD_HOST"],
            run.cfg["HTTPS_PORT"],
            run.revision,
            role,
            run.started_epoch,
            "0.2.0",
            "",
            bundle,
        ]
        return run.ssh(
            role, "set -- " + " ".join(map(shlex.quote, args)) + "\n" + old_remote
        )

    for role in ("DEV", "PROD"):
        run.step("01-reset-" + role.lower(), lambda r=role: run.reset(r))
    run.step("02-isolate-prod", lambda: run.guest("PROD", "isolate"))
    run.step("03-source", run.source)
    run.step("03-old-build", lambda: old_guest("DEV", "legacy-build"))
    run.step("03-venv", lambda: run.guest("DEV", "venv"))
    for bundle in ("app1", "app2"):
        run.step(
            "04-transfer-" + bundle, lambda b=bundle: run.transfer("0.2.0", bundle=b)
        )
    run.step("05-prepare-host", lambda: old_guest("PROD", "prepare-host"))
    for bundle in ("app1", "app2"):
        run.step(
            "05-install-" + bundle, lambda b=bundle: old_guest("PROD", "install", b)
        )
        run.step("05-health-" + bundle, lambda: old_guest("PROD", "health"))
    run.step(
        "06-credentials",
        lambda: run.credentials(component="core", directory="generated-certificates"),
    )
    run.step("06-old-e2e", lambda: run.guest("DEV", "prod-e2e"))
    run.step("06-markers", lambda: run.guest("DEV", "markers-create"))
    run.step("06-baseline", lambda: upgrade_020.guest(run, "baseline"))
    run.step("07-current-images", lambda: run.guest("DEV", "build-images"))
    run.step("07-current-bundles", lambda: run.guest("DEV", "bundle"))
    run.step("07-transfer-platform", lambda: run.transfer(bundle="platform"))
    run.step(
        "08-refusal", lambda: run.guest("PROD", "legacy-refusal", bundle="platform")
    )
    run.step("08-state", lambda: upgrade_020.guest(run, "trust-app1"))
    run.step("08-e2e", lambda: run.guest("DEV", "prod-e2e"))
    run.step("08-markers", lambda: run.guest("DEV", "markers-check"))
    run.finished = True
