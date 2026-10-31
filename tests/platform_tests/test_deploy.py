"""Isolated renderer/installer tests; no Podman, systemd, root or network."""

import base64
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from deployment import cli, common
from deployment import render as rendering

from helpers.deploy_fixture import DeployFixture, document
from helpers.render_helper import materialize_and_render


class ConfigTests(DeployFixture):
    def test_strings_and_integers_preserve_types(self):
        self.config.update(TEXT="no", NUMBER=42, EMPTY="", ZERO=0, NEGATIVE=-7)
        self.write_config()
        self.assertEqual(
            rendering.load_config(common.ROOT / "config.yaml"), self.config
        )

    def test_rejects_non_scalar_config_values(self):
        for value in (True, False, None, 1.5, [], {}, ["a"], {"a": "b"}):
            with self.subTest(value=value):
                self.config["VALUE"] = value
                self.write_config()
                with self.assertRaisesRegex(
                    common.DeployError, "VALUE.*string or an integer"
                ):
                    rendering.load_config(common.ROOT / "config.yaml")

    def test_invalid_values_are_not_disclosed(self):
        """Keep secret-bearing invalid config values out of errors and CLI output."""
        private = "synthetic-private-value"
        for key, value in (
            ("VALUE", [private]),
            ("VALUE", {"token": private}),
            ("HTTPS_PORT", private),
        ):
            with self.subTest(key=key, value_type=type(value).__name__):
                self.config = {"HTTPS_PORT": 8443, key: value}
                self.write_config()
                with self.assertRaises(common.DeployError) as caught:
                    rendering.load_config(common.ROOT / "config.yaml")
                self.assertNotIn(private, str(caught.exception))
                with mock.patch.object(sys, "argv", ["deploy.sh", "prepare"]):
                    self.assertEqual(cli.main(), 1)
                self.assertNotIn(
                    private, self.stdout.getvalue() + self.stderr.getvalue()
                )

    def test_rejects_non_mapping_document(self):
        for text in ("", "null", "[]", "text", "42"):
            with self.subTest(text=text):
                self.write("config.yaml", text)
                with self.assertRaisesRegex(common.DeployError, "KEY: value"):
                    rendering.load_config(common.ROOT / "config.yaml")

    def test_rejects_non_string_keys(self):
        for key in (12, True, None):
            with self.subTest(key=key):
                self.write(
                    "config.yaml", yaml.safe_dump({key: "x", "HTTPS_PORT": 8443})
                )
                with self.assertRaisesRegex(common.DeployError, "keys.*strings"):
                    rendering.load_config(common.ROOT / "config.yaml")

    def test_port_boundaries(self):
        for port in (1, 65535):
            with self.subTest(port=port):
                self.config["HTTPS_PORT"] = port
                self.write_config()
                self.assertEqual(
                    rendering.load_config(common.ROOT / "config.yaml")["HTTPS_PORT"],
                    port,
                )

    def test_invalid_ports_and_missing_port(self):
        for port in (0, -1, 65536, "8443", True, False, None, 1.5, [], {}):
            with self.subTest(port=port):
                self.config["HTTPS_PORT"] = port
                self.write_config()
                with self.assertRaisesRegex(common.DeployError, "HTTPS_PORT"):
                    rendering.load_config(common.ROOT / "config.yaml")
        # Only components using it need HTTPS_PORT; their placeholders require it.
        self.config.pop("HTTPS_PORT")
        self.write_config()
        self.assertNotIn(
            "HTTPS_PORT", rendering.load_config(common.ROOT / "config.yaml")
        )

    def test_duplicate_key_reports_second_line(self):
        self.write(
            "config.yaml", "HTTPS_PORT: 8443\nHOSTNAME: first\nHOSTNAME: second\n"
        )
        with self.assertRaises(yaml.YAMLError) as caught:
            rendering.load_config(common.ROOT / "config.yaml")
        self.assertIn("duplicate key 'HOSTNAME'", str(caught.exception))
        self.assertIn("line 3", str(caught.exception))

    def test_invalid_yaml_does_not_disclose_source_values(self):
        """Retain YAML line diagnostics without echoing secret-bearing source lines."""
        for text in (
            "HTTPS_PORT: 8443\nTOKEN: first\nTOKEN: private-value\n",
            "HTTPS_PORT: 8443\nTOKEN: [private-value\n",
        ):
            self.write("config.yaml", text)
            with self.assertRaises(yaml.YAMLError) as caught:
                rendering.load_config(common.ROOT / "config.yaml")
            self.assertIn("line", str(caught.exception))
            self.assertNotIn("private-value", str(caught.exception))

    def test_duplicate_nested_key_reports_line(self):
        self.write(
            "config.yaml",
            "HTTPS_PORT: 8443\nSECRET_FILES:\n  a: [{path: one}]\n  a: [{path: two}]\n",
        )
        with self.assertRaisesRegex(yaml.YAMLError, "line 4"):
            rendering.load_config(common.ROOT / "config.yaml")

    def test_groups_are_validated_separately(self):
        self.config.update(
            SECRET_FILES={"a": [{"path": "one"}]}, VOLUME_FILES={"b": [{"path": "two"}]}
        )
        self.write_config()
        self.assertEqual(
            rendering.load_config(common.ROOT / "config.yaml"), self.config
        )


