"""The tools RPM and <product>-admin (backlog 69 WP2) with real RPM files.

Skipped where rpmbuild is not installed. The release and tools RPMs are built
for real and read with real rpm -qp; FakeHost stands in for everything that
reads or changes the host: the RPM database (a set of installed RPM files),
dnf, SELinux, systemd, sudo, prepare-host.sh and setpriv. The credential
writer runs for real as the test user.
"""

import copy
import grp
import pwd
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import rpms

from helpers.product_fixture import WORKER, ProductFixture

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import admin  # pyright: ignore[reportMissingImports] - tools/ is added above
import host  # pyright: ignore[reportMissingImports] - tools/ is added above

# The real function: ProductFixture replaces subprocess.run with a recorder.
RUN = subprocess.run
ACCOUNT = pwd.struct_passwd(
    ("operator-a", "x", 1000, 1000, "", "/home/operator-a", "/bin/bash")
)
RELEASE = "/var/lib/cedar/releases/cedar-worker-1.2.3"


def real(arguments, stdin=None):
    return RUN(
        arguments,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )


class Restarted(Exception):
    """os.execv of the new tools; the test checks its arguments."""


class FakeHost:
    """The host as admin.py sees it through its commands."""

    def __init__(self, root, build_command):
        self.build_command = build_command  # Podman for bundle builds
        self.lib = root / "var-lib"
        self.rpmdb = root / "rpmdb"
        self.rpmdb.mkdir()
        self.installed = {}  # package name -> installed RPM file
        self.extra_installed = []  # rpm -qa lines of packages without a file
        self.damaged = set()
        self.selinux = "Enforcing"
        self.sudo = "User {} is not allowed to run sudo on lab."
        self.trusted = True
        self.prepare_status = 0
        self.transactions = []
        self.prepared = []
        self.trust_runs = []

    def install(self, path):
        name = real(["rpm", "-qp", "--queryformat", "%{NAME}", str(path)]).stdout
        target = self.rpmdb / Path(path).name
        shutil.copyfile(str(path), str(target))
        self.installed[name] = target
        self.damaged.discard(name)

    def command(self, arguments, **kwargs):
        args = list(map(str, arguments))
        stdin = kwargs.get("input")

        def done(stdout="", status=0, stderr=""):
            return subprocess.CompletedProcess(args, status, stdout, stderr)

        if args[0] == "podman":
            return self.build_command(arguments, **kwargs)
        if args[0] == "rpmbuild" or args[:2] == ["rpm", "-qp"]:
            return RUN(arguments, **kwargs)
        if args[:2] == ["rpm", "-qa"]:
            lines = [
                real(["rpm", "-qp", "--queryformat", args[3], str(path)]).stdout
                for path in self.installed.values()
            ]
            return done("".join(lines + self.extra_installed))
        if args[:3] == ["rpm", "-q", "--dump"]:
            return real(["rpm", "-qp", "--dump", str(self.installed[args[3]])])
        if args[:2] == ["rpm", "-V"]:
            return done(status=1 if args[2] in self.damaged else 0)
        if args == ["rpm", "-q", "rpm-plugin-fapolicyd"]:
            return done("rpm-plugin-fapolicyd-1.3.3-1.el9.x86_64\n")
        if args[: len(admin.DNF)] == admin.DNF:
            operation, files = args[len(admin.DNF)], args[len(admin.DNF) + 1 :]
            self.transactions.append((operation, [Path(f).name for f in files]))
            for path in files:
                self.install(path)
            return done()
        if args == ["getenforce"]:
            return done(self.selinux + "\n")
        if args[:2] == ["systemctl", "is-active"]:
            return done("active\n")
        if args[:2] == ["systemd-analyze", "cat-config"]:
            return done("# /etc/systemd/journald.conf\n[Journal]\n#Storage=auto\n")
        if args[:3] == ["sudo", "-n", "-l"]:
            return done(self.sudo.format(args[-1]) + "\n")
        if args[0] in ("systemd-tmpfiles", "journalctl"):
            return done()
        if args[0] == "bash" and args[1].endswith("scripts/prepare-host.sh"):
            self.prepared.append(args[2:])
            if self.prepare_status == 0:
                for name in ("state", "incoming"):
                    (self.lib / "cedar" / name).mkdir(parents=True, exist_ok=True)
            return done(status=self.prepare_status)
        if args[0] == "setpriv":
            rest = args[args.index("--") + 1 :]
            if rest[-1] == "--help":
                self.trust_runs.append(args)
                if self.trusted:
                    return done("Usage: ./deploy.sh ...\n")
                return done(status=1, stderr="PermissionError: [Errno 1] denied")
            if rest[0] == "python3":
                return real(rest, stdin=stdin)
        raise AssertionError("Unexpected host command: " + str(args))


