"""Build real bundle archives with only the Podman subprocess stubbed."""

import hashlib
import subprocess
import tarfile
import unittest
from pathlib import Path
from unittest import mock

import bundle
import yaml

from helpers.bundle_fixture import BundleFixture


class BundleTests(BundleFixture):
    def test_host_preparation_ships_real_helper_with_checksum(self):
        source = Path(__file__).resolve().parents[2] / "scripts"
        for name in ("prepare-host.sh",):
            (bundle.ROOT / "scripts" / name).write_bytes((source / name).read_bytes())
        bundle.build()
        with tarfile.open(
            str(bundle.DIST / "myproduct-1.2.3-offline.tar.gz")
        ) as archive:
            checksums = self.archive_bytes(archive, "checksums.sha256").decode()
            for name in ("prepare-host.sh",):
                contents = self.archive_bytes(archive, "scripts/" + name)
                self.assertEqual(contents, (source / name).read_bytes())
                self.assertIn(
                    hashlib.sha256(contents).hexdigest() + "  scripts/" + name,
                    checksums,
                )

    def test_build_contents_modes_ownership_and_all_checksums(self):
        bundle.build()
        path = bundle.DIST / "myproduct-1.2.3-offline.tar.gz"
        self.assertTrue(path.exists())
        self.assertEqual(
            self.process.call_args_list,
            [
                mock.call(
                    [
                        "podman",
                        "save",
                        "-m",
                        "-o",
                        str(bundle.STAGE / "myproduct-1.2.3/images/images.tar"),
                        "localhost/app:1",
                        "localhost/init:1",
                    ],
                    check=True,
                ),
            ],
        )
        with tarfile.open(str(path)) as archive:
            prefix = "myproduct-1.2.3/"
            regular = {
                m.name[len(prefix) :] for m in archive.getmembers() if m.isfile()
            }
            self.assertFalse(
                any(
                    member.name.startswith(prefix + "dev/")
                    for member in archive.getmembers()
                )
            )
            self.assertEqual(
                regular,
                {
                    "VERSION",
                    "deploy.sh",
                    "deployment/__init__.py",
                    "deployment/__main__.py",
                    "README.md",
                    "config.defaults.yaml",
                    "scripts/prepare-host.sh",
                    "quadlet/template.kube",
                    "quadlet/template.network",
                    "images/images.tar",
                    "images/images.txt",
                    "manifests/app.yaml",
                    "checksums.sha256",
                },
            )
            self.assertEqual(
                self.archive_bytes(archive, "images/images.txt"),
                b"localhost/app:1\nlocalhost/init:1\n",
            )
            for member in archive.getmembers():
                self.assertEqual(
                    (member.uid, member.gid, member.uname, member.gname),
                    (0, 0, "root", "root"),
                )
            for name in ("deploy.sh", "scripts/prepare-host.sh"):
                self.assertEqual(archive.getmember(prefix + name).mode, 0o755)
            self.assertEqual(archive.getmember(prefix + "credentials").mode, 0o700)
            self.assertTrue(archive.getmember(prefix + "build").isdir())
            seen = set()
            for line in (
                self.archive_bytes(archive, "checksums.sha256")
                .decode("utf-8")
                .splitlines()
            ):
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    hashlib.sha256(self.archive_bytes(archive, name)).hexdigest(),
                    digest,
                )
                seen.add(name)
            self.assertEqual(seen, regular - {"checksums.sha256"})
        digest, filename = (
            Path(str(path) + ".sha256").read_text().strip().split("  ", 1)
        )
        self.assertEqual(filename, path.name)
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_real_package_and_nested_files_ship_without_bytecode_or_old_module(self):
        source = Path(__file__).resolve().parents[2] / "deployment"
        for path in source.glob("*.py"):
            self.write("deployment/" + path.name, path.read_text())
        self.write("deployment/__pycache__/cached.cpython-312.pyc", "bytecode excluded")
        self.write("deployment/stray.pyo", "bytecode excluded")
        bundle.build()
        with tarfile.open(
            str(bundle.DIST / "myproduct-1.2.3-offline.tar.gz")
        ) as archive:
            names = {member.name for member in archive.getmembers()}
            for path in source.glob("*.py"):
                self.assertIn("myproduct-1.2.3/deployment/" + path.name, names)
            self.assertNotIn("myproduct-1.2.3/deploy.py", names)
            self.assertFalse(
                any(
                    "__pycache__" in name or name.endswith((".pyc", ".pyo"))
                    for name in names
                )
            )

    def test_package_symlink_cannot_bundle_declared_private_state(self):
        self.write(
            "config.yaml",
            "SECRET_FILES:\n  generated-files:\n  - path: private\n    generate:\n    - token\n",
        )
        private = self.write("private/token", "private-fixture")
        (self.root / "deployment/alias.py").symlink_to(private)
        with self.assertRaisesRegex(bundle.BundleError, "generated secret"):
            bundle.build()
        self.process.assert_not_called()

    def test_external_secret_source_and_directory_alias_are_private_without_generation(
        self,
    ):
        private = self.write("outside-credentials/key", "private-fixture")
        self.write("files/public", "public-fixture")
        alias = self.root / "files/alias"
        for source in (private, private.parent):
            self.write(
                "config.yaml",
                yaml.safe_dump({"SECRET_FILES": {"private": [{"path": str(source)}]}}),
            )
            alias.symlink_to(source, target_is_directory=source.is_dir())
            with self.assertRaisesRegex(bundle.BundleError, "secret"):
                bundle.build()
            self.process.assert_not_called()
            alias.unlink()

    def test_generated_volume_file_alias_stays_out_of_offline_archive(self):
        self.write(
            "config.yaml",
            yaml.safe_dump(
                {
                    "VOLUME_FILES": {
                        "private": [{"path": "private", "generate": ["key"]}]
                    }
                }
            ),
        )
        private = self.write("private/key", "private-fixture")
        self.write("files/public", "public-fixture")
        (self.root / "files/alias").symlink_to(private)
        with self.assertRaisesRegex(bundle.BundleError, "secret"):
            bundle.build()
        self.process.assert_not_called()

    def test_optional_files_tree_is_included(self):
        self.write("files/templates/nested/example.txt", "example\n")
        bundle.build()
        with tarfile.open(
            str(bundle.DIST / "myproduct-1.2.3-offline.tar.gz")
        ) as archive:
            self.assertEqual(
                self.archive_bytes(archive, "files/templates/nested/example.txt"),
                b"example\n",
            )
            self.assertIn(
                b"files/templates/nested/example.txt",
                self.archive_bytes(archive, "checksums.sha256"),
            )

    def test_generated_secret_under_shipped_files_is_rejected(self):
        """Refuse a bundle that would copy a declared generated secret."""
        for config in ("config.yaml", "config.defaults.yaml"):
            with self.subTest(config=config):
                self.write(
                    config,
                    "SECRET_FILES:\n  generated-files:\n  - path: files/private\n    generate:\n    - token\n",
                )
                self.write("files/private/token", "synthetic-private-value")
                with self.assertRaisesRegex(bundle.BundleError, "generated secret"):
                    bundle.build()
                self.process.assert_not_called()
                self.assertFalse(bundle.DIST.exists())
                (self.root / config).unlink()

    def test_shipped_symlink_cannot_copy_a_generated_secret(self):
        """Reject a files alias pointing at a private generated file or directory."""
        self.write(
            "config.yaml",
            "SECRET_FILES:\n  generated-files:\n  - path: private\n    generate:\n    - token\n",
        )
        secret = self.write("private/token", "synthetic-private-value")
        (self.root / "files").mkdir()
        for target in (secret, secret.parent):
            with self.subTest(target=target.name):
                alias = self.root / "files/alias"
                alias.symlink_to(target, target_is_directory=target.is_dir())
                with self.assertRaisesRegex(bundle.BundleError, "generated secret"):
                    bundle.build()
                self.process.assert_not_called()
                self.assertFalse(bundle.DIST.exists())
                alias.unlink()

    def test_private_credentials_and_symlink_aliases_cannot_enter_archives(self):
        """Externally delivered keys are private without any generation declaration."""
        component = self.root / "components/app1"
        for base in (
            "credentials",
            "components/app1/credentials",
            "build/dev/app1/credentials",
        ):
            key = self.write(
                base + "/todo/client.key", "externally-delivered-private-key"
            )
            guard = bundle.generated_secret_guard([self.root, component])
            for source in (key, key.parent, key.parent.parent):
                with self.subTest(base=base, source=source.name):
                    with self.assertRaisesRegex(bundle.BundleError, "credentials"):
                        guard(source.parent, [source.name])
                    alias = self.root / "files/alias"
                    alias.parent.mkdir(exist_ok=True)
                    alias.symlink_to(source, target_is_directory=source.is_dir())
                    with self.assertRaisesRegex(bundle.BundleError, "credentials"):
                        guard(alias.parent, [alias.name])
                    alias.unlink()
        alias = self.root / "files/alias"
        alias.symlink_to(key.parent, target_is_directory=True)
        with self.assertRaisesRegex(bundle.BundleError, "credentials"):
            bundle.build()
        self.assertFalse(bundle.DIST.exists())
        self.process.assert_not_called()

    def test_multiple_files_documents_flow_maps_and_init_containers(self):
        self.write(
            "manifests/second.yaml",
            """# Empty document
---
kind: Pod
spec:
  containers: [{image: 'registry.firma.no/team/app:1'}]
  initContainers: [{image: 'localhost/init:1'}]
---
kind: Pod
spec:
  containers:
  - image: "localhost/app:1" # duplicate
    imagePullPolicy: Never
---
kind: ConfigMap
data: {image: ignored}
""",
        )
        self.assertEqual(
            bundle.manifest_images(),
            [
                "localhost/app:1",
                "localhost/init:1",
                "registry.firma.no/team/app:1",
            ],
        )

    def test_unsupported_kinds_fail_before_podman_or_stage_changes(self):
        """A Deployment or List would bypass lifecycle checks; refuse it at build."""
        old = self.write("build/bundle/keep", "previous build")
        for kind in ("Deployment", "List", None):
            with self.subTest(kind=kind):
                self.write(
                    "manifests/bad.yaml",
                    yaml.safe_dump(
                        {
                            "kind": kind,
                            "spec": {
                                "template": {
                                    "spec": {"containers": [{"image": "localhost/a:1"}]}
                                }
                            },
                        }
                    ),
                )
                with self.assertRaisesRegex(
                    bundle.BundleError, "bad.yaml: unsupported resource kind"
                ):
                    bundle.build()
        self.assertEqual(old.read_text(), "previous build")
        self.process.assert_not_called()
        self.assertFalse(bundle.DIST.exists())

    def test_invalid_image_fails_before_stage_is_removed_or_podman_runs(self):
        old = self.write("build/bundle/keep", "previous build")
        self.write(
            "manifests/bad.yaml",
            "kind: Pod\nspec:\n  initContainers:\n  - image: team/app:1\n",
        )
        with self.assertRaisesRegex(bundle.BundleError, "team/app:1.*fully qualified"):
            bundle.build()
        self.assertEqual(old.read_text(), "previous build")
        self.process.assert_not_called()
        self.assertFalse(bundle.DIST.exists())

    def test_image_validation_errors_are_bundle_errors(self):
        for image in (
            "postgres:16",
            "team/app:1",
            "@@IMAGE@@",
            "localhost/app:@@TAG@@",
            None,
        ):
            with self.subTest(image=image):
                self.write(
                    "manifests/app.yaml",
                    yaml.safe_dump(
                        {"kind": "Pod", "spec": {"containers": [{"image": image}]}}
                    ),
                )
                with self.assertRaises(bundle.BundleError):
                    bundle.manifest_images()
                self.assertEqual(bundle.main([]), 1)
                self.assertIn("ERROR:", self.errors.getvalue())
                self.assertNotIn("Traceback", self.errors.getvalue())
        self.process.assert_not_called()

    def test_no_images_or_no_manifests(self):
        manifest = self.write("manifests/app.yaml", "---\nkind: ConfigMap\n")
        with self.assertRaisesRegex(bundle.BundleError, "No images"):
            bundle.build()
        manifest.unlink()
        with self.assertRaisesRegex(bundle.BundleError, "No images"):
            bundle.build()
        self.process.assert_not_called()

    def test_invalid_yaml_returns_error_without_podman(self):
        self.write("manifests/app.yaml", "spec: [")
        self.assertEqual(bundle.main([]), 1)
        self.assertIn("ERROR:", self.errors.getvalue())
        self.assertNotIn("Traceback", self.errors.getvalue())
        self.process.assert_not_called()

    def test_duplicate_manifest_keys_fail_before_build(self):
        self.write(
            "manifests/app.yaml",
            "spec:\n  containers:\n  - image: localhost/first:1\n"
            "    image: localhost/second:1\n",
        )
        self.assertEqual(bundle.main([]), 1)
        self.assertIn("line 4", self.errors.getvalue())
        self.assertNotIn("Traceback", self.errors.getvalue())
        self.process.assert_not_called()
        self.assertFalse(bundle.STAGE.exists())

    def test_failed_save_returns_one_without_final_bundle(self):
        self.process.side_effect = subprocess.CalledProcessError(1, "podman save")
        self.assertEqual(bundle.main([]), 1)
        self.assertIn("ERROR:", self.errors.getvalue())
        self.assertFalse(bundle.DIST.exists())

    def test_main_success(self):
        self.assertEqual(bundle.main([]), 0)

    def test_registry_pulls_are_sorted_and_localhost_names_are_preserved(self):
        """Pull each remote name once, including localhost:port, and never build."""
        bundle.pull_images(
            [
                "registry.example.test/team/app:1",
                "localhost/app:1",
                "localhost:5000/test:2",
                "registry.example.test/team/app:1",
            ]
        )
        self.assertEqual(
            self.process.call_args_list,
            [
                mock.call(
                    ["podman", "pull", "--policy=always", image],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for image in (
                    "localhost:5000/test:2",
                    "registry.example.test/team/app:1",
                )
            ],
        )

    def test_registry_pull_precedes_save_and_archive_checksums_verify(self):
        """Bundle a registry image with its exact full name after a successful pull."""
        self.write(
            "manifests/remote.yaml",
            "kind: Pod\nspec: {containers: [{image: 'registry.example.test/app:2'}]}\n",
        )
        bundle.build()
        self.assertEqual(
            self.process.call_args_list[0][0][0],
            [
                "podman",
                "pull",
                "--policy=always",
                "registry.example.test/app:2",
            ],
        )
        self.assertEqual(
            self.process.call_args_list[1][0][0][-3:],
            [
                "localhost/app:1",
                "localhost/init:1",
                "registry.example.test/app:2",
            ],
        )
        with tarfile.open(
            str(bundle.DIST / "myproduct-1.2.3-offline.tar.gz")
        ) as archive:
            self.assertIn(
                b"registry.example.test/app:2\n",
                self.archive_bytes(archive, "images/images.txt"),
            )
            self.assertIn(
                b"registry.example.test/app:2",
                self.archive_bytes(archive, "images/images.tar"),
            )
            for line in (
                self.archive_bytes(archive, "checksums.sha256")
                .decode("utf-8")
                .splitlines()
            ):
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    hashlib.sha256(self.archive_bytes(archive, name)).hexdigest(),
                    digest,
                )

    def test_failed_pull_reports_only_image_and_login_hint_without_save_or_build(self):
        """Suppress registry diagnostic credentials and refuse cached/build fallback."""
        self.write(
            "manifests/remote.yaml",
            "kind: Pod\nspec: {containers: [{image: 'registry.example.test/app:2'}]}\n",
        )
        self.process.side_effect = subprocess.CalledProcessError(
            125,
            "podman pull",
            output=b"private-auth-token",
            stderr=b"private-auth-token",
        )
        self.assertEqual(bundle.main([]), 1)
        self.process.assert_called_once()
        self.assertIn("registry.example.test/app:2", self.errors.getvalue())
        self.assertIn("podman login registry.example.test", self.errors.getvalue())
        self.assertEqual(len(self.errors.getvalue().splitlines()), 1)
        self.assertNotIn(
            "private-auth-token", self.errors.getvalue() + self.output.getvalue()
        )
        self.assertFalse(bundle.DIST.exists())

    def test_component_default_and_dev_generated_paths_guard_materialized_aliases(self):
        """Reject symlink copies of generated dev secrets declared by every new source."""
        component = self.root / "components/app1"
        for source in (
            "config/common.defaults.yaml",
            "components/app1/config.defaults.yaml",
            "components/app1/config.yaml",
            "config/dev.yaml",
            "components/app1/config.dev.yaml",
            "build/dev/app1/config.yaml",
        ):
            with self.subTest(source=source):
                path = self.write(
                    source,
                    "SECRET_FILES:\n  generated-files:\n  - path: private\n    generate:\n    - token\n",
                )
                secret_base = (
                    "components/app1"
                    if source == "components/app1/config.yaml"
                    else "build/dev/app1"
                )
                secret = self.write(
                    secret_base + "/private/token", "private-generated-value"
                )
                alias = self.root / "files/alias"
                alias.parent.mkdir(exist_ok=True)
                alias.symlink_to(secret)
                guard = bundle.generated_secret_guard([self.root, component])
                with self.assertRaisesRegex(bundle.BundleError, "generated secret"):
                    guard(alias.parent, [alias.name])
                alias.unlink()
                path.unlink()
        self.process.assert_not_called()

    def test_component_bundles_include_only_selected_components_and_images(self):
        """Build three independent archives with matching platform versions and no local state."""
        self.write_component_catalog()
        bundle.build()
        for name, components in (
            ("platform", ("platform",)),
            ("identity", ("identity",)),
            ("app1", ("app1",)),
            ("app2", ("app2",)),
            ("help", ("help",)),
        ):
            with tarfile.open(
                str(
                    bundle.DIST
                    / (
                        "myproduct-"
                        + name
                        + "-"
                        + (
                            {"platform": "1.0.0", "identity": "1.1.0"}.get(
                                name, "1.2.3"
                            )
                        )
                        + "-offline.tar.gz"
                    )
                )
            ) as archive:
                prefix = (
                    "myproduct-"
                    + name
                    + "-"
                    + ({"platform": "1.0.0", "identity": "1.1.0"}.get(name, "1.2.3"))
                    + "/"
                )
                members = {
                    member.name[len(prefix) :] for member in archive.getmembers()
                }
                stream = archive.extractfile(prefix + "images/images.txt")
                assert stream is not None
                self.assertEqual(
                    stream.read().decode().splitlines(),
                    sorted("localhost/" + component + ":1" for component in components),
                )
                for component in ("platform", "identity", "app1", "app2", "help"):
                    self.assertEqual(
                        "components/" + component + "/manifests/pod.yaml" in members,
                        component in components,
                    )
                    self.assertNotIn(
                        "components/" + component + "/config.yaml", members
                    )
                self.assertIn("config/common.defaults.yaml", members)
                self.assertNotIn("config/dev.yaml", members)
                self.assertFalse(
                    any(
                        "__pycache__" in name or name.endswith(".pyc")
                        for name in members
                    )
                )
                for component in components:
                    self.assertIn(
                        "components/" + component + "/config.defaults.yaml", members
                    )
                # The version is compiled into bundle.yaml; no version files ship.
                self.assertNotIn("components/platform/VERSION", members)
                self.assertNotIn("components/identity/VERSION", members)
                version_file = archive.extractfile(prefix + "VERSION")
                assert version_file is not None
                self.assertEqual(
                    version_file.read().decode().strip(),
                    {"platform": "1.0.0", "identity": "1.1.0"}.get(name, "1.2.3"),
                )
                descriptor_file = archive.extractfile(prefix + "bundle.yaml")
                assert descriptor_file is not None
                descriptor = yaml.safe_load(descriptor_file.read())
                self.assertEqual(descriptor["name"], name)
                self.assertEqual(
                    descriptor["version"],
                    {"platform": "1.0.0", "identity": "1.1.0"}.get(name, "1.2.3"),
                )
                # Without route or client files only the gateway is required.
                self.assertEqual(
                    descriptor["requires"],
                    {}
                    if name == "platform"
                    else {"platform": {"min": "1.0.0", "before": "2.0.0"}},
                )
                checksum = archive.extractfile(prefix + "checksums.sha256")
                assert checksum is not None
                lines = checksum.read().decode().splitlines()
                for line in lines:
                    digest, filename = line.split("  ", 1)
                    data = archive.extractfile(prefix + filename)
                    assert data is not None
                    self.assertEqual(hashlib.sha256(data.read()).hexdigest(), digest)
                self.assertEqual(
                    {line.split("  ", 1)[1] for line in lines},
                    {
                        member.name[len(prefix) :]
                        for member in archive.getmembers()
                        if member.isfile()
                        and member.name != prefix + "checksums.sha256"
                    },
                )

        self.assertEqual(
            (bundle.DIST / "current-bundles.txt").read_text().splitlines(),
            [
                "myproduct-platform-1.0.0-offline.tar.gz",
                "myproduct-identity-1.1.0-offline.tar.gz",
                "myproduct-app1-1.2.3-offline.tar.gz",
                "myproduct-app2-1.2.3-offline.tar.gz",
                "myproduct-help-1.2.3-offline.tar.gz",
            ],
        )

    def test_selected_components_build_only_those_bundles(self):
        """A partial build validates the catalog but writes only the named bundles."""
        self.write_component_catalog()
        bundle.build()
        current = (bundle.DIST / "current-bundles.txt").read_text()
        self.write("components/app1/VERSION", "1.2.4\n")
        self.process.reset_mock()
        bundle.build(["app1"])
        saved = [
            call[0][0]
            for call in self.process.call_args_list
            if call[0][0][:2] == ["podman", "save"]
        ]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][-1], "localhost/app1:1")
        self.assertTrue((bundle.DIST / "myproduct-app1-1.2.4-offline.tar.gz").is_file())
        for name in ("app2", "help"):
            self.assertFalse(
                (bundle.DIST / ("myproduct-" + name + "-1.2.4-offline.tar.gz")).exists()
            )
        # The complete product list is written only by a full build.
        self.assertEqual((bundle.DIST / "current-bundles.txt").read_text(), current)

    def test_archives_use_gzip_level_6(self):
        """Level 9 is about three times slower for under 1 % smaller archives."""
        self.write_component_catalog()
        bundle.build(["help"])
        header = (bundle.DIST / "myproduct-help-1.2.3-offline.tar.gz").read_bytes()[:10]
        # XFL is 2 for level 9, 4 for level 1 and 0 for the levels in between.
        self.assertEqual(header[:2], b"\x1f\x8b")
        self.assertEqual(header[8], 0)

    def test_unknown_selected_component_builds_nothing(self):
        self.write_component_catalog()
        with self.assertRaisesRegex(bundle.BundleError, "Unknown component reports"):
            bundle.build(["app1", "reports"])
        self.process.assert_not_called()
        self.assertFalse(bundle.DIST.exists())

    def test_sha256_reads_more_than_one_chunk(self):
        path = self.root / "large.bin"
        data = bytes(range(256)) * 8193
        path.write_bytes(data)
        self.assertEqual(bundle.sha256(path), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
