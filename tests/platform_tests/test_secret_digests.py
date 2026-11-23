"""A generated secret's SHA-256 published for another component (backlog 88).

Synthetic producer and consumer declarations; the demo's Identity and app1
are covered in demo_tests/test_audit_digest_demo.py.
"""

import base64
import contextlib
import copy
import hashlib
import io
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from deployment import common, deploy, templates, validation
from deployment import render as rendering

from helpers.product_fixture import RENAMED, ProductFixture

KEY = b"Synthetic0Key1For2Digest3Tests45"
# Independently computed: printf %s "$KEY" | sha256sum
DIGEST = b"3517e65d36a5eba9e64b51e0d38fd32bc2bca547e0b5c4f3d3e6aff7a00657cb"
OTHER_KEY = b"OtherSynthetic0Key1For2Digests34"
OTHER_DIGEST = b"40162b1bcce45a44a26fdfc9aea66a825305c56358739be4005c40d59a3fbc6a"


def producer_config(**source):
    entry = {
        "path": "credentials/key",
        "generate": ["token"],
        "sha256": "credentials/key-sha256",
    }
    entry.update(source)
    return {common.SECRET_FILES: {"producer-key": [entry]}}


class DigestFixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.base = self.root / "producer"
        self.base.mkdir()
        self.path = self.base / "config.yaml"
        self.config = producer_config()
        self.key = self.base / "credentials/key/token"
        self.digest = self.base / "credentials/key-sha256/token"
        self.output = io.StringIO()

    def render(self, config=None):
        """The shared materialization dev prepare and production install run.

        Returns the install YAML; stdout and stderr are collected in output.
        """
        config = config or self.config
        with contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(
            self.output
        ):
            rendering.check_digest_outputs(config, self.base)
            return rendering.materialize(config, self.path, [], self.base / "files")[0]

    def write_key(self, data=KEY):
        self.key.parent.mkdir(parents=True, exist_ok=True)
        self.key.write_bytes(data)
        self.key.chmod(0o600)

    def assert_private(self):
        self.assertEqual(stat.S_IMODE(self.digest.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.digest.parent.stat().st_mode), 0o700)

    def assert_no_value(self, text):
        for value in (KEY, DIGEST, OTHER_KEY, OTHER_DIGEST):
            self.assertNotIn(value.decode(), text)
            self.assertNotIn(base64.b64encode(value).decode(), text)