@unittest.skipUnless(shutil.which("rpmbuild"), "rpmbuild is not installed")
class AdminFixture(ProductFixture):
    def setUp(self):
        super().setUp()
        self.product_name = "cedar"
        product: dict = copy.deepcopy(WORKER)
        product["worker"]["files"] = {"notes.txt": "public\n"}
        self.write_product(product, version="1.2.3")
        self.build_and_unpack()
        self.stack.enter_context(
            mock.patch.multiple(rpms, ROOT=self.source, DIST=self.source / "dist")
        )
        self.host = FakeHost(self.root, self.host_command)
        self.process.side_effect = self.host.command
        self.release_rpm, self.tools_rpm = rpms.build()
        self.delivery = self.root / "mnt"
        self.delivery.mkdir()
        for path in (self.release_rpm, self.tools_rpm):
            shutil.copyfile(str(path), str(self.delivery / path.name))
        # The administrator installed the tools from the medium (bootstrap).
        self.host.install(self.tools_rpm)

        (self.root / "etc").mkdir()
        tools = self.root / "tools"
        tools.mkdir()
        (tools / "bundle.yaml").write_text("product: cedar\n")
        (self.root / "os-release").write_text('ID="ol"\nVERSION_ID="9.6"\n')
        self.fapolicyd = self.root / "fapolicyd.conf"
        self.fapolicyd.write_text("trust = rpmdb,file\nsubj_cache_size = 16381\n")
        self.stack.enter_context(
            mock.patch.multiple(
                host, TOOLS=tools, LIB=self.host.lib, ETC=self.root / "etc"
            )
        )
        self.stack.enter_context(
            mock.patch.multiple(
                admin,
                JOURNAL=self.root / "journal",
                OS_RELEASE=self.root / "os-release",
                FAPOLICYD_CONF=self.fapolicyd,
                TRUST_WAIT=0,
            )
        )
        self.euid.return_value = 0

        def getpwnam(name):
            if name != ACCOUNT.pw_name:
                raise KeyError(name)
            return ACCOUNT

        for target, name, value in (
            (admin.pwd, "getpwnam", mock.Mock(side_effect=getpwnam)),
            (admin.pwd, "getpwuid", mock.Mock(return_value=ACCOUNT)),
            (admin.os, "getgrouplist", mock.Mock(return_value=[1000])),
            (admin.grp, "getgrgid", mock.Mock(return_value=grp.struct_group(
                ("operator-a", "x", 1000, [])))),
            (admin.shutil, "which", mock.Mock(return_value="/usr/bin/found")),
            (admin.os, "execv", mock.Mock(side_effect=Restarted)),
        ):  # fmt: skip
            self.stack.enter_context(mock.patch.object(target, name, value))

    def admin(self, *arguments):
        self.stdout.seek(0)
        self.stdout.truncate()
        self.stderr.seek(0)
        self.stderr.truncate()
        return admin.main([str(argument) for argument in arguments])

    def first_install(self):
        self.assertEqual(
            self.admin(self.delivery, "--user", "operator-a", "--port", "8443"),
            0,
            self.stderr.getvalue(),
        )


