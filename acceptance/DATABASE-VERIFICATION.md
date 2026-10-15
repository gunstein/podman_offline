# PostgreSQL configuration and runtime verification

This report separates local tests, acceptance-harness tests and actual VM runs.
It records database-specific results; full lifecycle/security evidence remains
in the acceptance run directories. No passwords, connection strings, complete
container inspect objects or environment dumps belong in evidence.

## Implementation

Release `VERSION=0.2.1`, `CORE_VERSION=0.2.1` adds component `DB_HOST`, `DB_PORT`,
`DB_USER` and `DB_NAME` and moves all three database password files into the
existing `GENERATED_SECRETS` mechanism. Existing names, volumes, Secret names/keys
and password file paths are retained. The certificate script generates only its
remaining certificate/demo-user material. Production config is authoritative;
operators add required DB fields/list entries manually before upgrading.

Identity builds `ConnectionStrings__Default` at startup inside its image with
NpgsqlConnectionStringBuilder, then uses that environment value exclusively.
The bootstrap and ASP.NET application share a process. Todo uses the same DB
parameters and mounted Secret through psycopg keyword parameters. Both strip only
trailing LF, preserving significant spaces and special characters. Invalid UTF-8,
empty values, embedded LF/CR and NUL are rejected. No password enters ordinary
config or placeholders, argv, a ConfigMap or a rendered connection string.

Database lifecycle preflight derives password/PVC bindings from the manifest.
A missing password can be generated only after Podman explicitly reports no
volume. Existing volumes, volume-check errors, empty/invalid/non-regular files
stop the operation. No automatic recovery, ALTER ROLE, role/privilege migration,
password rotation or volume deletion/reinitialization is implemented.

See [operator documentation](../README.md#postgresql-configuration-and-credentials)
for ownership, paths, backups and manual 0.2.0 upgrade steps.

## Local checks

- 181 product unit/integration tests with PyYAML 6.0.3 / Python 3.14.4.
- The same product suite with PyYAML 5.4.1 / Python 3.11.17.
- 142 acceptance-harness tests (external transports stubbed).
- Ruff 0.17.0 check and format; pyright 1.1.414, including Todo with its application
  dependencies; vermin 1.8.0 with the existing host-tool/test target `3.6-`;
  ShellCheck 0.11.0 for the tracked shell entrypoints/scripts.

These tests cover required fields and text environment values, actual generated
Kube Secret payloads, Secret/key bindings, exclusive private generation,
independent app passwords, unchanged legacy bytes, invalid/non-regular files,
missing-file/existing-volume guards before image/state changes, controlled check
errors, shallow dev overrides including unused help DB_PORT, and private error/
logging/authentication classification. Existing bundle, checksums, symlink,
SELinux/fapolicyd harness, configuration and lifecycle tests remain enabled.
Unit/harness tests do not prove database authentication or offline installation.

## Actual VM runs

Both configured disposable lab VMs use **rootless Podman 5.8.2** on Oracle Linux 9.
The server image is `localhost/myproduct-postgres:17.11` (upstream PostgreSQL 17.11).
Identity uses .NET 8 / Npgsql 8.0.9; Todo uses Python 3.12 / psycopg 3.2.10.
No Kubernetes/Podman environment-variable expansion is used or claimed verified.
Only the two already authorized lab VMs are reset/changed by the full harness.

Run evidence lives under `~/podman-offline-acceptance-runs/<run>/`, including
REPORT.md, EVIDENCE.md, record.jsonl, immutable source.bundle and per-step logs.
Verification uses detached clean temporary snapshots; the user branch is not
committed or pushed by the verification procedure.

| Run | Source snapshot | Result |
| --- | --- | --- |
| 2026-10-14-database-app1-01 | fd1b7db | NOT CLEAN: strict database runtime negative check stopped the run |
| 2026-10-14-database-app1-02 | 5cb8ae1 | CLEAN PASS: full app1-first lifecycle |
| 2026-10-14-database-app2-01 | 437bc34 | CLEAN PASS: final app2-first lifecycle and expanded DB checks |

The first failure was retained rather than relabeled: psycopg/libpq's handshake
exception lacked SQLSTATE. Npgsql verified 28P01; Python now privately recognizes
the exact PostgreSQL FATAL password-authentication reply when SQLSTATE is absent.
DNS/refusal/timeout messages do not satisfy that classification. An independent
focused real-container rerun verified all three password fixtures before the
full rerun; disposable resources were removed. The harness also handles kube
cleanup removing its own Secret, without ignoring failed volume inspections.

The `database-runtime` action actually initializes separate disposable databases
from kube Secrets using a non-default host, port 5544, user and database. It tests
Identity's environment path and Python's file path with semicolons, both quote
types, dollar signs, spaces, equals, Unicode and legacy hexadecimal/LF credentials.
Correct credentials must run SELECT 1; wrong credentials must fail authentication.
The final focused action also checks missing/invalid parameters and invalid files,
retained password bytes through GENERATED_SECRETS, the guard against an actually
initialized volume, and private log checks. Negative inputs use a separate copy;
the original password and database role are never changed.

Full-run `database-auth` checks installed Identity and both Todo directions before
lifecycle testing, after reboot and after upgrades. A correct connection precedes
each sibling-secret negative attempt against the same host/port/user/database.
This proves credential separation, not full network isolation. Original CRUD,
shared-login, data-marker, private-state fingerprint, restart/crash/hang/reboot,
help-only/app-only/core-upgrade, older-core-refusal and survivor checks remain.
The final action also checks installed database/client logs privately for password
or complete connection-string disclosure.

## Limits and deferred work

Both full runs finished with CLEAN PASS, including offline installation,
authentication, restart/crash/hang/reboot, scoped help/app/core upgrades, older-core
refusal, survivor e2e/data markers and clean final audit. The final run uses the
exact final active code; only this report/documentation were updated afterwards.
A passing harness step is not presented as real runtime evidence. Python 3.6 compatibility is checked
statically; no actual Python 3.6 interpreter run was performed. Podman versions
other than 5.8.2 and localized PostgreSQL authentication diagnostics were not tested.

Legacy hexadecimal/LF credentials and byte preservation/reuse against an already
initialized database are tested. A separate full installation upgrade from a
retained 0.2.0 release was not run; its required manual config additions are
documented and pre-image missing-setting failures are tested locally. There is
no automatic migration of a retained 0.1.x monolithic installation. The examples
remain examples; production licensing, privilege redesign and application schema
migration are outside this change. Password rotation and recovery procedures are
separate future work; existing volume/password backups must be restored together.
