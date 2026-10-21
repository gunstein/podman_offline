# Components and the catalog

A product is a set of components. Each component is one directory under
`components/` and one entry in `bundles.yaml`, and it becomes one offline
bundle. The deploy tools read these declarations; they contain no list of
component names. The five shipped components (`platform`, `identity`, `app1`,
`app2`, `help`) are one demo product, not a built-in model.

## Three representations of one model

| Where | File | Written by | Read by |
| --- | --- | --- | --- |
| Source checkout | `bundles.yaml` (the catalog) | you | `./deploy validate`, `./deploy prepare`, `dev/dev.sh`, `./build-bundle.sh`, image helpers |
| Unpacked bundle | `bundle.yaml` (one compiled descriptor) | `./build-bundle.sh` | `init-config`, `validate`, `install`, `uninstall` |
| Target host | `/var/lib/<product>/metadata/<id>.json` | `install` | later installs and uninstalls of any component |

`deployment/catalog.py` validates all three with the same rules. The compiled
descriptor adds what the target cannot look up: the component's version and the
version ranges of its dependencies. Installed metadata lets a target find the
dependents and registration owners of a component without the source checkout,
and without the release directories of other components.

## The catalog: `bundles.yaml`

```yaml
product: <name>                  # required; names the whole installation
components:
  <id>:
    requires: [<id>, ...]        # installed first; default []
    upgrade: always              # or newer-only; default always
    public_from: <id>            # take PUBLIC_ORIGIN, HTTPS_PORT and its shares from this dependency
    shares: [<NAME>, ...]        # config names this component's public_from dependents take from it
    routes: <id>                 # register route.conf with this dependency
    clients: <id>                # register client.yaml with this dependency
    accepts:                     # roles this component serves
      routes: <id>-<volume>      # volume that receives all routes
      clients: <id>-<volume>     # volume that receives all OIDC clients
```

`product:` is required; every component field is optional, and `<id>: {}` is a
complete entry. Unknown fields,
duplicate keys and invalid values are refused before any file, secret, image or
service is touched. Errors name `bundles.yaml`, the component and the field.

### Product name

`product:` names everything the installation creates: the bundle archives
`<product>-<id>-<version>-offline.tar.gz`, the default service user and home
`/var/lib/<product>`, the units `<product>-<id>.service` with their Quadlet
files, and the shared network `<product>`. It is compiled into every
`bundle.yaml` and installed metadata, so the target needs no other setting;
install and uninstall refuse a bundle whose product differs from the installed
components'. Use lowercase letters, digits and inner hyphens, a letter first and
at most 32 characters. The demo uses `myproduct`; the renamed acceptance product
uses `shop`. A standalone manifest fixture (no `bundles.yaml`) is always
`myproduct`.

### Component IDs

IDs use lowercase letters, digits and inner hyphens: `my-identity` is valid,
`my_identity` and `MyIdentity` are not. An ID becomes the prefix of every Pod,
Secret, PVC and ConfigMap the component owns, its systemd unit
(`<product>-<id>.service`) and directory names, so names are checked, never
rewritten. `installed`, `metadata`, `routes`, `clients` and `files` are
reserved for shared state on the target. No ID may be another ID followed by
`-`: with `orders` and `orders-data`, the name `orders-data-db` would belong to
both, so their volumes could be confused. The catalog and install refuse such a
pair, also against already installed components.

Component IDs, image names, resource names, public URL paths and OIDC client
IDs are separate things. Only resource names carry the component ID; for
example the renamed acceptance product serves component `inventory` at `/stock`
with client ID `inventory` and component `orders` with client ID `orders-web`.

### Selection

The catalog is the product. Only listed components are prepared, started in
dev, scanned for images, built, bundled and guarded. A directory under
`components/` without a catalog entry is ignored, even if it is invalid. A
listed component whose directory is missing is an error, not a silent removal.

### Dependencies and order

`requires` names components in the same catalog; unknown names, a component
naming itself and cycles are refused. Components are processed in dependency
order: dependencies first, otherwise in catalog order. Manifests inside a
component keep their file order.