class AdminInstallTests(AdminFixture):
    def test_first_installation_then_an_unchanged_repeat(self):
        self.first_install()
        self.assertEqual(
            self.host.transactions,
            [("install", [self.release_rpm.name])],
        )
        self.assertEqual(
            self.host.prepared, [["--port", "8443", "--user", "operator-a"]]
        )
        conf = self.root / "etc/cedar/host.conf"
        self.assertIn("\nHTTPS_PORT=8443\n", conf.read_text())
        self.assertEqual(stat.S_IMODE(conf.stat().st_mode), 0o644)
        self.assertTrue((self.root / "journal").is_dir())
        (run,) = self.host.trust_runs
        self.assertEqual(
            run[:9],
            ["setpriv", "--reuid=1000", "--regid=1000", "--clear-groups",
             "--inh-caps=-all", "--ambient-caps=-all", "--bounding-set=-all",
             "--no-new-privs", "--"],
        )  # fmt: skip
        self.assertEqual(run[-2:], [RELEASE + "/deploy.sh", "--help"])
        self.assertIn(
            "[OK] operator-a can run cedar-worker-1.2.3", self.stdout.getvalue()
        )
        self.assertTrue(
            self.stdout.getvalue().endswith("PASS: cedar-admin completed\n")
        )
        # The repeat takes the account and port from the host and installs nothing.
        self.assertEqual(self.admin(self.delivery), 0, self.stderr.getvalue())
        self.assertEqual(len(self.host.transactions), 1)
        self.assertIn(
            "[OK] cedar-worker-1.2.3 1.2.3 is installed", self.stdout.getvalue()
        )
        self.assertEqual(
            self.host.prepared[-1], ["--port", "8443", "--user", "operator-a"]
        )

    def test_first_run_asks_for_the_account_and_port(self):
        terminal = mock.Mock(isatty=mock.Mock(return_value=True))
        with mock.patch.object(admin.sys, "stdin", terminal), mock.patch(
            "builtins.input", side_effect=["operator-a", ""]
        ) as asked:
            self.assertEqual(self.admin(self.delivery), 0, self.stderr.getvalue())
        self.assertEqual(
            [call[0][0] for call in asked.call_args_list],
            [
                "Runtime account (an existing login account without sudo): ",
                "HTTPS port [8443]: ",
            ],
        )
        self.assertEqual(
            self.host.prepared, [["--port", "8443", "--user", "operator-a"]]
        )

    def test_without_a_terminal_the_missing_option_is_named(self):
        with mock.patch.object(admin.sys, "stdin", mock.Mock(isatty=lambda: False)):
            self.assertEqual(self.admin(self.delivery, "--port", "8443"), 1)
        self.assertIn(
            "ERROR: Give --user; there is no terminal", self.stderr.getvalue()
        )
        self.assertEqual(self.host.transactions, [])

    def test_the_account_and_port_are_not_changed_after_preparation(self):
        self.first_install()
        self.assertEqual(self.admin(self.delivery, "--port", "9443"), 1)
        self.assertIn("uses HTTPS port 8443 on this host", self.stderr.getvalue())
        self.assertEqual(self.admin(self.delivery, "--user", "operator-b"), 1)
        self.assertIn("runs as operator-a on this host", self.stderr.getvalue())

    def test_preflight_names_every_problem_before_any_change(self):
        self.host.selinux = "Permissive"
        self.host.sudo = "User {} may run the following commands on lab:\n    (ALL) ALL"
        self.fapolicyd.write_text("trust = file\nsubj_cache_size = 1549\n")
        self.assertEqual(
            self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
        )
        errors = self.stderr.getvalue()
        for expected in (
            "ERROR: Preflight stopped before any change:",
            "- SELinux is Permissive; the system administrator sets it to Enforcing",
            "- fapolicyd does not trust the RPM database (trust = file",
            "- operator-a may use sudo",
        ):
            self.assertIn(expected, errors)
        self.assertEqual((self.host.transactions, self.host.prepared), ([], []))
        self.assertFalse((self.root / "journal").exists())

    def test_a_missing_os_package_is_named(self):
        def which(name):
            return None if name == "semanage" else "/usr/bin/" + name

        with mock.patch.object(admin.shutil, "which", side_effect=which):
            self.assertEqual(
                self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
            )
        self.assertIn(
            "semanage is missing; install the OL9 package policycoreutils-python-utils",
            self.stderr.getvalue(),
        )

    def test_unknown_account_and_privileged_group_are_refused(self):
        self.assertEqual(
            self.admin(self.delivery, "--user", "nobody-here", "--port", "8443"), 1
        )
        self.assertIn("Account nobody-here does not exist", self.stderr.getvalue())
        wheel = grp.struct_group(("wheel", "x", 10, []))
        with mock.patch.object(admin.grp, "getgrgid", return_value=wheel):
            self.assertEqual(
                self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
            )
        self.assertIn("privileged group(s) wheel", self.stderr.getvalue())

    def test_newer_tools_are_installed_first_and_started_again(self):
        self.host.installed.clear()
        with self.assertRaises(Restarted):
            self.admin(
                self.delivery, "--user", "operator-a", "--port", "8443", "--verbose"
            )
        self.assertEqual(self.host.transactions, [("install", [self.tools_rpm.name])])
        admin.os.execv.assert_called_once_with(
            "/usr/sbin/cedar-admin",
            ["/usr/sbin/cedar-admin", str(self.delivery), "--user", "operator-a",
             "--port", "8443", "--verbose"],
        )  # fmt: skip
        self.assertEqual(self.host.prepared, [])

    def test_same_version_with_other_content_is_refused(self):
        notes = self.source / "components/worker/files/notes.txt"
        notes.write_text("changed without a new version\n")
        self.build_and_unpack()
        archive = self.source / "dist/cedar-worker-1.2.3-offline.tar.gz"
        other = rpms.build_rpm(archive, "cedar", "worker", "1.2.3", self.root / "other")
        self.host.install(other)
        self.assertEqual(
            self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
        )
        self.assertIn(
            "cedar-worker-1.2.3 1.2.3 is installed with other content; one version has "
            "one content",
            self.stderr.getvalue(),
        )
        self.assertEqual(self.host.transactions, [])

    def test_a_damaged_identical_package_is_reinstalled(self):
        self.host.install(self.release_rpm)
        self.host.damaged.add("cedar-worker-1.2.3")
        self.first_install()
        self.assertEqual(
            self.host.transactions, [("reinstall", [self.release_rpm.name])]
        )
        self.assertIn("is damaged (rpm -V); reinstalling it", self.stderr.getvalue())

    def test_an_older_release_than_installed_is_refused(self):
        self.host.extra_installed.append(
            "cedar-worker-1.3.0 1.3.0 /var/lib/cedar/releases/cedar-worker-1.3.0\n"
        )
        self.assertEqual(
            self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
        )
        self.assertIn(
            self.release_rpm.name + " is older than the installed worker 1.3.0; "
            "deliver 1.3.0 or newer",
            self.stderr.getvalue(),
        )
        self.assertEqual(self.host.transactions, [])

    def test_failed_host_preparation_writes_no_host_conf(self):
        self.host.prepare_status = 1
        self.assertEqual(
            self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
        )
        self.assertIn(
            "Host preparation stopped; fix what it names", self.stderr.getvalue()
        )
        self.assertFalse((self.root / "etc/cedar/host.conf").exists())

    def test_an_untrusted_release_stops_with_the_fapolicyd_remedy(self):
        self.host.trusted = False
        self.assertEqual(
            self.admin(self.delivery, "--user", "operator-a", "--port", "8443"), 1
        )
        self.assertIn(
            f"operator-a cannot run {RELEASE}/deploy.sh (PermissionError: [Errno 1] "
            "denied); fapolicyd must trust RPM-installed files",
            self.stderr.getvalue(),
        )

    def test_usage_and_root_errors(self):
        self.assertEqual(self.admin("--credentials", self.delivery, "--user", "x"), 2)
        self.assertIn(
            "ERROR: --credentials takes no --user or --port", self.stderr.getvalue()
        )
        self.assertEqual(self.admin(self.delivery, "--port", "80"), 2)
        self.euid.return_value = 1000
        self.assertEqual(self.admin(self.delivery), 1)
        self.assertIn(
            "ERROR: Run it as administrator: sudo cedar-admin", self.stderr.getvalue()
        )


