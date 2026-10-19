#!/usr/bin/env python3
"""Run explicit unittest groups or export a self-contained offline platform suite."""

import argparse
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


def export_platform(target):
    """Copy only platform code/tests and declarative fixtures, never demo inputs."""
    if target.exists():
        raise ValueError("Export destination already exists")
    target.mkdir(parents=True)
    for name in ("bundle.py", "deploy", "build-bundle.sh", "README.md"):
        shutil.copy2(str(ROOT / name), str(target / name))
    for name in ("deployment", "scripts", "quadlet", "examples"):
        shutil.copytree(
            str(ROOT / name),
            str(target / name),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for name in ("helpers", "fixtures", "platform_tests"):
        shutil.copytree(
            str(TESTS / name),
            str(target / "tests" / name),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    shutil.copy2(str(TESTS / "run.py"), str(target / "tests/run.py"))
    shutil.copy2(str(TESTS / "README.md"), str(target / "tests/README.md"))
    (target / "dev").mkdir()
    for name in ("build-images.sh", "pull-images.sh", "generate-certificates.sh"):
        shutil.copy2(str(ROOT / "dev" / name), str(target / "dev" / name))
    fixture = TESTS / "fixtures/catalog"
    shutil.copytree(str(fixture / "components"), str(target / "components"))
    for name in ("bundles.yaml",):
        shutil.copy2(str(fixture / name), str(target / name))


def cases(suite):
    """Flatten for inventory comparisons without invoking a test."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def load_group(group):
    """Standard discovery: helper classes have no test methods to duplicate."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(TESTS))
    try:
        import yaml  # noqa: F401 - report the offline runtime prerequisite clearly
    except ImportError:
        raise ValueError("Platform tests require PyYAML for python3") from None
    directory = TESTS if group == "all" else TESTS / (group + "_tests")
    if not directory.is_dir():
        raise ValueError("Requested test group is not present in this copy")
    return unittest.defaultTestLoader.discover(str(directory), top_level_dir=str(TESTS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "group", choices=("platform", "demo", "all"), nargs="?", default="all"
    )
    parser.add_argument(
        "--list", action="store_true", help="Print test IDs without running them"
    )
    parser.add_argument(
        "--isolate",
        action="store_true",
        help="Run platform tests in a disposable copy without demo files",
    )
    parser.add_argument(
        "--export",
        type=Path,
        help="Write a self-contained platform copy for offline transfer; do not run it",
    )
    options = parser.parse_args()
    if (options.isolate or options.export) and options.group != "platform":
        parser.error("--isolate/--export require the platform group")
    try:
        if options.export:
            export_platform(options.export.resolve())
            print("Platform suite exported")
            return 0
        if options.isolate:
            with tempfile.TemporaryDirectory(prefix="platform-suite-") as directory:
                target = Path(directory) / "source"
                export_platform(target)
                arguments = [
                    sys.executable,
                    "-B",
                    str(target / "tests/run.py"),
                    "platform",
                ]
                if options.list:
                    arguments.append("--list")
                return subprocess.run(
                    arguments, cwd=str(target), check=False
                ).returncode
        suite = load_group(options.group)
        if options.list:
            for case in cases(suite):
                print(case.id())
            return 0
        return (
            0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1
        )
    except (ValueError, OSError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
