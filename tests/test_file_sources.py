"""One source declaration controls delivery and optional one-time generation."""

import base64
import tarfile

import yaml
from test_deploy import DeployFixture, document

from deployment import common, deploy
from deployment import render as rendering


class FileSourceTests(DeployFixture):
    def test_volume_generation_renders_import_and_preserves_bytes(self):
        self.config["VOLUME_FILES"] = {
            "payload": [{"path": "private", "generate": ["session-key"]}]
        }
        self.write_config()
        self.manifest(
            [
                document(
                    "Pod",
                    "app",
                    spec={
                        "containers": [
                            {
                                "name": "app",
                                "image": "localhost/app:1",
                                "imagePullPolicy": "Never",
                                "volumeMounts": [
                                    {"name": "files", "mountPath": "/files"}
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "files",
                                "persistentVolumeClaim": {"claimName": "payload"},
                            }
                        ],
                    },
                )
            ]
        )
        deploy.prepare()
        source = self.root / "private/session-key"
        before = source.read_bytes()
        self.assertEqual(len(before), 32)
        self.assertEqual(self.mode(source), 0o600)
        self.assertEqual(self.mode(source.parent), 0o700)
        archive = common.BUILD / "files/payload.tar"
        archive_before = archive.read_bytes()
        with tarfile.open(str(archive)) as tar:
            stream = tar.extractfile("session-key")
            assert stream is not None
            with stream:
                self.assertEqual(stream.read(), before)
        deploy.prepare()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(archive.read_bytes(), archive_before)
        self.assertEqual(self.mode(archive), 0o600)
        self.assertNotIn(before.decode(), self.stdout.getvalue())

    def test_multiple_sources_mix_generated_files_and_external_binary_data(self):
        external = self.write("external/certificate", b"\x00\xffcertificate", 0o600)
        self.write("second/other", b"externally supplied", 0o600)
        config = {
            "SECRET_FILES": {
                "keys": [
                    {"path": "credentials", "generate": ["password"]},
                    {"path": str(external)},
                    {"path": "second"},
                ]
            }
        }
        rendering.generate_secrets(config, self.root)
        groups = rendering.load_file_group(config, "SECRET_FILES", self.root)
        secret = rendering.secret_documents(groups)[0]
        self.assertEqual(set(secret["data"]), {"password", "certificate", "other"})
        for name, value in secret["data"].items():
            path = next(path for path in groups["keys"] if path.name == name)
            self.assertEqual(base64.b64decode(value), path.read_bytes())
        before = external.read_bytes()
        rendering.generate_secrets(config, self.root)
        self.assertEqual(external.read_bytes(), before)

    def test_invalid_source_declarations_fail_before_any_generation(self):
        for source in (
            "old-string",
            {},
            {"path": ""},
            {"path": False},
            {"path": "private", "generat": ["key"]},
            {"path": "private", "generate": None},
            {"path": "private", "generate": "key"},
            {"path": "private", "generate": ["invalid\x00key"]},
        ):
            config = {
                "SECRET_FILES": {
                    "keys": [
                        {"path": "private", "generate": ["first"]},
                        source,
                    ]
                }
            }
            with self.subTest(source=source), self.assertRaises(common.DeployError):
                rendering.generate_secrets(config, self.root)
            self.assertFalse((self.root / "private").exists())

    def test_generated_source_directories_cannot_escape_config(self):
        outside = self.root / "outside"
        outside.mkdir()
        base = self.root / "component"
        base.mkdir()
        (base / "alias").symlink_to(outside, target_is_directory=True)
        for source in ("../outside", str(outside), "alias", "~", "~someone"):
            config = {"VOLUME_FILES": {"keys": [{"path": source, "generate": ["key"]}]}}
            failure = self.assertRaisesRegex(common.DeployError, "config directory")
            with self.subTest(source=source), failure:
                rendering.generate_secrets(config, base)
            self.assertFalse((outside / "key").exists())

    def test_duplicate_generation_across_deliveries_fails_before_writes(self):
        source = {"path": "private", "generate": ["key"]}
        config = {
            "SECRET_FILES": {"secret": [source]},
            "VOLUME_FILES": {"volume": [source]},
        }
        with self.assertRaisesRegex(common.DeployError, "duplicate generated"):
            rendering.generate_secrets(config, self.root)
        self.assertFalse((self.root / "private").exists())

    def test_generation_source_must_be_a_directory(self):
        self.write("file", b"retained")
        config = {"SECRET_FILES": {"keys": [{"path": "file", "generate": ["key"]}]}}
        with self.assertRaisesRegex(common.DeployError, "must be a directory"):
            rendering.generate_secrets(config, self.root)
        self.assertEqual((self.root / "file").read_bytes(), b"retained")

    def test_removed_top_level_field_is_rejected_instead_of_ignored(self):
        config = {"HTTPS_PORT": 8443, "GENERATED_SECRETS": ["private/key"]}
        path = self.write("config.yaml", yaml.safe_dump(config))
        with self.assertRaisesRegex(common.DeployError, "not supported"):
            rendering.load_config(path)
        with self.assertRaisesRegex(common.DeployError, "not supported"):
            rendering.generate_secrets(config, self.root)
        self.assertFalse((self.root / "private").exists())