class AdminSelectionTests(unittest.TestCase):
    def test_packages_of_this_product_are_recognised_by_name_and_path(self):
        for name, version, path, expected in (
            ("cedar-tools", "0.1.0", "/usr/libexec/cedar-tools", ""),
            ("cedar-worker-1.2.3", "1.2.3", RELEASE, "worker"),
            ("cedar-x-worker-1.2.3", "1.2.3",
             "/var/lib/cedar-x/releases/cedar-x-worker-1.2.3", None),
            ("cedar-worker-1.2.3", "1.2.4", RELEASE, None),
            ("cedar-worker-1.2.3", "1.2.3", "/opt/elsewhere", None),
            ("cedarx-tools", "0.1.0", "/usr/libexec/cedarx-tools", None),
        ):  # fmt: skip
            with self.subTest(name=name, version=version):
                self.assertEqual(
                    host.component_of("cedar", name, version, path), expected
                )

    def test_the_newest_delivered_version_of_each_component_is_chosen(self):
        def package(component, version):
            name = "cedar-tools" if not component else f"cedar-{component}-{version}"
            return host.Package(name, version, component, Path(name + ".rpm"))

        delivery = [
            package("worker", "1.2.3"),
            package("worker", "1.10.0"),
            package("worker", "1.9.0"),
            package("", "0.2.0"),
            package("", "0.1.0"),
        ]
        installed = [host.Package("cedar-tools", "0.1.0", "", None)]
        with mock.patch.object(admin, "run") as run:
            install, reinstall = admin.select("cedar", delivery, installed)
        self.assertEqual(
            [(p.component, p.version) for p in install],
            [("", "0.2.0"), ("worker", "1.10.0")],
        )
        self.assertEqual(reinstall, [])
        run.assert_not_called()  # Nothing of the same name and version is installed.


