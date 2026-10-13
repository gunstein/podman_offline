"""Isolated renderer/installer tests; no Podman, systemd, root or network."""

import base64
import contextlib
import io
import os
import runpy
import stat
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import deploy


def document(kind, name, **values):
    result = {"apiVersion": "v1", "kind": kind, "metadata": {"name": name}}
    result.update(values)
    return result


class DeployFixture(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        paths = {
            "HOME": self.root / "home",
            "ROOT": self.root,
            "CONFIG": self.root / "config.yaml",
            "MANIFESTS": self.root / "manifests",
            "BUILD": self.root / "build",
            "QUADLET_TEMPLATE": self.root / "quadlet/myproduct.kube",
            "QUADLET_DIR": self.root / "home/.config/containers/systemd",
            "QUADLET_TARGET": self.root
            / "home/.config/containers/systemd/myproduct.kube",
            "QUADLET_YAML": self.root
            / "home/.config/containers/systemd/myproduct.yaml",
            "FILES_DIR": self.root / "home/files",
        }
        for name, path in paths.items():
            self.stack.enter_context(mock.patch.object(deploy, name, path))
        self.process = self.stack.enter_context(mock.patch.object(subprocess, "run"))
        self.euid = self.stack.enter_context(
            mock.patch.object(os, "geteuid", return_value=1000)
        )
        runtime = Path("/run/user/1000")
        original_is_dir = Path.is_dir
        self.stack.enter_context(
            mock.patch.object(
                Path,
                "is_dir",
                lambda path: True if path == runtime else original_is_dir(path),
            )
        )
        self.stack.enter_context(
            mock.patch.dict(
                os.environ,
                {"XDG_RUNTIME_DIR": str(runtime), "HOME": str(self.root / "home")},
            )
        )
        self.stdout = self.stack.enter_context(
            contextlib.redirect_stdout(io.StringIO())
        )
        self.stderr = self.stack.enter_context(
            contextlib.redirect_stderr(io.StringIO())
        )
        deploy.MANIFESTS.mkdir()
        self.config = {"HTTPS_PORT": 8443, "HOSTNAME": "example.test"}
        self.write_config()

    def write(self, name, contents: object = b"test\n", mode=0o644):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, str):
            contents = contents.encode("utf-8")
        assert isinstance(contents, bytes)
        path.write_bytes(contents)
        path.chmod(mode)
        return path

    def write_config(self):
        self.write("config.yaml", yaml.safe_dump(self.config))
        if getattr(self, "production_config", False):
            self.write("home/config.yaml", yaml.safe_dump(self.config), 0o600)

    def manifest(self, docs, name="10-pod.yaml"):
        return self.write("manifests/" + name, yaml.safe_dump_all(docs))

    def file_config(self, group, spec):
        self.config[group] = spec
        self.write_config()
        return deploy.load_file_group(self.config, group)

    def volume_fixture(self):
        self.write("files/message.txt", "hello\n", 0o600)
        self.file_config("VOLUME_FILES", {"uploads": ["files/message.txt"]})
        self.manifest(
            [
                document(
                    "Pod",
                    "app",
                    spec={
                        "volumes": [
                            {
                                "name": "uploads",
                                "persistentVolumeClaim": {"claimName": "uploads"},
                            }
                        ]
                    },
                )
            ]
        )

    def install_fixture(self):
        self.volume_fixture()
        self.production_config = True
        self.stack.enter_context(
            mock.patch.dict(os.environ, {"HOME": str(self.root / "home")})
        )
        self.config["VOLUME_FILES"] = {"uploads": ["../files/message.txt"]}
        self.write("quadlet/myproduct.kube", "[Kube]\nYaml=myproduct.yaml\n")
        self.write("quadlet/myproduct.network", "[Network]\nNetworkName=myproduct\n")
        self.write("images/images.tar")
        self.config["APP_IMAGE"] = "localhost/app:1"
        self.write_config()
        self.manifest(
            [
                {
                    "kind": "Pod",
                    "spec": {
                        "containers": [
                            {"image": "@@APP_IMAGE@@", "imagePullPolicy": "Never"},
                            {"image": "localhost/app:1", "imagePullPolicy": "Never"},
                        ],
                        "initContainers": [
                            {"image": "localhost/init:1", "imagePullPolicy": "Never"}
                        ],
                    },
                }
            ],
            "20-images.yaml",
        )

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)


class ConfigTests(DeployFixture):
    def test_strings_and_integers_preserve_types(self):
        self.config.update(TEXT="no", NUMBER=42, EMPTY="", ZERO=0, NEGATIVE=-7)
        self.write_config()
        self.assertEqual(deploy.load_config(deploy.CONFIG), self.config)

    def test_rejects_non_scalar_config_values(self):
        for value in (True, False, None, 1.5, [], {}, ["a"], {"a": "b"}):
            with self.subTest(value=value):
                self.config["VALUE"] = value
                self.write_config()
                with self.assertRaisesRegex(
                    deploy.DeployError, "VALUE.*string or an integer"
                ):
                    deploy.load_config(deploy.CONFIG)

    def test_rejects_non_mapping_document(self):
        for text in ("", "null", "[]", "text", "42"):
            with self.subTest(text=text):
                self.write("config.yaml", text)
                with self.assertRaisesRegex(deploy.DeployError, "KEY: value"):
                    deploy.load_config(deploy.CONFIG)

    def test_rejects_non_string_keys(self):
        for key in (12, True, None):
            with self.subTest(key=key):
                self.write(
                    "config.yaml", yaml.safe_dump({key: "x", "HTTPS_PORT": 8443})
                )
                with self.assertRaisesRegex(deploy.DeployError, "keys.*strings"):
                    deploy.load_config(deploy.CONFIG)

    def test_port_boundaries(self):
        for port in (1, 65535):
            with self.subTest(port=port):
                self.config["HTTPS_PORT"] = port
                self.write_config()
                self.assertEqual(deploy.load_config(deploy.CONFIG)["HTTPS_PORT"], port)

    def test_invalid_ports_and_missing_port(self):
        for port in (0, -1, 65536, "8443", True, False, None, 1.5, [], {}):
            with self.subTest(port=port):
                self.config["HTTPS_PORT"] = port
                self.write_config()
                with self.assertRaisesRegex(deploy.DeployError, "HTTPS_PORT"):
                    deploy.load_config(deploy.CONFIG)
        self.config.pop("HTTPS_PORT")
        self.write_config()
        with self.assertRaisesRegex(deploy.DeployError, "1-65535"):
            deploy.load_config(deploy.CONFIG)

    def test_duplicate_key_reports_second_line(self):
        self.write(
            "config.yaml", "HTTPS_PORT: 8443\nHOSTNAME: first\nHOSTNAME: second\n"
        )
        with self.assertRaises(yaml.YAMLError) as caught:
            deploy.load_config(deploy.CONFIG)
        self.assertIn("duplicate key 'HOSTNAME'", str(caught.exception))
        self.assertIn("line 3", str(caught.exception))

    def test_duplicate_nested_key_reports_line(self):
        self.write(
            "config.yaml", "HTTPS_PORT: 8443\nSECRET_FILES:\n  a: [one]\n  a: [two]\n"
        )
        with self.assertRaisesRegex(yaml.YAMLError, "line 4"):
            deploy.load_config(deploy.CONFIG)

    def test_groups_are_validated_separately(self):
        self.config.update(SECRET_FILES={"a": ["one"]}, VOLUME_FILES={"b": ["two"]})
        self.write_config()
        self.assertEqual(deploy.load_config(deploy.CONFIG), self.config)


