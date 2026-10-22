# Misplaced container fields (backlog 62)

Implemented 2026-10-22 on `fix/62-manifest-container-fields`.

`render.pod_specs(documents, source)` rejects nineteen container-only fields
when they appear directly under a Pod's `spec`. The exact field list is in
[README](../README.md#components-and-bundles)'s validate documentation and
`deployment/render.py: CONTAINER_ONLY_FIELDS`. Diagnostics name the source
manifest, `spec.<field>` and the intended ordinary/init-container location;
field values are never included. The check does not move fields or select a
recipient container.

This is a focused structural guard, not full Kubernetes schema validation.
It does not recursively ban keys, constrain arbitrary ConfigMap/Secret data or
annotations, add resource kinds, or restrict Pod fields through an allowlist.
Fields with Pod-level uses, such as `securityContext` and `restartPolicy`, are
not in the guard. No schema downloads, new dependencies or host CLI are needed.

## Regression evidence

`tests/platform_tests/test_manifest_structure.py` uses an arbitrary minimal
`processor` component with an external image, retained password and generated
Secret template. It has no apps, database, public URL, gateway or Identity.
It covers:

- All nineteen guarded fields through the public validate CLI handler, prepare
  and bundle build, with source/field diagnostics and redaction.
- No host commands, credential-content reads during validate, or changes to
  existing config, credentials, output and sibling state on rejection.
- A valid Secret/key reference moved from init `env` to `spec.env` in an unpacked,
  relocated release with source removed and retained production configuration.
  Validate and install refuse; repair permits validate and install retry.
- Valid ordinary/init env, multiple Secret-based init entries, both YAML sequence
  indentation styles, arbitrary ConfigMap/Secret keys and annotation names.

The existing `broken_orders` fixture also includes misplaced Secret-based env,
so renamed-product validate/prepare/install ordering regressions exercise this
error alongside existing semantic failures, including before password generation.

Initial implementation checks at `6392d34` (Python 3.14 / local PyYAML):

- Focused product tests: `PYTHONPATH=tests python3 -B -m unittest
  platform_tests.test_manifest_structure platform_tests.test_validation_order
  platform_tests.test_validate`: **31 passed**.
- Isolated product suite: `python3 -B tests/run.py platform --isolate`:
  **387 passed**. Expected negative signing diagnostics are part of passing tests.
- Acceptance-harness tests: `python3 -B -m unittest discover -s acceptance
  -p 'test_*.py'`: **233 passed**. The harness was not changed; these tests stub
  runtime transport.
- Ruff for changed Python files, format check for all documented Python paths,
  pyright for all documented Python paths, and Python 3.6 compatibility via
  vermin: passed. Full-tree Ruff also reports twelve existing findings in
  `acceptance/init_secret_test.py`, `acceptance/test_init_secret.py` and
  `tests/platform_tests/test_secret_templates.py`; none are in this change.
- `git diff --check` and local documentation-link checks: passed.

## Understandability and lifecycle review

The catalog/component manifests and effective config remain authoritative;
bundle descriptors and installed metadata are unchanged. Source prepare and
bundle install enter `deploy.validate_component` through `check_manifests`;
read-only validate calls `validate_component` directly. It calls
`render.effective_documents`: source manifest -> replacement ->
`check_pod_specs` -> `pod_specs` structure guard -> mount/pull-policy and
reference/database semantic checks -> preflight -> materialize.
The guard uses explicit source context. Bundle `manifest_images` also calls
`pod_specs` per source file before image discovery, staging or image operations.

For an already-installed equal version with `upgrade: newer-only`,
`install_checks` returns `render=False`. Validate and install then share
`install_preconditions`, which loads each source file and calls `pod_specs`
with its path before combining documents for image discovery. This preserves
source diagnostics even when effective rendering and materialization are skipped.

Success still reaches the existing materialization and installation flow.
A misplaced field raises before generation, persistent writes or host commands;
no pending work is created or acknowledged. Existing config, credentials, output
and sibling state survive. Repairing the manifest allows an ordinary retry using
that same durable state. No new state machine, alternate validator, demo branch
or migration was introduced. The affected flow and diff were reviewed separately
from tests; the understandability review passed.

## Verification limits

No real Podman/systemd/SELinux/fapolicyd run was performed for this change.
Product tests and acceptance-harness results do not establish runtime Secret
value delivery. Backlog 61's normal and renamed runtime runs passed separately
at the earlier `52f28e4` revision ([evidence](INIT-SECRET.md#completed-real-lab-verification-2026-10-22));
they do not constitute a runtime run of this structural-validation change. Python 3.6 syntax
compatibility was checked statically, not by running a Python 3.6 interpreter.
This change rejects the confirmed YAML placement mistake and makes no claim
about the remaining private Grate failure.

## Review follow-up: equal-version newer-only installs

Review of `main...6392d34` found that the equal-version `newer-only` path
rejected `spec.env` but reported only `manifests`, losing the source filename.
The new regression failed for both validate and install before the fix.
`install_preconditions` now checks each file with explicit source context before
collecting its documents, reusing the existing shape check.

The relocated-release regression now runs both `always` and `newer-only`, asserts
the actual render decision after the first install, and requires the filename in
both commands' failures. Both paths preserve config, credentials, output and
sibling state, read no credentials and make no host calls on rejection; repair
permits retry. The diff and successful/rejected repeat flows were reviewed;
the understandability review passed with no new state or validation engine.

Follow-up verification (Python 3.14): focused product suite **32 passed**;
isolated platform suite **388 passed**. Changed-file Ruff, full documented
format/Pyright/Vermin checks, relative documentation links and `git diff --check`
passed. Acceptance-harness code is unchanged and its tests were not rerun for
this follow-up; the **233 passed** above are the initial implementation's run.
No real Podman/systemd/SELinux/fapolicyd verification or Python 3.6 interpreter
run was performed for the follow-up.