class AdminCredentialTests(AdminFixture):
    def setUp(self):
        super().setUp()
        self.first_install()
        self.incoming = self.host.lib / "cedar/incoming"
        self.media = self.root / "usb"
        self.password = self.media / "worker/credentials/database/password"
        self.password.parent.mkdir(parents=True)
        self.password.write_text("delivered-secret-value\n")
        (self.media / "cedar-notes.txt").write_text("not a credential\n")
        (self.media / "photos").mkdir()

    def test_files_are_copied_with_the_same_layout_and_kept_on_a_repeat(self):
        self.assertEqual(
            self.admin("--credentials", self.media), 0, self.stderr.getvalue()
        )
        target = self.incoming / "worker/credentials/database/password"
        self.assertEqual(target.read_text(), "delivered-secret-value\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in self.incoming.iterdir()), ["worker"])
        self.assertIn(
            "[OK] incoming/worker/credentials/database/password\n",
            self.stdout.getvalue(),
        )
        self.assertEqual(
            self.admin("--credentials", self.media), 0, self.stderr.getvalue()
        )
        self.assertIn("password is already there", self.stdout.getvalue())
        for stream in (self.stdout, self.stderr):
            self.assertNotIn("delivered-secret-value", stream.getvalue())

    def test_a_different_existing_file_stops_before_any_copy(self):
        self.assertEqual(self.admin("--credentials", self.media), 0)
        self.password.write_text("another-secret\n")
        (self.password.parent / "user").write_text("reports\n")
        self.assertEqual(self.admin("--credentials", self.media), 1)
        self.assertIn(
            "ERROR: incoming/worker/credentials/database/password already exist with other "
            "content; nothing was copied",
            self.stderr.getvalue(),
        )
        self.assertNotIn("another-secret", self.stderr.getvalue())
        database = self.incoming / "worker/credentials/database"
        self.assertEqual(
            (database / "password").read_text(), "delivered-secret-value\n"
        )
        self.assertFalse((database / "user").exists())

    def test_links_unknown_components_and_unprepared_hosts_are_refused(self):
        outside = self.root / "outside"
        outside.write_text("not delivered\n")
        link = self.password.parent / "linked"
        link.symlink_to(outside)
        self.assertEqual(self.admin("--credentials", self.media), 1)
        self.assertIn("linked is a link or special file", self.stderr.getvalue())
        link.unlink()
        (self.media / "reports/credentials").mkdir(parents=True)
        self.assertEqual(self.admin("--credentials", self.media), 1)
        self.assertIn(
            "no cedar release of reports is installed", self.stderr.getvalue()
        )
        self.assertFalse((self.incoming / "worker").exists())
        shutil.rmtree(str(self.host.lib / "cedar/state"))
        self.assertEqual(self.admin("--credentials", self.media), 1)
        self.assertIn(
            "is not prepared; first run sudo cedar-admin", self.stderr.getvalue()
        )


@unittest.skipUnless(shutil.which("rpmbuild"), "rpmbuild is not installed")
class ToolsRpmTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.product_name = "cedar"
        self.write_product(copy.deepcopy(WORKER), version="1.2.3")
        self.stack.enter_context(
            mock.patch.multiple(rpms, ROOT=self.source, DIST=self.source / "dist")
        )
        self.process.side_effect = RUN

    def query(self, rpm, *args):
        return real(["rpm", "-qp", *args, str(rpm)]).stdout

    def test_tools_package_holds_the_command_and_what_it_imports(self):
        (rpm,) = rpms.build(tools=True)
        version = (self.source / "tools/VERSION").read_text().strip()
        self.assertEqual(rpm.name, f"cedar-tools-{version}-1.noarch.rpm")
        requires = self.query(rpm, "--requires").split()
        for package in ("python3", "python3-pyyaml", "util-linux", "rpm", "dnf"):
            self.assertIn(package, requires)
        self.assertIn(
            "removing cedar-tools is refused",
            self.query(rpm, "--queryformat", "%{PREUN}"),
        )
        dump = {
            line.split()[0]: line.split()
            for line in self.query(rpm, "--dump").splitlines()
        }
        libexec = "/usr/libexec/cedar-tools/"
        for installed, source in rpms.TOOLS_FILES.items():
            self.assertEqual(
                dump[libexec + installed][3], rpms.sha256(self.source / source)
            )
        self.assertEqual(dump["/usr/sbin/cedar-admin"][4], "0100755")
        self.assertEqual(dump["/usr/bin/cedar"][4], "0100755")
        self.assertEqual(dump[libexec + "scripts/prepare-host.sh"][4], "0100755")
        self.assertEqual(dump[libexec + "admin.py"][4], "0100644")
        self.assertIn(libexec + "bundle.yaml", dump)
        with self.assertRaisesRegex(
            rpms.RpmError, r"give tools \(tools/VERSION\) a new VERSION"
        ):
            rpms.build(tools=True)

    def test_the_packaged_files_are_enough_to_run_the_command(self):
        """The same layout as /usr/libexec/<product>-tools, run the way the wrapper runs it."""
        libexec = self.root / "libexec"
        for installed, source in rpms.TOOLS_FILES.items():
            (libexec / installed).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(self.source / source), str(libexec / installed))
        (libexec / "bundle.yaml").write_text("product: cedar\n")
        for script, usage in (
            ("admin.py", "Usage: sudo cedar-admin <directory>"),
            ("runtime.py", "Usage: cedar [<component>] [--public-origin <url>]"),
        ):
            with self.subTest(script=script):
                result = real(
                    [sys.executable, "-E", "-s", "-B", str(libexec / script), "--help"],
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(usage), result.stdout)


if __name__ == "__main__":
    unittest.main()
