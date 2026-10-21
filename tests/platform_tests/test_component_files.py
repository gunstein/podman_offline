"""Portable public inputs in dev and relocated releases, without app sources."""

import base64
import copy
import os
import shutil
import tarfile
from pathlib import Path
from unittest import mock

import bundle
import yaml
from deployment import common, deploy, validation
from deployment import render as rendering

from helpers.product_fixture import RENAMED, ProductFixture, pod


class ComponentFileTests(ProductFixture):
    def product(self):
        self.write_product(
            {
                "processor": {
                    "catalog": {},
                    "defaults": {
                        "VOLUME_FILES": {
                            "processor-seed": [{"component_file": "sql/reference.sql"}]
                        },
                        "SECRET_FILES": {
                            "processor-public": [{"component_file": "public.pem"}]
                        },
                    },
                    "manifests": [
                        pod(
                            "processor-job",
                            "localhost/worker:1",
                            ["pvc:processor-seed", "secret:processor-public"],
                        )
                    ],
                }
            }
        )
        self.files = self.source / "components/processor/files"
        (self.files / "sql").mkdir(parents=True)
        (self.files / "sql/reference.sql").write_bytes(b"first release\n")
        (self.files / "public.pem").write_bytes(b"public binary\x00input")

    def settings(self):
        return deploy.dev_settings()[1]["processor"]

    def snapshot(self):
        return {
            str(path.relative_to(self.source)): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def test_same_logical_config_in_dev_relocated_install_and_new_release(self):
        self.product()
        config = self.settings()
        before = self.snapshot()
        with mock.patch.object(
            Path, "read_bytes", side_effect=AssertionError("validate read contents")
        ):
            validation.validate()
        self.assertEqual(self.snapshot(), before)
        self.process.assert_not_called()
        deploy.prepare()
        first = self.build_and_unpack()["processor"]
        # The new version must not overwrite existing authoritative defaults.
        defaults = yaml.safe_load(
            (self.source / "components/processor/config.defaults.yaml").read_text()
        )
        defaults["NEW_DEFAULT"] = "not-added-to-retained-config"
        (self.source / "components/processor/config.defaults.yaml").write_text(
            yaml.safe_dump(defaults)
        )
        (self.source / "components/processor/VERSION").write_text("1.0.1\n")
        (self.files / "sql/reference.sql").write_bytes(b"second release\n")
        second = self.build_and_unpack()["processor"]
        shutil.rmtree(self.source)
        relocated = self.root / "relocated"
        shutil.move(str(self.releases), str(relocated))
        first, second = relocated / first.name, relocated / second.name
        self.install(first)
        persistent = common.HOME / "processor/config.yaml"
        self.assertEqual(rendering.load_config(persistent), config)
        retained = persistent.read_bytes()
        self.assert_archive(b"first release\n")
        installed_yaml = common.QUADLET_DIR / "myproduct-processor.yaml"
        docs = list(yaml.safe_load_all(installed_yaml.read_text()))
        secret = next(doc for doc in docs if doc["kind"] == "Secret")
        self.assertEqual(
            base64.b64decode(secret["data"]["public.pem"]), b"public binary\x00input"
        )
        self.use_root(second)
        self.assertEqual(validation.validate_bundle()[1], [])
        deploy.install()
        self.assertEqual(persistent.read_bytes(), retained)
        self.assert_archive(b"second release\n")
        self.assertNotIn(str(relocated), persistent.read_text())
        self.assertFalse((second / "apps").exists())
        (second / "components/processor/files/sql/reference.sql").unlink()
        before = installed_yaml.read_bytes()
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "Missing component_file"):
            deploy.install()
        self.assertEqual(installed_yaml.read_bytes(), before)
        self.process.assert_not_called()

    def assert_archive(self, expected):
        with tarfile.open(
            str(common.HOME / "processor/files/processor-seed.tar")
        ) as archive:
            stream = archive.extractfile("reference.sql")
            assert stream is not None
            self.assertEqual(stream.read(), expected)

    def test_unsafe_declarations_fail_before_output_generation_or_host_commands(self):
        self.product()
        config_path = self.source / "components/processor/config.dev.yaml"
        invalid = [
            {"component_file": value}
            for value in (
                "",
                ".",
                "/etc/passwd",
                "../notifier/file",
                "sql/../../file",
                "~/.key",
                "missing.sql",
                17,
            )
        ] + [
            {"path": "private", "component_file": "public.pem"},
            {"component_file": "public.pem", "generate": []},
            {"component_file": "public.pem", "generate": ["password"]},
        ]
        for source in invalid:
            config_path.write_text(
                yaml.safe_dump({"VOLUME_FILES": {"processor-seed": [source]}})
            )
            before = self.snapshot()
            for action in (deploy.prepare, validation.validate):
                with self.subTest(source=source, action=action.__name__):
                    with self.assertRaises(common.DeployError):
                        action()
            self.assertEqual(self.snapshot(), before)
            self.process.assert_not_called()

    def test_symlink_ancestors_descendants_and_special_files_are_refused(self):
        self.product()
        outside = self.root / "outside"
        outside.write_text("private-external-value")
        nested = self.files / "sql/deep/nested"
        nested.mkdir(parents=True)
        entries = [nested / "link", nested / "pipe"]
        entries[0].symlink_to(outside)
        os.mkfifo(str(entries[1]))
        entry = {"component_file": "sql"}
        for path in entries:
            with self.subTest(path=path), self.assertRaises(
                common.DeployError
            ) as failure:
                rendering.resolve_file_source(entry, component="processor")
            self.assertNotIn("private-external-value", str(failure.exception))
            path.unlink()
        # Even an in-tree link is refused; the release has no mutable aliases.
        link = self.files / "alias"
        link.symlink_to(self.files / "public.pem")
        with self.assertRaisesRegex(common.DeployError, "symlink"):
            rendering.resolve_file_source(
                {"component_file": "alias"}, component="processor"
            )
        link.unlink()
        actual = self.files.with_name("actual")
        self.files.rename(actual)
        self.files.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(common.DeployError, "symlink"):
            rendering.resolve_file_source(
                {"component_file": "public.pem"}, component="processor"
            )

    def test_standalone_context_is_refused_before_generation(self):
        self.product()
        config = self.settings()
        config["SECRET_FILES"]["processor-generated"] = [
            {"path": "private", "generate": ["password"]}
        ]
        with self.assertRaisesRegex(common.DeployError, "explicit component context"):
            rendering.materialize(
                config, self.root / "config.yaml", [], self.root / "files"
            )
        self.assertFalse((self.root / "private").exists())

    def test_directory_delivery_keeps_volume_trees_and_secret_one_level_rules(self):
        self.product()
        nested = self.files / "sql/nested"
        nested.mkdir()
        (nested / "extra.sql").write_bytes(b"nested public input")
        config = {"VOLUME_FILES": {"processor-seed": [{"component_file": "sql"}]}}
        groups = rendering.load_file_group(
            config, common.VOLUME_FILES, component="processor"
        )
        rendering.write_file_archives(groups, self.root / "archives")
        with tarfile.open(str(self.root / "archives/processor-seed.tar")) as archive:
            stream = archive.extractfile("nested/extra.sql")
            assert stream is not None
            self.assertEqual(stream.read(), b"nested public input")
        config = {"SECRET_FILES": {"processor-public": [{"component_file": "sql"}]}}
        with self.assertRaisesRegex(
            common.DeployError, "Secrets can only contain files"
        ):
            rendering.check_component_file_sources(config, "processor")

    def test_public_secret_key_size_and_redaction_rules_are_preserved(self):
        self.product()
        config = self.settings()
        self.assertEqual(
            rendering.secret_keys(config, self.root / "config.yaml", [], "processor"),
            {"processor-public": {"public.pem"}},
        )
        sources = rendering.load_file_group(
            config, common.SECRET_FILES, component="processor"
        )
        with mock.patch.object(common, "MAX_SECRET_SIZE", 1), self.assertRaises(
            common.DeployError
        ) as failure:
            rendering.secret_documents(sources)
        self.assertNotIn("public binary", str(failure.exception))
        invalid = self.files / "bad name"
        invalid.write_text("do-not-print")
        config["SECRET_FILES"]["processor-public"] = [{"component_file": "bad name"}]
        with self.assertRaisesRegex(common.DeployError, "file name") as failure:
            rendering.load_file_group(
                config, common.SECRET_FILES, component="processor"
            )
        self.assertNotIn("do-not-print", str(failure.exception))
        config["SECRET_FILES"]["processor-generated"] = [
            {"path": "private", "generate": ["token"]}
        ]
        with self.assertRaisesRegex(common.DeployError, "file name"):
            rendering.materialize(
                config,
                self.root / "config.yaml",
                [],
                self.root / "files",
                component="processor",
            )
        self.assertFalse((self.root / "private").exists())

    def test_bundle_guard_allows_public_secret_but_preserves_private_alias_protection(
        self,
    ):
        self.product()
        self.build_and_unpack()
        private_alias = self.source / "build/dev/processor/credentials/alias"
        private_alias.parent.mkdir(parents=True)
        private_alias.symlink_to(self.files / "public.pem")
        (self.source / "components/processor/config.dev.yaml").write_text(
            yaml.safe_dump(
                {"SECRET_FILES": {"processor-private": [{"path": "credentials/alias"}]}}
            )
        )
        with self.assertRaisesRegex(bundle.BundleError, "secret"):
            bundle.build()

    def test_sensitive_dev_seed_is_external_and_not_needed_in_production(self):
        self.product()
        external = self.root / "local-dev-seed.sql"
        external.write_text("sensitive-dev-fixture")
        (self.source / "components/processor/config.dev.yaml").write_text(
            yaml.safe_dump(
                {
                    "VOLUME_FILES": {
                        "processor-seed": [
                            {"component_file": "sql/reference.sql"},
                            {"path": str(external)},
                        ]
                    }
                }
            )
        )
        deploy.prepare()
        release = self.build_and_unpack()["processor"]
        with tarfile.open(
            str(next((self.source / "dist").glob("*.tar.gz")))
        ) as archive:
            self.assertFalse(
                any("local-dev-seed" in member.name for member in archive.getmembers())
            )
        external.unlink()
        shutil.rmtree(self.source)
        self.install(release)
        self.assertEqual(validation.validate_bundle()[1], [])
        self.assert_archive(b"first release\n")

    def test_database_password_cannot_be_a_component_file(self):
        product = copy.deepcopy(RENAMED)
        product["orders"]["defaults"]["SECRET_FILES"]["orders-database-password"] = [
            {"component_file": "password"}
        ]
        self.write_product(product)
        path = self.source / "components/orders/files/password"
        path.parent.mkdir(parents=True)
        path.write_text("private-password-content")
        self.provide_credentials(product, common.BUILD / "dev")
        for action in (validation.validate, deploy.prepare):
            with self.assertRaisesRegex(
                common.DeployError, "database passwords cannot use component_file"
            ) as failure:
                action()
            self.assertNotIn("private-password-content", str(failure.exception))
        self.process.assert_not_called()
