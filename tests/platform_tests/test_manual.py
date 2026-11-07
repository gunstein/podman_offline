"""The production manual stays in step with the commands it tells the operator to type.

docs/PRODUCTION-INSTALL.md is printed and followed literally (backlog 69 WP5).
These checks catch a renamed option, a changed prompt or a changed "next"
line in tools/ that the manual does not follow. They do not run the
procedure; the --admin-rpm lab scenario does that.
"""

import re
import shlex
import sys
import unittest
from pathlib import Path

from deployment import arguments

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import admin  # pyright: ignore[reportMissingImports] - tools/ is added above
import runtime  # pyright: ignore[reportMissingImports] - tools/ is added above

MANUAL = ROOT / "docs/PRODUCTION-INSTALL.md"
PRODUCT = "myproduct"  # the manual's example product name


def blocks(kind):
    return re.findall(r"```" + kind + r"\n(.*?)\n```", MANUAL.read_text(), re.DOTALL)


def commands():
    """Each line of the manual's sh blocks: what the operator types."""
    return [line for block in blocks("sh") for line in block.splitlines()]


class ManualTests(unittest.TestCase):
    def test_every_product_command_parses_with_the_real_parser(self):
        checked = []
        for line in commands():
            words = shlex.split(line)
            if words[:2] == ["sudo", PRODUCT + "-admin"]:
                parser, rest = admin.parser(PRODUCT), words[2:]
            elif words[:1] == [PRODUCT]:
                parser, rest = runtime.parser(PRODUCT), words[1:]
            else:
                continue
            with self.subTest(line=line):
                arguments.parse(parser, rest)
                checked.append(line)
        # The manual's ordinary tasks: delivery, credentials and the runtime command.
        self.assertIn("sudo myproduct-admin /mnt", checked)
        self.assertIn("sudo myproduct-admin --credentials /mnt", checked)
        self.assertIn("myproduct", checked)

    def test_every_prompt_shown_is_a_question_the_tools_ask(self):
        source = (ROOT / "tools/admin.py").read_text() + (
            ROOT / "tools/runtime.py"
        ).read_text()
        questions = set(re.findall(r'ask\(\s*"([^"]+)"', source))
        # A prompt line is "<question> [<default>]: <answer>"; output lines
        # start with [OK] or PASS:.
        shown = [
            match.group(1)
            for block in blocks("text")
            for match in re.finditer(
                r"^(?!\[OK\]|PASS:)(.+?)(?: \[[^\]]*\])?:(?: |$)", block, re.MULTILINE
            )
        ]
        self.assertEqual(sorted(set(shown)), sorted(questions))

    def test_every_manual_section_a_message_names_exists(self):
        source = "".join(
            (ROOT / "tools" / name).read_text() for name in ("admin.py", "runtime.py")
        )
        cited = set(re.findall(r'see \\?"([^"\\]+)\\?" in the manual', source))
        headings = set(re.findall(r"^#+ (.+)$", MANUAL.read_text(), re.MULTILINE))
        self.assertEqual(cited, {"If a command stops", "Before you begin"})
        self.assertLessEqual(cited, headings)

    def test_the_next_line_of_the_admin_command_is_the_manual_line(self):
        # test_admin checks that the command prints this line for its account.
        self.assertIn(
            "[OK] next: log in as produser (at the console, or ssh "
            "produser@<server>) and run myproduct",
            MANUAL.read_text(),
        )


if __name__ == "__main__":
    unittest.main()
