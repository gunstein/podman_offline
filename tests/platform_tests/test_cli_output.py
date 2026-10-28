"""deploy.sh's argparse command line (backlog 73) and operator messages (backlog 74)."""

import contextlib
import copy
import io
import logging
import socket
import tempfile
from pathlib import Path
from unittest import mock

import bundle
from deployment import cli, common, deploy, output

from helpers.deploy_fixture import DeployFixture
from helpers.product_fixture import ProductFixture, pod


class ParserTests(DeployFixture):
    """Every accepted form, refusals and help, without running a command."""

    def parse(self, *arguments):
        return cli.parser().parse_args(list(arguments))

    def test_accepted_forms_keep_their_meaning(self):
        for arguments, expected in (
            (["validate"], {"command": "validate"}),
            (["prepare"], {"command": "prepare"}),
            (["install"], {"command": "install"}),
            (["init-layout"], {"command": "init-layout"}),
            (["init-config", "app1"], {"command": "init-config", "component": "app1"}),
            (["uninstall"], {"component": None, "delete_data": False}),
            (["uninstall", "app1"], {"component": "app1", "delete_data": False}),
            (["uninstall", "--delete-data"], {"component": None, "delete_data": True}),
            (
                ["uninstall", "app1", "--delete-data"],
                {"component": "app1", "delete_data": True},
            ),
            (
                ["uninstall", "--delete-data", "app1"],
                {"component": "app1", "delete_data": True},
            ),
            (["status"], {"command": "status", "json": False}),
            (["status", "--json"], {"command": "status", "json": True}),
            (["install", "--verbose"], {"command": "install", "verbose": True}),
            (["--verbose", "install"], {"command": "install", "verbose": True}),
            (["install"], {"verbose": False}),
        ):
            with self.subTest(arguments=arguments):
                parsed = vars(self.parse(*arguments))
                for key, value in expected.items():
                    self.assertEqual(parsed[key], value)

    def test_refused_forms_exit_two_on_stderr_without_running(self):
        for arguments in (
            [],
            ["unknown"],
            ["prepare", "extra"],
            ["install", "prepare"],
            ["init-config"],
            ["init-config", "app1", "app2"],
            ["init-config", "my_identity"],
            ["uninstall", "app1", "app2"],
            ["uninstall", "--delete-data", "--delete-data"],
            ["uninstall", "--delete"],
            ["status", "worker"],
            ["status", "--js"],
            ["status", "--json", "--json"],
            ["status", "--delete-data"],
            ["--verb", "install"],
            ["install", "--verbose", "--verbose"],
        ):
            with self.subTest(arguments=arguments):
                self.stdout.truncate(0)
                self.stderr.truncate(0)
                with mock.patch.object(deploy, "install") as install:
                    self.assertEqual(cli.main(arguments), 2)
                install.assert_not_called()
                self.assertEqual(self.stdout.getvalue(), "")
                self.assertIn("Usage: ./deploy.sh ", self.stderr.getvalue())
                self.assertIn("ERROR: ", self.stderr.getvalue())
        self.process.assert_not_called()

    def test_help_per_command_exits_zero_on_stdout(self):
        for command, usage in (
            (None, cli.USAGE),
            ("validate", "./deploy.sh validate"),
            ("prepare", "./deploy.sh prepare"),
            ("install", "./deploy.sh install"),
            ("init-layout", "./deploy.sh init-layout"),
            ("init-config", "./deploy.sh init-config <component>"),
            ("uninstall", "./deploy.sh uninstall [<component>] [--delete-data]"),
            ("status", "./deploy.sh status [--json]"),
        ):
            with self.subTest(command=command):
                self.stdout.truncate(0)
                self.stdout.seek(0)
                arguments = ([command] if command else []) + ["--help"]
                self.assertEqual(cli.main(arguments), 0)
                self.assertTrue(self.stdout.getvalue().startswith("Usage: " + usage))
                self.assertIn(
                    "--verbose" if command else "init-config", self.stdout.getvalue()
                )
        self.process.assert_not_called()

    def test_build_bundle_arguments(self):
        with mock.patch.object(bundle, "build") as build:
            self.assertEqual(bundle.main(["--help"]), 0)
            self.assertEqual(bundle.main(["--verb"]), 2)
            build.assert_not_called()
            self.assertEqual(bundle.main(["app1", "help", "--verbose"]), 0)
            build.assert_called_once_with(["app1", "help"])
        self.assertTrue(output.log.isEnabledFor(logging.DEBUG))
        self.assertIn("PASS: ./build-bundle.sh completed", self.stdout.getvalue())


