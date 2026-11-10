"""<product>, the runtime command (backlog 69 WP3), against a fake host.

The installed releases are directories with a real descriptor in
bundle.yaml and lines of rpm -qa; FakeReleases plays each release's deploy.sh
(init-layout, status --json, init-config, install, status) and remembers what
it installed. The credential move runs for real on temporary directories.
"""

import contextlib
import io
import json
import os
import pwd
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from deployment import output

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import host  # pyright: ignore[reportMissingImports] - tools/ is added above
import runtime  # pyright: ignore[reportMissingImports] - tools/ is added above

ACCOUNT = pwd.struct_passwd(
    ("operator-a", "x", 1000, 1000, "", "/home/operator-a", "/bin/bash")
)
# The gateway's new config, written with the answers in one step.
WEB_INIT = (
    "init-config web --set PUBLIC_ORIGIN=https://shop.example:9443 "
    "--set HTTPS_PORT=9443 --set IP_ADDRESS=10.0.0.5"
)
# A gateway, an app that needs it and a worker that needs nothing.
DESCRIPTORS = {
    "web": {"requires": {}, "accepts": {"routes": "web-routes"}},
    "api": {"requires": {"web": {"min": "1.0.0", "before": "2.0.0"}}, "accepts": {}},
    "worker": {"requires": {}, "accepts": {}},
}


