"""dev/seed-db.sh: SQL in one component's running dev database (backlog 81).

The lookup runs on a really prepared dev installation of the renamed product.
The run goes through a stand-in podman that executes the fixed script with
real sh, in an environment that plays the database container's, and a
stand-in psql that records what it gets.
"""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml
from helpers.product_fixture import RENAMED, REPO, ProductFixture

from deployment import common, deploy
from platform_tests.test_database_preflight import environment_orders, mounted_orders

# Saved before the fixture replaces subprocess.run with a recorder.
REAL_RUN = subprocess.run

_spec = importlib.util.spec_from_file_location("seed_db", REPO / "dev/seed_db.py")
seed_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_db)

PODMAN = """\
#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
record = Path(os.environ["SEED_RECORD"])
(record / "podman-args.json").write_text(json.dumps(sys.argv[1:]))
if os.environ.get("PODMAN_STATUS"):
    sys.stdin.buffer.read()
    sys.exit(int(os.environ["PODMAN_STATUS"]))
env = json.loads((record / "container-env.json").read_text())
sys.exit(subprocess.run(["/bin/sh"] + sys.argv[5:], env=env).returncode)
"""
PSQL = """\
#!/bin/sh
printf '%s\\n' "$@" > "$SEED_RECORD/psql-args"
for name in PGPASSWORD PGDATABASE PGHOSTADDR PGCONNECT_TIMEOUT PGSERVICE; do
    eval "printf '%s' \\"\\${$name-unset}\\"" > "$SEED_RECORD/$name"
done
cat > "$SEED_RECORD/sql"
echo 'query result PRIVATE_MARKER'
printf '%s' "$PSQL_STDERR" >&2
exit "${PSQL_STATUS:-0}"
"""
PASSWORD = "p$a'ss; w x"


def install_documents():
    return [d for d in yaml.safe_load_all((common.BUILD / "install.yaml").read_text())]


def write_install(documents):
    (common.BUILD / "install.yaml").write_text(yaml.safe_dump_all(documents))


def pod(documents, name):
    return next(
        d
        for d in documents
        if d and d["kind"] == "Pod" and d["metadata"]["name"] == name
    )


class SeedFixture(ProductFixture):
    def prepare(self, product=None):
        product = product or copy.deepcopy(RENAMED)
        self.write_product(product)
        self.provide_credentials(product, common.BUILD / "dev")
        deploy.prepare()

    def manifest(self, component, name):
        return self.source / "components" / component / "manifests" / name


