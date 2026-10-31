"""Renamed-product acceptance: generator, dev rendering and scenario wiring, without a lab."""

import contextlib
import filecmp
import gzip
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import renamed_product
import yaml
from test_acceptance import runner, shell_code

from deployment import catalog

ROOT = Path(__file__).resolve().parent.parent
REMOTE = Path(__file__).with_name("remote.sh").read_text()
# The generated product's dependency order; the harness reads it from the build.
RENAMED_ORDER = ("gateway", "login-service", "orders", "inventory", "manual")
OLD_PREFIX = re.compile(r"^(platform|identity|app1|app2|help)(-|$)")


def resource_names(value, found):
    """Collect metadata names and every Secret/PVC/ConfigMap reference."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "metadata" and isinstance(item, dict):
                found.add(item.get("name"))
            elif key in ("claimName", "secretName"):
                found.add(item)
            elif key in (
                "configMap",
                "configMapRef",
                "secretRef",
                "secretKeyRef",
            ) and isinstance(item, dict):
                found.add(item.get("name"))
            resource_names(item, found)
    elif isinstance(value, list):
        for item in value:
            resource_names(item, found)
    return found


def images(directory, components="*"):
    return sorted(
        set(
            re.findall(
                r"image: (\S+)",
                "".join(
                    path.read_text()
                    for component in components
                    for path in sorted(
                        directory.glob("components/" + component + "/manifests/*.yaml")
                    )
                ),
            )
        )
    )


class GeneratorTests(unittest.TestCase):
    """The renamed product differs from the demo only in declarations."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.target = Path(directory.name) / "renamed"
        with contextlib.redirect_stdout(io.StringIO()):
            renamed_product.generate(ROOT, self.target)

    def test_catalog_and_components_use_only_new_ids(self):
        descriptors = catalog.source_descriptors(self.target)
        self.assertEqual(
            list(descriptors),
            ["gateway", "login-service", "orders", "inventory", "manual"],
        )
        self.assertEqual(tuple(descriptors), RENAMED_ORDER)
        for old, new in renamed_product.NAMES.items():
            self.assertEqual(
                (self.target / "components" / new / "VERSION").read_bytes(),
                (ROOT / "components" / old / "VERSION").read_bytes(),
            )
        self.assertEqual(descriptors["orders"]["clients"], "login-service")
        self.assertEqual(
            descriptors["gateway"]["accepts"], {"routes": "gateway-routes"}
        )
        self.assertEqual(
            sorted(path.name for path in (self.target / "components").iterdir()),
            ["gateway", "inventory", "login-service", "manual", "orders"],
        )
        names = set()
        for path in self.target.glob("components/*/manifests/*.yaml"):
            for document in yaml.safe_load_all(path.read_text()):
                resource_names(document, names)
        self.assertTrue(names)
        self.assertFalse([name for name in names if OLD_PREFIX.match(str(name))])

    def test_images_and_generic_files_are_unchanged(self):
        self.assertEqual(images(self.target), images(ROOT, renamed_product.NAMES))
        for name in ("deployment", "dev", "scripts", "quadlet", "apps"):
            comparison = filecmp.dircmp(
                str(ROOT / name), str(self.target / name), ignore=["__pycache__"]
            )
            self.assertFalse(comparison.diff_files, name)
            self.assertFalse(comparison.left_only, name)
        for name in ("bundle.py", "deploy.sh", "build-bundle.sh"):
            self.assertEqual(
                (ROOT / name).read_bytes(), (self.target / name).read_bytes()
            )

    def test_application_identity_and_paths_are_runtime_settings(self):
        client = yaml.safe_load(
            (self.target / "components/orders/client.yaml").read_text()
        )
        self.assertEqual(client["id"], "orders-web")
        self.assertEqual(client["base_path"], "/orders")
        self.assertEqual(client["scopes"], ["openid", "profile", "orders-web"])
        stock = yaml.safe_load(
            (self.target / "components/inventory/client.yaml").read_text()
        )
        self.assertEqual((stock["id"], stock["base_path"]), ("inventory", "/stock"))
        manifest = self.target / "components/orders/manifests/60-todo.yaml"
        pod = next(yaml.safe_load_all(manifest.read_text()))
        # The app reads them from client.yaml through ENVIRONMENT.
        backend = yaml.safe_load(
            (self.target / "components/orders/config.defaults.yaml").read_text()
        )["ENVIRONMENT"]["backend"]
        self.assertEqual(
            (backend["APP_ID"], backend["BASE_PATH"]),
            ("@@CLIENT_ID@@", "@@CLIENT_BASE_PATH@@"),
        )
        self.assertEqual(pod["spec"]["initContainers"][0]["name"], "prepare-database")
        route = (self.target / "components/inventory/route.conf").read_text()
        self.assertIn("location /stock/api/", route)
        self.assertIn("set $inventory_backend inventory-todo:8000;", route)
        self.assertNotIn("app2", route)
        self.assertIn(
            "set $login_service_upstream login-service-server:8080;",
            (self.target / "components/login-service/route.conf").read_text(),
        )
        defaults = yaml.safe_load(
            (self.target / "components/orders/config.defaults.yaml").read_text()
        )
        self.assertEqual(defaults["DB_HOST"], "orders-postgres")
        self.assertIn("orders-database-password", defaults["SECRET_FILES"])
        self.assertFalse((self.target / "components/orders/config.dev.yaml").exists())
        self.assertEqual(
            defaults["VOLUME_FILES"]["orders-seed"],
            [{"component_file": "sql/010-reference.sql"}],
        )
        self.assertEqual(
            (
                self.target / "components/orders/files/sql/010-reference.sql"
            ).read_bytes(),
            (ROOT / "components/app1/files/sql/010-reference.sql").read_bytes(),
        )
        self.assertFalse(
            (self.target / "components/inventory/config.dev.yaml").exists()
        )

    @unittest.skipUnless(shutil.which("git"), "Git is required")
    def test_untracked_local_files_are_never_copied(self):
        """Local dev config and credentials stay out of the generated tree."""
        source = self.target.parent / "source"
        (source / "config").mkdir(parents=True)
        (source / "config/common.defaults.yaml").write_text("{}\n")
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add", "-A"], check=True)
        (source / "config/dev.yaml").write_text("SECRET_FILES: {platform-x: []}\n")
        (source / "credentials").mkdir()
        (source / "credentials/key").write_text("private")
        target = self.target.parent / "copy"
        renamed_product.copy_tracked_files(source, target)
        self.assertEqual(
            sorted(str(path.relative_to(target)) for path in target.rglob("*")),
            ["config", "config/common.defaults.yaml"],
        )

    def test_platform_group_inventory_survives_renamed_generation(self):
        def inventory(directory):
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(directory / "tests/run.py"),
                    "platform",
                    "--list",
                ],
                cwd=str(directory),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.splitlines()

        expected = inventory(ROOT)
        self.assertTrue(expected)
        self.assertEqual(expected, inventory(self.target))

    def test_inventory_drop_action_removes_derived_route_and_client(self):
        """The lab action edits the generated tree; only the build is stubbed."""
        build = self.target / "build-bundle.sh"
        build.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nmkdir -p dist && cd dist\n"
            'name="shop-$1-$(cat ../components/$1/VERSION)-offline.tar.gz"\n'
            'touch "$name" && sha256sum "$name" > "$name.sha256"\n'
        )
        before = catalog.source_descriptors(self.target)["inventory"]
        self.assertEqual(
            (before["routes"], before["clients"]), ("gateway", "login-service")
        )
        result = subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail\n"
                + shell_code(REMOTE, action="renamed-inventory-drop"),
            ],
            env=dict(os.environ, renamed=str(self.target), product_name="shop"),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = catalog.source_descriptors(self.target)
        major, minor, patch = before["version"].split(".")
        version = ".".join((major, minor, str(int(patch) + 1)))
        self.assertEqual(
            result.stdout, "shop-inventory-" + version + "-offline.tar.gz\n"
        )
        self.assertEqual(after["inventory"]["version"], version)
        self.assertEqual(
            (after["inventory"]["routes"], after["inventory"]["clients"]), (None, None)
        )
        self.assertNotIn("login-service", after["inventory"]["requires"])
        self.assertEqual(after["orders"]["clients"], "login-service")

    def test_existing_target_is_never_overwritten(self):
        with self.assertRaisesRegex(SystemExit, "already exists"):
            renamed_product.generate(ROOT, self.target)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
    def test_generated_tree_prepares_with_moved_demo_credentials(self):
        """Run the real prepare in the generated tree with Podman reporting no volumes."""
        work = self.target.parent
        shim = work / "bin"
        shim.mkdir()
        (shim / "podman").write_text("#!/bin/sh\nexit 1\n")
        (shim / "podman").chmod(0o755)
        env = dict(os.environ, PATH=str(shim) + os.pathsep + os.environ["PATH"])
        dev = self.target / "build/dev"

        def run(*args):
            result = subprocess.run(
                list(args),
                cwd=str(self.target),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        tool = str(self.target / "acceptance/renamed_product.py")
        run(sys.executable, "-B", tool, "credentials", str(dev), "myproduct-proxy")
        key = dev / "orders/credentials/todo/todo-client.key"
        before = key.read_bytes()
        run(
            sys.executable,
            "-B",
            tool,
            "credentials",
            str(dev),
            "myproduct-proxy",
            "orders",
        )
        self.assertEqual(key.read_bytes(), before)
        for name in ("platform", "identity", "app1", "app2", "help"):
            self.assertFalse((dev / name).exists(), name)
        run("./deploy.sh", "prepare")
        documents = list(
            yaml.safe_load_all((self.target / "build/install.yaml").read_text())
        )
        pods = sorted(
            doc["metadata"]["name"] for doc in documents if doc["kind"] == "Pod"
        )
        self.assertEqual(
            pods,
            [
                "gateway-proxy",
                "inventory-postgres",
                "inventory-todo",
                "login-service-postgres",
                "login-service-server",
                "manual-web",
                "orders-postgres",
                "orders-todo",
            ],
        )
        registration = json.loads((dev / "clients/orders/client.json").read_text())
        self.assertEqual(registration["Id"], "orders-web")
        self.assertEqual(
            sorted(path.name for path in (dev / "routes").iterdir()),
            ["inventory.conf", "login-service.conf", "manual.conf", "orders.conf"],
        )
        # Only gateway's defaults hold the public settings; dev gives every
        # other component gateway's values.
        sources = self.target / "components"
        gateway = yaml.safe_load((dev / "gateway/config.yaml").read_text())
        for name in ("login-service", "orders", "inventory", "manual"):
            defaults = sources / name / "config.defaults.yaml"
            if defaults.exists():
                self.assertNotIn("PUBLIC_ORIGIN", yaml.safe_load(defaults.read_text()))
            config = yaml.safe_load((dev / name / "config.yaml").read_text())
            self.assertEqual(config["PUBLIC_ORIGIN"], gateway["PUBLIC_ORIGIN"], name)


class RemoteActionTests(unittest.TestCase):
    def test_target_credential_mapping_matches_the_generator(self):
        code = shell_code(REMOTE, function="demo_credentials")
        mapping = dict(
            re.findall(r"^\s*([a-z0-9-]+)\) demo=([a-z0-9]+);;", code, re.MULTILINE)
        )
        self.assertEqual(
            mapping, {new: old for old, new in renamed_product.NAMES.items()}
        )

    def test_demo_credentials_run_the_script_from_stdin(self):
        """Product bundles lack the demo script; the target runs the copied one on stdin."""
        code = shell_code(REMOTE, function="demo_credentials")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, base = root / "state", root / "base"
            state.mkdir(mode=0o700)
            base.mkdir()
            shutil.copy2(ROOT / "dev/generate-certificates.sh", base)
            script = (
                "set -euo pipefail\n"
                f"state={shlex.quote(str(state))}\nbase={shlex.quote(str(base))}\n"
                "prod_host=proxy.test\n"
                'as_product() { (cd "$state" && "$@"); }\n'
                'sudo() { shift; "$@"; }\n'
                + code
                + "demo_credentials identity\ndemo_credentials gateway\n"
            )
            result = subprocess.run(
                ["bash", "-c", script],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((state / "PKI/private/ca.crt").is_file())
            self.assertTrue(
                (state / "identity/credentials/identity/identity.crt").is_file()
            )
            # gateway reuses the platform recipe, then the result is moved.
            self.assertTrue((state / "gateway/credentials/web/web.crt").is_file())
            self.assertFalse((state / "platform").exists())

    def test_unit_tests_run_without_the_lab_signing_key(self):
        """DEV exports the lab key for builds; product tests must not inherit it."""
        self.assertIn(
            'unit) cd "$src"; env -u BUNDLE_SIGNING_KEY -u GNUPGHOME python3 -B '
            "tests/run.py all;;",
            REMOTE,
        )

    def test_bundle_argument_accepts_any_component_id_only(self):
        self.assertIn(
            "[[ $bundle =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || exit 2", REMOTE
        )
        for action in (
            "renamed-generate",
            "renamed-dev-up",
            "renamed-dev-e2e",
            "renamed-dev-down",
            "renamed-bundle",
            "renamed-init-check",
            "renamed-remove-manual",
            "renamed-uninstall",
        ):
            shell_code(REMOTE, action=action)
        generate = shell_code(REMOTE, action="renamed-generate")
        self.assertIn('diff -r -x __pycache__ "$src/$path" "$renamed/$path"', generate)
        uninstall = shell_code(REMOTE, action="renamed-uninstall")
        self.assertIn('test "$http" = 404', uninstall)
        self.assertIn('sudo -n test -d "$state/clients/orders"', uninstall)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(runner, "RUNS", root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = runner.Run("renamed", "not-used")
        self.harness.renamed_product = True
        self.harness.meta.update(
            version="0.4.9", platform_version="0.4.7", identity_version="0.4.7"
        )
        for name in ("readiness", "reset", "source", "credentials"):
            setattr(self.harness, name, mock.Mock())
        self.calls = []

        def guest(role, action, *args, **kwargs):
            self.calls.append((role, action, kwargs.get("bundle")))
            if action == "renamed-bundle-list":
                return "".join(
                    "shop-" + name + "-0.4.9-offline.tar.gz\n" for name in RENAMED_ORDER
                )
            if action == "renamed-inventory-drop":
                return "shop-inventory-0.4.10-offline.tar.gz\n"
            return ""

        self.harness.guest = mock.Mock(side_effect=guest)
        self.harness.transfer = mock.Mock()

    def steps(self):
        return [
            json.loads(line)["step"]
            for line in (self.harness.folder / "record.jsonl").read_text().splitlines()
        ]

    def test_renamed_flow_runs_dev_bundle_offline_install_and_scoped_uninstall(self):
        self.harness.execute()
        self.assertTrue(self.harness.finished)
        installs = [bundle for _, action, bundle in self.calls if action == "install"]
        self.assertEqual(installs, list(RENAMED_ORDER) + ["orders", "inventory"])
        self.assertEqual(
            [call.kwargs for call in self.harness.transfer.call_args_list],
            [{"bundle": name, "tree": "renamed"} for name in RENAMED_ORDER]
            + [{"version": "0.4.10", "bundle": "inventory", "tree": "renamed"}],
        )
        self.harness.credentials.assert_called_once_with("login-service")
        actions = [action for _, action, _ in self.calls]
        for earlier, later in (
            ("renamed-generate", "renamed-dev-up"),
            ("renamed-dev-down", "renamed-bundle"),
            ("renamed-markers-create", "restart"),
            ("restart", "renamed-markers-check"),
            ("renamed-inventory-drop", "renamed-registrations-removed"),
            ("renamed-registrations-removed", "renamed-uninstall"),
        ):
            self.assertLess(actions.index(earlier), actions.index(later))
        self.assertIn(("PROD", "renamed-uninstall", "inventory"), self.calls)
        # manual leaves the source product after bundling; prod uninstalls it last.
        self.assertLess(
            actions.index("renamed-bundle"), actions.index("renamed-remove-manual")
        )
        self.assertLess(
            actions.index("renamed-remove-manual"), actions.index("install")
        )
        self.assertEqual(self.calls[-3], ("PROD", "renamed-uninstall", "manual"))
        # Backlog 64: the login home still holds only the bootstrap file.
        self.assertEqual(self.calls[-1], ("PROD", "home-unchanged", None))
        # No demo-specific production checks run in this scenario.
        for demo in ("check", "prod-e2e", "uninstall", "dev-up", "bundle"):
            self.assertNotIn(demo, actions)
        self.assertIn("10-survivor", self.steps())
        self.assertIn("10-survivor-after-removal", self.steps())
        self.assertEqual(self.harness.meta["inventory_without_registrations"], "0.4.10")

    def test_inventory_without_registrations_must_be_newer(self):
        def guest(role, action, *args, **kwargs):
            self.calls.append((role, action, kwargs.get("bundle")))
            if action in ("renamed-bundle-list", "renamed-inventory-drop"):
                return "shop-inventory-0.4.9-offline.tar.gz\n"
            return ""

        self.harness.guest = mock.Mock(side_effect=guest)
        with self.assertRaisesRegex(
            RuntimeError, "STOP at 10-inventory-drop-registrations"
        ):
            self.harness.execute()
        self.assertFalse(self.harness.report())

    def test_failure_stops_the_renamed_flow_and_is_not_clean(self):
        def guest(role, action, *args, **kwargs):
            self.calls.append((role, action, kwargs.get("bundle")))
            if action == "renamed-dev-e2e":
                raise RuntimeError("smoke failed")

        self.harness.guest = mock.Mock(side_effect=guest)
        with self.assertRaisesRegex(RuntimeError, "STOP at 03-renamed-dev-e2e"):
            self.harness.execute()
        self.assertEqual(self.calls[-1][1], "renamed-dev-e2e")
        self.harness.transfer.assert_not_called()
        self.assertFalse(self.harness.report())

    def test_bundle_versions_come_from_the_build_listing_in_order(self):
        listing = (
            "+ podman save ...\n"
            "myproduct-gateway-0.4.9-offline.tar.gz\n"
            "myproduct-login-service-0.4.8-offline.tar.gz\n"
            "myproduct-orders-1.2.3-offline.tar.gz\n"
        )
        self.assertEqual(
            list(runner.bundle_versions(listing).items()),
            [("gateway", "0.4.9"), ("login-service", "0.4.8"), ("orders", "1.2.3")],
        )
        with self.assertRaisesRegex(RuntimeError, "No bundles listed"):
            runner.bundle_versions("build failed\n")
        # The renamed product's archives carry its own product name.
        self.assertEqual(
            runner.bundle_versions("shop-orders-1.2.3-offline.tar.gz\n", "shop"),
            {"orders": "1.2.3"},
        )
        with self.assertRaisesRegex(RuntimeError, "No bundles listed"):
            runner.bundle_versions("myproduct-orders-1.2.3-offline.tar.gz\n", "shop")

    def test_renamed_scenario_runs_under_the_generated_product_name(self):
        """The harness and the generator name the same product and service user."""
        self.assertEqual(runner.RENAMED_PRODUCT, renamed_product.PRODUCT)
        self.assertEqual(
            renamed_product.rename_catalog(
                {
                    "gateway": "platform",
                    "identity": "identity",
                    "components": {"app1": {}},
                }
            )["product"],
            runner.RENAMED_PRODUCT,
        )
        harness = runner.Run("product-name", "not-used")
        self.assertEqual(harness.product, "myproduct")
        harness.renamed_product = True
        self.assertEqual(harness.product, "shop")

    def test_transfer_reads_the_renamed_tree_and_version_keys(self):
        harness = runner.Run("transfer", "not-used")
        harness.renamed_product = True
        harness.meta.update(
            platform_version="0.4.7", identity_version="0.4.7", version="0.4.9"
        )
        harness.command = mock.Mock()
        harness.ssh = mock.Mock()
        harness.host = lambda role: role.lower()
        harness.guest = mock.Mock()
        archive = harness.folder / "shop-gateway-0.4.7-offline.tar.gz"
        archive.write_bytes(b"archive")
        harness.meta["bundles_built"] = runner.bundle_versions(
            "build noise\nshop-gateway-0.4.7-offline.tar.gz\n", "shop"
        )
        harness.transfer(bundle="gateway", tree="renamed")
        sources = [call.args[0][-2] for call in harness.command.call_args_list]
        # Demo provisioning travels separately; product bundles do not carry it.
        self.assertTrue(sources[0].endswith("/dev/generate-certificates.sh"))
        # PROD's fapolicyd denies opening untrusted Python files: the probe
        # travels compressed and no .py file is written to PROD.
        self.assertEqual(sources[1].name, "prepare_host_test.py.gz")
        self.assertEqual(
            gzip.decompress(sources[1].read_bytes()),
            (runner.ROOT / "acceptance/prepare_host_test.py").read_bytes(),
        )
        targets = [str(call.args[0][-1]) for call in harness.command.call_args_list]
        self.assertEqual([t for t in targets if t.endswith(".py")], [])
        self.assertTrue(
            sources[2].endswith("/renamed/dist/shop-gateway-0.4.7-offline.tar.gz")
        )
        harness.guest.assert_called_once_with(
            "PROD", "publish-release", "0.4.7", bundle="gateway"
        )


if __name__ == "__main__":
    unittest.main()
