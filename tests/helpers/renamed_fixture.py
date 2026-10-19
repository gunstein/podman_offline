"""A fully renamed product works through declarations alone (backlog item 20)."""

import json
import shutil
import subprocess
import sys

from deployment import common

from helpers.product_fixture import RENAMED, ProductFixture
from helpers.retry_fixture import DRIVER, REAL_RUN, SOURCE


class RenamedFixture(ProductFixture):
    """gateway, login-service, orders, inventory and manual; no demo names anywhere."""

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)

    def install_all(self):
        """Build, delete the source checkout, then install offline in dependency order."""
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.HOME)
        restarts = {}
        for name in ("gateway", "login-service", "orders", "inventory", "manual"):
            restarts[name] = self.install(releases[name])
        return releases, restarts

    def attempt(self, release, **options):
        """Run one install in a fresh interpreter against the same persistent home."""
        parameters = dict(
            root=str(release),
            home=str(common.HOME),
            source=str(SOURCE),
            record=str(self.root / "attempt.json"),
            action="install",
            **options,
        )
        result = REAL_RUN(
            [sys.executable, "-B", str(DRIVER)],
            input=json.dumps(parameters),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        events = json.loads((self.root / "attempt.json").read_text())["events"]
        return result.returncode, events

    def install_shared(self):
        """Build, delete the source and install the gateway and login-service."""
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.HOME)
        for name in ("gateway", "login-service"):
            self.install(releases[name])
        return releases