class LookupTests(SeedFixture):
    """The database container comes from the prepared install.yaml."""

    def test_a_password_secret_mounted_as_its_directory(self):
        self.prepare()
        self.assertEqual(seed_db.database_container("orders"), "orders-postgres-db")

    def test_a_password_file_from_mounts(self):
        self.prepare(mounted_orders())
        self.assertEqual(seed_db.database_container("orders"), "orders-postgres-db")

    def test_a_password_path_from_environment(self):
        self.prepare(environment_orders())
        self.assertEqual(seed_db.database_container("orders"), "orders-postgres-db")

    def test_only_ordinary_containers_count(self):
        self.prepare()
        documents = install_documents()
        spec = pod(documents, "orders-postgres")["spec"]
        spec["initContainers"] = [dict(spec["containers"][0], name="restore")]
        write_install(documents)
        self.assertEqual(seed_db.database_container("orders"), "orders-postgres-db")

    def test_a_secret_is_read_by_key_names_only(self):
        """A password path from a Secret is seen and refused as before."""
        self.prepare()
        documents = install_documents()
        db = pod(documents, "orders-postgres")["spec"]["containers"][0]
        db["env"] = [e for e in db["env"] if e["name"] != "POSTGRES_PASSWORD_FILE"]
        db["envFrom"] = [{"secretRef": {"name": "orders-db-hidden"}}]
        documents.append(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "orders-db-hidden"},
                "data": {"POSTGRES_PASSWORD_FILE": "L3J1bi9zZWNyZXRz"},
            }
        )
        write_install(documents)
        with self.assertRaisesRegex(
            common.DeployError, "Invalid POSTGRES_PASSWORD_FILE"
        ):
            seed_db.database_container("orders")

    def test_zero_or_several_databases_stop(self):
        self.prepare()
        with self.assertRaisesRegex(
            common.DeployError,
            r"inventory has 0 PostgreSQL database containers \(none\)",
        ):
            seed_db.database_container("inventory")
        documents = install_documents()
        spec = pod(documents, "orders-postgres")["spec"]
        spec["containers"].append(dict(spec["containers"][0], name="copy"))
        write_install(documents)
        with self.assertRaisesRegex(
            common.DeployError,
            r"orders has 2 .*\(orders-postgres-db, orders-postgres-copy\); "
            "seed-db supports exactly one",
        ):
            seed_db.database_container("orders")

    def rename_source_pod(self, old, new):
        for path in (self.source / "components/orders/manifests").glob("*.yaml"):
            documents = list(yaml.safe_load_all(path.read_text()))
            for doc in documents:
                if doc and doc["kind"] == "Pod" and doc["metadata"]["name"] == old:
                    doc["metadata"]["name"] = new
                    path.write_text(yaml.safe_dump_all(documents))
                    return
        raise AssertionError("no source Pod " + old)

    def test_source_pod_names_are_checked_before_the_lookup(self):
        self.prepare()
        for new, pattern in (
            ("@@WEB_POD@@", "Pod name @@WEB_POD@@ is a placeholder"),
            # A foreign Pod that exists in install.yaml is never selected.
            ("inventory-web", "Pod name must start with orders-"),
            (
                "orders-other",
                r"Pod orders-other is not in .*install.yaml; run ./dev/dev.sh up",
            ),
        ):
            with self.subTest(new):
                self.rename_source_pod("orders-web", new)
                with self.assertRaisesRegex(common.DeployError, pattern):
                    seed_db.database_container("orders")
                self.rename_source_pod(new, "orders-web")

    def test_a_pod_declared_twice_is_named(self):
        product = copy.deepcopy(RENAMED)
        extra = copy.deepcopy(product["orders"]["manifests"][1])
        extra["spec"]["containers"][0]["name"] = "extra"
        product["orders"]["manifests"].append(extra)
        self.write_product(product)
        common.BUILD.mkdir(exist_ok=True)
        (common.BUILD / "install.yaml").write_text("")
        with self.assertRaisesRegex(
            common.DeployError, "Pod orders-postgres is declared 2 times in "
        ):
            seed_db.database_container("orders")

    def test_catalog_and_prepared_files(self):
        self.prepare()
        with self.assertRaisesRegex(common.DeployError, "shipping is not a component"):
            seed_db.check_component("shipping")
        # Another component's files are never read.
        (self.source / "components/inventory/VERSION").write_text("not a version\n")
        self.assertEqual(seed_db.database_container("orders"), "orders-postgres-db")
        (common.BUILD / "install.yaml").unlink()
        with self.assertRaisesRegex(
            common.DeployError, "install.yaml is missing; run ./dev/dev.sh up"
        ):
            seed_db.database_container("orders")


