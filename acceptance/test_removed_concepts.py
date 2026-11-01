"""The harness must not use what the product removed (backlog 78).

When a field, layout or placeholder leaves the product, add it to REMOVED in
the same change. The lab code and its tests then fail here, locally, instead of
in a 10-30 minute lab run (docs/REVIEW_GUIDE.md, section 4).
"""

import re
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Pattern -> what replaced it. Mentions in Markdown history are not checked.
REMOVED = {
    r'\["upgrade"\]|"upgrade":|upgrade: always|newer-only': (
        "backlog 77: every install renders again; only a downgrade is refused"
    ),
    r'"shares"': "backlog 77: PUBLIC_ORIGIN/HTTPS_PORT come from the gateway",
    r"common\.defaults\.yaml": "backlog 77: one config.defaults.yaml per component",
    r"components/[^/\"']+/config\.dev\.yaml": "backlog 77: only config/dev.yaml",
    r"GENERATED_SECRETS": "generate: on a SECRET_FILES/VOLUME_FILES source",
    r"STANDALONE_PRODUCT|examples/run\.sh": "backlog 77: no standalone mode",
    r"with_gateway_settings": "backlog 77: catalog.operator_config",
}


def stale_references(paths):
    """[(file, line number, replacement)] for each use of a removed concept."""
    found = []
    for path in paths:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for pattern, replacement in REMOVED.items():
                if re.search(pattern, line):
                    found.append((path.name, number, replacement))
    return found


def harness_files():
    """The lab code and its tests: Python and shell beside this file."""
    return sorted(
        path
        for path in list(HERE.glob("*.py")) + list(HERE.glob("*.sh"))
        if path.name != Path(__file__).name
    )


class RemovedConceptTests(unittest.TestCase):
    def test_the_harness_uses_no_removed_concept(self):
        self.assertEqual(stale_references(harness_files()), [])

    def test_a_stale_fixture_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            stale = Path(directory) / "test_stale.py"
            stale.write_text('descriptor = {"name": "app1", "upgrade": "always"}\n')
            self.assertEqual(
                stale_references([stale]),
                [("test_stale.py", 1, REMOVED[next(iter(REMOVED))])],
            )


if __name__ == "__main__":
    unittest.main()