Each bundle records a version range for every dependency, computed from that
dependency's version when the bundle is built: the same minor series while the
version is 0.x (`0.4.2` gives `{min: 0.4.2, before: 0.5.0}`), otherwise the same
major series. Install refuses a missing or incompatible dependency, and an
upgrade that would break the recorded range of an installed dependent.
Uninstall refuses while an installed component still requires it.

### Versions and upgrades

Each component must contain `components/<id>/VERSION` with one
`major.minor.patch` version. This is its only source version; `version_file`
is not accepted in `bundles.yaml`. Components released together keep the same
number in their separate files. Missing, invalid or escaping version files are
refused before building. Each bundle retains an informational root `VERSION`;
installed metadata stores its compiled version, so existing installations need
no migration. Standalone manifest fixtures without a catalog keep root `VERSION`.

- `upgrade: always` renders and restarts the component on every install.
- `upgrade: newer-only` installs a missing or newer version, keeps an equal
  installed version unchanged (its route/client imports may still be rebuilt)
  and refuses a downgrade. The demo uses it for `platform` and `identity`.

### Public settings and shared settings

`public_from: <id>` declares that the component uses the same `PUBLIC_ORIGIN`
and `HTTPS_PORT` as that dependency, plus every name that dependency lists in
`shares`. `init-config` copies these values from the dependency's persistent
config, dev prepare copies them from the dependency's dev config, and install
(and `validate`) refuse a mismatch, naming the setting, both files and the
owner, never the values. A component without `public_from` needs none of them
unless its manifests use them.

```yaml
gateway:
  shares: [SHOP_NAME]            # dependents with public_from: gateway take it
orders:
  requires: [gateway]
  public_from: gateway           # gets PUBLIC_ORIGIN, HTTPS_PORT and SHOP_NAME
```

`shares` holds config names (`A-Z`, `0-9`, `_`, the placeholder rule) without
repeats. `PUBLIC_ORIGIN` and `HTTPS_PORT` are always shared; listing them changes
nothing. The owner's own config must define every name it shares. `shares` is
compiled into `bundle.yaml` and installed metadata, so a dependent's install
compares against the owner's installed declaration without the source. An owner
upgrade that stops sharing a name an installed dependent takes from it is
refused before any write; keep the name until the dependents no longer use it.
A descriptor from before `shares` existed is read as sharing nothing.

### Component dev configuration

Source dev merges optional common defaults, component defaults, global
`config/dev.yaml`, then `components/<id>/config.dev.yaml`. Values replace whole
top-level values, including file/Secret maps and source lists. The component dev
file is tracked shared configuration, contains no secret values, and wins over
the ignored global dev file. It is excluded from bundles and never read by
production `init-config`, `validate` or `install`.

An owner's component dev settings are inherited by its `public_from` dependents.
A dependent that declares any of those shared keys in its own component dev file
is refused, rather than silently losing the value to inheritance. This includes
`PUBLIC_ORIGIN`, `HTTPS_PORT` and custom `shares`. Shared keys always come from
the owner's effective dev config, which includes global `config/dev.yaml`, so a
global value reaches the owner and every dependent identically. An owner's own
`config.dev.yaml` value is more specific and wins over the global one for all
dependents alike, as production `init-config` also inherits from the owner
(backlog 58).