class DigestWriteTests(DigestFixture):
    def test_known_digest_without_newline_private(self):
        self.write_key()
        self.render()
        self.assertEqual(self.digest.read_bytes(), DIGEST)
        self.assert_private()
        self.assert_no_value(self.output.getvalue())

    def test_generated_key_is_hashed_and_kept(self):
        self.render()
        generated = self.key.read_bytes()
        self.assertEqual(len(generated), 32)
        self.assertEqual(
            self.digest.read_bytes(), hashlib.sha256(generated).hexdigest().encode()
        )
        self.render()
        self.assertEqual(self.key.read_bytes(), generated)

    def test_correct_file_is_left_untouched(self):
        self.write_key()
        self.render()
        self.assertIn("Wrote SHA-256 file", self.output.getvalue())
        before = self.digest.stat()
        self.output = io.StringIO()
        self.render()
        after = self.digest.stat()
        self.assertEqual(
            (before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns)
        )
        self.assertNotIn("SHA-256", self.output.getvalue())

    def test_missing_or_wrong_digest_is_written_again_without_changing_the_key(self):
        self.write_key()
        self.render()
        self.digest.write_bytes(b"wrong")
        self.render()
        self.assertEqual(self.digest.read_bytes(), DIGEST)
        self.digest.unlink()
        self.render()
        self.assertEqual(self.digest.read_bytes(), DIGEST)
        self.assertEqual(self.key.read_bytes(), KEY)
        self.assert_private()

    def test_equal_bytes_with_other_permissions_are_refused(self):
        self.write_key()
        self.render()
        self.digest.chmod(0o644)
        with self.assertRaisesRegex(
            common.DeployError, r"key-sha256/token has mode 0644; set it to 0600"
        ) as caught:
            self.render()
        self.assert_no_value(str(caught.exception))
        self.digest.chmod(0o600)
        self.digest.parent.chmod(0o755)
        with self.assertRaisesRegex(
            common.DeployError, r"key-sha256 has mode 0755; set it to 0700"
        ):
            self.render()

    def test_link_directory_or_unreadable_target_is_refused_before_comparison(self):
        self.write_key()
        self.render()
        self.digest.unlink()
        self.digest.symlink_to(self.key)
        with self.assertRaisesRegex(common.DeployError, "must be a regular file"):
            self.render()
        self.assertEqual(self.key.read_bytes(), KEY)
        self.digest.unlink()
        self.digest.mkdir()
        with self.assertRaisesRegex(common.DeployError, "must be a regular file"):
            self.render()
        self.digest.rmdir()
        self.render()
        with mock.patch.object(
            Path, "read_bytes", side_effect=PermissionError("denied")
        ), self.assertRaisesRegex(common.DeployError, "cannot read .*key-sha256/token"):
            rendering.digest_is_current(self.digest, DIGEST, "here")

    def test_failure_before_the_rename_keeps_the_previous_digest(self):
        self.write_key()
        self.render()
        self.write_key(OTHER_KEY)
        with mock.patch.object(
            rendering.os, "replace", side_effect=OSError("disk full")
        ), self.assertRaises(OSError):
            self.render()
        self.assertEqual(self.digest.read_bytes(), DIGEST)
        self.assertEqual(
            sorted(p.name for p in self.digest.parent.iterdir()), ["token"]
        )
        self.render()
        self.assertEqual(self.digest.read_bytes(), OTHER_DIGEST)

    def test_failure_on_first_creation_leaves_no_final_file(self):
        self.write_key()
        with mock.patch.object(
            rendering.os, "replace", side_effect=OSError("disk full")
        ), self.assertRaises(OSError):
            self.render()
        self.assertEqual(list(self.digest.parent.iterdir()), [])

    def test_temporary_file_is_private(self):
        self.write_key()
        modes = []
        real_replace = os.replace

        def replace(source, target, **directories):
            modes.append(
                stat.S_IMODE(os.stat(source, dir_fd=directories["src_dir_fd"]).st_mode)
            )
            real_replace(source, target, **directories)

        with mock.patch.object(rendering.os, "replace", side_effect=replace):
            self.render()
        self.assertEqual(modes, [0o600])

    def test_first_creation_is_private_under_any_umask(self):
        for umask in (0o022, 0o222):
            with self.subTest(umask=oct(umask)):
                self.write_key()
                if self.digest.parent.exists():
                    self.digest.unlink()
                    self.digest.parent.rmdir()
                previous = os.umask(umask)
                try:
                    self.render()
                finally:
                    os.umask(previous)
                self.assertEqual(self.digest.read_bytes(), DIGEST)
                self.assert_private()
                before = self.digest.stat().st_mtime_ns
                self.render()
                self.assertEqual(self.digest.stat().st_mtime_ns, before)

    def test_new_directories_are_0700_from_creation_on_an_empty_tree(self):
        """Created with 0700 directly: an interruption never leaves 0755 behind."""
        for umask in (0o022, 0o222):
            with self.subTest(umask=oct(umask)):
                tree = self.root / ("tree-" + oct(umask))
                created = []
                real_mkdir = os.mkdir

                def mkdir(
                    path, mode=0o777, real_mkdir=real_mkdir, created=created, **kwargs
                ):
                    real_mkdir(path, mode, **kwargs)
                    created.append(stat.S_IMODE(os.stat(path).st_mode))

                previous = os.umask(umask)
                try:
                    with mock.patch.object(os, "mkdir", side_effect=mkdir):
                        rendering.make_private_directories(tree / "credentials/a/b")
                finally:
                    os.umask(previous)
                self.assertEqual(created, [0o700] * 4)
        self.write_key()
        previous = os.umask(0o222)
        try:
            self.render(producer_config(sha256="credentials/a/b"))
        finally:
            os.umask(previous)
        self.assertEqual((self.base / "credentials/a/b/token").read_bytes(), DIGEST)
        for path in (self.base / "credentials/a", self.base / "credentials/a/b"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_unsearchable_output_directory_gets_the_chmod_message(self):
        self.write_key()
        self.render()
        self.digest.parent.chmod(0o600)
        self.addCleanup(self.digest.parent.chmod, 0o700)
        with self.assertRaisesRegex(
            common.DeployError, "key-sha256 has mode 0600; set it to 0700"
        ):
            self.render()

    def test_a_destination_changed_before_the_rename_is_refused_not_replaced(self):
        self.write_key()
        self.render()
        self.write_key(OTHER_KEY)
        for change, message in (
            (lambda: self.digest.chmod(0o644), "has mode 0644; set it to 0600"),
            (
                lambda: (self.digest.unlink(), self.digest.symlink_to(self.key)),
                "must be a regular file",
            ),
        ):
            with self.subTest(message=message):
                real_fsync = os.fsync
                calls = []

                def fsync(
                    descriptor, real_fsync=real_fsync, calls=calls, change=change
                ):
                    real_fsync(descriptor)
                    if not calls:  # the temporary file is written: now change it
                        calls.append(descriptor)
                        change()

                with mock.patch.object(
                    rendering.os, "fsync", side_effect=fsync
                ), self.assertRaisesRegex(common.DeployError, message):
                    self.render()
                self.assertEqual(
                    [p.name for p in self.digest.parent.iterdir()], ["token"]
                )
                self.assertEqual(self.key.read_bytes(), OTHER_KEY)
                if self.digest.is_symlink():
                    self.assertEqual(self.key.read_bytes(), OTHER_KEY)
                    self.digest.unlink()
                    self.digest.write_bytes(DIGEST)
                self.digest.chmod(0o600)

    def test_existing_directory_with_another_mode_is_refused(self):
        self.write_key()
        self.digest.parent.mkdir(mode=0o750)
        self.digest.parent.chmod(0o750)
        with self.assertRaisesRegex(
            common.DeployError, "has mode 0750; set it to 0700"
        ):
            self.render()
        self.assertFalse(self.digest.exists())

    def test_digest_comes_from_the_rendered_bytes_not_a_second_read(self):
        self.write_key()
        real = rendering.secret_documents

        def documents_then_replace(secrets):
            docs = real(secrets)
            self.write_key(OTHER_KEY)  # the raw file changes after it was read
            return docs

        with mock.patch.object(
            rendering, "secret_documents", side_effect=documents_then_replace
        ):
            text = self.render()
        self.assertEqual(self.digest.read_bytes(), DIGEST)
        secret = next(
            doc
            for doc in yaml.safe_load_all(text)
            if doc["metadata"]["name"] == "producer-key"
        )
        self.assertEqual(base64.b64decode(secret["data"]["token"]), KEY)

    def test_byte_rule_refuses_without_naming_the_value(self):
        for data in (b"\xff\xfe-not-utf-8", b"", KEY + b"\r\n", KEY + b"\n", b" x"):
            with self.subTest(data=data):
                documents = [
                    {
                        "metadata": {"name": "producer-key"},
                        "data": {"token": base64.b64encode(data).decode()},
                    }
                ]
                with self.assertRaisesRegex(
                    common.DeployError,
                    r"SECRET_FILES.producer-key/token: a hashed secret must be one",
                ) as caught:
                    rendering.write_digests(self.config, self.base, documents)
                self.assert_no_value(str(caught.exception))
                self.assertFalse(self.digest.exists())


class DigestPathTests(DigestFixture):
    def test_declaration_syntax(self):
        refused = {
            "~/digest": "relative directory below credentials",
            "../digest": "relative directory below credentials",
            "/abs/digest": "relative directory below credentials",
            "other/digest": "relative directory below credentials",
            "credentials": "relative directory below credentials",
            "credentials/../x": "relative directory below credentials",
            "credentials/./x": "relative directory below credentials",
        }
        for value, message in refused.items():
            with self.subTest(value=value), self.assertRaisesRegex(
                common.DeployError, message
            ):
                rendering.file_group_sources(
                    producer_config(sha256=value), common.SECRET_FILES
                )
        for config, group in (
            (
                {
                    "producer-key": [
                        {"path": "credentials/key", "sha256": "credentials/s"}
                    ]
                },
                common.SECRET_FILES,
            ),
            (
                {"producer-key": [{"component_file": "x", "sha256": "credentials/s"}]},
                common.SECRET_FILES,
            ),
            (
                {
                    "producer-files": [
                        {
                            "path": "credentials/key",
                            "generate": ["t"],
                            "sha256": "credentials/s",
                        }
                    ]
                },
                common.VOLUME_FILES,
            ),
        ):
            with self.subTest(config=config), self.assertRaisesRegex(
                common.DeployError, "sha256 is allowed only on a SECRET_FILES path"
            ):
                rendering.file_group_sources({group: config}, group)

    def test_collision_with_another_raw_directory_is_refused_and_its_bytes_survive(
        self,
    ):
        config = producer_config()
        config[common.SECRET_FILES]["producer-other"] = [
            {"path": "credentials/key-sha256", "generate": ["token"]}
        ]
        other = self.base / "credentials/key-sha256/token"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"another credential")
        with self.assertRaisesRegex(common.DeployError, "overlaps"):
            rendering.check_digest_outputs(config, self.base)
        self.assertEqual(other.read_bytes(), b"another credential")
        for path in ("credentials", "credentials/key-sha256/inner"):
            nested = producer_config()
            nested[common.SECRET_FILES]["producer-other"] = [{"path": path}]
            with self.subTest(path=path), self.assertRaisesRegex(
                common.DeployError, "overlaps"
            ):
                rendering.check_digest_outputs(nested, self.base)

    def test_redirected_component_or_credentials_is_refused_before_generation(self):
        # credentials/ to another directory inside the component (which the
        # generation path check accepts), and the component directory itself.
        inside = self.base / "other"
        outside = self.root / "elsewhere"
        for elsewhere in (inside, outside):
            elsewhere.mkdir()
            (elsewhere / "kept").write_bytes(b"kept")
            elsewhere.chmod(0o755)
        for link, elsewhere in (
            (self.base / "credentials", inside),
            (self.base, outside),
        ):
            with self.subTest(link=link.name):
                if link == self.base:
                    os.rename(str(self.base), str(self.root / "real"))
                link.symlink_to(elsewhere)
                rendering.generated_secret_paths(self.config, self.base)  # accepted
                with self.assertRaisesRegex(common.DeployError, "must be a directory"):
                    rendering.check_digest_outputs(self.config, self.base)
                self.assertEqual(sorted(p.name for p in elsewhere.iterdir()), ["kept"])
                self.assertEqual(stat.S_IMODE(elsewhere.stat().st_mode), 0o755)
                link.unlink()

    def test_two_sources_cannot_publish_into_one_directory(self):
        config = producer_config()
        config[common.SECRET_FILES]["producer-other"] = [
            {
                "path": "credentials/other",
                "generate": ["token"],
                "sha256": "credentials/key-sha256",
            }
        ]
        with self.assertRaisesRegex(common.DeployError, "overlaps"):
            rendering.check_digest_outputs(config, self.base)
        self.assertFalse(self.digest.exists())

    def test_one_source_publishes_several_keys(self):
        config = producer_config(generate=["token", "second"])
        (self.base / "credentials/key").mkdir(parents=True)
        (self.base / "credentials/key/second").write_bytes(OTHER_KEY)
        self.write_key()
        self.render(config)
        self.assertEqual(self.digest.read_bytes(), DIGEST)
        self.assertEqual(
            (self.base / "credentials/key-sha256/second").read_bytes(), OTHER_DIGEST
        )

    def test_a_component_without_sha256_is_not_inspected(self):
        config = {common.SECRET_FILES: {"plain": [{"path": "credentials/x"}]}}
        with mock.patch.object(rendering, "check_digest_destination") as check:
            rendering.check_digest_outputs(config, self.base)
        check.assert_not_called()


