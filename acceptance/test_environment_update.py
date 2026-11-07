"""The environment update probe's verdict, without Podman (environment_update_test)."""

import copy
import unittest

import environment_update_test as probe
from init_secret_test import ProbeFailure

# What the probe observes in the running container, written out by hand.
BEFORE = {
    "id": "a" * 64,
    "values": {"EXISTING_SETTING": "original", "ADDED_SETTING": None},
    "secret": "1" * 64,
}
AFTER = {
    "id": "b" * 64,
    "values": {
        "EXISTING_SETTING": "original",
        "ADDED_SETTING": "environment-update-test",
    },
    "secret": "1" * 64,
}


class VerdictTests(unittest.TestCase):
    def test_a_new_container_with_both_values_and_the_same_secret_passes(self):
        probe.check(BEFORE, AFTER)

    def test_each_wrong_observation_fails(self):
        def changed(observation, key, value):
            result = copy.deepcopy(observation)
            if key in ("id", "secret"):
                result[key] = value
            else:
                result["values"][key] = value
            return result

        for label, before, after, cause in (
            ("variable already there", changed(BEFORE, "ADDED_SETTING", "x"), AFTER,
             "unexpected test variables before"),
            ("old container kept", BEFORE, changed(AFTER, "id", BEFORE["id"]),
             "did not replace the container"),
            ("variable missing", BEFORE, changed(AFTER, "ADDED_SETTING", None),
             "ADDED_SETTING is missing or wrong"),
            ("old value", BEFORE, changed(AFTER, "ADDED_SETTING", "stale"),
             "ADDED_SETTING is missing or wrong"),
            ("existing changed", BEFORE, changed(AFTER, "EXISTING_SETTING", "other"),
             "EXISTING_SETTING changed"),
            ("secret regenerated", BEFORE, changed(AFTER, "secret", "2" * 64),
             "generated secret changed"),
        ):  # fmt: skip
            with self.subTest(label), self.assertRaisesRegex(ProbeFailure, cause):
                probe.check(before, after)

    def test_the_probe_runs_in_the_dev_runtime_step(self):
        from pathlib import Path

        remote = Path(__file__).with_name("remote.sh").read_text()
        step = remote[remote.index("database-runtime)") :]
        step = step[: step.index(";;")]
        self.assertIn("python3 acceptance/environment_update_test.py", step)
        source = Path(probe.__file__).read_text()
        # The real command both times; no direct prepare or kube play.
        self.assertEqual(source.count('"dev/dev.sh"), "up"]'), 2)
        self.assertNotIn('"kube", "play"', source)


if __name__ == "__main__":
    unittest.main()
