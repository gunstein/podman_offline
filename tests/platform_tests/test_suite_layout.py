"""Keep the offline test boundary explicit without recursively executing suites."""

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def runner():
    spec = importlib.util.spec_from_file_location("suite_runner", ROOT / "tests/run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SuiteLayoutTests(unittest.TestCase):
    def test_helpers_never_import_test_modules_or_demo_inputs(self):
        for path in (ROOT / "tests/helpers").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    names = (node.module or "").split(".")
                    self.assertFalse(
                        any(
                            name.startswith("test_") or name == "demo_tests"
                            for name in names
                        ),
                        str(path),
                    )

    def test_platform_export_contains_only_platform_tests_and_fixture_components(self):
        tool = runner()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "offline"
            tool.export_platform(target)
            self.assertFalse((target / "apps").exists())
            for name in ("VERSION", "PLATFORM_VERSION", "IDENTITY_VERSION"):
                self.assertFalse((target / name).exists())
            for component in (target / "components").iterdir():
                self.assertTrue((component / "VERSION").is_file())
            self.assertFalse((target / "tests/demo_tests").exists())
            self.assertEqual(
                (target / "bundles.yaml").read_bytes(),
                (ROOT / "tests/fixtures/catalog/bundles.yaml").read_bytes(),
            )
            self.assertTrue((target / "tests/helpers/deploy_fixture.py").is_file())
            with self.assertRaisesRegex(ValueError, "already exists"):
                tool.export_platform(target)
