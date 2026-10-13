"""Test registry evidence and failure handling without Podman, TLS keys or network access."""

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml

spec = importlib.util.spec_from_file_location(
    "registry_test", Path(__file__).with_name("registry_test.py")
)
assert spec is not None and spec.loader is not None
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


class RegistryTests(unittest.TestCase):
    """Verify safe access evidence and exact pull/save/error criteria."""

    def setUp(self):
        """Capture output and use an isolated fixture directory."""
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.out, self.err = io.StringIO(), io.StringIO()
        self.stack.enter_context(contextlib.redirect_stdout(self.out))
        self.stack.enter_context(contextlib.redirect_stderr(self.err))

    def requests(self):
        """Build public manifest/blob response fixtures with private headers to omit."""
        return "\n".join(
            json.dumps(
                {
                    "http.request.method": "GET",
                    "http.response.status": 200,
                    "http.request.uri": "/v2/acceptance/busybox/" + suffix,
                    "authorization": "private-auth-token",
                }
            )
            for suffix in ("manifests/1.37.0", "blobs/sha256:" + "a" * 64)
        )

    def test_registry_logs_require_manifest_and_blob_gets_across_separate_streams(self):
        """Prove data download from both log streams without printing private log fields."""
        manifest, blob = self.requests().splitlines()
        result = subprocess.CompletedProcess([], 0, manifest, blob)
        with mock.patch.object(subprocess, "run", return_value=result) as command:
            registry.registry_requests("test-registry", "test-time")
        self.assertEqual(self.out.getvalue().count("REGISTRY_REQUEST"), 2)
        self.assertNotIn(
            "private-auth-token", self.out.getvalue() + self.err.getvalue()
        )
        self.assertEqual(command.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(command.call_args.kwargs["stderr"], subprocess.PIPE)

    def test_missing_or_failed_blob_download_fails(self):
        """Reject access evidence without a successful blob GET."""
        manifest = self.requests().splitlines()[0]
        result = subprocess.CompletedProcess([], 0, manifest, "")
        with (
            mock.patch.object(subprocess, "run", return_value=result),
            self.assertRaisesRegex(RuntimeError, "blobs GET"),
        ):
            registry.registry_requests("test-registry", "test-time")

    def test_private_query_and_unrelated_messages_are_not_access_evidence(self):
        """Omit authentication queries, headers and unrelated registry messages."""
        data = json.dumps(
            {
                "http.request.method": "GET",
                "http.response.status": 200,
                "http.request.uri": "/v2/acceptance/busybox/manifests/1.37.0?token=private-auth-token",
            }
        )
        self.assertFalse(registry.access_requests(data))
        self.assertFalse(registry.access_requests('{"msg":"private-auth-token"}'))

    def test_malformed_registry_json_fails_without_echoing_content(self):
        """Reject malformed logs rather than interpreting arbitrary diagnostic content."""
        for value in ("private-auth-token", "[]"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(RuntimeError, "Invalid registry JSON"),
            ):
                registry.access_requests(value)
        self.assertNotIn(
            "private-auth-token", self.out.getvalue() + self.err.getvalue()
        )

    def test_expected_failure_requires_exact_exit_and_keeps_stderr_separate(self):
        """Accept only exit 1 for a planned negative bundle test."""
        for status, accepted in ((0, False), (1, True), (125, False)):
            result = subprocess.CompletedProcess(
                [], status, "stdout-data\n", "stderr-data\n"
            )
            with (
                self.subTest(status=status),
                mock.patch.object(subprocess, "run", return_value=result),
            ):
                if accepted:
                    registry.command(["fixture"], expected_failure=True)
                else:
                    with self.assertRaises(RuntimeError):
                        registry.command(["fixture"], expected_failure=True)
        self.assertIn("stdout-data", self.out.getvalue())
        self.assertNotIn("stderr-data", self.out.getvalue())
        self.assertIn("stderr-data", self.err.getvalue())

    def test_image_cache_probe_does_not_accept_arbitrary_podman_failure(self):
        """Allow only exists=0 and missing=1; permission/configuration failures stop."""
        for status, expected in ((0, True), (1, False), (125, None)):
            with (
                self.subTest(status=status),
                mock.patch.object(
                    subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], status, "", ""),
                ),
            ):
                if expected is None:
                    with self.assertRaises(RuntimeError):
                        registry.image_exists("registry.example.test/app:1")
                else:
                    self.assertEqual(
                        registry.image_exists("registry.example.test/app:1"), expected
                    )

    def test_operation_guard_rejects_builds_and_save_after_pull_failure(self):
        """Refuse a hidden build or save fallback in the registry-only phase."""
        log = self.root / "operations.txt"
        for operations in (["pull"], ["build"], ["pull", "save"]):
            log.write_text("\n".join(operations) + "\n")
            if operations == ["pull"]:
                registry.check_operations(log, ["pull"])
            else:
                with self.assertRaises(RuntimeError):
                    registry.check_operations(log, ["pull"])

    def test_negative_bundle_checks_name_login_hint_and_no_fallback(self):
        """Reject a generic exit-1 error or any successful-save/build fallback."""
        (self.root / "manifests").mkdir()
        image = "registry.example.test/app:1"
        log = self.root / "operations.txt"

        def failure(arguments, **kwargs):
            """Return the expected public diagnostic and record one failed pull."""
            log.write_text("pull\n")
            return "", "ERROR: Cannot pull " + image + "; check podman login\n"

        with mock.patch.object(registry, "command", side_effect=failure):
            registry.negative_bundle(self.root, image, {}, log, "cached image")
        self.assertIn("no save/build fallback", self.out.getvalue())
        with (
            mock.patch.object(
                registry, "command", return_value=("", "ERROR: bad YAML\n")
            ),
            self.assertRaisesRegex(RuntimeError, "Wrong diagnostic"),
        ):
            registry.negative_bundle(self.root, image, {}, log, "cached image")

    def run_fixture(self, fail_push=False, existing_certificate=False):
        """Simulate the full registry lifecycle and cache without executing host commands."""
        runtime, home, base = (
            self.root / "runtime",
            self.root / "home",
            self.root / "base",
        )
        runtime.mkdir(mode=0o700)
        home.mkdir()
        base.mkdir()
        certificate = home / ".config/containers/certs.d/127.0.0.1:17000"
        if existing_certificate:
            certificate.mkdir(parents=True)
            (certificate / "ca.crt").write_text("existing certificate")
        cache, calls, server = set(), [], types.SimpleNamespace(running=True)

        def command(arguments, cwd=None, env=None, expected_failure=False):
            """Emulate cache mutations and write only the public bundle fixture artifacts."""
            args = list(map(str, arguments))
            calls.append(args)
            if args[0] == "openssl":
                Path(args[args.index("-keyout") + 1]).write_text(
                    "synthetic-test-private-key"
                )
                Path(args[args.index("-out") + 1]).write_text("synthetic certificate")
            elif args[:2] == ["podman", "port"]:
                return "127.0.0.1:17000\n", ""
            elif args[:3] == ["podman", "image", "inspect"]:
                return "a" * 64 + "\n", ""
            elif args[:2] == ["podman", "pull"] and args[-1] == registry.SOURCE:
                cache.add(registry.SOURCE)
            elif args[:2] == ["podman", "tag"]:
                cache.add(args[-1])
            elif args[:3] == ["podman", "image", "rm"]:
                cache.discard(args[-1])
            elif args[:2] == ["podman", "push"] and fail_push:
                raise RuntimeError("simulated push failure")
            elif args[:2] == ["podman", "stop"]:
                server.running = False
            elif args[0] == "date":
                return "2026-10-13T10:00:00Z\n", ""
            elif args == ["python3", "bundle.py"]:
                assert cwd is not None and env is not None
                image = yaml.safe_load((cwd / "manifests/app.yaml").read_text())[
                    "spec"
                ]["containers"][0]["image"]
                log = Path(env["REGISTRY_COMMAND_LOG"])
                if "/acceptance/missing:" in image or not server.running:
                    self.assertTrue(expected_failure)
                    log.write_text("pull\n")
                    return "", "ERROR: Cannot pull " + image + "; check podman login\n"
                cache.add(image)
                log.write_text("pull\nsave\n")
                path = cwd / "build/bundle/myproduct-0.0.0/images"
                path.mkdir(parents=True)
                (path / "images.txt").write_text(image + "\n")
            elif args == ["bash", "dev/pull-images.sh"]:
                assert env is not None
                Path(env["REGISTRY_COMMAND_LOG"]).write_text("pull\n")
            return "", ""

        def exists(image):
            """Resolve the synthetic image ID only while a fixture alias remains cached."""
            return bool(cache) if image == "a" * 64 else image in cache

        with (
            mock.patch.object(registry, "command", side_effect=command),
            mock.patch.object(registry, "image_exists", side_effect=exists),
            mock.patch.object(Path, "home", return_value=home),
            mock.patch.dict("os.environ", {"XDG_RUNTIME_DIR": str(runtime)}),
            mock.patch("shutil.which", return_value="/usr/bin/podman"),
            mock.patch.object(
                subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, self.requests(), ""),
            ),
        ):
            if fail_push or existing_certificate:
                with self.assertRaises((RuntimeError, FileExistsError)):
                    registry.main(base, "fixture")
            else:
                registry.main(base, "fixture")
        self.assertFalse(list(runtime.iterdir()))
        self.assertNotIn(
            "synthetic-test-private-key", self.out.getvalue() + self.err.getvalue()
        )
        self.assertIn(
            ["podman", "rm", "--force", "--volumes", "offline-registry-fixture"], calls
        )
        return calls, certificate

    def test_full_fixture_proves_download_and_cached_failures_then_removes_keys(self):
        """Exercise both source modes and planned negative pulls with automatic secret cleanup."""
        calls, certificate = self.run_fixture()
        self.assertFalse(certificate.exists())
        self.assertIn(["bash", "dev/build-images.sh"], calls)
        self.assertIn(["bash", "dev/pull-images.sh"], calls)
        self.assertEqual(calls.count(["python3", "bundle.py"]), 3)
        self.assertNotIn(["podman", "build"], [args[:2] for args in calls])
        self.assertIn("zero builds", self.out.getvalue())

    def test_failed_fixture_still_removes_registry_and_private_keys(self):
        """Clean up owned registry resources after an unexpected setup failure."""
        _, certificate = self.run_fixture(fail_push=True)
        self.assertFalse(certificate.exists())
        self.assertIn("simulated push failure", self.err.getvalue())

    def test_preexisting_registry_certificate_is_never_deleted(self):
        """Refuse an existing certificate directory without touching the user's certificate."""
        _, certificate = self.run_fixture(existing_certificate=True)
        self.assertEqual((certificate / "ca.crt").read_text(), "existing certificate")


if __name__ == "__main__":
    unittest.main()
