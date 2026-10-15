"""Test smoke-test error redaction without requests, network or demo credentials."""

import ast
import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

SOURCE = Path(__file__).resolve().parent.parent / "dev/smoke-test.py"


class RequestError(Exception):
    """Represent a requests failure without importing a third-party dependency."""


class SmokeErrorTests(unittest.TestCase):
    """Keep callback URLs, form data and session state out of failure output."""

    def namespace(self):
        """Load login functions in isolation with stubbed network and file access."""
        tree = ast.parse(SOURCE.read_text())
        isolated = ast.parse("")
        isolated.body = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("login", "require_success")
        ]
        namespace = {
            "urlparse": urlparse,
            "Path": mock.MagicMock(),
            "os": types.SimpleNamespace(getenv=lambda key, default: default),
            "ROOT": Path("fixture"),
            "ORIGIN": "https://example.test",
            "BASE_PATH": "/app1",
            "client": mock.Mock(),
            "get": mock.Mock(),
            "LoginForm": mock.Mock(),
        }
        namespace[
            "Path"
        ].return_value.__truediv__.return_value.read_text.return_value = (
            "synthetic-password"
        )
        namespace["LoginForm"].return_value.fields = {
            "__RequestVerificationToken": "synthetic-form-token"
        }
        exec(compile(isolated, str(SOURCE), "exec"), namespace)  # noqa: S102 - repository-owned functions
        return namespace

    def test_callback_http_error_does_not_disclose_url_or_form(self):
        """Reject a failing OIDC callback without its code, state or form tokens."""
        namespace = self.namespace()
        private_url = (
            "https://example.test/auth/callback?code=private-code&state=private-state"
        )
        namespace["get"].return_value = types.SimpleNamespace(
            status_code=200, url="https://example.test/identity/account/login", text=""
        )
        response = mock.Mock(status_code=500, url=private_url)
        response.raise_for_status.side_effect = RuntimeError(private_url)
        namespace["client"].return_value.post.return_value = response
        with self.assertRaises(RuntimeError) as caught:
            namespace["login"]("alice")
        for private in (
            "private-code",
            "private-state",
            "synthetic-password",
            "synthetic-form-token",
        ):
            self.assertNotIn(private, str(caught.exception))

    def test_unexpected_redirect_does_not_disclose_query(self):
        """Reject an unexpected sign-in destination without printing its URL."""
        namespace = self.namespace()
        namespace["get"].return_value = mock.Mock(
            status_code=200,
            url="https://example.test/wrong?code=private-code&state=private-state",
        )
        with self.assertRaises(AssertionError) as caught:
            namespace["login"]("alice")
        self.assertNotIn("private-code", str(caught.exception))
        self.assertNotIn("private-state", str(caught.exception))

    def test_shared_identity_session_needs_no_password_form(self):
        """Accept an SSO return to this app without opening or submitting a password."""
        namespace = self.namespace()
        browser = mock.Mock()
        namespace["get"].side_effect = [
            types.SimpleNamespace(status_code=200, url="https://example.test/app1/"),
            types.SimpleNamespace(
                json=lambda: {"user": {"sub": "alice"}, "csrf": "synthetic-csrf"}
            ),
        ]
        self.assertIs(namespace["login"]("alice", browser), browser)
        browser.post.assert_not_called()
        namespace["Path"].assert_not_called()

    def test_cli_does_not_log_exception_contents(self):
        """Redact HTTP exception URLs and assertion payloads at the CLI boundary."""
        tree = ast.parse(SOURCE.read_text())
        isolated = ast.parse("")
        isolated.body = [tree.body[-1]]
        for error in (
            RuntimeError("private-code private-state"),
            AssertionError("private-code private-state"),
            RequestError("callback?code=private-code&state=private-state"),
        ):
            output = io.StringIO()
            namespace = {
                "__name__": "__main__",
                "main": mock.Mock(side_effect=error),
                "sys": sys,
                "requests": types.SimpleNamespace(RequestException=RequestError),
            }
            failure = self.assertRaises(SystemExit)
            with contextlib.redirect_stderr(output), failure:
                exec(compile(isolated, str(SOURCE), "exec"), namespace)  # noqa: S102 - repository-owned CLI
            self.assertEqual(failure.exception.code, 1)
            self.assertIn("FAIL:", output.getvalue())
            self.assertNotIn("private-code", output.getvalue())
            self.assertNotIn("private-state", output.getvalue())