class FakeReleases:
    """The installed releases and their deploy.sh, as the runtime command sees them."""

    def __init__(self, lib):
        self.lib = lib
        self.rpm_lines = []
        self.installed = {}  # component -> version completed
        self.pending = None
        self.fail = set()  # components whose install fails
        self.check_fail = set()  # components whose check-environment fails
        self.changed = set()  # completed components whose environment changed
        self.calls = []

    def add(self, component, version, descriptor=None):
        name = f"cedar-{component}-{version}"
        release = self.lib / "cedar/releases" / name
        release.mkdir(parents=True)
        (release / "bundle.yaml").write_text(
            yaml.safe_dump(descriptor or DESCRIPTORS[component])
        )
        self.rpm_lines.append(f"{name} {version} /var/lib/cedar/releases/{name}\n")

    def command(self, arguments, **kwargs):
        args = list(map(str, arguments))

        def done(stdout="", status=0, stderr=""):
            return subprocess.CompletedProcess(args, status, stdout, stderr)

        if args[:2] == ["rpm", "-qa"]:
            return done("".join(self.rpm_lines))
        if args[:2] == ["ip", "-4"]:
            return done("192.0.2.1 via 10.0.0.1 dev eth0 src 10.0.0.5 uid 1000\n")
        if args[0] != "bash" or not args[1].endswith("/deploy.sh"):
            raise AssertionError("Unexpected host command: " + str(args))
        release = Path(args[1]).parent.name  # cedar-<component>-<version>
        component, version = release[len("cedar-") :].rsplit("-", 1)
        command = args[2:]
        self.calls.append((component, command))
        if command == ["status", "--json"]:
            return done(
                json.dumps(
                    {
                        "product": "cedar",
                        "components": [
                            {"name": name, "version": done_version, "complete": True}
                            for name, done_version in self.installed.items()
                            if not self.pending or self.pending["component"] != name
                        ],
                        "pending": self.pending,
                    }
                )
            )
        if command[0] == "check-environment":
            if component in self.check_fail:
                return done(status=1)
            if command[-1] == "--json":
                applied = (
                    self.installed.get(component) == version
                    and component not in self.changed
                )
                return done(json.dumps({"applied": applied, "component": component}))
            return done()
        if command[0] == "init-config":
            config = self.lib / "cedar/state" / command[1] / "config.yaml"
            config.parent.mkdir(parents=True, exist_ok=True)
            settings = dict(
                command[index + 1].split("=", 1)
                for index, item in enumerate(command)
                if item == "--set"
            )
            config.write_text(yaml.safe_dump(settings))
        if command[:1] == ["install"]:
            if component in self.fail:
                self.pending = {"operation": "install", "component": component}
                return done(status=1)
            self.installed[component] = version
            self.changed.discard(component)
            # deploy.sh install removes the uninstall record (backlog 85).
            record = self.lib / "cedar/state/uninstalled" / component
            if record.is_file():
                record.unlink()
            if self.pending and self.pending["component"] == component:
                self.pending = None
        return done()

    def commands(self, component=None):
        return [
            " ".join(command)
            for name, command in self.calls
            if component is None or name == component
        ]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        lib = self.root / "var-lib"
        (lib / "cedar/state").mkdir(parents=True)
        (lib / "cedar/incoming").mkdir()
        etc = self.root / "etc"
        (etc / "cedar").mkdir(parents=True)
        (etc / "cedar/host.conf").write_text(
            "# Written by cedar-admin\nHTTPS_PORT=9443\n"
        )
        tools = self.root / "tools"
        tools.mkdir()
        (tools / "bundle.yaml").write_text("product: cedar\n")
        self.releases = FakeReleases(lib)
        for component in ("web", "api", "worker"):
            self.releases.add(component, "1.0.0")
        self.stack.enter_context(
            mock.patch.multiple(host, LIB=lib, ETC=etc, TOOLS=tools)
        )
        self.stack.enter_context(
            mock.patch.object(subprocess, "run", side_effect=self.releases.command)
        )
        self.stack.enter_context(mock.patch.object(os, "geteuid", return_value=1000))
        self.stack.enter_context(
            mock.patch.object(pwd, "getpwuid", return_value=ACCOUNT)
        )
        self.stack.enter_context(
            mock.patch.object(output, "SYSLOG", str(self.root / "no-journal"))
        )
        self.addCleanup(output.configure)
        self.stack.enter_context(
            mock.patch.object(runtime.socket, "getfqdn", return_value="shop.example")
        )
        self.lib = lib
        self.stdout = self.stack.enter_context(
            contextlib.redirect_stdout(io.StringIO())
        )
        self.stderr = self.stack.enter_context(
            contextlib.redirect_stderr(io.StringIO())
        )

    def run_command(self, *arguments):
        for stream in (self.stdout, self.stderr):
            stream.seek(0)
            stream.truncate()
        self.releases.calls.clear()
        return runtime.main(list(arguments))

    def first_run(self):
        code = self.run_command(
            "--public-origin", "https://shop.example:9443", "--ip-address", "10.0.0.5"
        )
        self.assertEqual(code, 0, self.stderr.getvalue())

    def deliver(self, component, relative, text):
        path = self.lib / "cedar/incoming" / component / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_ctrl_c_names_the_next_action_without_a_traceback(self):
        with mock.patch.object(
            runtime, "install", side_effect=KeyboardInterrupt
        ), mock.patch.object(runtime.output, "audit") as audit:
            self.assertEqual(self.run_command(), 130)
        self.assertEqual(
            self.stderr.getvalue(),
            "ERROR: Interrupted; run the same command again to continue\n",
        )
        self.assertEqual(audit.call_args_list[-1], mock.call("cedar: interrupted"))

    def test_first_run_installs_every_component_in_dependency_order(self):
        self.deliver("web", "credentials/web/web.key", "private-key-text\n")
        self.first_run()
        self.assertEqual(
            self.releases.commands(),
            [
                "init-layout",
                "status --json",
                WEB_INIT,
                "install",
                "init-config api",
                "install",
                "init-config worker",
                "install",
                "status",
            ],
        )
        self.assertEqual([name for name, _ in self.releases.calls[2:4]], ["web", "web"])
        key = self.lib / "cedar/state/web/credentials/web/web.key"
        self.assertEqual(key.read_text(), "private-key-text\n")
        self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(key.parent.stat().st_mode), 0o700)
        self.assertEqual(list((self.lib / "cedar/incoming").iterdir()), [])
        self.assertIn(
            "[OK] web: 1 delivered credential file(s)", self.stdout.getvalue()
        )
        self.assertNotIn(
            "private-key-text", self.stdout.getvalue() + self.stderr.getvalue()
        )
        self.assertTrue(self.stdout.getvalue().endswith("PASS: cedar completed\n"))

    def test_an_unchanged_repeat_installs_nothing_and_asks_nothing(self):
        self.first_run()
        with mock.patch.object(runtime.sys, "stdin", mock.Mock(isatty=lambda: False)):
            self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        self.assertEqual(
            self.releases.commands(), ["init-layout", "status --json", "status"]
        )
        for name in ("web", "api", "worker"):
            self.assertIn(f"[OK] {name} 1.0.0 is installed", self.stdout.getvalue())

    def test_the_first_run_asks_with_suggestions(self):
        terminal = mock.Mock(isatty=mock.Mock(return_value=True))
        with mock.patch.object(host.sys, "stdin", terminal), mock.patch(
            "builtins.input", side_effect=["", ""]
        ) as asked:
            self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        self.assertEqual(
            [call.args[0] for call in asked.call_args_list],
            [
                "Public address (https://<host name>:<port>) [https://shop.example:9443]: ",
                "IP address the server listens on [10.0.0.5]: ",
            ],
        )
        self.assertIn(
            WEB_INIT,
            self.releases.commands(),
        )

    def test_without_a_terminal_the_missing_answer_is_named(self):
        with mock.patch.object(host.sys, "stdin", mock.Mock(isatty=lambda: False)):
            self.assertEqual(self.run_command("--ip-address", "10.0.0.5"), 1)
        self.assertIn("ERROR: Give --public-origin", self.stderr.getvalue())
        self.assertFalse((self.lib / "cedar/state/web/config.yaml").exists())
        self.assertNotIn("install", self.releases.commands())

    def test_a_failed_install_stops_and_the_next_run_resumes_it_first(self):
        self.releases.fail.add("api")
        self.assertEqual(
            self.run_command(
                "--public-origin",
                "https://shop.example:9443",
                "--ip-address",
                "10.0.0.5",
            ),
            1,
        )
        self.assertIn(
            "deploy.sh install stopped; fix what it names", self.stderr.getvalue()
        )
        self.assertEqual(self.releases.commands("worker"), [])
        self.releases.fail.clear()
        self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        installs = [
            name for name, command in self.releases.calls if command == ["install"]
        ]
        self.assertEqual(installs, ["api", "worker"])
        # api has its config from the first run; it is not initialised again.
        self.assertNotIn("init-config api", self.releases.commands())

    def test_an_upgrade_installs_only_the_newer_release_without_new_config(self):
        self.first_run()
        self.releases.add("api", "1.1.0")
        self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        self.assertEqual(self.releases.commands("api"), ["install"])
        self.assertEqual(self.releases.installed["api"], "1.1.0")

    def test_an_uninstalled_component_stays_out_until_it_is_named(self):
        """Backlog 85: its release stays installed, but the runtime user removed it."""
        self.first_run()
        del self.releases.installed["worker"]
        # The record deploy.sh uninstall writes; the status report comes from
        # web's release and, like a release before backlog 85, never names it.
        record = self.root / "var-lib/cedar/state/uninstalled/worker"
        record.parent.mkdir(parents=True)
        record.write_text("1.0.0\n")
        self.releases.calls.clear()
        self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        self.assertNotIn("install", self.releases.commands("worker"))
        self.assertIn(
            "[OK] worker was uninstalled; run cedar worker to install it again",
            self.stdout.getvalue(),
        )
        # A later run still leaves it out; naming it installs it again.
        self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        self.assertNotIn("worker", self.releases.installed)
        self.assertEqual(self.run_command("worker"), 0, self.stderr.getvalue())
        self.assertEqual(self.releases.installed["worker"], "1.0.0")
        self.assertFalse(record.exists())

    def test_an_unfinished_uninstall_is_never_installed_again(self):
        self.first_run()
        self.releases.pending = {
            "operation": "uninstall",
            "component": "worker",
            "owners": [],
        }
        self.releases.calls.clear()
        self.assertEqual(self.run_command(), 1)
        self.assertRegex(
            self.stderr.getvalue(),
            "The uninstall of worker is unfinished; run the same ./deploy.sh "
            "uninstall command in its release again .with --delete-data if you gave it.",
        )
        self.assertNotIn(("worker", ["install"]), self.releases.calls)

    def test_a_named_component_still_finishes_a_pending_uninstall_first(self):
        self.first_run()
        self.releases.pending = {
            "operation": "uninstall",
            "component": "worker",
            "owners": [],
        }
        self.assertEqual(self.run_command("worker"), 1)
        self.assertIn("The uninstall of worker is unfinished", self.stderr.getvalue())

    def test_a_named_component_is_installed_again_with_its_current_config(self):
        self.first_run()
        self.assertEqual(self.run_command("worker"), 0, self.stderr.getvalue())
        self.assertEqual(
            self.releases.commands(),
            ["init-layout", "status --json", "install", "status"],
        )
        self.assertEqual(self.run_command("reports"), 1)
        self.assertIn(
            "No cedar release of reports is installed; installed: web, api, worker",
            self.stderr.getvalue(),
        )

    def test_options_for_an_existing_gateway_config_are_not_applied_silently(self):
        self.first_run()
        self.assertEqual(
            self.run_command("web", "--public-origin", "https://other.example:9443"), 0
        )
        self.assertIn("apply only to a new config", self.stderr.getvalue())
        self.assertNotIn("init-config", " ".join(self.releases.commands()))

    def test_a_different_credential_stops_before_anything_is_copied(self):
        self.first_run()
        existing = self.lib / "cedar/state/web/credentials/web/web.key"
        existing.parent.mkdir(parents=True)
        existing.write_text("installed-key\n")
        self.deliver("web", "credentials/web/web.key", "another-key\n")
        new = self.deliver("web", "credentials/web/web.crt", "certificate\n")
        self.assertEqual(self.run_command("web"), 1)
        self.assertIn("credentials/web/web.key in", self.stderr.getvalue())
        self.assertIn("nothing was copied", self.stderr.getvalue())
        self.assertNotIn("another-key", self.stderr.getvalue())
        self.assertFalse((existing.parent / "web.crt").exists())
        self.assertTrue(new.exists())
        self.assertNotIn("install", self.releases.commands())

    def test_files_for_a_component_not_installed_now_are_named(self):
        self.first_run()
        self.deliver("worker", "credentials/token/value", "token\n")
        self.assertEqual(self.run_command(), 0)
        self.assertIn(
            "holds delivered files that worker does not use yet; run cedar worker",
            self.stderr.getvalue(),
        )
        self.assertTrue(
            (self.lib / "cedar/incoming/worker/credentials/token/value").exists()
        )
        # cedar worker takes them; then nothing is waiting and nothing is said.
        self.assertEqual(self.run_command("worker"), 0)
        self.assertFalse((self.lib / "cedar/incoming/worker").exists())
        self.assertEqual(self.run_command(), 0)
        self.assertNotIn("does not use yet", self.stderr.getvalue())

    def test_identical_credentials_are_kept_and_links_and_partial_copies_refused(self):
        self.first_run()
        self.deliver("worker", "credentials/token/value", "token\n")
        self.assertEqual(self.run_command("worker"), 0)
        self.deliver("worker", "credentials/token/value", "token\n")
        self.assertEqual(self.run_command("worker"), 0)
        self.assertFalse((self.lib / "cedar/incoming/worker").exists())
        for name, make in (
            ("linked", lambda path: path.symlink_to(self.root / "elsewhere")),
            ("value.partial", lambda path: path.write_text("half")),
        ):
            with self.subTest(name=name):
                path = self.lib / "cedar/incoming/worker/credentials/token" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                make(path)
                self.assertEqual(self.run_command("worker"), 1)
                self.assertIn(name, self.stderr.getvalue())
                path.unlink()

    def test_root_another_account_and_missing_releases_are_refused(self):
        with mock.patch.object(os, "geteuid", return_value=0):
            self.assertEqual(self.run_command(), 1)
        self.assertIn("not as root", self.stderr.getvalue())
        other = pwd.struct_passwd(
            ("operator-b", "x", 2000, 2000, "", "/home/b", "/bin/bash")
        )
        with mock.patch.object(pwd, "getpwuid", return_value=other):
            self.assertEqual(self.run_command(), 1)
        self.assertIn("cedar runs as operator-b on this host; log in as operator-b",
                      self.stderr.getvalue())  # fmt: skip
        self.releases.rpm_lines.clear()
        self.assertEqual(self.run_command(), 1)
        self.assertIn("No cedar release is installed; the administrator runs",
                      self.stderr.getvalue())  # fmt: skip
        self.assertEqual(self.releases.calls, [])

    def test_a_missing_dependency_is_named_before_any_step(self):
        self.releases.rpm_lines = [
            line for line in self.releases.rpm_lines if "-web-" not in line
        ]
        self.assertEqual(self.run_command(), 1)
        self.assertIn(
            "api requires web, which is not installed; the administrator delivers "
            "the cedar-web RPM",
            self.stderr.getvalue(),
        )
        self.assertEqual(self.releases.calls, [])