class RunTests(SeedFixture):
    """The command with a stand-in podman and psql."""

    def setUp(self):
        super().setUp()
        self.prepare()
        self.work = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.record = self.work / "record"
        self.record.mkdir()
        tools = {"bin": ("podman",), "image": ("psql", "cat", "sh")}
        for directory, names in tools.items():
            (self.work / directory).mkdir()
            for name in names:
                path = self.work / directory / name
                if name in ("cat", "sh"):
                    path.symlink_to("/bin/" + name)
                else:
                    path.write_text(PODMAN if name == "podman" else PSQL)
                    path.chmod(0o755)
        self.password = self.work / "password"
        self.password.write_text(PASSWORD + "\n")
        self.sql = self.work / "seed data" / "populate.sql"
        self.sql.parent.mkdir()
        self.sql.write_bytes(b"INSERT INTO t VALUES ('a b', $$x$$);\n\xe2\x82\xac\n")
        os.environ["PATH"] = str(self.work / "bin") + os.pathsep + os.environ["PATH"]
        os.environ["SEED_RECORD"] = str(self.record)
        os.environ.pop("PODMAN_STATUS", None)
        self.process.side_effect = REAL_RUN
        self.container({})

    def container(self, changes, image="image"):
        """The database container's environment; None removes a variable."""
        env = {
            "PATH": str(self.work / image),
            "POSTGRES_USER": "orders",
            "POSTGRES_DB": "host=other dbname=x",
            "POSTGRES_PASSWORD_FILE": str(self.password),
            "PGHOSTADDR": "192.0.2.1",
            "PGSERVICE": "other",
            "SEED_RECORD": str(self.record),
        }
        env.update(changes)
        env = {key: value for key, value in env.items() if value is not None}
        (self.record / "container-env.json").write_text(json.dumps(env))

    def run_seed(self, sql=None):
        for path in self.record.glob("*"):
            if path.name != "container-env.json":
                path.unlink()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = seed_db.main(["orders", str(sql or self.sql)])
        return status, out.getvalue(), err.getvalue()

    def recorded(self, name):
        return (self.record / name).read_text()

    def build_state(self):
        return {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(common.BUILD.rglob("*"))
            if path.is_file()
        }

    def test_the_sql_reaches_psql_unchanged(self):
        before = self.build_state()
        status, out, err = self.run_seed()
        self.assertEqual((status, err), (0, ""))
        self.assertEqual(out, f"[OK] seeded orders from {self.sql}\n")
        self.assertEqual(
            json.loads(self.recorded("podman-args.json")),
            ["exec", "-i", "orders-postgres-db", "sh", "-c", seed_db.SCRIPT],
        )
        self.assertEqual((self.record / "sql").read_bytes(), self.sql.read_bytes())
        self.assertEqual(
            self.recorded("psql-args").splitlines(),
            [
                "--no-psqlrc",
                "-w",
                "-h",
                "127.0.0.1",
                "-U",
                "orders",
                "--set",
                "ON_ERROR_STOP=1",
                "--single-transaction",
                "--file=-",
            ],
        )
        self.assertEqual(self.recorded("PGPASSWORD"), PASSWORD)
        self.assertNotIn(PASSWORD, self.recorded("psql-args"))
        self.assertNotIn(PASSWORD, self.recorded("podman-args.json"))
        # A connection-string-like name stays a name; loopback is pinned.
        self.assertEqual(self.recorded("PGDATABASE"), "host=other dbname=x")
        self.assertEqual(self.recorded("PGHOSTADDR"), "127.0.0.1")
        self.assertEqual(self.recorded("PGSERVICE"), "unset")
        self.assertEqual(self.recorded("PGCONNECT_TIMEOUT"), "5")
        self.assertEqual(self.build_state(), before)

    def assert_failed(self, message, psql_started=True):
        before = self.build_state()
        status, out, err = self.run_seed()
        self.assertEqual((status, out), (1, ""))
        self.assertTrue(
            err.startswith(f"ERROR: seeding orders from {self.sql} failed: "), err
        )
        self.assertIn(message, err)
        self.assertNotIn("PRIVATE_MARKER", err)
        self.assertNotIn(PASSWORD, err)
        self.assertEqual((self.record / "psql-args").exists(), psql_started)
        self.assertEqual(self.build_state(), before)
        return err

    def test_each_status_has_its_message(self):
        for status, message in (
            (
                "125",
                "podman cannot run a command in orders-postgres-db; run ./dev/dev.sh up",
            ),
            ("126", "the command cannot start in orders-postgres-db"),
            ("127", "cat or psql is missing"),
        ):
            with self.subTest(status):
                os.environ["PODMAN_STATUS"] = status
                self.assert_failed(message, psql_started=False)
        os.environ.pop("PODMAN_STATUS")
        for status, message in (
            ("1", "psql failed"),
            (
                "2",
                "the connection or authentication failed; check that orders-postgres-db",
            ),
            ("9", "unexpected status 9"),
        ):
            with self.subTest(status):
                self.container({"PSQL_STATUS": status, "PSQL_STDERR": "PRIVATE_MARKER"})
                self.assert_failed(message)

    def test_the_container_checks_stop_before_psql(self):
        for change, message in (
            ({"POSTGRES_USER": None}, "POSTGRES_USER is not set in orders-postgres-db"),
            ({"POSTGRES_DB": ""}, "POSTGRES_DB is not set in orders-postgres-db"),
            ({"POSTGRES_PASSWORD_FILE": None}, "POSTGRES_PASSWORD_FILE is not set"),
            (
                {"POSTGRES_PASSWORD_FILE": str(self.work / "absent")},
                (
                    "the password file in orders-postgres-db is missing, unreadable "
                    "or empty; restore the existing credential"
                ),
            ),
        ):
            with self.subTest(change):
                self.container(change)
                self.assert_failed(message, psql_started=False)
        self.password.write_text("\n")
        self.container({})
        self.assert_failed("is missing, unreadable or empty", psql_started=False)
        # A path cat cannot read, also when the tests run as root.
        self.container({"POSTGRES_PASSWORD_FILE": str(self.work)})
        self.assert_failed("is missing, unreadable or empty", psql_started=False)

    def test_missing_tools_are_not_a_credential_problem(self):
        for removed in ("psql", "cat"):
            with self.subTest(removed):
                image = "image-without-" + removed
                (self.work / image).mkdir()
                for name in {"psql", "cat", "sh"} - {removed}:
                    (self.work / image / name).symlink_to(self.work / "image" / name)
                self.container({}, image)
                self.assert_failed("cat or psql is missing", psql_started=False)

    def test_an_sql_error_names_only_its_line(self):
        for stderr, message in (
            (
                'psql:<stdin>:7: ERROR:  invalid input syntax: "PRIVATE_MARKER"\n',
                "the SQL failed at line 7; fix the SQL; its changes were rolled back",
            ),
            # A NOTICE with the same prefix comes first; the error's line counts.
            (
                (
                    "psql:<stdin>:2: NOTICE:  PRIVATE_MARKER\n"
                    "psql:<stdin>:7: ERROR:  PRIVATE_MARKER\n"
                ),
                "the SQL failed at line 7;",
            ),
            (
                "psql:<stdin>:2: NOTICE:  PRIVATE_MARKER\n",
                "the SQL failed; fix the SQL",
            ),
            ("psql:<stdin>:0: ERROR:  PRIVATE_MARKER\n", "the SQL failed; fix the SQL"),
            (
                "psql:<stdin>:x7: ERROR:  PRIVATE_MARKER\n",
                "the SQL failed; fix the SQL",
            ),
        ):
            with self.subTest(stderr):
                self.container({"PSQL_STATUS": "3", "PSQL_STDERR": stderr})
                self.assert_failed(message)

    def test_an_unreadable_sql_file_stops_before_podman(self):
        for sql in (self.work / "absent.sql", self.work):
            with self.subTest(sql):
                status, out, err = self.run_seed(sql)
                self.assertEqual((status, out), (1, ""))
                self.assertIn(f"ERROR: Cannot read {sql}", err)
                self.assertFalse((self.record / "podman-args.json").exists())

    def test_the_order_is_catalog_sql_then_prepared_files(self):
        (common.BUILD / "install.yaml").unlink()
        status, out, err = self.run_seed(self.work / "absent.sql")
        self.assertEqual((status, out), (1, ""))
        self.assertEqual(err, f"ERROR: Cannot read {self.work / 'absent.sql'}\n")

    def test_a_damaged_prepared_file_shows_no_value(self):
        """A parser message can quote a Secret value; only the path is named."""
        install = common.BUILD / "install.yaml"
        for text in (
            "kind: Secret\nmetadata: {name: orders-x}\ndata: {k: !!int PRIVATE_MARKER}\n",
            "kind: Secret\ndata: [PRIVATE_MARKER\n",
            "kind: Pod\nmetadata: {name: orders-postgres}\nspec: {containers: [PRIVATE_MARKER]}\n",
            "kind: Secret\nmetadata: PRIVATE_MARKER\n",
            "kind: Secret\nmetadata: {name: orders-x}\ndata: {k: !!bool PRIVATE_MARKER}\n",
            "kind: {field: PRIVATE_MARKER}\n",
        ):
            with self.subTest(text):
                install.write_text(text)
                status, out, err = self.run_seed()
                self.assertEqual((status, out), (1, ""))
                self.assertRegex(
                    err, r"^ERROR: .*install.yaml.*; run ./dev/dev.sh up\n$"
                )
                self.assertNotIn("PRIVATE_MARKER", err)
                self.assertNotIn("Traceback", err)
                self.assertFalse((self.record / "podman-args.json").exists())