class ReplaceTests(unittest.TestCase):
    def test_preserves_integer_and_string_types(self):
        for value in (8443, "8443", "no", ""):
            with self.subTest(value=value):
                result = rendering.replace("@@VALUE@@", {"VALUE": value})
                self.assertEqual(result, value)
                self.assertIs(type(result), type(value))

    def test_missing_key(self):
        with self.assertRaisesRegex(common.DeployError, "Missing MISSING"):
            rendering.replace("@@MISSING@@", {})

    def test_nested_maps_and_lists(self):
        source = {"outer": [{"port": "@@PORT@@", "list": ["@@TEXT@@", None, True]}]}
        self.assertEqual(
            rendering.replace(source, {"PORT": 1234, "TEXT": "ok"}),
            {"outer": [{"port": 1234, "list": ["ok", None, True]}]},
        )
        self.assertEqual(source["outer"][0]["port"], "@@PORT@@")

    def test_partial_placeholder_is_left_for_render_validation(self):
        self.assertEqual(rendering.replace("prefix-@@X@@", {"X": "ok"}), "prefix-@@X@@")


class FileGroupTests(DeployFixture):
    def test_multiple_secrets_directory_and_binary_roundtrip(self):
        binary = bytes(range(256)) + b"\x00\xff\r\n"
        self.write("input/token.txt", "example only\n")
        self.write("input/binary.bin", binary)
        self.write("other/item", b"second")
        groups = self.file_config(
            "SECRET_FILES", {"first": ["input"], "second": ["other/item"]}
        )
        docs = {
            doc["metadata"]["name"]: doc for doc in rendering.secret_documents(groups)
        }
        self.assertEqual(set(docs), {"first", "second"})
        self.assertEqual(set(docs["first"]["data"]), {"token.txt", "binary.bin"})
        self.assertEqual(base64.b64decode(docs["first"]["data"]["binary.bin"]), binary)
        self.assertEqual(base64.b64decode(docs["second"]["data"]["item"]), b"second")

    def test_secret_filenames(self):
        for name in ("with space", "\u00e6.txt", "bad@name"):
            with self.subTest(name=name):
                self.write(name)
                with self.assertRaisesRegex(common.DeployError, "the file name"):
                    self.file_config("SECRET_FILES", {"test": [name]})
        self.write("OK-a_b.c")
        self.assertIn("test", self.file_config("SECRET_FILES", {"test": ["OK-a_b.c"]}))

    def test_secret_rejects_subdirectory(self):
        self.write("tree/nested/file")
        with self.assertRaisesRegex(
            common.DeployError, "Secrets can only contain files"
        ):
            self.file_config("SECRET_FILES", {"test": ["tree"]})

    def test_secret_limit_is_per_id_and_counts_document_overhead(self):
        self.write("first", b"a" * 200000)
        self.write("second", b"b" * 200000)
        groups = self.file_config(
            "SECRET_FILES", {"first": ["first"], "second": ["second"]}
        )
        self.assertEqual(len(rendering.secret_documents(groups)), 2)
        with self.assertRaisesRegex(common.DeployError, "too large.*Podman secret"):
            rendering.secret_documents(
                {"combined": [self.root / "first", self.root / "second"]}
            )
        self.write("boundary", b"x" * (common.MAX_SECRET_SIZE * 3 // 4))
        with self.assertRaisesRegex(common.DeployError, "too large"):
            rendering.secret_documents({"boundary": [self.root / "boundary"]})

    def test_tilde_and_absolute_paths(self):
        path = self.write("home/test.bin", b"\x00\xff")
        with mock.patch.dict(os.environ, {"HOME": str(path.parent)}):
            groups = self.file_config("SECRET_FILES", {"test": ["~/test.bin"]})
        self.assertEqual(groups["test"], [path])
        self.assertEqual(rendering.resolve_path(str(path), self.root), path)

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
                error = self.assertRaises(common.DeployError)
                with self.subTest(group=group, spec=spec):
                    with error:
                        self.file_config(group, spec)

    def test_missing_file_and_name_collisions(self):
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            with self.subTest(group=group):
                with self.assertRaisesRegex(common.DeployError, "Missing"):
                    self.file_config(group, {"test": ["missing"]})
                self.write("a/file")
                self.write("b/file")
                for entries in (["a", "b"], ["a/file", "a/file"]):
                    with self.assertRaisesRegex(common.DeployError, "same name"):
                        self.file_config(group, {"test": entries})

    def test_false_like_groups_are_not_empty_mappings(self):
        """Reject non-map file groups even when their values are false-like."""
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            for value in (False, 0, "", [], None):
                error = self.assertRaisesRegex(common.DeployError, group)
                with self.subTest(group=group, value_type=type(value).__name__):
                    with error:
                        self.file_config(group, value)

    def test_absent_groups(self):
        for group in ("SECRET_FILES", "VOLUME_FILES"):
            self.assertEqual(
                rendering.load_file_group(self.config, group, self.root), {}
            )


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
        output = common.BUILD / "files"
        rendering.write_file_archives(groups, output)
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

    def test_archive_checksums_ignore_timestamps_but_detect_content_changes(self):
        """Equivalent staged registrations have identical bytes despite fresh file/dir times."""
        source = self.write("stage/app1/client.json", "public-client")
        output = common.BUILD / "files"
        volumes = {"identity-clients": [source.parent]}
        rendering.write_file_archives(volumes, output)
        archive = output / "identity-clients.tar"
        before = archive.read_bytes()
        os.utime(str(source), (10, 10))
        os.utime(str(source.parent), (20, 20))
        rendering.write_file_archives(volumes, output)
        self.assertEqual(archive.read_bytes(), before)
        with tarfile.open(str(archive)) as tar:
            self.assertTrue(all(member.mtime == 0 for member in tar.getmembers()))
        source.write_text("changed-public-client")
        rendering.write_file_archives(volumes, output)
        self.assertNotEqual(archive.read_bytes(), before)

    def test_existing_archive_permissions_are_restricted(self):
        item = self.write("item")
        output = common.BUILD / "files"
        self.write("build/files/one.tar", "old", 0o666)
        output.chmod(0o777)
        rendering.write_file_archives({"one": [item]}, output)
        self.assertEqual(self.mode(output), 0o700)
        self.assertEqual(self.mode(output / "one.tar"), 0o600)

    def test_claim_points_at_requested_archive(self):
        claims = rendering.volume_claims({"one": [], "two": []}, common.FILES_DIR)
        self.assertEqual([doc["metadata"]["name"] for doc in claims], ["one", "two"])
        self.assertEqual(
            claims[0]["metadata"]["annotations"][common.IMPORT_SOURCE],
            str(common.FILES_DIR / "one.tar"),
        )

    def test_empty_volumes_do_not_create_directory(self):
        rendering.write_file_archives({}, common.FILES_DIR)
        self.assertFalse(common.FILES_DIR.exists())


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
                    rendering.check_links(docs, {(kind, "known"): "config.known"})
                    self.assertEqual(
                        rendering.references(docs, set()), {(kind, "known")}
                    )

    def test_every_missing_reference(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            for ref in self.refs(kind, "missing"):
                error = self.assertRaisesRegex(
                    common.DeployError, kind + ".*missing.*does not exist"
                )
                with self.subTest(kind=kind, ref=ref):
                    with error:
                        rendering.check_links([ref], {})

    def test_duplicate_definitions(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            error = self.assertRaisesRegex(common.DeployError, "defined more than once")
            with self.subTest(kind=kind):
                with error:
                    rendering.check_links(
                        [document(kind, "same"), document(kind, "same")], {}
                    )

    def test_volume_names_are_unique_across_secret_pvc_and_configmap(self):
        kinds = ("Secret", "PersistentVolumeClaim", "ConfigMap")
        for first in kinds:
            for second in kinds:
                error = self.assertRaisesRegex(
                    common.DeployError, "same.*more than once"
                )
                with self.subTest(first=first, second=second):
                    with error:
                        rendering.check_links(
                            [document(first, "same"), document(second, "same")], {}
                        )

    def test_configmap_does_not_satisfy_secret_or_pvc_reference(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            error = self.assertRaisesRegex(common.DeployError, "does not exist")
            with self.subTest(kind=kind):
                with error:
                    rendering.check_links(
                        [document("ConfigMap", "known")] + self.refs(kind, "known"), {}
                    )

    def test_unused_config_ids(self):
        for kind, group in (
            ("Secret", "SECRET_FILES"),
            ("PersistentVolumeClaim", "VOLUME_FILES"),
        ):
            error = self.assertRaisesRegex(common.DeployError, group + ".id.*not used")
            with self.subTest(kind=kind):
                with error:
                    rendering.check_links(
                        [document(kind, "id")], {(kind, "id"): group + ".id"}
                    )

    def test_manifest_defined_objects_are_allowed_even_if_unused(self):
        docs = [
            document("Secret", "same", stringData={"token": "test"}),
            document("PersistentVolumeClaim", "data"),
        ]
        rendering.check_links(docs, {})
        rendering.check_links(
            docs
            + self.refs("Secret", "same")
            + self.refs("PersistentVolumeClaim", "data"),
            {},
        )


class GeneratedSecretTests(DeployFixture):
    """Test one-time private files and their existing SECRET_FILES delivery."""

    def configure_generated(self):
        """Add a generated file and a manifest envFrom Secret reference."""
        self.config["SECRET_FILES"] = {
            "app-secrets": [{"path": "credentials/app", "generate": ["key"]}]
        }
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
        return self.root / "credentials/app/key"

    def test_prepare_creates_private_alphanumeric_file_without_logging_value(self):
        """Generate 32 characters once and deliver their bytes through SECRET_FILES."""
        path = self.configure_generated()
        text = materialize_and_render()
        value = path.read_bytes()
        self.assertEqual(len(value), 32)
        self.assertTrue(
            all(
                chr(byte) in rendering.string.ascii_letters + rendering.string.digits
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
        docs = list(yaml.safe_load_all(text))
        secret = next(doc for doc in docs if doc["kind"] == "Secret")
        self.assertTrue(
            base64.b64decode(secret["data"]["key"]) == value, "Secret bytes differ"
        )
        materialize_and_render()
        self.assertTrue(
            path.read_bytes() == value, "Repeated prepare changed the secret"
        )
        self.process.assert_not_called()

    def test_empty_or_directory_path_is_not_regenerated(self):
        """Reject empty files and directory targets without replacing them."""
        path = self.configure_generated()
        self.write("credentials/app/key", b"")
        with self.assertRaisesRegex(common.DeployError, "empty"):
            materialize_and_render()
        self.assertEqual(path.stat().st_size, 0)
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(common.DeployError, "regular file"):
            materialize_and_render()
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
                with self.assertRaisesRegex(common.DeployError, "config directory"):
                    rendering.generate_secrets(
                        {
                            "SECRET_FILES": {
                                "generated": [{"path": ".", "generate": [entry]}]
                            }
                        },
                        self.root,
                    )
                self.assertFalse((outside / "key").exists())

    def test_invalid_list_and_entries_are_rejected(self):
        """Require generation to be a list of relative file paths on a source."""
        for entries in (None, "key", {}, 1, [False], [1]):
            error = self.assertRaisesRegex(common.DeployError, "list")
            with self.subTest(entries=entries):
                with error:
                    rendering.generate_secrets(
                        {
                            "SECRET_FILES": {
                                "generated": [{"path": ".", "generate": entries}]
                            }
                        },
                        self.root,
                    )

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
            rendering.generate_secrets(self.config, self.root)
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

    def test_configmap_data_spec_is_not_a_pod_specification(self):
        """Render valid ConfigMap data named spec without treating it as a pod."""
        self.manifest([document("ConfigMap", "settings", data={"spec": "plain text"})])
        docs = list(yaml.safe_load_all(materialize_and_render()))
        self.assertEqual(docs[0]["data"]["spec"], "plain text")

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
        self.assertIn("settings", materialize_and_render())

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
                    common.DeployError, "10-app.yaml.*ConfigMap.*missing"
                ):
                    materialize_and_render()
                self.assertFalse(common.BUILD.exists())

    def test_mounts_and_never_policy_accept_containers_and_init(self):
        """Validate regular and init containers in Pod specs."""
        self.manifest([document("ConfigMap", "settings")], "90-settings.yaml")
        for group in ("containers", "initContainers"):
            with self.subTest(group=group):
                self.manifest([self.pod(group)], "10-app.yaml")
                materialize_and_render(write_archives=False)

    def test_unsupported_kinds_fail_before_generation_or_output(self):
        """The same valid pod spec in a Deployment or List is refused, not half-checked."""
        self.config["SECRET_FILES"] = {
            "db": [{"path": "secrets/db", "generate": ["password"]}]
        }
        self.write_config()
        spec = self.pod("containers")["spec"]
        for doc in (
            document("Deployment", "app", spec={"template": {"spec": spec}}),
            {"kind": "List", "items": [self.pod("containers")]},
            {"spec": spec},
            ["not", "a", "map"],
        ):
            with self.subTest(doc=doc):
                self.manifest([doc], "10-app.yaml")
                with self.assertRaisesRegex(
                    common.DeployError, "10-app.yaml: unsupported resource kind"
                ):
                    materialize_and_render()
                self.assertFalse((self.root / "secrets").exists())
                self.assertFalse(common.BUILD.exists())
        self.process.assert_not_called()

    def test_unknown_mounts_report_file_and_container(self):
        """Reject mounts absent from the pod volumes in both container groups."""
        for group in ("containers", "initContainers"):
            with self.subTest(group=group):
                self.manifest([self.pod(group, mount="missing")], "10-app.yaml")
                with self.assertRaisesRegex(
                    common.DeployError, "10-app.yaml.*worker.*undefined volume.*missing"
                ):
                    materialize_and_render()
                self.assertFalse(common.BUILD.exists())

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
                        common.DeployError,
                        "10-app.yaml.*worker.*imagePullPolicy: Never",
                    ):
                        materialize_and_render()
                    self.assertFalse(common.BUILD.exists())


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
                with self.assertRaises(common.DeployError) as error:
                    materialize_and_render()
                self.assertIn(
                    str((common.ROOT / "manifests") / "42-bad.yaml"),
                    str(error.exception),
                )
                self.assertIn(message, str(error.exception))
                self.assertFalse(common.BUILD.exists())

    def test_render_without_archive_writes_still_validates(self):
        self.volume_fixture()
        text = materialize_and_render(common.FILES_DIR, write_archives=False)
        self.assertIn(str(common.FILES_DIR / "uploads.tar"), text)
        self.assertFalse(common.FILES_DIR.exists())
        self.manifest([document("ConfigMap", "uploads")], "99-collision.yaml")
        with self.assertRaisesRegex(common.DeployError, "uploads.*more than once"):
            materialize_and_render(common.FILES_DIR, write_archives=False)
        self.assertFalse(common.FILES_DIR.exists())

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
        docs = list(yaml.safe_load_all(materialize_and_render()))
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
                with self.assertRaisesRegex(common.DeployError, error):
                    materialize_and_render()
                self.assertFalse(common.BUILD.exists())
        self.manifest([document("Pod", "bad", value="@@BAD@@")], "99-bad.yaml")
        old = self.write("build/files/uploads.tar", b"previous archive")
        with self.assertRaises(common.DeployError):
            materialize_and_render()
        self.assertEqual(old.read_bytes(), b"previous archive")

    def test_no_archives_for_unused_id_or_large_secret(self):
        self.volume_fixture()
        ((common.ROOT / "manifests") / "10-pod.yaml").unlink()
        with self.assertRaisesRegex(common.DeployError, "not used"):
            materialize_and_render()
        self.assertFalse(common.BUILD.exists())
        # Size needs the file bytes, so it is checked after the declarations.
        self.volume_fixture()
        self.write("large", b"x" * 400000)
        self.file_config("SECRET_FILES", {"large": ["large"]})
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
                            },
                            {"name": "large", "secret": {"secretName": "large"}},
                        ]
                    },
                )
            ],
            "10-pod.yaml",
        )
        with self.assertRaisesRegex(common.DeployError, "too large"):
            materialize_and_render()
        self.assertFalse(common.BUILD.exists())

    def test_duplicate_manifest_keys_report_line(self):
        self.write("manifests/bad.yaml", "kind: Pod\nkind: Secret\n")
        with self.assertRaisesRegex(yaml.YAMLError, "line 2"):
            materialize_and_render()
        self.assertFalse(common.BUILD.exists())

    def test_missing_config(self):
        (common.ROOT / "config.yaml").unlink()
        with self.assertRaisesRegex(common.DeployError, "Missing"):
            materialize_and_render()