class ReplaceTests(unittest.TestCase):
    def test_preserves_integer_and_string_types(self):
        for value in (8443, "8443", "no", ""):
            with self.subTest(value=value):
                result = deploy.replace("@@VALUE@@", {"VALUE": value})
                self.assertEqual(result, value)
                self.assertIs(type(result), type(value))

    def test_missing_key(self):
        with self.assertRaisesRegex(deploy.DeployError, "Missing MISSING"):
            deploy.replace("@@MISSING@@", {})

    def test_nested_maps_and_lists(self):
        source = {"outer": [{"port": "@@PORT@@", "list": ["@@TEXT@@", None, True]}]}
        self.assertEqual(
            deploy.replace(source, {"PORT": 1234, "TEXT": "ok"}),
            {"outer": [{"port": 1234, "list": ["ok", None, True]}]},
        )
        self.assertEqual(source["outer"][0]["port"], "@@PORT@@")

    def test_partial_placeholder_is_left_for_render_validation(self):
        self.assertEqual(deploy.replace("prefix-@@X@@", {"X": "ok"}), "prefix-@@X@@")


class FileGroupTests(DeployFixture):
    def test_multiple_secrets_directory_and_binary_roundtrip(self):
        binary = bytes(range(256)) + b"\x00\xff\r\n"
        self.write("input/token.txt", "example only\n")
        self.write("input/binary.bin", binary)
        self.write("other/item", b"second")
        groups = self.file_config(
            "SECRET_FILES", {"first": ["input"], "second": ["other/item"]}
        )
        docs = {doc["metadata"]["name"]: doc for doc in deploy.secret_documents(groups)}
        self.assertEqual(set(docs), {"first", "second"})
        self.assertEqual(set(docs["first"]["data"]), {"token.txt", "binary.bin"})
        self.assertEqual(base64.b64decode(docs["first"]["data"]["binary.bin"]), binary)
        self.assertEqual(base64.b64decode(docs["second"]["data"]["item"]), b"second")

    def test_secret_filenames(self):
        for name in ("with space", "æ.txt", "bad@name"):
            with self.subTest(name=name):
                self.write(name)
                with self.assertRaisesRegex(deploy.DeployError, "the file name"):
                    self.file_config("SECRET_FILES", {"test": [name]})
        self.write("OK-a_b.c")
        self.assertIn("test", self.file_config("SECRET_FILES", {"test": ["OK-a_b.c"]}))

    def test_secret_rejects_subdirectory(self):
        self.write("tree/nested/file")
        with self.assertRaisesRegex(
            deploy.DeployError, "Secrets can only contain files"
        ):
            self.file_config("SECRET_FILES", {"test": ["tree"]})

    def test_secret_limit_is_per_id_and_counts_document_overhead(self):
        self.write("first", b"a" * 200000)
        self.write("second", b"b" * 200000)
        groups = self.file_config(
            "SECRET_FILES", {"first": ["first"], "second": ["second"]}
        )
        self.assertEqual(len(deploy.secret_documents(groups)), 2)
        with self.assertRaisesRegex(deploy.DeployError, "too large.*Podman secret"):
            deploy.secret_documents(
                {"combined": [self.root / "first", self.root / "second"]}
            )
        self.write("boundary", b"x" * (deploy.MAX_SECRET_SIZE * 3 // 4))
        with self.assertRaisesRegex(deploy.DeployError, "too large"):
            deploy.secret_documents({"boundary": [self.root / "boundary"]})

    def test_tilde_and_absolute_paths(self):
        path = self.write("home/test.bin", b"\x00\xff")
        with mock.patch.dict(os.environ, {"HOME": str(path.parent)}):
            groups = self.file_config("SECRET_FILES", {"test": ["~/test.bin"]})
        self.assertEqual(groups["test"], [path])
        self.assertEqual(deploy.resolve_path(str(path)), path)

    def test_invalid_group_and_entries(self):
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            for spec in (
                "bad",
                ["a"],
                {"UPPER": ["x"]},
                {12: ["x"]},
                {"-bad": ["x"]},
                {"bad-": ["x"]},
                {"a": []},
                {"a": "x"},
                {"a": [12]},
                {"a": None},
            ):
                error = self.assertRaises(deploy.DeployError)
                with self.subTest(group=group, spec=spec), error:
                    self.file_config(group, spec)

    def test_missing_file_and_name_collisions(self):
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            with self.subTest(group=group):
                with self.assertRaisesRegex(deploy.DeployError, "Missing"):
                    self.file_config(group, {"test": ["missing"]})
                self.write("a/file")
                self.write("b/file")
                for entries in (["a", "b"], ["a/file", "a/file"]):
                    with self.assertRaisesRegex(deploy.DeployError, "same name"):
                        self.file_config(group, {"test": entries})

    def test_absent_groups(self):
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            self.assertEqual(deploy.load_file_group(self.config, group), {})


class VolumeTests(DeployFixture):
    def test_tar_contents_ownership_modes_and_symlinks(self):
        self.write("single", b"\x00\xff", 0o600)
        self.write("tree/plain", "plain", 0o666)
        self.write("tree/sub/run.sh", "#!/bin/sh\n", 0o700)
        (self.root / "tree/sub").chmod(0o700)
        (self.root / "tree/link").symlink_to(self.root / "single")
        (self.root / "tree/dir-link").symlink_to(
            self.root / "tree/sub", target_is_directory=True
        )
        groups = self.file_config("VOLUME_FILES", {"uploads": ["single", "tree"]})
        output = deploy.BUILD / "files"
        deploy.write_file_archives(groups, output)
        self.assertEqual(self.mode(output), 0o700)
        self.assertEqual(self.mode(output / "uploads.tar"), 0o600)
        with tarfile.open(str(output / "uploads.tar")) as archive:
            self.assertEqual(
                set(archive.getnames()),
                {
                    "single",
                    "plain",
                    "sub",
                    "sub/run.sh",
                    "link",
                    "dir-link",
                    "dir-link/run.sh",
                },
            )
            for member in archive.getmembers():
                self.assertEqual(
                    (member.uid, member.gid, member.uname, member.gname),
                    (0, 0, "root", "root"),
                )
                self.assertFalse(member.issym() or member.islnk())
                self.assertEqual(
                    member.mode,
                    0o755
                    if member.isdir() or member.name.endswith("run.sh")
                    else 0o644,
                )
            for name in ("single", "link"):
                stream = archive.extractfile(name)
                self.assertIsNotNone(stream)
                assert stream is not None
                with stream:
                    self.assertEqual(stream.read(), b"\x00\xff")

    def test_existing_archive_permissions_are_restricted(self):
        item = self.write("item")
        output = deploy.BUILD / "files"
        self.write("build/files/one.tar", "old", 0o666)
        output.chmod(0o777)
        deploy.write_file_archives({"one": [item]}, output)
        self.assertEqual(self.mode(output), 0o700)
        self.assertEqual(self.mode(output / "one.tar"), 0o600)

    def test_claim_points_at_requested_archive(self):
        claims = deploy.volume_claims({"one": [], "two": []}, deploy.FILES_DIR)
        self.assertEqual([doc["metadata"]["name"] for doc in claims], ["one", "two"])
        self.assertEqual(
            claims[0]["metadata"]["annotations"][deploy.IMPORT_SOURCE],
            str(deploy.FILES_DIR / "one.tar"),
        )

    def test_empty_volumes_do_not_create_directory(self):
        deploy.write_file_archives({}, deploy.FILES_DIR)
        self.assertFalse(deploy.FILES_DIR.exists())


class LinkTests(unittest.TestCase):
    def refs(self, kind, name):
        if kind == "PersistentVolumeClaim":
            return [{"persistentVolumeClaim": {"claimName": name}}]
        return [
            {"secret": {"secretName": name}},
            {"secretKeyRef": {"name": name}},
            {"secretRef": {"name": name}},
        ]

    def test_every_reference_form_and_nested_lists(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            for ref in self.refs(kind, "known"):
                with self.subTest(kind=kind, ref=ref):
                    docs = [document(kind, "known"), {"nested": [{"more": ref}]}]
                    deploy.check_links(docs, {(kind, "known"): "config.known"})
                    self.assertEqual(deploy.references(docs, set()), {(kind, "known")})

    def test_every_missing_reference(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            for ref in self.refs(kind, "missing"):
                error = self.assertRaisesRegex(
                    deploy.DeployError, kind + ".*missing.*does not exist"
                )
                with self.subTest(kind=kind, ref=ref), error:
                    deploy.check_links([ref], {})

    def test_duplicate_definitions(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            error = self.assertRaisesRegex(deploy.DeployError, "defined more than once")
            with self.subTest(kind=kind), error:
                deploy.check_links([document(kind, "same"), document(kind, "same")], {})

    def test_volume_names_are_unique_across_secret_pvc_and_configmap(self):
        kinds = ("Secret", "PersistentVolumeClaim", "ConfigMap")
        for first in kinds:
            for second in kinds:
                error = self.assertRaisesRegex(
                    deploy.DeployError, "same.*more than once"
                )
                with self.subTest(first=first, second=second), error:
                    deploy.check_links(
                        [document(first, "same"), document(second, "same")], {}
                    )

    def test_configmap_does_not_satisfy_secret_or_pvc_reference(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            error = self.assertRaisesRegex(deploy.DeployError, "does not exist")
            with self.subTest(kind=kind), error:
                deploy.check_links(
                    [document("ConfigMap", "known")] + self.refs(kind, "known"), {}
                )

    def test_unused_config_ids(self):
        for kind, group in (
            ("Secret", "SECRET_FILES"),
            ("PersistentVolumeClaim", "VOLUME_FILES"),
        ):
            error = self.assertRaisesRegex(deploy.DeployError, group + ".id.*not used")
            with self.subTest(kind=kind), error:
                deploy.check_links(
                    [document(kind, "id")], {(kind, "id"): group + ".id"}
                )

    def test_manifest_defined_objects_are_allowed_even_if_unused(self):
        docs = [
            document("Secret", "same", stringData={"token": "test"}),
            document("PersistentVolumeClaim", "data"),
        ]
        deploy.check_links(docs, {})
        deploy.check_links(
            docs
            + self.refs("Secret", "same")
            + self.refs("PersistentVolumeClaim", "data"),
            {},
        )


class GeneratedSecretTests(DeployFixture):
    """Test one-time private files and their existing SECRET_FILES delivery."""

    def configure_generated(self):
        """Add a generated file and a manifest envFrom Secret reference."""
        self.config["GENERATED_SECRETS"] = ["generated-certificates/app/key"]
        self.config["SECRET_FILES"] = {"app-secrets": ["generated-certificates/app"]}
        self.write_config()
        self.manifest(
            [
                document(
                    "Pod",
                    "generated",
                    spec={
                        "containers": [
                            {
                                "name": "app",
                                "image": "localhost/app:1",
                                "imagePullPolicy": "Never",
                                "envFrom": [{"secretRef": {"name": "app-secrets"}}],
                            }
                        ]
                    },
                )
            ],
            "30-generated.yaml",
        )
        return self.root / "generated-certificates/app/key"

    def test_prepare_creates_private_alphanumeric_file_without_logging_value(self):
        """Generate 32 characters once and deliver their bytes through SECRET_FILES."""
        path = self.configure_generated()
        deploy.prepare()
        value = path.read_bytes()
        self.assertEqual(len(value), 32)
        self.assertTrue(
            all(
                chr(byte) in deploy.string.ascii_letters + deploy.string.digits
                for byte in value
            ),
            "Invalid generated characters",
        )
        self.assertEqual(self.mode(path), 0o600)
        self.assertEqual(self.mode(path.parent), 0o700)
        self.assertEqual(self.mode(path.parent.parent), 0o700)
        output = self.stdout.getvalue() + self.stderr.getvalue()
        self.assertIn(str(path), output)
        self.assertTrue(value.decode("ascii") not in output, "Generated value leaked")
        docs = list(yaml.safe_load_all((deploy.BUILD / "install.yaml").read_text()))
        secret = next(doc for doc in docs if doc["kind"] == "Secret")
        self.assertTrue(
            base64.b64decode(secret["data"]["key"]) == value, "Secret bytes differ"
        )
        deploy.prepare()
        self.assertTrue(
            path.read_bytes() == value, "Repeated prepare changed the secret"
        )
        self.process.assert_not_called()

    def test_install_keeps_existing_home_secret_across_releases(self):
        """Preserve home secrets on repeated install independently of dev/release paths."""
        self.install_fixture()
        self.config["VOLUME_FILES"] = {"uploads": ["files/message.txt"]}
        dev_path = self.configure_generated()
        deploy.prepare()
        dev_value = dev_path.read_bytes()
        prod_config = dict(self.config)
        prod_config["VOLUME_FILES"] = {"uploads": ["../files/message.txt"]}
        self.write("home/config.yaml", yaml.safe_dump(prod_config))
        deploy.generate_secrets(self.config, deploy.HOME)
        prod_path = deploy.HOME / "generated-certificates/app/key"
        before = prod_path.read_bytes()
        deploy.install()
        deploy.install()
        self.assertTrue(
            prod_path.read_bytes() == before, "Install changed the persistent secret"
        )
        self.assertTrue(
            dev_path.read_bytes() == dev_value, "Install changed the dev secret"
        )
        output = self.stdout.getvalue() + self.stderr.getvalue()
        self.assertTrue(before.decode("ascii") not in output, "Install logged a secret")

    def test_empty_or_directory_path_is_not_regenerated(self):
        """Reject empty files and directory targets without replacing them."""
        path = self.configure_generated()
        self.write("generated-certificates/app/key", b"")
        with self.assertRaisesRegex(deploy.DeployError, "empty"):
            deploy.prepare()
        self.assertEqual(path.stat().st_size, 0)
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(deploy.DeployError, "regular file"):
            deploy.prepare()
        self.assertTrue(path.is_dir())

    def test_escaping_paths_and_symlink_parents_are_rejected(self):
        """Reject lexical traversal, absolute paths and resolved symlink escapes."""
        outside = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (self.root / "outside-link").symlink_to(outside, target_is_directory=True)
        for entry in (
            "../key",
            "nested/../key",
            str(outside / "key"),
            "outside-link/key",
            "",
            ".",
        ):
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(deploy.DeployError, "config directory"):
                    deploy.generate_secrets({"GENERATED_SECRETS": [entry]}, self.root)
                self.assertFalse((outside / "key").exists())

    def test_invalid_list_and_entries_are_rejected(self):
        """Require a list of relative path strings for GENERATED_SECRETS."""
        for entries in (None, "key", {}, 1, [False], [1]):
            error = self.assertRaisesRegex(deploy.DeployError, "list")
            with self.subTest(entries=entries), error:
                deploy.generate_secrets({"GENERATED_SECRETS": entries}, self.root)

    def test_exclusive_creation_preserves_a_concurrent_nonempty_file(self):
        """Use O_EXCL and retain a file created by another writer before open."""
        path = self.configure_generated()
        value = os.urandom(32)
        original = os.open

        def race(target, flags, mode):
            """Simulate a competing creator without exposing its random contents."""
            if Path(target) == path:
                self.assertTrue(flags & os.O_EXCL)
                self.assertEqual(mode, 0o600)
                path.write_bytes(value)
                raise FileExistsError()
            return original(target, flags, mode)

        with mock.patch.object(os, "open", side_effect=race):
            deploy.generate_secrets(self.config, self.root)
        self.assertTrue(path.read_bytes() == value, "Concurrent file was overwritten")


class ManifestValidationTests(DeployFixture):
    """Validate offline policies and object links in real rendered manifests."""

    def pod(self, group="containers", mount="data", policy: object = "Never"):
        """Build a minimal pod spec with one mounted ConfigMap volume."""
        return document(
            "Pod",
            "app",
            spec={
                "volumes": [{"name": "data", "configMap": {"name": "settings"}}],
                group: [
                    {
                        "name": "worker",
                        "image": "localhost/app:1",
                        "imagePullPolicy": policy,
                        "volumeMounts": [{"name": mount, "mountPath": "/data"}],
                    }
                ],
            },
        )

    def test_configmap_reference_forms_accept_later_definition(self):
        """Resolve envFrom, env key and volume ConfigMaps across sorted files."""
        doc = self.pod()
        container = doc["spec"]["containers"][0]
        container["envFrom"] = [{"configMapRef": {"name": "settings"}}]
        container["env"] = [
            {
                "name": "VALUE",
                "valueFrom": {"configMapKeyRef": {"name": "settings", "key": "value"}},
            }
        ]
        self.manifest([doc], "10-app.yaml")
        self.manifest(
            [document("ConfigMap", "settings", data={"value": "ok"})],
            "90-settings.yaml",
        )
        self.assertIn("settings", deploy.render())

    def test_missing_configmap_forms_report_source(self):
        """Reject every missing ConfigMap reference with the originating filename."""
        for reference in (
            {"configMapRef": {"name": "missing"}},
            {"configMapKeyRef": {"name": "missing", "key": "value"}},
            {"configMap": {"name": "missing"}},
        ):
            with self.subTest(reference=reference):
                self.manifest([document("Pod", "app", spec=reference)], "10-app.yaml")
                with self.assertRaisesRegex(
                    deploy.DeployError, "10-app.yaml.*ConfigMap.*missing"
                ):
                    deploy.render()
                self.assertFalse(deploy.BUILD.exists())

    def test_mounts_and_never_policy_accept_containers_and_init(self):
        """Validate regular and init containers in Pod and nested Deployment specs."""
        self.manifest([document("ConfigMap", "settings")], "90-settings.yaml")
        for group in ("containers", "initContainers"):
            with self.subTest(group=group):
                pod = self.pod(group)
                deployment = document(
                    "Deployment", "app", spec={"template": {"spec": pod["spec"]}}
                )
                self.manifest([pod, deployment], "10-app.yaml")
                deploy.render(write_archives=False)

    def test_unknown_mounts_report_file_and_container(self):
        """Reject mounts absent from the pod volumes in both container groups."""
        for group in ("containers", "initContainers"):
            with self.subTest(group=group):
                self.manifest([self.pod(group, mount="missing")], "10-app.yaml")
                with self.assertRaisesRegex(
                    deploy.DeployError, "10-app.yaml.*worker.*undefined volume.*missing"
                ):
                    deploy.render()
                self.assertFalse(deploy.BUILD.exists())

    def test_missing_or_online_pull_policies_report_file(self):
        """Require Never for every regular/init container, including omitted policies."""
        for group in ("containers", "initContainers"):
            for policy in (None, "Always", "IfNotPresent"):
                with self.subTest(group=group, policy=policy):
                    pod = self.pod(group, policy=policy)
                    if policy is None:
                        del pod["spec"][group][0]["imagePullPolicy"]
                    self.manifest([pod], "10-app.yaml")
                    with self.assertRaisesRegex(
                        deploy.DeployError,
                        "10-app.yaml.*worker.*imagePullPolicy: Never",
                    ):
                        deploy.render()
                    self.assertFalse(deploy.BUILD.exists())


class RenderTests(DeployFixture):
    def test_manifest_errors_include_source_path(self):
        """Point at the right manifest for missing config, invalid data and partial placeholders."""
        for doc, message in (
            (document("Pod", "bad", value="@@UNKNOWN@@"), "Missing UNKNOWN"),
            (document("ConfigMap", "bad", data=["bad"]), "ConfigMap.data"),
            (document("Pod", "bad", value="prefix-@@HOSTNAME@@"), "Unreplaced"),
        ):
            with self.subTest(message=message):
                self.manifest([doc], "42-bad.yaml")
                with self.assertRaises(deploy.DeployError) as error:
                    deploy.render()
                self.assertIn(
                    str(deploy.MANIFESTS / "42-bad.yaml"), str(error.exception)
                )
                self.assertIn(message, str(error.exception))
                self.assertFalse(deploy.BUILD.exists())

    def test_real_product_manifests_render_with_dummy_files(self):
        """Render the demo's real manifest set and example config with local dummy files."""
        repo = Path(__file__).resolve().parent.parent
        self.config = deploy.load_config(repo / "config.example.yaml")
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            for paths in self.config[group].values():
                for path in paths:
                    self.write(path + "/dummy", b"dummy")
        self.write_config()
        for path in sorted((repo / "manifests").glob("*.yaml")):
            self.write("manifests/" + path.name, path.read_bytes())
        docs = list(yaml.safe_load_all(deploy.render(write_archives=False)))
        kinds = [doc["kind"] for doc in docs]
        self.assertEqual(kinds.count("Pod"), 6)
        self.assertEqual(kinds.count("Secret"), 7)
        self.assertEqual(kinds.count("PersistentVolumeClaim"), 4)
        self.assertEqual(kinds.count("ConfigMap"), 1)
        self.assertEqual(len(deploy.find_images(docs)), 6)
        self.process.assert_not_called()

    def test_render_without_archive_writes_still_validates(self):
        self.volume_fixture()
        text = deploy.render(deploy.FILES_DIR, write_archives=False)
        self.assertIn(str(deploy.FILES_DIR / "uploads.tar"), text)
        self.assertFalse(deploy.FILES_DIR.exists())
        self.manifest([document("ConfigMap", "uploads")], "99-collision.yaml")
        with self.assertRaisesRegex(deploy.DeployError, "uploads.*more than once"):
            deploy.render(deploy.FILES_DIR, write_archives=False)
        self.assertFalse(deploy.FILES_DIR.exists())

    def test_sorted_multidocument_manifests_and_configmap_strings(self):
        self.manifest([document("Pod", "last")], "20.yaml")
        self.manifest(
            [
                None,
                document(
                    "ConfigMap",
                    "first",
                    data={
                        "port": "@@HTTPS_PORT@@",
                        "host": "@@HOSTNAME@@",
                        "number": 5,
                    },
                ),
            ],
            "01.yaml",
        )
        docs = list(yaml.safe_load_all(deploy.render()))
        self.assertEqual([doc["metadata"]["name"] for doc in docs], ["first", "last"])
        self.assertEqual(
            docs[0]["data"], {"port": "8443", "host": "example.test", "number": "5"}
        )

    def test_no_archives_written_on_validation_failure(self):
        self.volume_fixture()
        cases = [
            (document("Pod", "bad", value="prefix-@@HOSTNAME@@"), "Unreplaced"),
            (document("Pod", "bad", value="@@UNKNOWN@@"), "Missing UNKNOWN"),
            (document("ConfigMap", "bad", data=["bad"]), "ConfigMap.data"),
            (
                document(
                    "Pod",
                    "bad",
                    spec={"persistentVolumeClaim": {"claimName": "unknown"}},
                ),
                "does not exist",
            ),
            (document("PersistentVolumeClaim", "uploads"), "defined more than once"),
        ]
        for doc, error in cases:
            with self.subTest(error=error):
                self.manifest([doc], "99-bad.yaml")
                with self.assertRaisesRegex(deploy.DeployError, error):
                    deploy.render()
                self.assertFalse(deploy.BUILD.exists())
        self.manifest([document("Pod", "bad", value="@@BAD@@")], "99-bad.yaml")
        old = self.write("build/files/uploads.tar", b"previous archive")
        with self.assertRaises(deploy.DeployError):
            deploy.render()
        self.assertEqual(old.read_bytes(), b"previous archive")

    def test_no_archives_for_unused_id_or_large_secret(self):
        self.volume_fixture()
        (deploy.MANIFESTS / "10-pod.yaml").unlink()
        with self.assertRaisesRegex(deploy.DeployError, "not used"):
            deploy.render()
        self.assertFalse(deploy.BUILD.exists())
        self.write("large", b"x" * 400000)
        self.file_config("SECRET_FILES", {"large": ["large"]})
        with self.assertRaisesRegex(deploy.DeployError, "too large"):
            deploy.render()
        self.assertFalse(deploy.BUILD.exists())

    def test_duplicate_manifest_keys_report_line(self):
        self.write("manifests/bad.yaml", "kind: Pod\nkind: Secret\n")
        with self.assertRaisesRegex(yaml.YAMLError, "line 2"):
            deploy.render()
        self.assertFalse(deploy.BUILD.exists())

    def test_missing_config(self):
        deploy.CONFIG.unlink()
        with self.assertRaisesRegex(deploy.DeployError, "Missing"):
            deploy.render()


class CommandTests(DeployFixture):
    def test_prepare_writes_private_yaml_and_archives(self):
        self.volume_fixture()
        deploy.prepare()
        output = deploy.BUILD / "install.yaml"
        self.assertEqual(self.mode(output), 0o600)
        self.assertEqual(self.mode(deploy.BUILD / "files/uploads.tar"), 0o600)
        docs = list(yaml.safe_load_all(output.read_text()))
        self.assertEqual(
            docs[0]["metadata"]["annotations"][deploy.IMPORT_SOURCE],
            str(deploy.BUILD / "files/uploads.tar"),
        )
        self.process.assert_not_called()
        output.chmod(0o666)
        deploy.prepare()
        self.assertEqual(self.mode(output), 0o600)

    def test_root_check_precedes_reads_writes_and_commands(self):
        self.euid.return_value = 0
        render = self.stack.enter_context(mock.patch.object(deploy, "render"))
        load = self.stack.enter_context(mock.patch.object(deploy, "find_images"))
        with self.assertRaisesRegex(deploy.DeployError, "root"):
            deploy.install()
        render.assert_not_called()
        load.assert_not_called()
        self.process.assert_not_called()
        self.assertFalse(deploy.QUADLET_DIR.exists())
        self.assertFalse(deploy.FILES_DIR.exists())

    def test_install_uses_persistent_config_not_release_config(self):
        self.install_fixture()
        self.write("config.yaml", "invalid release config")
        deploy.install()
        self.assertIn("localhost/app:1", deploy.QUADLET_YAML.read_text())

    def test_install_missing_persistent_config_names_expected_path(self):
        self.install_fixture()
        path = self.root / "home/config.yaml"
        path.unlink()
        with self.assertRaises(deploy.DeployError) as failure:
            deploy.install()
        self.assertIn(str(path), str(failure.exception))
        self.process.assert_not_called()

    def test_prepare_uses_release_config_even_when_home_config_exists(self):
        self.volume_fixture()
        self.write("home/config.yaml", "invalid prod config")
        with mock.patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            deploy.prepare()
        self.assertTrue((deploy.BUILD / "install.yaml").is_file())
        self.process.assert_not_called()

    def test_separate_config_directory_resolves_secrets_and_volumes(self):
        for directory in ("dev", "home"):
            with self.subTest(directory=directory):
                config_path = self.write(
                    directory + "/config.yaml",
                    yaml.safe_dump(
                        {
                            "HTTPS_PORT": 8443,
                            "SECRET_FILES": {"secret": ["generated/key"]},
                            "VOLUME_FILES": {"uploads": ["generated/message"]},
                        }
                    ),
                )
                self.write(directory + "/generated/key", b"persistent secret")
                self.write(directory + "/generated/message", b"persistent volume")
                self.manifest(
                    [
                        document(
                            "Pod",
                            "test",
                            spec={
                                "volumes": [
                                    {"secret": {"secretName": "secret"}},
                                    {"persistentVolumeClaim": {"claimName": "uploads"}},
                                ]
                            },
                        )
                    ]
                )
                docs = list(yaml.safe_load_all(deploy.render(config_path=config_path)))
                self.assertEqual(
                    base64.b64decode(docs[0]["data"]["key"]), b"persistent secret"
                )
                with tarfile.open(str(deploy.BUILD / "files/uploads.tar")) as archive:
                    content = archive.extractfile("message")
                    assert content is not None
                    with content:
                        self.assertEqual(content.read(), b"persistent volume")

    def test_paths_follow_user_database_even_when_home_differs(self):
        home = self.root / "other-service-user"
        environment = mock.patch.dict(os.environ, {"HOME": str(self.root / "operator")})
        lookup = mock.patch.object(
            deploy.pwd, "getpwuid", return_value=mock.Mock(pw_dir=str(home))
        )
        with environment, lookup as account:
            module = runpy.run_path(deploy.__file__, run_name="rootless_paths_test")
        account.assert_called_once_with(os.getuid())
        self.assertEqual(module["HOME"], home)
        self.assertEqual(module["QUADLET_DIR"], home / ".config/containers/systemd")
        self.assertEqual(
            module["QUADLET_YAML"], home / ".config/containers/systemd/myproduct.yaml"
        )
        self.assertEqual(module["FILES_DIR"], home / "files")

    def test_install_rejects_mismatched_home_before_any_action(self):
        self.install_fixture()
        operator = self.root / "operator"
        environment = mock.patch.dict(os.environ, {"HOME": str(operator)})
        renderer = mock.patch.object(deploy, "render")
        with environment, renderer as render:
            with self.assertRaisesRegex(
                deploy.DeployError, "HOME=.*differs.*user database"
            ) as failure:
                deploy.install()
            render.assert_not_called()
        self.assertIn(str(deploy.HOME), str(failure.exception))
        self.process.assert_not_called()
        self.assertFalse(deploy.QUADLET_DIR.exists())
        self.assertFalse(deploy.FILES_DIR.exists())

    def test_install_accepts_absent_home_using_user_database(self):
        self.install_fixture()
        os.environ.pop("HOME", None)
        deploy.install()
        self.assertTrue(deploy.QUADLET_YAML.is_file())

    def test_runtime_fallback_reaches_subprocesses(self):
        self.install_fixture()
        os.environ.pop("XDG_RUNTIME_DIR", None)
        original = Path.is_dir
        seen = []

        def is_dir(path):
            return True if path == Path("/run/user/1000") else original(path)

        def command(*args, **kwargs):
            seen.append(os.environ.get("XDG_RUNTIME_DIR"))

        self.process.side_effect = command
        with mock.patch.object(Path, "is_dir", is_dir):
            deploy.install()
        self.assertEqual(seen, ["/run/user/1000"] * 7)

    def test_existing_runtime_is_preserved(self):
        self.install_fixture()
        runtime = os.environ["XDG_RUNTIME_DIR"]
        self.process.side_effect = lambda *a, **k: self.assertEqual(
            os.environ["XDG_RUNTIME_DIR"], runtime
        )
        deploy.install()

    def test_missing_runtime_stops_before_render_and_commands(self):
        os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"
        directory = mock.patch.object(Path, "is_dir", return_value=False)
        renderer = mock.patch.object(deploy, "render")
        with directory, renderer as render:
            with self.assertRaisesRegex(
                deploy.DeployError, "runtime directory.*linger"
            ):
                deploy.install()
            render.assert_not_called()
        self.process.assert_not_called()
        self.assertFalse(deploy.QUADLET_DIR.exists())

    def test_foreign_runtime_is_rejected_before_any_action(self):
        for configured in (
            "/run/user/0",
            "/run/user/2000",
            "",
            str(self.root / "runtime"),
        ):
            with self.subTest(runtime=configured):
                os.environ["XDG_RUNTIME_DIR"] = configured
                renderer = mock.patch.object(deploy, "render")
                with renderer as render:
                    with self.assertRaisesRegex(
                        deploy.DeployError, "XDG_RUNTIME_DIR=.*expected /run/user/1000"
                    ) as error:
                        deploy.install()
                    self.assertIn(repr(configured), str(error.exception))
                    render.assert_not_called()
                self.process.assert_not_called()

    def test_install_order_files_and_permissions(self):
        self.install_fixture()
        events = []

        def command(args, check):
            self.assertTrue(check)
            events.append(args)
            if args[0] == "podman" and args[1] in ("load", "image"):
                self.assertFalse((deploy.FILES_DIR / "uploads.tar").exists())
                self.assertFalse(deploy.QUADLET_YAML.exists())
            if args[0] == "systemctl":
                self.assertTrue((deploy.FILES_DIR / "uploads.tar").exists())
                self.assertTrue(deploy.QUADLET_YAML.exists())
                self.assertEqual(
                    deploy.QUADLET_TARGET.with_suffix(".network").read_bytes(),
                    deploy.QUADLET_TEMPLATE.with_suffix(".network").read_bytes(),
                )
                self.assertEqual(
                    deploy.QUADLET_TARGET.read_bytes(),
                    deploy.QUADLET_TEMPLATE.read_bytes(),
                )

        self.process.side_effect = command
        deploy.install()
        self.assertEqual(
            events,
            [
                ["podman", "load", "-i", str(self.root / "images/images.tar")],
                ["podman", "image", "exists", "localhost/app:1"],
                ["podman", "image", "exists", "localhost/init:1"],
                ["systemctl", "--user", "daemon-reload"],
                ["systemctl", "--user", "restart", "myproduct.service"],
                ["systemctl", "--user", "is-active", "--quiet", "myproduct.service"],
                ["podman", "ps", "--all", "--pod"],
            ],
        )
        for path, mode in (
            (deploy.QUADLET_YAML, 0o600),
            (deploy.QUADLET_TARGET, 0o644),
            (deploy.QUADLET_TARGET.with_suffix(".network"), 0o644),
            (deploy.FILES_DIR, 0o700),
            (deploy.FILES_DIR / "uploads.tar", 0o600),
        ):
            self.assertEqual(self.mode(path), mode)
        docs = list(yaml.safe_load_all(deploy.QUADLET_YAML.read_text()))
        self.assertEqual(
            docs[0]["metadata"]["annotations"][deploy.IMPORT_SOURCE],
            str(deploy.FILES_DIR / "uploads.tar"),
        )

    def test_command_failure_returns_one_with_hints_and_stops(self):
        self.install_fixture()
        for failing in (0, 3, 4, 5, 6):
            with self.subTest(failing=failing):
                self.process.reset_mock()
                self.process.side_effect = [None] * failing + [
                    subprocess.CalledProcessError(1, "test-command")
                ]
                self.stderr.seek(0)
                self.stderr.truncate()
                with mock.patch.object(deploy.sys, "argv", ["deploy", "install"]):
                    self.assertEqual(deploy.main(), 1)
                self.assertEqual(self.process.call_count, failing + 1)
                self.assertIn(
                    "journalctl --user -u myproduct.service", self.stderr.getvalue()
                )
                self.assertIn("podman-user-generator --dryrun", self.stderr.getvalue())
                self.assertNotIn("Traceback", self.stderr.getvalue())

    def test_invalid_arguments_return_two_without_side_effects(self):
        for args in ([], ["unknown"], ["prepare", "extra"], ["install", "prepare"]):
            argv = mock.patch.object(deploy.sys, "argv", ["deploy"] + args)
            with self.subTest(args=args), argv:
                self.assertEqual(deploy.main(), 2)
        self.process.assert_not_called()
        self.assertFalse(deploy.BUILD.exists())

    def test_prepare_success_and_validation_failure_exit_codes(self):
        with mock.patch.object(deploy.sys, "argv", ["deploy", "prepare"]):
            self.assertEqual(deploy.main(), 0)
            self.write("config.yaml", "HTTPS_PORT: invalid")
            self.assertEqual(deploy.main(), 1)
        self.assertIn("ERROR:", self.stderr.getvalue())

    def test_missing_archive_stops_before_quadlet(self):
        self.install_fixture()
        (self.root / "images/images.tar").unlink()
        with mock.patch.object(deploy.sys, "argv", ["deploy", "install"]):
            self.assertEqual(deploy.main(), 1)
        self.assertIn("Missing image archive", self.stderr.getvalue())
        self.assertIn("images.tar", self.stderr.getvalue())
        self.process.assert_not_called()
        self.assertFalse(deploy.QUADLET_DIR.exists())

    def test_missing_image_stops_before_quadlet_and_names_image(self):
        self.install_fixture()
        for failing, image in ((1, "localhost/app:1"), (2, "localhost/init:1")):
            with self.subTest(image=image):
                self.process.reset_mock()
                self.process.side_effect = [None] * failing + [
                    subprocess.CalledProcessError(
                        1, ["podman", "image", "exists", image]
                    )
                ]
                self.stderr.seek(0)
                self.stderr.truncate()
                with mock.patch.object(deploy.sys, "argv", ["deploy", "install"]):
                    self.assertEqual(deploy.main(), 1)
                self.assertIn("ERROR:", self.stderr.getvalue())
                self.assertIn(image, self.stderr.getvalue())
                self.assertNotIn("Traceback", self.stderr.getvalue())
                self.assertEqual(self.process.call_count, failing + 1)
                self.assertFalse(deploy.QUADLET_DIR.exists())

    def test_failed_image_check_preserves_existing_quadlet_files(self):
        self.install_fixture()
        deploy.QUADLET_DIR.mkdir(parents=True)
        deploy.QUADLET_YAML.write_text("old yaml")
        deploy.QUADLET_TARGET.write_text("old kube")
        self.process.side_effect = [None, subprocess.CalledProcessError(125, "exists")]
        with self.assertRaisesRegex(deploy.DeployError, "localhost/app:1.*exit 125"):
            deploy.install()
        self.assertEqual(deploy.QUADLET_YAML.read_text(), "old yaml")
        self.assertEqual(deploy.QUADLET_TARGET.read_text(), "old kube")

    def test_failed_image_operations_preserve_existing_archives(self):
        self.install_fixture()
        archive = deploy.FILES_DIR / "uploads.tar"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"previous archive")
        for failing in (0, 1, 2):
            with self.subTest(failing=failing):
                self.process.side_effect = [None] * failing + [
                    subprocess.CalledProcessError(1, "podman")
                ]
                with mock.patch.object(deploy.sys, "argv", ["deploy", "install"]):
                    self.assertEqual(deploy.main(), 1)
                self.assertEqual(archive.read_bytes(), b"previous archive")
                self.assertFalse(deploy.QUADLET_DIR.exists())
        (self.root / "images/images.tar").unlink()
        with self.assertRaisesRegex(deploy.DeployError, "Missing image archive"):
            deploy.install()
        self.assertEqual(archive.read_bytes(), b"previous archive")

    def test_install_validates_rendered_image_names(self):
        self.install_fixture()
        for image in ("postgres:16", "team/app:1"):
            with self.subTest(image=image):
                self.config["APP_IMAGE"] = image
                self.write_config()
                self.process.reset_mock()
                with self.assertRaisesRegex(deploy.DeployError, "fully qualified"):
                    deploy.install()
                self.process.assert_called_once_with(
                    ["podman", "load", "-i", str(self.root / "images/images.tar")],
                    check=True,
                )
                self.assertFalse(deploy.QUADLET_DIR.exists())


class ImageTests(unittest.TestCase):
    def test_image_errors_identify_container_and_group(self):
        """Keep the container name in every image error, also after splitting off the registry."""
        for group in ("containers", "initContainers"):
            for image in (None, "postgres:16", "@@IMAGE@@"):
                with self.subTest(group=group, image=image):
                    doc = {"spec": {group: [{"name": "backend", "image": image}]}}
                    with self.assertRaises(deploy.DeployError) as error:
                        deploy.find_images([doc])
                    self.assertIn("'backend'", str(error.exception))
                    self.assertIn(group, str(error.exception))

    def test_pods_deployments_duplicates_and_init_containers(self):
        docs = [
            None,
            {
                "kind": "Pod",
                "spec": {
                    "containers": [{"image": "localhost/app:1"}],
                    "initContainers": [{"image": "registry.firma.no/team/init:1"}],
                },
            },
            {
                "kind": "Deployment",
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {"image": "docker.io/library/postgres:16"},
                                {"image": "localhost/app:1"},
                            ],
                            "initContainers": [{"image": "localhost/app:1"}],
                        }
                    }
                },
            },
            {"kind": "ConfigMap", "data": {"image": "ignored"}},
        ]
        self.assertEqual(
            deploy.find_images(docs),
            [
                "docker.io/library/postgres:16",
                "localhost/app:1",
                "registry.firma.no/team/init:1",
            ],
        )

    def test_no_images(self):
        for docs in (
            [],
            [None],
            [{"image": "localhost/ignored:1"}],
            [{"spec": {"containers": []}}],
        ):
            error = self.assertRaisesRegex(deploy.DeployError, "No images")
            with self.subTest(docs=docs), error:
                deploy.find_images(docs)

    def test_rejects_placeholders_and_unqualified_names(self):
        for image, error in (
            ("@@IMAGE@@", "placeholders"),
            ("localhost/app:@@VERSION@@", "placeholders"),
            ("postgres:16", "fully qualified"),
            ("team/app:1", "fully qualified"),
            ("localhost", "fully qualified"),
            ("localhost/", "fully qualified"),
        ):
            expected = self.assertRaisesRegex(deploy.DeployError, error)
            with self.subTest(image=image), expected:
                deploy.find_images([{"spec": {"containers": [{"image": image}]}}])

    def test_accepts_full_registry_names_and_ports(self):
        for image in (
            "docker.io/library/postgres:16",
            "registry.firma.no/team/app:1",
            "localhost/myapp:1.0.0",
            "registry:5000/team/app:1",
        ):
            with self.subTest(image=image):
                self.assertEqual(
                    deploy.find_images([{"spec": {"containers": [{"image": image}]}}]),
                    [image],
                )

    def test_invalid_image_values_are_expected_errors(self):
        for container in (
            {},
            {"image": None},
            {"image": 42},
            {"image": ""},
            {"image": []},
            "invalid",
        ):
            error = self.assertRaisesRegex(deploy.DeployError, "image name as a string")
            with self.subTest(container=container), error:
                deploy.find_images([{"spec": {"containers": [container]}}])


if __name__ == "__main__":
    unittest.main()