class LauncherTests(SeedFixture):
    """dev/seed-db.sh itself: no traceback and nothing private, whatever it reads."""

    def setUp(self):
        super().setUp()
        self.prepare()
        (self.source / "dev").mkdir()
        for name in ("seed-db.sh", "seed_db.py"):
            (self.source / "dev" / name).write_bytes((REPO / "dev" / name).read_bytes())
        self.sql = self.source / "seed.sql"
        self.sql.write_text("SELECT 1;\n")

    def launch(self):
        launcher = self.source / "dev/seed-db.sh"
        return REAL_RUN(
            ["bash", str(launcher), "orders", str(self.sql)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )

    def assert_refused(self, message):
        result = self.launch()
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        self.assertEqual(result.returncode, 1, output)
        self.assertIn(message, output)
        self.assertNotIn("PRIVATE_MARKER", output)
        self.assertNotIn("Traceback", output)

    def test_a_damaged_prepared_file(self):
        install = common.BUILD / "install.yaml"
        for text, message in (
            (
                b"kind: Secret\nmetadata: {name: orders-x}\ndata: {k: !!bool PRIVATE_MARKER}\n",
                "install.yaml cannot be read as YAML; run ./dev/dev.sh up",
            ),
            (
                b"kind: {field: PRIVATE_MARKER}\n",
                "install.yaml is not a valid prepared file; run ./dev/dev.sh up",
            ),
            (b"kind: Secret\ndata: {k: \xff PRIVATE_MARKER}\n", "run ./dev/dev.sh up"),
        ):
            with self.subTest(text):
                install.write_bytes(text)
                self.assert_refused(message)

    def test_a_damaged_catalog(self):
        bundles = self.source / "bundles.yaml"
        bundles.write_text(bundles.read_text() + "extra: !!int PRIVATE_MARKER\n")
        self.assert_refused("bundles.yaml cannot be read; fix it")

    def test_every_source_document_is_checked(self):
        manifest = self.source / "components/orders/manifests"
        path = min(manifest.glob("*.yaml"))
        original = path.read_text()
        for extra, message in (
            ("kind: Pod\nmetadata: PRIVATE_MARKER\n", "metadata must be a map"),
            (
                "kind: ConfigMap\nmetadata: {name: inventory-settings}\n",
                "ConfigMap name must start with orders-",
            ),
        ):
            with self.subTest(extra):
                path.write_text(original + "---\n" + extra)
                self.assert_refused(message)