if __name__ == "__main__":
    unittest.main()


class EnvironmentTests(RuntimeTests):
    """cedar --environment <name> (backlog 85): the operator's file decides."""

    def place(self, name, text):
        path = self.lib / "cedar/state" / (name + ".yaml")
        path.write_text(text)
        return path

    def environment_run(self, *arguments):
        return self.run_command(
            "--environment",
            "prod1",
            "--public-origin",
            "https://shop.example:9443",
            "--ip-address",
            "10.0.0.5",
            *arguments,
        )

    def test_only_the_listed_components_are_deployed_with_the_file(self):
        self.place("prod1", "components: [web, api]\n")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        self.assertEqual(
            self.releases.commands(),
            [
                "check-environment prod1",
                "check-environment prod1",
                "init-layout",
                "status --json",
                WEB_INIT.replace(
                    "init-config web", "init-config web --environment prod1"
                ),
                "install --environment prod1",
                "init-config api --environment prod1",
                "install --environment prod1",
                "status",
            ],
        )
        self.assertNotIn("worker", [name for name, _ in self.releases.calls])
        self.assertEqual(sorted(self.releases.installed), ["api", "web"])

    def test_missing_packages_and_dependencies_change_nothing(self):
        self.releases.add("web", "2.0.0")
        for label, text, pattern in (
            ("missing package", "components: [web, api, reports]\n",
             "no release package of reports"),
            ("incompatible", "components: [web, api]\n",
             "api needs web 1.0.0 or newer before 2.0.0, installed: 2.0.0"),
            ("dependency not listed", "components: [api]\n",
             "api requires web; add web to components:"),
            ("no components", "overrides: {}\n", "components: must list"),
            ("repeated", "components: [web, web]\n", "components: must list"),
        ):  # fmt: skip
            with self.subTest(label):
                self.place("prod1", text)
                self.assertEqual(self.environment_run(), 1)
                self.assertRegex(self.stderr.getvalue(), pattern)
                self.assertEqual(self.releases.calls, [])
                if label in ("missing package", "incompatible"):
                    self.assertIn(
                        "Nothing was changed. The administrator installs the cedar "
                        "release packages (sudo cedar-admin <delivery directory>); "
                        "then run the same command again",
                        self.stderr.getvalue(),
                    )
        self.assertEqual(self.run_command("--environment", "absent"), 1)
        self.assertIn("Missing", self.stderr.getvalue())
        self.assertIn(
            "absent.yaml; place the environment file there", self.stderr.getvalue()
        )

    def test_a_refused_check_stops_before_any_install(self):
        self.place("prod1", "components: [web, api]\n")
        self.releases.check_fail.add("api")
        self.assertEqual(self.environment_run(), 1)
        # Not even the bootstrap file is written (init-layout).
        self.assertEqual(
            self.releases.commands(),
            ["check-environment prod1", "check-environment prod1"],
        )
        self.assertEqual(self.releases.installed, {})

    def test_without_the_environment_its_components_are_not_installed(self):
        """Product owner, 2026-11-10: plain cedar stops before the first install."""
        self.place("prod1", "components: [web, api, worker]\n")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        records = self.lib / "cedar/state/environment"
        records.mkdir()
        (records / "worker.json").write_text(
            json.dumps(
                {
                    "api_secret": None,
                    "environment": "prod1",
                    "overrides": {"main": {"MODE": "fast"}},
                }
            )
        )
        # Nothing to do: nothing is refused.
        self.assertEqual(self.run_command(), 0, self.stderr.getvalue())
        self.releases.add("worker", "1.1.0")
        self.releases.add("web", "1.1.0")
        for arguments, command in (
            ((), "Run cedar --environment prod1"),
            (("worker",), "Run cedar --environment prod1 worker"),
        ):
            with self.subTest(arguments):
                self.releases.calls.clear()
                self.assertEqual(self.run_command(*arguments), 1)
                self.assertIn(
                    "worker was installed with --environment prod1, which gave it "
                    "overrides or an API secret line; nothing was changed. " + command,
                    self.stderr.getvalue(),
                )
                self.assertNotIn("install", self.releases.commands())
        # With the environment it proceeds.
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        self.assertEqual(self.releases.installed["worker"], "1.1.0")

    def test_messages_name_the_command_with_its_environment(self):
        self.place("prod1", "components: [web, api]\n")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        incoming = self.lib / "cedar/incoming/api"
        incoming.mkdir(parents=True)
        (incoming / "token").write_text("delivered")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        self.assertIn(
            "use yet; run cedar --environment prod1 api to install it with them",
            self.stderr.getvalue(),
        )

    def test_a_changed_environment_installs_only_the_changed_components(self):
        """The same versions: only what the file now changes is installed again."""
        self.place("prod1", "components: [web, api, worker]\n")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        self.releases.calls.clear()
        self.releases.changed.add("worker")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        self.assertEqual(
            [name for name, command in self.releases.calls if command[0] == "install"],
            ["worker"],
        )
        self.assertIn(
            "[OK] web 1.0.0 is installed with environment prod1", self.stdout.getvalue()
        )
        # Asked at each component's turn, after the installs before it.
        self.assertEqual(
            self.releases.commands("worker"),
            [
                "check-environment prod1",
                "check-environment prod1 --json",
                "install --environment prod1",
                "status",
            ],
        )
        # Nothing changed: nothing is installed, and a named one always is.
        self.releases.calls.clear()
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        self.assertNotIn("install --environment prod1", self.releases.commands())
        self.assertEqual(self.environment_run("api"), 0, self.stderr.getvalue())
        self.assertEqual(
            self.releases.commands("api")[-1], "install --environment prod1"
        )

    def test_an_uninstalled_listed_component_stops_until_it_is_named(self):
        self.place("prod1", "components: [web, api, worker]\n")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        del self.releases.installed["worker"]
        record = self.lib / "cedar/state/uninstalled/worker"
        record.parent.mkdir()
        record.write_text("1.0.0\n")
        self.assertEqual(self.environment_run(), 1)
        self.assertIn(
            "worker was uninstalled but is in components: of "
            + str(self.lib / "cedar/state/prod1.yaml")
            + "; remove it there, or run cedar --environment prod1 worker to install "
            "it again",
            self.stderr.getvalue(),
        )
        self.assertEqual(self.releases.calls, [])
        self.assertEqual(self.environment_run("worker"), 0, self.stderr.getvalue())
        self.assertFalse(record.exists())
        self.assertIn(
            ("worker", ["install", "--environment", "prod1"]), self.releases.calls
        )

    def test_a_pending_operation_outside_the_environment_stops(self):
        self.place("prod1", "components: [web, api]\n")
        self.releases.pending = {
            "operation": "install",
            "component": "worker",
            "owners": [],
        }
        self.assertEqual(self.environment_run(), 1)
        self.assertIn(
            "The install of worker is unfinished, and worker is not in this environment",
            self.stderr.getvalue(),
        )
        self.assertNotIn("install --environment prod1", self.releases.commands())

    def test_identity_comes_before_the_components_it_may_register(self):
        identity = {"requires": {}, "accepts": {}, "identity": "zed"}
        for name in ("alpha", "zed"):
            self.releases.add(name, "1.0.0", identity)
        self.place("prod1", "components: [alpha, zed]\n")
        self.assertEqual(self.environment_run(), 0, self.stderr.getvalue())
        installs = [
            name for name, command in self.releases.calls if command[0] == "install"
        ]
        self.assertEqual(installs, ["zed", "alpha"])