Relative file sources still resolve from `build/dev/<id>/`; generated config
there is output, never an input layer. See the [configuration examples and
precedence](../README.md#configuration-and-initialization). Portable shipped-file
references use `component_file` as described below.

### Bundled component file references

`SECRET_FILES` and `VOLUME_FILES` sources have exactly one of `path` or
`component_file`. The latter is relative to `components/<id>/files/` in the source
checkout or selected bundle (`common.ROOT`), with explicit current-component
context. It is retained logically in initialized config, so a newer bundle can
deliver changed bytes without config edits. Missing files fail; no source, sibling
or old-release fallback exists. Stable reference names remain part of the
operator's retained config contract.

`component_file` cannot generate credentials or supply a database password.
Symlinks and special files throughout selected trees, absolute/traversing paths
and missing component context are refused before writes. Delivery remains the
existing Secret/import-archive/PVC flow, with existing names, duplicate, type and
size rules. Secret delivery of a component file explicitly selects public bundle
content; external/generated credentials stay protected by the bundle guard.
Validation inspects names/types without reading input bytes.

For `sts`, use `component_file: sql/010-reference.sql` for shipped migrations in
`config.defaults.yaml`. A `config.dev.yaml` map can repeat that reference and add
`path: ~/dev-inputs/sts/900-dev-users.sql` for a sensitive local dev seed outside
`files/`. Production needs only the shipped input; the local path is neither
packaged nor read there. All of `files/` ships, including dev-only files stored
there. Test passwords must stay in external/generated credentials. See the
[complete sts example and offline upgrade commands](../README.md#portable-component-files).

Input resolution never executes or templates SQL. The consuming image owns that
behavior. Import volumes retain unlisted files, so removing a migration source
does not remove its old imported copy. The demo uses idempotent SQL and documents
partial commits/retry; it adds no migration framework or rollback guarantee.

### Reserved configuration names

All settings are written the same way, but these names have built-in meaning.
The tools must know them to validate values, derive the hostname and build
redirect URIs, so they cannot be renamed or shared freely:

| Name | What the tools do with it |
| --- | --- |
| `PUBLIC_ORIGIN` | Validated as an HTTPS origin; always shared with `public_from` dependents (copied at `init-config` and in dev, compared at install); OIDC redirect URIs are built from it |
| `HTTPS_PORT` | Validated as a port 1-65535; always shared and compared like `PUBLIC_ORIGIN` |
| `PUBLIC_HOSTNAME` | Always derived from `PUBLIC_ORIGIN`; setting it is an error; cannot be shared |
| `SECRET_FILES`, `VOLUME_FILES`, `SECRET_TEMPLATES` | File-source and Secret-template declarations, not placeholder values; cannot be shared |
| Any other name, e.g. `PUBLIC_MY_SETTING` | Only replaces `@@NAME@@`; each component keeps its own copy unless the `public_from` owner lists it in `shares` |

A `PUBLIC_` prefix has no meaning of its own. `deploy.PUBLIC_KEYS` and
`catalog.UNSHAREABLE` hold these names in code.

### Registrations: routes and OIDC clients

A component that serves a role declares `accepts`. At most one component may
accept each role. A component that uses a role names that owner in `routes` or
`clients`, lists it in `requires`, and ships the matching file:

| Role | File in the component | Owner's import |
| --- | --- | --- |
| `routes` | `route.conf`, an nginx location block | `installed.conf`, every route concatenated |
| `clients` | `client.yaml` | one directory per component plus `installed.json` |

The file must exist exactly when the role is declared. The owner's manifests
mount the declared volume; its archive is rebuilt from the current
registrations on every change, so removed registrations do not stay active.

`client.yaml` follows the protocol of the existing apps and Identity:

```yaml
id: orders-web                 # the app's APP_ID; any valid ID, unique across clients
base_path: /orders             # the app's BASE_PATH; redirect URI is origin + base_path + /auth/callback
scopes: [openid, profile, orders-web]   # the app requests its client ID as a scope
certificate: credentials/client/client.crt   # public certificate, relative to the config folder
environment:                   # optional: the app's variables carrying id and base_path
  id: APP_ID
  base_path: BASE_PATH
```

A component with `clients` must also declare `public_from`, because the
redirect URI needs the public origin. Only public certificates are accepted.

The same id and base_path appear in three places: `client.yaml`, the app's own
settings and `route.conf`. A mismatch would show only as an OIDC failure at
login, so `validate`, `prepare` and `install` check it first: `route.conf` must
have a `location` for `base_path`, and with `environment:` every container that
sets a named variable must set it to the `client.yaml` value (and one must set
it). The tools do not know an app's variable names; a product names them here.

Restarts follow the changes: no change restarts no owner, a route change the
route owner, a client change the client owner. The selected component restarts
first and owners after it, so a gateway publishes a route only once the service
behind it is back. Unrelated components never restart.

## Secret templates

`SECRET_TEMPLATES` builds complete private configuration values at render time,
without changing an application's image or code:

```yaml
DB_HOST: database
DB_PORT: '5432'
DB_NAME: app
DB_USER: app
SECRET_FILES:
  orders-database-password:
    - path: credentials/database
      generate: [password]
SECRET_TEMPLATES:
  orders-database:
    ConnectionStrings__Default: "Host=@@DB_HOST@@;Port=@@DB_PORT@@;Database=@@DB_NAME@@;Username=@@DB_USER@@;Password=@@secret:orders-database-password/password@@"
```

The application container consumes the result with ordinary Kubernetes YAML:

```yaml
env:
  - name: ConnectionStrings__Default
    valueFrom:
      secretKeyRef:
        name: orders-database
        key: ConnectionStrings__Default
```

An application that reads files can instead mount this Secret with
`volumes[].secret.items`, selecting the same key. Secret IDs follow the component
prefix/name rules and cannot collide with `SECRET_FILES`, `VOLUME_FILES` or
manifest resources; keys follow the Secret file-name rule. Each ID has a nonempty
mapping of keys to string templates. It is a reserved setting and cannot be shared.

Secret templates and ConfigMap `data` values accept placeholders inside strings.
In Secret templates, `@@NAME@@` reads this
component's effective string/integer config (including shared settings).
`@@secret:<id>/<file>@@` reads a file key delivered by this component's
`SECRET_FILES`, including a declared generated file. A declared source without
`generate` may be supplied by the operator after `init-config`; it must exist
before install. `validate` and `install` report a missing source file without
reading or printing its contents during declaration validation. References to
other templates, recursive expansion, expressions and commands are unsupported. Other manifest
fields still replace whole values only.

The renderer removes trailing LF bytes from a secret input, matching PostgreSQL's
`file_env`; it never rewrites the source file. Inputs containing semicolons, single
or double quotes, control characters, leading/trailing whitespace, or placeholder
markers (`@@`) are refused without including their values in diagnostics.
Generated alphanumeric passwords satisfy this rule. The renderer does not escape
for connection strings, URLs or other target formats. Use a file-aware app or
prepare the complete value externally for formats requiring other encodings.
An existing database password failing the rule must be changed through a
coordinated database-role/password-file/client rotation or recovery procedure
(backlog 2/3), never by deleting the file and letting install regenerate it.

`validate` checks recipe shape, public inputs and file-key declarations without
reading credentials. Secret bytes are checked only during materialization after
database preflight and permitted generation. Derived values have no separate
persistent source: config plus the original password file are authoritative.
Actual rendering recomputes values; `upgrade: newer-only` with an equal version
still skips rendering, and a systemd restart uses the last installed YAML.
Existing installations must explicitly add the new declaration to their persistent
config before upgrading to a manifest that references it; `init-config` retains
existing config rather than merging new defaults.

The output is an Opaque Secret in the existing 0600 install YAML. Base64 is not
encryption; protect YAML, source files, Podman storage and backups. Environment
values are visible to the service user/root through `podman inspect`, process
environments and child processes. File mounts avoid the extra environment copy
but still require suitable container ownership/modes. No new credential files,
network services, SELinux exceptions or fapolicyd trust rules are needed.

## ConfigMap inline values

A ConfigMap's `data` values can combine ordinary configuration values, including
in multi-line file content:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-settings
data:
  DB_HOST: '@@DB_HOST@@'
  API_URL: 'http://@@API_HOST@@:@@API_PORT@@/v1'
  client.conf: |
    server=@@API_HOST@@
    port=@@API_PORT@@
```

Inline inputs must be strings or integers and the result is always text.
Whole-value replacement retains its existing type behavior before ConfigMap data
is converted with `str()`. The same single-pass substitution function serves
Secret recipes and ConfigMaps, but ConfigMaps have no access to Secret contents:
`@@secret:<id>/<file>@@` is refused with a pointer to `SECRET_TEMPLATES`.
Keep private input in `SECRET_FILES`, not ordinary public config.

ConfigMap public text does not use the Secret recipe's character restrictions:
quotes, semicolons and multi-line text remain valid. There is no recursive
expansion or escape syntax for `@@`; malformed markers or markers remaining in
a substituted value are refused. Dollar syntax such as `${HTTPS_PORT}`, `$host`
and shell/nginx templates is preserved verbatim.

Outside ConfigMap `data` and `SECRET_TEMPLATES`, fields such as container
`env.value`, images, names, volume bindings and ConfigMap metadata still require
whole-value placeholders. Validation is shared by initialization, validate and
rendering before generation or host commands. Config changes take effect when
a component actually renders; the existing equal-version `newer-only` policy
and ordinary restart behavior apply here too.

The demo's platform ConfigMap supplies `PUBLIC_ENDPOINT` from
`PUBLIC_HOSTNAME` and `HTTPS_PORT`. The acceptance health check verifies both the
rendered value and `printenv PUBLIC_ENDPOINT` inside the consuming proxy. It
follows the ConfigMap reference, so the same check covers the renamed `shop`
gateway and all six scenarios without generic deploy-code changes.

## Manifest resource kinds

A component's `manifests/*.yaml` may contain only `Pod`, `ConfigMap`,
`PersistentVolumeClaim` and `Secret` documents (empty documents are ignored).
Every other kind, such as `Deployment` or `List`, and a document without a
`kind` is refused by `./build-bundle.sh`, `prepare` and `install` before any
Podman call or write. The lifecycle checks (resource names, pull policy, mounts,
images, database preflight, uninstall cleanup) read Pods only, so another kind
would pass some checks and skip others.

## Installed state

```text
/var/lib/<product>/
├── <id>/config.yaml        authoritative config (init-config, then you)
├── metadata/<id>.json      compiled descriptor, written before registrations
├── installed/<id>          version, written last: the install is complete
├── routes/<id>.conf        registered routes
├── clients/<id>/           registered public client files
└── pending-operation.json  unfinished owner work for a retry
```

`installed/<id>` without `metadata/<id>.json` is an error. Metadata without the
marker is an unfinished install that a retry completes. Removing a component
from a new source catalog never changes installed state; only an explicit
uninstall from that component's bundle does.

## Demo provisioning

Generic tools never create certificates or demo users. For the shipped demo:

```sh
./dev/build-images.sh && ./dev/pull-images.sh
dev/demo-credentials.sh && ./deploy validate && dev/dev.sh up
```

After adding or changing a component, run `./deploy validate` first: it
reports the first finding of every component (file, document or container and
the declaration it expected) without writing anything or calling Podman.

`dev/demo-credentials.sh` runs `dev/generate-certificates.sh` for the five
demo components. Another product prepares its own credentials in
`build/dev/<id>/` (dev) or `/var/lib/<product>/<id>/` (production) before
prepare or install.

## Example: add a service with an external image

Add `components/reports/manifests/10-reports.yaml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: reports-web
spec:
  containers:
  - name: web
    image: registry.example.com/team/reports:1.4.0
    imagePullPolicy: Never
```

Add `components/reports/route.conf`:

```nginx
location /reports/ {
    set $reports_upstream reports-web:8080;
    proxy_pass http://$reports_upstream;
}
```

Add the entry to `bundles.yaml`:

```yaml
  reports:
    requires: [platform]
    public_from: platform
    routes: platform
```

No Python or shell file changes. `./deploy prepare` and `dev/dev.sh up` start
it; `./build-bundle.sh` pulls the image, saves it in
`dist/<product>-reports-<version>-offline.tar.gz` and lists it in
`dist/current-bundles.txt`; `./build-bundle.sh reports` builds only that bundle
and leaves the list unchanged. On the target: `./deploy init-config reports`,
prepare any credentials, then `./deploy install` from that bundle. Installing
it restarts `reports` and `platform`.

A worker without a gateway needs only the manifest and `worker: {}`.

## Example: remove a service

1. Stop the dev product while the service is still rendered: `dev/dev.sh down`.
   This stops only what the last prepare rendered and keeps volumes.
2. Remove its catalog entry and `components/<id>/`, and remove it from every
   other entry's `requires`, `routes` or `clients`. A remaining reference fails
   before any write and names the declaration.
3. `./deploy validate`, `dev/dev.sh up` and `./build-bundle.sh`. The service is gone from
   `build/install.yaml`, the dev route/client imports and
   `dist/current-bundles.txt`. Older archives stay in `dist/` for hosts that
   still run the service; `current-bundles.txt` names only the current product.
4. On a target, keep the service's earlier bundle and run `./deploy uninstall`
   from it (`--delete-data` also deletes its volumes and private state). Other
   components and their registrations stay.

Dev data volumes of a removed service are not deleted; remove them with
`podman volume rm <id>-...` when they are no longer needed.
