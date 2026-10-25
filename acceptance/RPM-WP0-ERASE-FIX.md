# WP0 probe release directory ownership correction

The full run `wp0-full-20261025-181152` at `c313036` passed 20 case/profile
combinations and stopped at F/P1. Its authorized erase returned
`Erase postcondition failed`; the failure audit reported no events. F/P2,
G/P1 and H/P1 were not reached. This was not a full WP0 PASS.

## Finding and correction

The probe fixture generator listed release files in `%files`, but omitted
ownership of the release directory itself. Removing those files does not
instruct RPM to remove their unowned parent directory. This conflicts with
the unchanged erase postcondition: both the package and its tree must be absent.
The recorded error combines these conditions, so the historical transcript
alone does not establish which condition failed or the final directory contents.
No follow-up VM inspection was performed for this correction.

`fixtures.build` now accepts explicit directory ownership. Both versions of
each probe release own exactly their own leaf directory through `%dir`.
Shared parents and sibling trees are excluded. Tools packages are unchanged.
This changes only the small WP0 probe implementation, not product packaging.
The guard, authorization record, lock protocol, trust predicate and erase
postconditions are unchanged; no manual recursive deletion was added.

## Local verification

- `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`: 339 passed.
- `python3 -B -m unittest acceptance.test_rpm_wp0 acceptance.test_rpm_wp0_trust`:
  73 passed.
- WP0-scoped Ruff, Ruff format, Pyright and ShellCheck: passed.
- `git diff --check`: passed.

The regression exercises the real spec generator for two distinct release
names, checks the staged payload and exact `%files` manifest, and checks that
all release fixtures request their own directory while tools request none.
RPM building and signing are stubbed in these tests. A local disposable OL9
container was inspected for available tools; it has RPM but no rpmbuild.
No RPM transaction or corrected F probe was run, and no signing home or lab
configuration was read. Product/unit tests were not run: product code is unchanged.

## Understandability and remaining verification

Static developer review: pass. The release fixture declares its directory;
the builder writes that ownership into the spec. After authorized removal,
`mechanisms.erase` still requires package and directory absence and verifies
the sibling before success. A refused scriptlet or remaining tree still stops
the case; the controller retains evidence and does not continue the matrix.
Trust inventory already excludes directories by file mode.

Operator commands and stop/retry rules are unchanged. No human usability
assessment was performed. The VM was left untouched. Separate code review
and an authorized lab run remain necessary; the historical successful cases
do not verify these rebuilt probe packages, and WP0 remains incomplete.
