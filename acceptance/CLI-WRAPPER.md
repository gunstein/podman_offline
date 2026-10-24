# CLI wrapper name (backlog 60)

Implemented on `fix/60-deploy-sh` (2026-10-24), based on item 59 commit `6c9a461`.
The two changes are stacked and included in `feature/39-component-status`.

## Contract and changes

The only current executable is `deploy.sh`, in source and new component or
standalone bundles. The rename preserves the exact wrapper bytes, executable
mode, Bash shebang, `set -euo pipefail`, change to the wrapper's own directory,
and `exec python3 -B -m deployment "$@"`. Python modules (including
`deployment.deploy`) and subcommand/argument semantics retain their names.
There is no `deploy` alias or migration layer in the pre-customer model.

Updated references include bundle copying/private-source guards/0755 mode,
checksum inventory, platform-suite export, dev and standalone example callers,
release validation/safety probes, renamed-product and init-Secret scenarios,
fixtures, usage/error/retry messages, current operator docs and planned backlog
commands. Both architecture PNGs were regenerated from the updated Mermaid
source using `CHROMIUM=/usr/bin/google-chrome bash dev/render-diagrams.sh`.

The release helper trusts the authenticated complete inventory rather than a
hardcoded wrapper basename; its trust algorithm does not change. The new wrapper
is included in the existing inventory/checksum tests.

## Regression evidence

Existing tests were adapted, rather than introducing a second lifecycle harness:

- `test_bundle.py` requires `deploy.sh` in the exact archive file set, mode 0755
  and checksums. An old-name alias would fail the file-set assertion.
- `test_wrappers.py` invokes actual executable wrappers from an unrelated working
  directory in fresh processes. It checks source validate/prepare, positional
  init-config arguments, usage and error exits, bundle init-config/validate/
  install/uninstall, retained persistent config and sibling state.
- That wrapper fixture has external images and no `apps/`. It deletes its source,
  relocates the unpacked releases before production installation, verifies exact
  wrapper bytes/modes and absence of the old alias, and checks no bytecode or
  caller-directory writes. Host account/runtime/Podman/systemd transport is stubbed.
- Exit statuses remain 0 for success, 1 for expected operational refusal and 2
  for usage errors. `--help` retains the existing usage/error status 2; this task
  does not add a new help subcommand or change the CLI contract.
- Existing retry, retained-credential, isolation, renamed-product and acceptance
  tests run with the new caller paths. The release-safety probe invokes
  `deploy.sh validate` as the separate runtime account.

Current-change local results:

| Evidence | Result |
| --- | --- |
| Focused wrapper/bundle/suite-export/Quadlet tests | 39 passed |
| `python3 -B tests/run.py platform --isolate` | 441 passed |
| `python3 -B tests/run.py demo` | 66 passed |
| `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | 243 passed; stubbed runtime transport |
| Full documented Ruff format check / Pyright / Vermin | Passed; 0 type errors, minimum Python 3.6 |
| Bash syntax for changed shell entry points and scripts | Passed |
| Mermaid CLI rendering | Both architecture diagrams generated successfully |
| Local documentation links and `git diff --check` | Passed; 263 local link targets checked |

Full-tree Ruff still has the same 12 baseline findings in
`acceptance/init_secret_test.py`, `acceptance/test_init_secret.py` and
`tests/platform_tests/test_secret_templates.py`. The rename touches path strings
in the first two files, which contain 11 of those existing findings. This lint
gate is not green; the unrelated findings were not repaired in this rename.
ShellCheck is unavailable in this environment; shell syntax was checked with Bash.

## Remaining old references

The remaining old executable references were inspected:

- `acceptance/remote.sh`'s `legacy-install` action invokes the genuine pinned
  0.2.0 wrapper `deploy`; the legacy trust fixture also retains `deploy.py` paths.
  These historical inputs must not be rewritten to pretend they shipped deploy.sh.
- Historical acceptance reports, `examples/RESULTS.md`, the explicitly historical
  portion of `acceptance/README.md`, recorded backlog evidence and descriptions
  of the old wrapper retain their original command names.
- The DR plan's linked `podman_test/deploy/...` paths refer to another repository.
- Python module/function references, conceptual deployment prose, the
  `deploy-install.png` artifact identifier and tests asserting absence of `deploy`
  are not active old-wrapper callers.

Current code paths and current operator commands use `deploy.sh` consistently.

## Understandability and verification limits

Successful flow: the caller executes `deploy.sh` -> Bash selects its own release
working directory -> `exec` transfers unchanged arguments to
`deployment.__main__` -> `cli.main` dispatches the existing owning function.
The authoritative catalog/config/state and lifecycle ordering are unchanged.
Expected failures return the existing CLI code through Python and Bash without
being converted to success. `-B` still prevents bytecode writes to trusted trees.

The reviewed diff changes wrapper references and tests/docs, not lifecycle state
schemas, credential generation, pending-operation ownership or completion rules.
Fresh-process retry continues to use the same durable state. Source, bundle,
error and isolated release paths were traced separately from automated checks;
the understandability review passed.

The subsequent [2026-10-24 real lab matrix](STATUS.md#completed-real-lab-verification-2026-10-24)
completed all six scenarios with CLEAN PASS, including normal and renamed
products, on identical product/harness code at `7ef9671` and `137a2da` (only
documentation differs). It verifies actual wrapper execution on OL9 with
Podman/systemd, SELinux Enforcing and fapolicyd. See that report for exact run IDs,
log verification, warnings and the early-cache-eviction observation.
Python 3.6 interpreter execution remains outstanding. Automated execution does
not establish operator usability; the [AI findings and pending human trial](OPERATOR-REVIEW.md)
remain separate.
