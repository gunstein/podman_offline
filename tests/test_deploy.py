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
        runtime = self.root / "runtime"
        runtime.mkdir()
        self.stack.enter_context(
            mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)})
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
                            {"image": "@@APP_IMAGE@@"},
                            {"image": "localhost/app:1"},
                        ],
                        "initContainers": [{"image": "localhost/init:1"}],
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
                    deploy.DeployError, "VALUE.*tekst eller heltall"
                ):
                    deploy.load_config(deploy.CONFIG)

    def test_rejects_non_mapping_document(self):
        for text in ("", "null", "[]", "text", "42"):
            with self.subTest(text=text):
                self.write("config.yaml", text)
                with self.assertRaisesRegex(deploy.DeployError, "KEY: verdi"):
                    deploy.load_config(deploy.CONFIG)

    def test_rejects_non_string_keys(self):
        for key in (12, True, None):
            with self.subTest(key=key):
                self.write(
                    "config.yaml", yaml.safe_dump({key: "x", "HTTPS_PORT": 8443})
                )
                with self.assertRaisesRegex(deploy.DeployError, "nøkler.*tekst"):
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
        self.assertIn("duplikat nøkkel 'HOSTNAME'", str(caught.exception))
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
        with self.assertRaisesRegex(deploy.DeployError, "Mangler MISSING"):
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
                with self.assertRaisesRegex(deploy.DeployError, "filnavnet"):
                    self.file_config("SECRET_FILES", {"test": [name]})
        self.write("OK-a_b.c")
        self.assertIn("test", self.file_config("SECRET_FILES", {"test": ["OK-a_b.c"]}))

    def test_secret_rejects_subdirectory(self):
        self.write("tree/nested/file")
        with self.assertRaisesRegex(
            deploy.DeployError, "Secrets kan bare inneholde filer"
        ):
            self.file_config("SECRET_FILES", {"test": ["tree"]})

    def test_secret_limit_is_per_id_and_counts_document_overhead(self):
        self.write("first", b"a" * 200000)
        self.write("second", b"b" * 200000)
        groups = self.file_config(
            "SECRET_FILES", {"first": ["first"], "second": ["second"]}
        )
        self.assertEqual(len(deploy.secret_documents(groups)), 2)
        with self.assertRaisesRegex(deploy.DeployError, "for stor.*Podman-secret"):
            deploy.secret_documents(
                {"combined": [self.root / "first", self.root / "second"]}
            )
        self.write("boundary", b"x" * (deploy.MAX_SECRET_SIZE * 3 // 4))
        with self.assertRaisesRegex(deploy.DeployError, "for stor"):
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
                with self.assertRaisesRegex(deploy.DeployError, "Mangler"):
                    self.file_config(group, {"test": ["missing"]})
                self.write("a/file")
                self.write("b/file")
                for entries in (["a", "b"], ["a/file", "a/file"]):
                    with self.assertRaisesRegex(deploy.DeployError, "samme navn"):
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
                    deploy.DeployError, kind + ".*missing.*finnes ikke"
                )
                with self.subTest(kind=kind, ref=ref), error:
                    deploy.check_links([ref], {})

    def test_duplicate_definitions(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            error = self.assertRaisesRegex(deploy.DeployError, "definert flere ganger")
            with self.subTest(kind=kind), error:
                deploy.check_links([document(kind, "same"), document(kind, "same")], {})

    def test_volume_names_are_unique_across_secret_pvc_and_configmap(self):
        kinds = ("Secret", "PersistentVolumeClaim", "ConfigMap")
        for first in kinds:
            for second in kinds:
                error = self.assertRaisesRegex(deploy.DeployError, "same.*flere")
                with self.subTest(first=first, second=second), error:
                    deploy.check_links(
                        [document(first, "same"), document(second, "same")], {}
                    )

    def test_configmap_does_not_satisfy_secret_or_pvc_reference(self):
        for kind in ("Secret", "PersistentVolumeClaim"):
            error = self.assertRaisesRegex(deploy.DeployError, "finnes ikke")
            with self.subTest(kind=kind), error:
                deploy.check_links(
                    [document("ConfigMap", "known")] + self.refs(kind, "known"), {}
                )

    def test_unused_config_ids(self):
        for kind, group in (
            ("Secret", "SECRET_FILES"),
            ("PersistentVolumeClaim", "VOLUME_FILES"),
        ):
            error = self.assertRaisesRegex(
                deploy.DeployError, group + ".id.*brukes ikke"
            )
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


class RenderTests(DeployFixture):
    def test_render_without_archive_writes_still_validates(self):
        self.volume_fixture()
        text = deploy.render(deploy.FILES_DIR, write_archives=False)
        self.assertIn(str(deploy.FILES_DIR / "uploads.tar"), text)
        self.assertFalse(deploy.FILES_DIR.exists())
        self.manifest([document("ConfigMap", "uploads")], "99-collision.yaml")
        with self.assertRaisesRegex(deploy.DeployError, "uploads.*flere"):
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
            (document("Pod", "bad", value="prefix-@@HOSTNAME@@"), "Uerstattet"),
            (document("Pod", "bad", value="@@UNKNOWN@@"), "Mangler UNKNOWN"),
            (document("ConfigMap", "bad", data=["bad"]), "ConfigMap.data"),
            (
                document(
                    "Pod",
                    "bad",
                    spec={"persistentVolumeClaim": {"claimName": "unknown"}},
                ),
                "finnes ikke",
            ),
            (document("PersistentVolumeClaim", "uploads"), "definert flere ganger"),
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
        with self.assertRaisesRegex(deploy.DeployError, "brukes ikke"):
            deploy.render()
        self.assertFalse(deploy.BUILD.exists())
        self.write("large", b"x" * 400000)
        self.file_config("SECRET_FILES", {"large": ["large"]})
        with self.assertRaisesRegex(deploy.DeployError, "for stor"):
            deploy.render()
        self.assertFalse(deploy.BUILD.exists())

    def test_duplicate_manifest_keys_report_line(self):
        self.write("manifests/bad.yaml", "kind: Pod\nkind: Secret\n")
        with self.assertRaisesRegex(yaml.YAMLError, "line 2"):
            deploy.render()
        self.assertFalse(deploy.BUILD.exists())

    def test_missing_config(self):
        deploy.CONFIG.unlink()
        with self.assertRaisesRegex(deploy.DeployError, "Mangler"):
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

    def test_paths_follow_home(self):
        home = self.root / "other-service-user"
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            module = runpy.run_path(deploy.__file__, run_name="rootless_paths_test")
        self.assertEqual(module["QUADLET_DIR"], home / ".config/containers/systemd")
        self.assertEqual(
            module["QUADLET_YAML"], home / ".config/containers/systemd/myproduct.yaml"
        )
        self.assertEqual(module["FILES_DIR"], home / "files")

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
        for configured in ("", str(self.root / "missing-runtime")):
            with self.subTest(runtime=configured):
                os.environ["XDG_RUNTIME_DIR"] = configured
                directory = mock.patch.object(Path, "is_dir", return_value=False)
                renderer = mock.patch.object(deploy, "render")
                with directory, renderer as render:
                    with self.assertRaisesRegex(
                        deploy.DeployError, "runtime-katalog.*linger"
                    ):
                        deploy.install()
                    render.assert_not_called()
                self.process.assert_not_called()
                self.assertFalse(deploy.QUADLET_DIR.exists())

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
        self.assertIn("Mangler image-arkivet", self.stderr.getvalue())
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
        with self.assertRaisesRegex(deploy.DeployError, "Mangler image-arkivet"):
            deploy.install()
        self.assertEqual(archive.read_bytes(), b"previous archive")

    def test_install_validates_rendered_image_names(self):
        self.install_fixture()
        for image in ("postgres:16", "team/app:1"):
            with self.subTest(image=image):
                self.config["APP_IMAGE"] = image
                self.write_config()
                self.process.reset_mock()
                with self.assertRaisesRegex(deploy.DeployError, "fullt kvalifisert"):
                    deploy.install()
                self.process.assert_called_once_with(
                    ["podman", "load", "-i", str(self.root / "images/images.tar")],
                    check=True,
                )
                self.assertFalse(deploy.QUADLET_DIR.exists())


class ImageTests(unittest.TestCase):
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
            error = self.assertRaisesRegex(deploy.DeployError, "Ingen images")
            with self.subTest(docs=docs), error:
                deploy.find_images(docs)

    def test_rejects_placeholders_and_unqualified_names(self):
        for image, error in (
            ("@@IMAGE@@", "placeholders"),
            ("localhost/app:@@VERSION@@", "placeholders"),
            ("postgres:16", "fullt kvalifisert"),
            ("team/app:1", "fullt kvalifisert"),
            ("localhost", "fullt kvalifisert"),
            ("localhost/", "fullt kvalifisert"),
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
            error = self.assertRaisesRegex(deploy.DeployError, "image-navn som tekst")
            with self.subTest(container=container), error:
                deploy.find_images([{"spec": {"containers": [container]}}])


if __name__ == "__main__":
    unittest.main()
