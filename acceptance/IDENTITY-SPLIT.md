# Identity split verification — 0.4.0

Implementation baseline: `7172f25a466e28653d2e52b52eff16517cf1d3fc`
(separate platform, Identity still included). Before changes, 195 product tests
and 152 acceptance-harness tests passed with Python 3.12.14 / PyYAML 6.0.3.
Historical reports, including PLATFORM-RENAME.md and TEST-BASELINE.md, retain
their original evidence and architecture.

## Ownership and compatibility

| Bundle | Own resources and persistent state | Requires |
| --- | --- | --- |
| platform | HTTPS proxy, web TLS, `platform-routes`, platform config | none |
| identity | IdentityServer, PostgreSQL, DB password/data, signing pair, API secret, demo users, Data Protection, `identity-clients`, identity config | platform |
| app1 / app2 | Own Todo pods/database/config, DB password, session material and private client pair | platform + identity |
| help | Static help pod/config and public route | platform |

All five archives contain only their own component/images plus the common
installer/scripts/metadata. `PLATFORM_VERSION` and `IDENTITY_VERSION` independently
version their own bundles; `VERSION` versions app/help. Initial values are 0.4.0.
Only the proxy image changes to 0.4.0, matching its changed route configuration;
Identity's unchanged application image remains 0.2.1. Dev/lab build images from
the matching source and manifest tags. The acceptance upgrade builds a new,
observable Identity application image rather than retagging the existing one.

The fixed dependency graph uses the existing inclusive `min` / exclusive `before`
syntax. Default 0.4.0 requirements accept `[0.4.0, 0.5.0)`; 1.x+ use a major-series
upper bound. Requirements are saved in `HOME/dependencies/<component>.json`.
Incoming dependency versions and all installed dependent contracts are validated
before secret/image/state operations, without reading old release directories.
Shared equal versions retain installed rendered resources, newer versions upgrade,
and older versions refuse. Missing/invalid stored contracts refuse a shared upgrade.

Platform now retains only `generated-certificates/web` and public routes.
Identity's directory owns the previous identity, identity-db, app and users
credential subdirectories, all under `HOME/identity/generated-certificates/`.
The former platform identity/data/protection/client resources become
`identity-server`, `identity-postgres`, `identity-data`, `identity-protection`,
`identity-clients`, `identity-settings`, `identity-signing`, `identity-api-secrets`,
`identity-database-password` and `identity-demo-users`. These are fresh-install
resource names; no existing persistent material is moved or regenerated.
Shared `PKI/private` and `myproduct.network` retain their existing lifecycles.

Identity owns its `/identity/` route registration. Public route changes update
only platform imports/restart; public client metadata/certificate changes update
only Identity imports/restart. Both changes restart both owners. Identical
registrations restart neither shared service. App private keys remain in their
own app. Current indexes keep stale imported files inactive after removal.
Issuer, public paths, client IDs, scopes, redirects and cookies are unchanged.
Dynamic route upstream resolution lets platform serve help without Identity.

Uninstall respects the fixed graph: apps block Identity, help does not; all four
dependents block platform. Removed app routes/clients refresh their respective
owners. Identity removal removes its route while retaining platform/help.
Data/config/credentials remain by default; `--delete-data` removes only volumes
and state declared by the selected component. Shared CA/network are retained.

## Existing installations

This release requires a fresh installation. Core 0.2.x and combined platform /
Identity 0.3.x cannot be upgraded automatically. Guards inspect concrete old
credential/import paths, platform config/rendered service references, pre-0.4
platform markers and old retained volume names. Missing installed markers and
mixed/partial state do not bypass detection. Necessary volume-check failures
refuse; certificate generation also guards against the old layout before writes.
A pure proxy platform alone is valid. Old state remains manageable using its
previous release. No automatic rename, database initialization, secret replacement,
cleanup or schema migration is provided. Backlog item 11 covers a separate,
reviewed migration procedure for both prior layouts.

## Local verification

Final local checks: 205 product tests and 158 acceptance-harness tests passed
with Python 3.12.14 / PyYAML 6.0.3. Ruff lint and format, pyright (zero errors),
vermin (Python 3.6 minimum) and shellcheck passed. Tests use real temporary files, rendered manifests, public registration/import archives,
bundle tarballs and checksums; Podman/systemd/VM transport is stubbed.

New product coverage includes independent Identity versions/range rejection,
app refusal without Identity before writes, help without Identity, four exact
registration/restart combinations, independent imports, uninstall blocking,
scoped deletion and unchanged old credentials/config/services/volumes on refusal.
The certificate guard is exercised before CA/new Identity creation.

New harness tests execute the actual Identity build heredoc against an isolated
source fixture with image transport stubbed and inspect its resulting archive.
They verify transfer of only Identity, both installed apps, refusal to retire old
trust after any failed check, and focus mode without Identity. Runtime observation
validation rejects an unchanged/wrong image ID, wrong image name, missing new
health content, or changed credentials/data volumes. Database log checks verify
the separated Identity container names and keep credentials out of evidence.

## Real lab runs pending

No actual Podman/Quadlet/fapolicyd/SELinux/VM acceptance run was performed here.
Local results do not prove target DNS, service health/restarts, retained runtime
volume identity, shared SSO, database authentication, offline operation or reboot
persistence. Python 3.6 compatibility is checked statically with vermin; no Python
3.6 runtime or second PyYAML version was available in this environment.

Run from a clean committed checkout with the existing configured disposable lab
VMs. Each command resets both VMs; run separately:

```sh
python3 acceptance/acceptance.py --run identity-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run identity-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run identity-upgrade --identity-only run
python3 acceptance/acceptance.py --run help-no-identity --platform-help-only run
python3 acceptance/acceptance.py --run identity-core-refusal --legacy-refusal run
```

The full runs retain app/help/platform upgrades, stop/start/crash/hang, reboot,
markers, shared login and persistent-state checks. The focused Identity run
installs platform/Identity/both apps/help, creates data, builds a newer Identity
image with an added health release value, transfers only its archive/checksum,
installs and requires a different running image ID matching the new tag plus
observable application content. Private config/credential hashes and modes and
database/Data Protection volume names/mountpoints/creation times must match.
Login, both apps' retained markers and database authentication are checked before
old Identity trust is retired. Platform/apps/help process identities, versions,
config/credential/import/unit hashes, network identity and trust must remain equal.

`--platform-help-only` installs only platform/help and checks verified HTTPS help
without an Identity directory/marker. `--legacy-refusal` retains genuine pinned
core 0.2.0 refusal checks. The historical successful 0.2.0 upgrade remains runnable
at `511099e`, as described in TEST-BASELINE.md. Real combined-platform 0.3.x
migration remains future work, with local refusal coverage in this release.

Next implementation: backlog item 1 (deploy maintainability refactor). Password
rotation, schema changes and migration are separate work; no module refactor is
included in this functional split.