class CommandTests(DeployFixture):
    def test_separate_config_directory_resolves_secrets_and_volumes(self):
        for directory in ("dev", "home"):
            with self.subTest(directory=directory):
                config_path = self.write(
                    directory + "/config.yaml",
                    yaml.safe_dump(
                        {
                            "HTTPS_PORT": 8443,
                            "SECRET_FILES": {"secret": [{"path": "generated/key"}]},
                            "VOLUME_FILES": {
                                "uploads": [{"path": "generated/message"}]
                            },
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
                docs = list(
                    yaml.safe_load_all(materialize_and_render(config_path=config_path))
                )
                self.assertEqual(
                    base64.b64decode(docs[0]["data"]["key"]), b"persistent secret"
                )
                with tarfile.open(str(common.BUILD / "files/uploads.tar")) as archive:
                    content = archive.extractfile("message")
                    assert content is not None
                    with content:
                        self.assertEqual(content.read(), b"persistent volume")

    def test_invalid_arguments_return_two_without_side_effects(self):
        for args in ([], ["unknown"], ["prepare", "extra"], ["install", "prepare"]):
            argv = mock.patch.object(cli.sys, "argv", ["deploy.sh"] + args)
            with self.subTest(args=args):
                with argv:
                    self.assertEqual(cli.main(), 2)
        self.process.assert_not_called()
        self.assertFalse(common.BUILD.exists())


class ImageTests(unittest.TestCase):
    def test_image_errors_identify_container_and_group(self):
        """Keep the container name in every image error, also after splitting off the registry."""
        for group in ("containers", "initContainers"):
            for image in (None, "postgres:16", "@@IMAGE@@"):
                with self.subTest(group=group, image=image):
                    doc = {
                        "kind": "Pod",
                        "spec": {group: [{"name": "backend", "image": image}]},
                    }
                    with self.assertRaises(common.DeployError) as error:
                        rendering.find_images([doc])
                    self.assertIn("'backend'", str(error.exception))
                    self.assertIn(group, str(error.exception))

    def test_pods_duplicates_and_init_containers(self):
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
                "kind": "Pod",
                "spec": {
                    "containers": [
                        {"image": "docker.io/library/postgres:16"},
                        {"image": "localhost/app:1"},
                    ],
                    "initContainers": [{"image": "localhost/app:1"}],
                },
            },
            {"kind": "ConfigMap", "data": {"image": "ignored"}},
        ]
        self.assertEqual(
            rendering.find_images(docs),
            [
                "docker.io/library/postgres:16",
                "localhost/app:1",
                "registry.firma.no/team/init:1",
            ],
        )

    def test_images_in_unsupported_kinds_are_refused_not_skipped(self):
        for doc in (
            {
                "kind": "Deployment",
                "spec": {"template": {"spec": {"containers": [{"image": "a"}]}}},
            },
            {"spec": {"containers": [{"image": "localhost/app:1"}]}},
        ):
            with self.subTest(doc=doc):
                with self.assertRaisesRegex(
                    common.DeployError, "unsupported resource kind"
                ):
                    rendering.find_images([doc])

    def test_no_images(self):
        for docs in (
            [],
            [None],
            [{"kind": "ConfigMap", "data": {"image": "localhost/ignored:1"}}],
            [{"kind": "Pod", "spec": {"containers": []}}],
        ):
            error = self.assertRaisesRegex(common.DeployError, "No images")
            with self.subTest(docs=docs):
                with error:
                    rendering.find_images(docs)

    def test_rejects_placeholders_and_unqualified_names(self):
        for image, error in (
            ("@@IMAGE@@", "placeholders"),
            ("localhost/app:@@VERSION@@", "placeholders"),
            ("postgres:16", "fully qualified"),
            ("team/app:1", "fully qualified"),
            ("localhost", "fully qualified"),
            ("localhost/", "fully qualified"),
        ):
            expected = self.assertRaisesRegex(common.DeployError, error)
            with self.subTest(image=image):
                with expected:
                    rendering.find_images(
                        [{"kind": "Pod", "spec": {"containers": [{"image": image}]}}]
                    )

    def test_accepts_full_registry_names_and_ports(self):
        for image in (
            "docker.io/library/postgres:16",
            "registry.firma.no/team/app:1",
            "localhost/myapp:1.0.0",
            "registry:5000/team/app:1",
        ):
            with self.subTest(image=image):
                self.assertEqual(
                    rendering.find_images(
                        [{"kind": "Pod", "spec": {"containers": [{"image": image}]}}]
                    ),
                    [image],
                )

    def test_invalid_image_values_are_expected_errors(self):
        for container in (
            {},
            {"image": None},
            {"image": 42},
            {"image": ""},
            {"image": []},
        ):
            error = self.assertRaisesRegex(common.DeployError, "image name as a string")
            with self.subTest(container=container):
                with error:
                    rendering.find_images(
                        [{"kind": "Pod", "spec": {"containers": [container]}}]
                    )
        with self.assertRaisesRegex(common.DeployError, "entries must be maps"):
            rendering.find_images([{"kind": "Pod", "spec": {"containers": ["x"]}}])


if __name__ == "__main__":
    unittest.main()
