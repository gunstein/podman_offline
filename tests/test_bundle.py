"""Build real bundle archives with only the Podman subprocess stubbed."""

import contextlib
import hashlib
import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import bundle


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(
            mock.patch.multiple(
                bundle,
                ROOT=self.root,
                STAGE=self.root / "build/bundle",
                DIST=self.root / "dist",
            )
        )
        self.output = self.stack.enter_context(
            contextlib.redirect_stdout(io.StringIO())
        )
        self.errors = self.stack.enter_context(
            contextlib.redirect_stderr(io.StringIO())
        )
        self.process = self.stack.enter_context(
            mock.patch.object(subprocess, "run", side_effect=self.save)
        )
        for name, text in {
            "VERSION": "1.2.3\n",
            "deploy": '#!/bin/sh\nexec python3 deploy.py "$@"\n',
            "deploy.py": "print('test fixture')\n",
            "README.md": "Test fixture only\n",
            "config.example.yaml": "HTTPS_PORT: 8443\n",
            "scripts/generate-certificates.sh": "#!/bin/sh\nexit 0\n",
            "scripts/prepare-host.sh": "#!/bin/sh\nexit 0\n",
            "dev/dev.sh": "#!/bin/sh\nexit 0\n",
            "dev/build-images.sh": "#!/bin/sh\nexit 0\n",
            "dev/smoke-test.py": "print('dev only')\n",
            "quadlet/myproduct.kube": "[Kube]\nYaml=myproduct.yaml\n",
            "quadlet/myproduct.network": "[Network]\nNetworkName=myproduct\n",
            "manifests/app.yaml": "kind: Pod\nspec:\n  initContainers:\n  - image: localhost/init:1\n  containers:\n  - name: app\n    image: localhost/app:1\n    imagePullPolicy: Never\n",
        }.items():
            self.write(name, text)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def save(self, args, check, **kwargs):
        """Stub registry pulls and write deterministic bytes for the multi-image save."""
        self.assertTrue(check)
        if args[:2] == ["podman", "pull"]:
            self.assertEqual(args[2], "--policy=always")
            self.assertEqual(
                kwargs, {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            )
            return
        self.assertEqual(args[:4], ["podman", "save", "-m", "-o"])
        Path(args[4]).write_bytes(("stub images " + " ".join(args[5:])).encode("utf-8"))

    def archive_bytes(self, archive, name):
        stream = archive.extractfile("myproduct-1.2.3/" + name)
        self.assertIsNotNone(stream)
        assert stream is not None
        with stream:
            return stream.read()

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
                    "deploy",
                    "deploy.py",
                    "README.md",
                    "config.example.yaml",
                    "scripts/generate-certificates.sh",
                    "scripts/prepare-host.sh",
                    "quadlet/myproduct.kube",
                    "quadlet/myproduct.network",
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
            for name in (
                "deploy",
                "scripts/generate-certificates.sh",
                "scripts/prepare-host.sh",
            ):
                self.assertEqual(archive.getmember(prefix + name).mode, 0o755)
            self.assertEqual(
                archive.getmember(prefix + "generated-certificates").mode, 0o700
            )
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

    def test_multiple_files_documents_flow_maps_and_deployments(self):
        self.write(
            "manifests/second.yaml",
            """# Empty document
---
kind: Deployment
spec:
  template:
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

    def test_invalid_image_fails_before_stage_is_removed_or_podman_runs(self):
        old = self.write("build/bundle/keep", "previous build")
        self.write(
            "manifests/bad.yaml",
            "spec:\n  initContainers:\n  - image: team/app:1\n",
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
                    yaml.safe_dump({"spec": {"containers": [{"image": image}]}}),
                )
                with self.assertRaises(bundle.BundleError):
                    bundle.manifest_images()
                self.assertEqual(bundle.main(), 1)
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
        self.assertEqual(bundle.main(), 1)
        self.assertIn("ERROR:", self.errors.getvalue())
        self.assertNotIn("Traceback", self.errors.getvalue())
        self.process.assert_not_called()

    def test_duplicate_manifest_keys_fail_before_build(self):
        self.write(
            "manifests/app.yaml",
            "spec:\n  containers:\n  - image: localhost/first:1\n"
            "    image: localhost/second:1\n",
        )
        self.assertEqual(bundle.main(), 1)
        self.assertIn("line 4", self.errors.getvalue())
        self.assertNotIn("Traceback", self.errors.getvalue())
        self.process.assert_not_called()
        self.assertFalse(bundle.STAGE.exists())

    def test_failed_save_returns_one_without_final_bundle(self):
        self.process.side_effect = subprocess.CalledProcessError(1, "podman save")
        self.assertEqual(bundle.main(), 1)
        self.assertIn("ERROR:", self.errors.getvalue())
        self.assertFalse(bundle.DIST.exists())

    def test_main_success(self):
        self.assertEqual(bundle.main(), 0)

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
            "spec: {containers: [{image: 'registry.example.test/app:2'}]}\n",
        )
        bundle.build()
        self.assertEqual(
            self.process.call_args_list[0].args[0],
            [
                "podman",
                "pull",
                "--policy=always",
                "registry.example.test/app:2",
            ],
        )
        self.assertEqual(
            self.process.call_args_list[1].args[0][-3:],
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
            "spec: {containers: [{image: 'registry.example.test/app:2'}]}\n",
        )
        self.process.side_effect = subprocess.CalledProcessError(
            125,
            "podman pull",
            output=b"private-auth-token",
            stderr=b"private-auth-token",
        )
        self.assertEqual(bundle.main(), 1)
        self.process.assert_called_once()
        self.assertIn("registry.example.test/app:2", self.errors.getvalue())
        self.assertIn("podman login registry.example.test", self.errors.getvalue())
        self.assertEqual(len(self.errors.getvalue().splitlines()), 1)
        self.assertNotIn(
            "private-auth-token", self.errors.getvalue() + self.output.getvalue()
        )
        self.assertFalse(bundle.DIST.exists())

    def test_sha256_reads_more_than_one_chunk(self):
        path = self.root / "large.bin"
        data = bytes(range(256)) * 8193
        path.write_bytes(data)
        self.assertEqual(bundle.sha256(path), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
