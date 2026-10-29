# Backlog 72 remaining matrix verification (recorded 2026-10-29)

Tested commit: `0ece0c1ff22126f9d7ca28056be0ca30b74c2dfd` on `main`.

The operator ran these five scenarios on **2026-10-28** (19:42–21:34 UTC). This entry was recorded on 2026-10-29 by checking the local `REPORT.md` metadata and `record.jsonl` files against the supplied terminal transcript. No tests or VM operations were rerun while documenting the results.

**All five runs were CLEAN PASS: 347/347 steps, including all five final audits and cleanup steps.** The shell summary was `Failed: none`.

| Run ID | Options | Passed steps | Scope |
| --- | --- | ---: | --- |
| `m72c-identity` | `--identity-only` | 66/66 | Pinned Identity 0.4.11 baseline and template upgrade |
| `m72c-renamed` | `--renamed-product` | 57/57 | Renamed product lifecycle, registration removal and retained-bundle uninstall |
| `m72c-app2` | `--first-app app2` | 125/125 | App2-first lifecycle, crash/hang/reboot and independent upgrades |
| `m72c-help` | `--help-only` | 60/60 | App1/platform/Identity/help and isolated help upgrade |
| `m72c-platform-help` | `--platform-help-only` | 39/39 | PROD platform/help without Identity or application databases |

## Product/unit and builds

`03-unit` passed **572 tests** in each of `m72c-identity`, `m72c-app2`, `m72c-help` and `m72c-platform-help`. The renamed scenario has no separate `03-unit` step. Image builds passed in all five scenarios; DEV required its usual network access for builds and dependencies.

## Acceptance-harness tests

These runs execute the real acceptance harness; they are not a new run of its isolated unittest suite. No `python3 -m unittest discover -s acceptance` result is claimed for `0ece0c1` from this batch. The earlier 358-test controller result remains scoped to `fd99d31`.

## Real Podman/systemd verification

Both configured disposable VMs (DEV 107 / PROD 108) report Oracle Linux **9.8**, rootless Podman **5.8.2**, systemd **252**, and **SELinux Enforcing**. PROD reports fapolicyd active/enabled and firewalld active; DEV reports fapolicyd inactive/disabled and firewalld active. PROD installs used signed offline bundles as the runtime account.

The previously failed `m72-identity` run at `58240ea` remains NOT CLEAN. Commit `0ece0c1` fixes its historical fixture: restoring Identity 0.4.11 now also removes `accepts.apis`, incoming `apis` roles and their `api.yaml`, matching that release. `m72c-identity` passed the baseline, DEV startup/sign-in, PROD installation and template upgrade, sibling/persistent-data checks, and audit. Its recorded baseline is `932c7f3a647a84fb5388144bc822f895cc40d959`, component version 0.4.11; the derived upgrade release is 0.4.12. The app2-first current-product run separately upgrades Identity 0.4.13 to 0.4.14. Neither the baseline nor derived release versions should be confused with the controller source revision.

The renamed run passed installation and health of `shop-login-service` 0.4.13, sign-in, restart/redeploy, inventory route/client removal, survivor checks, retained manual-bundle uninstall and final audit. This closes the outstanding renamed-product regression for backlog 72. With app3 excluded, the generated owner has no API registrations; successful startup exercises the empty owner Secret path. This batch did not separately extract `login-service-apis` data, inspect its environment, or capture the inactive-API log line; the byte-level/rotation evidence remains the earlier focused demo result.

The app2-first run passed crash and hang recovery, reboot/offline checks, help/app1/platform/Identity upgrades, sibling/data preservation, app1 uninstall and app2 survival. The help-only run passed isolated help upgrade and continued app1 operation. The platform/help run passed PROD proxy/help without Identity. Its DEV flow still builds and tests the demo catalog; this is not a minimal arbitrary-worker test.

Every `11-prod-audit` recorded filtered launcher diagnostics and `PASS: no FANOTIFY/AVC events since run start`. Full journals and credentials are not reproduced here.

## Contracts, understandability and limits

The recorded flows cover the historical version/catalog contract, renamed product/component isolation, signed offline delivery, dependency subsets, registration removal, sibling/data preservation and lifecycle health. This update changes evidence only. The baseline flow is explicit: `prepare` restores pinned files, `old_catalog` adjusts the disposable catalog, and the upgrade builder uses the tested revision for the new release. No generic deployment changes or extra abstraction were introduced while recording the results.

The five remaining fixed scenarios are now recorded as passing at `0ece0c1`; the normal app1-first run at `fd99d31` is separate historical evidence, not a sixth run at this commit. No `--whoami` or `--status-retry` run occurred in this batch. App3 remains outside the fixed PROD matrix. API-secret interruption/retry, real `hash: none` / multiple-API deployments, the organisation's backend, two-level CA, post-logout redirect and session revocation remain outside these results. No AI manual walkthrough or unassisted human operator trial was performed; logging existing automated evidence changes no operator procedure.

## Private artifact fingerprints

Original artifacts remain in `~/podman-offline-acceptance-runs/<run-id>/`. Only fingerprints are copied here; no secret values or raw logs are committed.

| Run ID | SHA-256 of record.jsonl | SHA-256 of final audit log |
| --- | --- | --- |
| `m72c-identity` | `e948c20f36f5127e3de5378f0aa9e7e64efcac063f39223eff0c1ee1da3797af` | `afa247bc97208b11b3e9e8263b00e1965aa47c863208cd5eb6f17520f76f6493` |
| `m72c-renamed` | `8e59cc187f8cc0e93ad5c3cafa7c03cf905816c39c6a024bab190008b1110246` | `4e6fc177ee26c37da39b2cf7681fea560008adde07c720338bfd1fb5e53b0606` |
| `m72c-app2` | `9161f8639d50f15195d153bbde11dbb3060d19a6745ed96dc5bc82a05239719f` | `f7606f52572674a20b841f8d2b16513f39da29b1b4cc0c4b5dfacfbd49e8bc45` |
| `m72c-help` | `a7ac45d0adc5bec85eb0fafd7d94464753c48d7e1a61f7197df9aa1507db3ed5` | `1170e0003a970e69f791ce24228bbe13681196e8ac61f10893a5898d72cfc1f0` |
| `m72c-platform-help` | `da943cc7164f217a1353342deb5794a4a2421a56088942feff57485c99489488` | `e83e6745ce524b464bcff204c589a360dac9b66a2d8002100dad31cff4fe4eec` |