class MessageTests(DeployFixture):
    """One convention: INFO to stdout, WARNING/ERROR to stderr, DEBUG with --verbose."""

    def test_streams_per_message_class_and_unchanged_text(self):
        output.configure()
        output.log.info("[OK] step")
        output.log.info("PASS: done")
        output.log.debug("+ podman ps")
        output.log.warning("WARNING: careful; do this next")
        output.log.error("ERROR: failed; do that next")
        self.assertEqual(self.stdout.getvalue(), "[OK] step\nPASS: done\n")
        self.assertEqual(
            self.stderr.getvalue(),
            "WARNING: careful; do this next\nERROR: failed; do that next\n",
        )

    def test_handlers_follow_a_later_redirect(self):
        later = io.StringIO()
        with contextlib.redirect_stdout(later):
            output.log.info("[OK] redirected")
        self.assertEqual(later.getvalue(), "[OK] redirected\n")
        self.assertEqual(self.stdout.getvalue(), "")

    def test_host_commands_show_only_with_verbose(self):
        output.configure()
        deploy.run("podman", "ps")
        self.assertNotIn("+ podman ps", self.stdout.getvalue())
        output.configure(verbose=True)
        deploy.run("podman", "ps")
        self.assertIn("+ podman ps\n", self.stdout.getvalue())
        self.assertEqual(self.process.call_count, 2)

    def test_prepare_success_and_failure_lines(self):
        self.assertEqual(cli.main(["prepare"]), 0)
        self.assertTrue(
            self.stdout.getvalue().endswith("PASS: ./deploy.sh prepare completed\n")
        )
        self.write("config.yaml", "HTTPS_PORT: invalid")
        self.stdout.truncate(0)
        self.stdout.seek(0)
        self.assertEqual(cli.main(["prepare"]), 1)
        self.assertNotIn("PASS:", self.stdout.getvalue())
        self.assertIn("ERROR: ", self.stderr.getvalue())


class Journal:
    """A fake /dev/log: a datagram socket that collects audit lines."""

    def __init__(self, directory):
        self.path = str(Path(directory) / "log")
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.bind(self.path)
        self.socket.settimeout(0)

    def lines(self):
        found = []
        with contextlib.suppress(BlockingIOError):
            while True:
                # SysLogHandler ends each datagram with NUL by default.
                found.append(self.socket.recv(65536).decode("utf-8").rstrip("\x00"))
        return found

    def close(self):
        self.socket.close()


class AuditTests(ProductFixture):
    """Operator actions reach the journal; no secret value reaches any handler."""

    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory(prefix="journal-", dir="/tmp")
        self.addCleanup(directory.cleanup)
        self.journal = Journal(directory.name)
        self.addCleanup(self.journal.close)
        self.stack.enter_context(mock.patch.object(output, "SYSLOG", self.journal.path))

    def product(self):
        worker = {
            "catalog": {},
            "defaults": {
                "SECRET_FILES": {
                    "worker-token": [
                        {"path": "credentials/token", "generate": ["value"]}
                    ]
                }
            },
            "manifests": [
                pod(
                    "worker-job",
                    "registry.example.test/team/worker:1",
                    ["secret:worker-token"],
                )
            ],
        }
        return {"worker": copy.deepcopy(worker)}

    def test_lifecycle_actions_are_audited_without_secret_values(self):
        self.write_product(self.product())
        releases = self.build_and_unpack()
        self.use_root(releases["worker"])
        self.assertEqual(cli.main(["init-config", "worker"]), 0)
        self.assertEqual(cli.main(["install", "--verbose"]), 0)
        # Read-only commands are not audited (the stubbed unit is not active).
        cli.main(["status"])
        self.assertEqual(cli.main(["uninstall", "--bad"]), 2)
        self.assertEqual(cli.main(["uninstall", "other"]), 1)
        lines = self.journal.lines()
        self.assertEqual(
            [line.split(": ", 1)[1] for line in lines],
            [
                "init-config worker 1.0.0: started",
                "init-config worker 1.0.0: completed",
                "install worker 1.0.0: started",
                "install worker 1.0.0: completed",
                "uninstall other 1.0.0: started",
                "uninstall other 1.0.0: failed (exit 1)",
            ],
        )
        for line in lines:
            self.assertRegex(line, r"^<14>myproduct\[[0-9]+\]: ")
        token = (common.STATE / "worker/credentials/token/value").read_text()
        self.assertTrue(token)
        self.assertIn("+ podman load", self.stdout.getvalue())
        for text in (self.stdout.getvalue(), self.stderr.getvalue(), "".join(lines)):
            self.assertNotIn(token, text)

    def test_commands_work_without_a_journal(self):
        self.journal.close()
        self.write_product(self.product())
        releases = self.build_and_unpack()
        self.use_root(releases["worker"])
        self.assertEqual(cli.main(["init-config", "worker"]), 0)
        output.audit("install worker 1.0.0: started")
        self.assertNotIn("Logging error", self.stderr.getvalue())