class PromisedFileTests(unittest.TestCase):
    """First-run catalog validate: a file an earlier component publishes."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "consumer/config.yaml"
        self.path.parent.mkdir()  # the consumer's own directory, as in dev and state
        self.promised = rendering.promised_files(
            producer_config(), self.root / "producer"
        )
        self.config = {
            common.SECRET_FILES: {
                "consumer-digest": [
                    {"path": "../producer/credentials/key-sha256/token"}
                ]
            },
            common.SECRET_TEMPLATES: {
                "consumer-main-env-secret": {
                    "VALUE": "@@secret:consumer-digest/token@@"
                }
            },
        }

    def check(self, config=None, documents=(), promised=None):
        validation.check_sources(
            config or self.config,
            self.path,
            list(documents),
            promised=self.promised if promised is None else promised,
        )

    def test_promised_file_counts_as_present_with_its_name(self):
        self.check()
        self.assertEqual(
            rendering.secret_keys(self.config, self.path, [], None, self.promised)[
                "consumer-digest"
            ],
            {"token"},
        )
        self.assertFalse((self.root / "producer").exists())

    def test_without_the_promise_the_missing_file_is_refused(self):
        with self.assertRaisesRegex(common.DeployError, "Missing .*key-sha256/token"):
            self.check(promised=frozenset())

    def test_misspelled_recipe_and_manifest_keys_are_refused(self):
        config = dict(self.config)
        config[common.SECRET_TEMPLATES] = {
            "consumer-main-env-secret": {"VALUE": "@@secret:consumer-digest/tokn@@"}
        }
        with self.assertRaisesRegex(
            common.DeployError,
            "missing declared source SECRET_FILES.consumer-digest/tokn",
        ):
            self.check(config)
        pod = {
            "kind": "Pod",
            "metadata": {"name": "consumer-main"},
            "spec": {
                "containers": [{"name": "main", "image": "localhost/x:1"}],
                "volumes": [
                    {
                        "name": "digest",
                        "secret": {
                            "secretName": "consumer-digest",
                            "items": [{"key": "tokn", "path": "t"}],
                        },
                    }
                ],
            },
        }
        with self.assertRaisesRegex(common.DeployError, "provides only token"):
            self.check(documents=[pod])

    def test_promised_name_beside_the_same_name_is_refused(self):
        delivered = self.root / "consumer/credentials/more/token"
        delivered.parent.mkdir(parents=True)
        delivered.write_bytes(b"x")
        for extra in (
            {"path": "credentials/more"},
            {"path": "credentials/generated", "generate": ["token"]},
        ):
            config = dict(self.config)
            config[common.SECRET_FILES] = {
                "consumer-digest": self.config[common.SECRET_FILES]["consumer-digest"]
                + [extra]
            }
            with self.subTest(extra=extra), self.assertRaisesRegex(
                common.DeployError, r"several files with the same name: \['token'\]"
            ):
                self.check(config)

    def test_published_digest_beside_a_generated_name_is_refused(self):
        """The same check whether the digest is published yet or not."""
        published = self.root / "producer/credentials/key-sha256/token"
        for exists in (False, True):
            if exists:
                published.parent.mkdir(parents=True)
                published.write_bytes(DIGEST)
            for generate in ("token", "./token"):
                config = dict(self.config)
                config[common.SECRET_FILES] = {
                    "consumer-digest": self.config[common.SECRET_FILES][
                        "consumer-digest"
                    ]
                    + [{"path": "credentials/local", "generate": [generate]}]
                }
                with self.subTest(
                    exists=exists, generate=generate
                ), self.assertRaisesRegex(
                    common.DeployError,
                    r"several files with the same name: \['token'\]",
                ):
                    self.check(config)

    def test_a_path_through_a_missing_directory_is_not_promised(self):
        config = dict(self.config)
        config[common.SECRET_FILES] = {
            "consumer-digest": [
                {"path": "../missing/../producer/credentials/key-sha256/token"}
            ]
        }
        with self.assertRaisesRegex(
            common.DeployError, "Missing .*missing/\\.\\./producer"
        ):
            self.check(config)
        self.assertIsNone(
            rendering.secret_keys(config, self.path, [], None, self.promised)[
                "consumer-digest"
            ]
        )

    def test_validation_opens_no_credential_file(self):
        with mock.patch.object(
            Path, "read_bytes", side_effect=AssertionError("read")
        ), mock.patch.object(Path, "read_text", side_effect=AssertionError("read")):
            self.check()

    def test_an_empty_promise_set_keeps_todays_keys(self):
        keys = rendering.secret_keys(self.config, self.path, [], None)
        self.assertIsNone(keys["consumer-digest"])
        templates.validate(self.config, keys)  # unknown keys are not judged


if __name__ == "__main__":
    unittest.main()


class DigestBundleLifecycleTests(ProductFixture):
    """Real bundles: the producer installs, the consumer installs on its own."""

    def setUp(self):
        super().setUp()
        product = copy.deepcopy(
            {name: RENAMED[name] for name in ("gateway", "login-service", "orders")}
        )
        product["login-service"]["defaults"] = {
            common.SECRET_FILES: {
                "login-service-audit": [
                    {
                        "path": "credentials/audit",
                        "generate": ["token"],
                        "sha256": "credentials/audit-sha256",
                    }
                ]
            }
        }
        product["login-service"]["env"] = {
            "main": {"AUDIT": "@@secret:login-service-audit/token@@"}
        }
        product["orders"]["defaults"][common.SECRET_FILES]["orders-audit-digest"] = [
            {"path": "../login-service/credentials/audit-sha256/token"}
        ]
        product["orders"]["env"] = {
            "main": dict(
                product["orders"]["env"]["main"],
                AUDIT_SHA256="@@secret:orders-audit-digest/token@@",
            )
        }
        self.write_product(product)
        self.releases_by_name = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(product, common.STATE)
        self.raw = common.STATE / "login-service/credentials/audit/token"
        self.digest = common.STATE / "login-service/credentials/audit-sha256/token"

    def files(self):
        return {
            path: (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes())
            for path in (self.raw, self.digest)
        }

    def test_producer_install_reinstall_then_separate_consumer_install(self):
        for name in ("gateway", "login-service"):
            self.install(self.releases_by_name[name])
        key = self.raw.read_bytes()
        self.assertEqual(len(key), 32)
        self.assertEqual(
            self.digest.read_bytes(), hashlib.sha256(key).hexdigest().encode()
        )
        before = self.files()
        # Same-version reinstall: both files stay as they are.
        self.install(self.releases_by_name["login-service"])
        self.assertEqual(self.files(), before)
        # The consumer's bundle alone: validate requires the published file.
        orders = self.releases_by_name["orders"]
        self.use_root(orders)
        deploy.init_config("orders")
        self.digest.rename(self.digest.with_name("kept"))
        with self.assertRaisesRegex(
            common.DeployError,
            r"Missing .*audit-sha256/token \(SECRET_FILES.orders-audit-digest\); "
            r"if another component publishes this file",
        ):
            validation.validate()
        self.digest.with_name("kept").rename(self.digest)
        validation.validate()
        # Install and same-version retry open nothing below the raw key's directory.
        forbidden = str(self.raw.parent.resolve())

        def guard(original):
            def checked(file, *args, **kwargs):
                path = "" if isinstance(file, int) else os.path.realpath(file)
                if path == forbidden or path.startswith(forbidden + os.sep):
                    raise AssertionError("the consumer opened the raw key")
                return original(file, *args, **kwargs)

            return checked

        with mock.patch("builtins.open", guard(open)), mock.patch.object(
            io, "open", guard(io.open)
        ), mock.patch.object(os, "open", guard(os.open)):
            self.install(orders)
            self.install(orders)
        rendered = yaml.safe_load_all(
            (common.QUADLET_DIR / "myproduct-orders.yaml").read_text()
        )
        secret = next(
            doc
            for doc in rendered
            if doc["metadata"]["name"] == "orders-main-env-secret"
        )
        self.assertEqual(
            base64.b64decode(secret["data"]["AUDIT_SHA256"]),
            hashlib.sha256(key).hexdigest().encode(),
        )
        self.assertEqual(self.files(), before)
        output = self.stdout.getvalue() + self.stderr.getvalue()
        self.assertNotIn(key.decode(), output)
        self.assertNotIn(hashlib.sha256(key).hexdigest(), output)
