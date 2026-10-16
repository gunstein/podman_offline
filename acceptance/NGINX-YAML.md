# Standard nginx configured from YAML (0.4.7)

Backlog item 18 removes the custom proxy build. Platform directly references
`docker.io/library/nginx:1.28-alpine`, the same base tag used by the deleted
Containerfile. The image series has not been changed. Other application image
tags, Containerfiles and build contexts are unchanged.

## Implementation

- `components/platform/manifests/20-proxy-config.yaml` declares the public
  `platform-proxy-config` ConfigMap. Its template is the former nginx config,
  with unchanged TLS protocols/paths, body limit, runtime resolver, `/livez`,
  route include and unknown-route 404. Routes remain separate registrations.
- `80-proxy.yaml` mounts the template read-only with requested mode `0444`.
  Its explicit `/bin/sh -ec` command reads the container's first nameserver,
  requires DNS/HTTPS_PORT, runs envsubst with only those two variables allowed,
  writes to the writable `/etc/nginx/conf.d/default.conf`, then execs nginx as
  the main process. Missing inputs or substitution failure stop startup.
  TLS Secret mode `0400`, TLS/routes mounts, ports, hostname and health probe
  remain unchanged. Host whole-value `@@...@@` rendering is unchanged.
- All three `apps/proxy/` files are removed. Existing `dev/build-images.sh`,
  `dev/pull-images.sh` and `bundle.py` are unchanged: nginx follows the existing
  registry discovery/pull/save path and is loaded offline before installation.
  Target manifests retain `imagePullPolicy: Never`.
- `deployment/deploy.py` includes declared, mounted ConfigMaps in the selected
  component's validated volume deletion list. Environment-only ConfigMaps add
  no volume. Names are checked against local declarations and the component
  prefix before stopping services, then saved in the existing pending record.
  A retry can finish after YAML removal, skip already removed volumes and
  preserve sibling state. Ordinary uninstall retains volumes/config/credentials.
- Release versions are 0.4.7 for all bundles, which ship the shared deploy code
  and documentation. No application code/images or build helper were changed.

The upstream nginx 1.28 Alpine Dockerfile was reviewed at
[docker-nginx commit ffe7297](https://github.com/nginx/docker-nginx/blob/ffe72978e08c5b0dacecd604e528f6d0741a9ae5/stable/alpine-slim/Dockerfile).
It installs gettext-envsubst and uses the normal root entrypoint/CMD. The
manifest supplies the startup command explicitly. This source review is not
verification of an image pulled or run in this workspace; actual image tooling,
ConfigMap population/modes and writable config paths remain target checks.

There is no migration, old proxy fallback, credential regeneration/rotation,
new component model or general lifecycle framework. No persisted installation,
database or lab environment was modified. Existing pending-state guards and
SELinux/fapolicyd setup remain in place.

## Local verification

Executed on 2026-10-16 with Python 3.12.14 / PyYAML 6.0.3:

| Check | Result |
| --- | --- |
| Product tests | 241 passed |
| Acceptance-harness tests | 160 passed |
| Ruff lint / format | passed, 56 Python files |
| Pyright | 0 errors, 0 warnings |
| Vermin | minimum Python 3.6 for host tools/product tests |
| ShellCheck | passed for documented shell entry points and extracted YAML startup command |
| git diff --check | passed |

New tests exercise actual platform rendering, public template/mount permissions,
the real shell/awk/GNU envsubst command with temporary paths and a recording
nginx stub, missing DNS/port, failed substitution, literal nginx variables and
exec process identity. No envsubst test was skipped in this run.

Actual dev helpers run against recording Podman stubs: all four remaining app
builds retain their exact tags/contexts, PostgreSQL retains its upstream pull
and local tag, and nginx is pulled without a proxy build. A real platform tar
archive includes both YAML files and the stock image name; every archive
checksum is verified, with image pull/save transport stubbed.

Scoped cleanup tests cover mounted versus environment-only ConfigMaps, malformed
or undeclared mounted sources refusing before side effects, and partial data
deletion retried in a fresh Python process after rendered YAML removal. Other
components' files and volumes remain unchanged. Existing retained-data,
dependency, registration-owner, credential and failure tests still run.

## Remaining target verification

Neither nginx nor Podman is installed in this workspace. The local shell test
uses host GNU envsubst and a recording nginx stub; it does not parse the result
with nginx, run Alpine tools, mount a real ConfigMap or prove Podman/systemd
behavior. Python 3.6 compatibility is static; no 3.6 interpreter or second
PyYAML version was available. Historical reports/evidence are unchanged and
are not evidence for this change.

Use the existing authorized disposable-lab matrix from a clean committed checkout:
app1-first, app2-first and platform/help-only. The acceptance runner resets its
configured VMs; no such reset was performed here. Verify:

1. Fresh platform alone and platform/help without Identity: stock image available
   offline, populated read-only template, runtime config, correct DNS and port,
   HTTPS `/livez`, unknown-route 404 and healthy systemd/Podman state.
2. Identity followed by app1/app2: HTTPS, login/SSO, public route/client imports,
   application access, and DNS resolution after backend replacement/restart.
3. Offline image loading with no target pull, correct ConfigMap/TLS file modes,
   SELinux/fapolicyd controls and normal signal/restart handling.
4. Retained-data uninstall/reinstall with unchanged credential/config bytes;
   explicit scoped deletion removes the platform ConfigMap volume and route/TLS
   volumes without touching other component state, including retry after failure.

Real container, HTTPS/SSO, restart/DNS, permission and target-policy checks remain
unverified until those fresh runs complete.
