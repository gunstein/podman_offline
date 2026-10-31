"""Runtime layer checks with Podman stubbed; these are not lab results."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from test_acceptance import shell_code
from test_components import REMOTE, guest_code


class ComponentDevHarnessTests(unittest.TestCase):
    def fixture(self, directory, first, second, value):
        docs = []
        for component in (first, second):
            docs.extend(
                [
                    {
                        "kind": "ConfigMap",
                        "metadata": {"name": component + "-settings"},
                        "data": {"DEMO_CONFIG_LAYER": value}
                        if component == first
                        else {},
                    },
                    {
                        "kind": "Pod",
                        "metadata": {"name": component + "-todo"},
                        "spec": {
                            "containers": [
                                {
                                    "name": "backend",
                                    "envFrom": [
                                        {
                                            "configMapRef": {
                                                "name": component + "-settings"
                                            }
                                        }
                                    ],
                                }
                            ]
                        },
                    },
                ]
            )
        path = Path(directory) / "install.yaml"
        path.write_text(yaml.safe_dump_all(docs))
        return path, docs

    def test_dev_prod_and_renamed_runtime_checks_read_only_the_marker(self):
        for first, second in (("app1", "app2"), ("orders", "inventory")):
            for mode, expected in (("dev", "defaults"), ("prod", "defaults")):
                with (
                    self.subTest(first=first, mode=mode),
                    tempfile.TemporaryDirectory() as directory,
                ):
                    path, _ = self.fixture(directory, first, second, expected)
                    code = guest_code("CONFIG_LAYERS")
                    run = mock.Mock(
                        side_effect=[
                            subprocess.CompletedProcess([], 0, expected + "\n", ""),
                            subprocess.CompletedProcess([], 0, "", ""),
                        ]
                    )
                    with (
                        mock.patch.object(subprocess, "run", run),
                        contextlib.redirect_stdout(io.StringIO()) as output,
                    ):
                        code["check_layers"]([path], mode, first, second)
                    self.assertIn("PASS: component dev layer", output.getvalue())
                    self.assertEqual(
                        run.call_args_list[0].args[0],
                        [
                            "podman",
                            "exec",
                            first + "-todo-backend",
                            "printenv",
                            "DEMO_CONFIG_LAYER",
                        ],
                    )
                    self.assertEqual(
                        run.call_args_list[1].args[0],
                        [
                            "podman",
                            "exec",
                            second + "-todo-backend",
                            "sh",
                            "-c",
                            'test "${DEMO_CONFIG_LAYER+x}" != x',
                        ],
                    )

    def test_wrong_layer_missing_marker_sibling_leakage_and_command_errors_fail(self):
        for case in (
            "wrong-rendered",
            "missing-marker",
            "wrong-runtime",
            "sibling-rendered",
            "sibling-runtime",
            "command-failure",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                path, docs = self.fixture(directory, "app1", "app2", "defaults")
                if case == "wrong-rendered":
                    docs[0]["data"]["DEMO_CONFIG_LAYER"] = "component-dev"
                if case == "missing-marker":
                    docs[0]["data"] = {}
                if case == "sibling-rendered":
                    docs[2]["data"]["DEMO_CONFIG_LAYER"] = "defaults"
                path.write_text(yaml.safe_dump_all(docs))
                first = subprocess.CompletedProcess(
                    [],
                    125 if case == "command-failure" else 0,
                    "private-fixture" if case == "wrong-runtime" else "defaults\n",
                    "private-stderr",
                )
                second = subprocess.CompletedProcess(
                    [], 1 if case == "sibling-runtime" else 0, "", ""
                )
                code = guest_code("CONFIG_LAYERS")
                with (
                    mock.patch.object(subprocess, "run", side_effect=[first, second]),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                    self.assertRaises(RuntimeError) as failure,
                ):
                    code["check_layers"]([path], "dev", "app1", "app2")
                self.assertNotIn("private-", str(failure.exception) + output.getvalue())
                self.assertNotIn("PASS:", output.getvalue())

    def test_missing_dev_consumers_fail_but_prod_help_only_needs_no_apps(self):
        code = guest_code("CONFIG_LAYERS")
        with mock.patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Missing dev layer consumer"):
                code["check_layers"]([], "dev", "app1", "app2")
            with contextlib.redirect_stdout(io.StringIO()):
                code["check_layers"]([], "prod", "app1", "app2", {"platform", "help"})
            run.assert_not_called()

    def test_installed_prod_app_without_consumer_fails_instead_of_passing(self):
        """A missing or misnamed installed app must not make the check vacuous."""
        code = guest_code("CONFIG_LAYERS")
        for installed, missing in (({"app1"}, "app1"), ({"app1", "app2"}, "app2")):
            with (
                self.subTest(installed=sorted(installed)),
                tempfile.TemporaryDirectory() as directory,
            ):
                path, docs = self.fixture(directory, "app1", "app2", "defaults")
                if missing == "app2":
                    docs = [d for d in docs if d["metadata"]["name"] != "app2-todo"]
                else:
                    docs = []
                path.write_text(yaml.safe_dump_all(docs))
                run = mock.Mock(
                    return_value=subprocess.CompletedProcess([], 0, "defaults\n", "")
                )
                with (
                    mock.patch.object(subprocess, "run", run),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                    self.assertRaisesRegex(
                        RuntimeError, "Missing installed layer consumer: " + missing
                    ),
                ):
                    code["check_layers"]([path], "prod", "app1", "app2", installed)
                self.assertNotIn("PASS:", output.getvalue())

    def test_production_check_reads_completion_markers(self):
        self.assertIn(
            '(Path(os.environ["PRODUCT_STATE"]) / "installed").glob("*")', REMOTE
        )
        self.assertIn("check_layers(paths, mode, first, second, installed)", REMOTE)

    def test_runtime_assertions_are_wired_into_dev_and_production_steps(self):
        for action in ("dev-up", "renamed-dev-up"):
            block = shell_code(REMOTE, action=action)
            self.assertIn("./dev/dev.sh up\n    config_layers dev", block)
        self.assertIn("config_layers prod", shell_code(REMOTE, function="healthy"))
