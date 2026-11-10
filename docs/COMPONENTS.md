# Components and the catalog

A product is a set of components. Each component is one directory under
`components/` and one entry in `bundles.yaml`, and it becomes one offline
bundle. The deploy tools read these declarations; they contain no list of
component names. The six shipped components (`platform`, `identity`, `app1`,
`app2`, `app3`, `help`) are one demo product, not a built-in model. `app3` is
the .NET/TypeScript demo of backlog 71; the fixed acceptance matrix installs
the other five.

## Three representations of one model

| Where | File | Written by | Read by |
| --- | --- | --- | --- |
| Source checkout | `bundles.yaml` (the catalog) | you | `./deploy.sh validate`, `./deploy.sh prepare`, `dev/dev.sh`, `./build-bundle.sh`, image helpers |
| Unpacked bundle | `bundle.yaml` (one compiled descriptor) | `./build-bundle.sh` | `init-config`, `validate`, `install`, `uninstall` |
| Target host | `/var/lib/<product>/state/metadata/<id>.json` | `install` | later installs and uninstalls of any component |

`deployment/catalog.py` validates all three with the same rules. The compiled
descriptor adds what the target cannot look up: the component's version and the
version ranges of its dependencies. Installed metadata lets a target find the
dependents and registration owners of a component without the source checkout,
and without the release directories of other components.

## The catalog: `bundles.yaml`

```yaml
product: myproduct          # required; names the whole installation
gateway: platform           # optional: the reverse proxy component
identity: identity          # optional: the component that registers OIDC clients and API secrets
components: [platform, identity, app1, reports]   # component IDs only
```

A component has no fields in the catalog. Everything else is derived from
`gateway:`, `identity:` and the component's files (backlog 77):

| Rule | Result |
| --- | --- |
| The gateway | Receives every `route.conf` in the volume `<gateway>-routes`, which its manifests must mount. |
| Every other component, when a gateway is set | Reads the gateway's `PUBLIC_ORIGIN` and `HTTPS_PORT` and requires the gateway. |
| A component with `route.conf` | Registers it with the gateway. Without a gateway, or on the gateway itself, it is refused. |
| A component with `client.yaml` | Registers it with identity and requires identity. It needs a gateway (the redirect URI uses the public origin); not on the gateway or identity itself. |
| A component whose secret identity's `ApiResources__<n>__ApiSecrets__0__Value` line names | Is an API: identity receives that secret ([API secrets](#api-secrets)) and the API requires identity. |
| Identity | Receives clients in `<identity>-clients` only while some component has `client.yaml`, and API secrets in the platform-rendered Secret `<identity>-apis` only while some component is an API. |
| A component with none of these files | Has no link to identity and does not depend on it. |

Dependencies exist only through these rules: the gateway, then identity. The
earlier map form with per-component fields (`requires`, `upgrade`, `shares`,
`public_from`, `routes`, `clients`, `apis`, `accepts`) is refused; there is
only one way to write a catalog. An explicit dependency between two
applications is not supported now (product owner, 2026-10-31). `./deploy.sh validate` prints what was derived:

```text
[OK] platform: receives routes in platform-routes
[OK] app3: public settings and routes from platform; client.yaml -> identity; API secret -> identity; requires platform, identity
[OK] help: public settings and routes from platform; requires platform
```

Unknown fields, duplicate keys and invalid values are refused before any file,
secret, image or service is touched. Errors name the file, the component and
the rule. The normalized result is compiled into each `bundle.yaml` exactly as
before, so targets never derive anything themselves.

### Product name

`product:` names everything the installation creates: the bundle archives
`<product>-<id>-<version>-offline.tar.gz`, the installation root
`/var/lib/<product>` with the bootstrap file `~/.<product>/<product>.env` of the
explicitly chosen runtime account (backlog 64), the units `<product>-<id>.service` with their Quadlet
files, and the shared network `<product>`. It is compiled into every
`bundle.yaml` and installed metadata, so the target needs no other setting;
install and uninstall refuse a bundle whose product differs from the installed
components'. Use lowercase letters, digits and inner hyphens, a letter first and
at most 32 characters. The demo uses `myproduct`; the renamed acceptance product
uses `shop`.

### Component IDs

IDs use lowercase letters, digits and inner hyphens: `my-identity` is valid,
`my_identity` and `MyIdentity` are not. An ID becomes the prefix of every Pod,
Secret, PVC and ConfigMap the component owns, its systemd unit
(`<product>-<id>.service`) and directory names, so names are checked, never
rewritten. `installed`, `metadata`, `routes`, `clients`, `apis` and `files` are
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
dev, scanned for images, built, bundled and guarded. A build environment can
build a subset of it ([the components of an
environment](#the-components-of-an-environment)). A directory under
`components/` without a catalog entry is ignored, even if it is invalid. A
listed component whose directory is missing is an error, not a silent removal.

### Dependencies and order

Every component except the gateway depends on the gateway, and a component
with `client.yaml` or an API secret depends on identity. Components are
processed in dependency order: dependencies first, otherwise in catalog order.
Manifests inside a component keep their file order.

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
no migration.

Every install renders and restarts the component again, also at the same
version, so a changed `config.yaml` or a replaced credential takes effect by
installing again. An older version than the installed one is refused
(backlog 77 removed the earlier `upgrade:` choice).

### Public settings

`PUBLIC_ORIGIN` and `HTTPS_PORT` are written once, in the gateway's
`config.yaml`. Every other component reads them from there when it is
validated, installed or prepared in dev; its own `config.yaml` does not hold
them, and a copy there is refused ("is read from gateway's config.yaml; remove
it here"). `init-config` checks the installed gateway's values but writes none
of them. To change the public address, edit the gateway's `config.yaml` and
install the components again. Without a gateway, a component that uses them
sets them in its own config. No other setting is shared between components.

### Component dev configuration

Source dev merges the component defaults, then the developer's local
`config/dev.yaml` (untracked, for every component). A setting replaces the
whole value; a `SECRET_FILES`/`VOLUME_FILES` ID replaces only that ID's source
list in the component it starts with, which must declare it. Its reserved
`overrides` block adds or replaces container variables as a build environment
file does ([environment overrides](#environment-overrides-configenvironmentyaml));
it is no setting and never reaches `build/dev/<id>/config.yaml`. The file is
excluded from bundles and never read by production `init-config`, `validate`
or `install`.

Every other component gets the gateway's effective dev `PUBLIC_ORIGIN` and
`HTTPS_PORT`, as production reads them from the gateway's `config.yaml`. A
component that sets either in its own `config.defaults.yaml` is refused. The
gateway's effective dev config includes `config/dev.yaml`, so a global value
reaches every component identically.

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
`config.defaults.yaml`. A `config/dev.yaml` entry for the same ID can repeat that reference and add
`path: ~/dev-inputs/sts/900-dev-users.sql` for a sensitive local dev seed outside
`files/`. Production needs only the shipped input; the local path is neither
packaged nor read there. All of `files/` ships, including dev-only files stored
there. Test passwords must stay in external/generated credentials. See the
[complete sts example and offline upgrade commands](../README.md#portable-component-files).

Input resolution never executes or templates SQL. The consuming image owns that
behavior. Import volumes retain unlisted files, so removing a migration source
does not remove its old imported copy; run an explicit file list or keep a
history table instead of executing everything in the volume. The demo runs each
idempotent file in its own transaction (`--single-transaction`), so a failed file
rolls back while completed files stay committed; it adds no migration framework
or cross-file rollback guarantee.

### Reserved configuration names

All settings are written the same way, but these names have built-in meaning.
The tools must know them to validate values, derive the hostname and build
redirect URIs, so they cannot be renamed:

| Name | What the tools do with it |
| --- | --- |
| `PUBLIC_ORIGIN` | Validated as an HTTPS origin; set only in the gateway's `config.yaml` and read from there by every other component; OIDC redirect URIs are built from it |
| `HTTPS_PORT` | Validated as a port 1-65535; set and read like `PUBLIC_ORIGIN` |
| `PUBLIC_HOSTNAME` | Always derived from `PUBLIC_ORIGIN`; setting it is an error |
| `SECRET_FILES`, `VOLUME_FILES` | File-source declarations, not placeholder values |
| `SECRET_TEMPLATES` | Refused in every config file; the platform's internal name for the Secrets it renders from `ENVIRONMENT` and `MOUNTS` |
| `ENVIRONMENT`, `MOUNTS` | Each container's environment and mounted files; only in the release's `config.defaults.yaml`, never in the operator's `config.yaml` or a dev file |
| `overrides` | Only in `config/dev.yaml` and a build environment file `config/<environment>.yaml`: per-component `ENVIRONMENT` overrides ([environment overrides](#environment-overrides-configenvironmentyaml)); never a setting |
| `COMPONENT_VERSION` | Only in a container `image`: the component's `VERSION` ([image versions](#image-versions-configimagesyaml)) |
| Any other name, e.g. `PUBLIC_MY_SETTING` | Only replaces `@@NAME@@` in its own component |

A name in `config/images.yaml` is an image variable and cannot also be a
setting in a component's `config.defaults.yaml`.

A `PUBLIC_` prefix has no meaning of its own. `catalog.PUBLIC_KEYS` holds the
two public names in code.

### Registrations: routes, OIDC clients and API secrets

| Registration | In the component | Received by |
| --- | --- | --- |
| Route | `route.conf`, an nginx location block | the gateway: volume `<gateway>-routes` with `installed.conf`, every route concatenated |
| OIDC client | `client.yaml` | identity: volume `<identity>-clients`, one directory per component plus `installed.json` |
| API secret | the API's own declared secret, named on identity's `ApiResources__<n>__ApiSecrets__0__Value` line | identity: Secret `<identity>-apis`, one key per API |

The receiving component's manifests must mount the volume in a container
(declaring it as a Pod volume is not enough; `validate` refuses that). Both
are rebuilt from the current registrations on every change, so removed
registrations do not stay active.

`client.yaml` follows the protocol of the existing apps and Identity:

```yaml
id: orders-web                 # any valid ID, unique across clients
base_path: /orders             # redirect URI is origin + base_path + /auth/callback
scopes: [openid, profile, orders-web]   # the app requests its client ID as a scope
certificate: credentials/client/client.crt   # public certificate, relative to the config folder
```

Only public certificates are accepted. The app receives the id and base path
from this file through `ENVIRONMENT`, so they are written only here:

```yaml
ENVIRONMENT:
  backend:
    APP_ID: '@@CLIENT_ID@@'
    BASE_PATH: '@@CLIENT_BASE_PATH@@'
```

`CLIENT_ID` and `CLIENT_BASE_PATH` exist only for a component with
`client.yaml` and cannot be set in config. `route.conf` must have a `location`
for `base_path`; `validate`, `prepare` and `install` check that first, because
a mismatch would otherwise show only as an OIDC failure at login.

Restarts follow the changes: no change restarts no owner, a route change the
gateway, a client change identity, an API secret change identity. The selected
component restarts first and the receivers after it, so a gateway publishes a
route only once the service behind it is back. Unrelated components never
restart.

## One config file per component: `config.defaults.yaml`

A component has one config file. Its top part holds the settings and secrets
the operator owns; `ENVIRONMENT` holds the environment of each container,
which belongs to the release:

```yaml
# components/orders/config.defaults.yaml

# Settings the operator may change: init-config copies them to config.yaml.
DB_HOST: orders-postgres
SECRET_FILES:
  orders-database-password:
  - path: credentials/database
    generate: [password]

# The environment of each container. It comes with the release and is never
# copied to config.yaml.
ENVIRONMENT:
  backend:
    ASPNETCORE_HTTP_PORTS: 5000
    Authentication__Authority: '@@PUBLIC_ORIGIN@@/identity'
    ConnectionStrings__Default: 'Host=@@DB_HOST@@;Database=orders;Username=orders;Password=@@secret:orders-database-password/password@@'
```

- `init-config` copies everything except `ENVIRONMENT` to the operator's
  `config.yaml`; the operator's file may not contain `ENVIRONMENT`. A new
  release therefore always brings its own environment, while the operator's
  values stay.
- Placeholders: `@@NAME@@` is a setting from the top part (or a shared public
  setting); `@@secret:<id>/<key>@@` is the file `<key>` of `SECRET_FILES.<id>`.
  There is no other form, and a secret is always declared in `SECRET_FILES`
  with its path.
- Every value is the text as written: `UMASK: 0022`, `ENABLED: yes` and
  `VERSION: 1.10` reach the container unchanged. Quote values that start with
  `@@`.
- Lines without a secret become the ConfigMap `<component>-<container>-env`;
  lines with one become the Secret `<component>-<container>-env-secret`. The
  platform adds `envFrom` for both to that container; nobody writes those
  names. `./deploy.sh validate` shows each container without values:

  ```text
  [OK] orders/backend: ENVIRONMENT -> 2 settings (ConfigMap orders-backend-env), 1 secret (Secret orders-backend-env-secret: orders-database-password)
  ```

Rules, each refused before anything is written with the file and the next step:

- `<container>` must be exactly one container (regular or init) of the
  component. A container in `ENVIRONMENT` has no hand-written `envFrom`, and a
  variable may not be both here and in the manifest's `env` (compared ignoring
  case, as .NET does).
- Keys: letters, digits, `_`, `-`, `.`, not starting with a digit; use `__`
  instead of `:`. Values: one line of text, no lists or maps.
- A secret must be declared in this component's `SECRET_FILES`; the error lists
  the declared IDs. A component uses only its own secrets (IDs starting with
  its own ID); the one exception is identity's API secret line below.
- Values follow the [secret value](#secret-values-in-environment-and-mounts) text rules: no
  surrounding spaces, quotes, `;`, control characters or `@@` in a substituted
  value. A secret that does not fit uses `secretKeyRef` in the manifest.
- `POSTGRES_PASSWORD_FILE` may be an `ENVIRONMENT` line (backlog 83): the
  platform's database check reads the container's effective environment.
  Declare it either in `ENVIRONMENT` or in the container's manifest `env`,
  never both. The same database password protection applies in both cases.

### Environment overrides: `config/<environment>.yaml`

One product can be delivered to several environments that need other values
for a few container variables (log levels, feature switches, limits) and share
every other declaration (backlog 84). The common values stay in the
component's `config.defaults.yaml`:

```yaml
# components/app1/config.defaults.yaml
ENVIRONMENT:
  app:
    Logging__LogLevel__Default: Information
    Features__Reports: "false"
```

An environment file names components under `overrides:`, its only
top-level key:

```yaml
# config/prod1.yaml
overrides:
  app1:
    ENVIRONMENT:
      app:
        Features__Reports: "true"
        Reports__MaxRows: "500"
```

`./build-bundle.sh --environment prod1` builds with it; app1's container
`app` then gets all three variables: `Logging__LogLevel__Default:
Information`, `Features__Reports: "true"` and `Reports__MaxRows: "500"`.
In dev, the same block is the reserved `overrides` key of `config/dev.yaml`,
next to its settings and file-source overrides:

```yaml
# config/dev.yaml
PUBLIC_ORIGIN: https://dev.example.test:8443
HTTPS_PORT: 8443

overrides:
  app1:
    ENVIRONMENT:
      app:
        Logging__LogLevel__Default: Debug
```

How overrides merge (`environment.merge`):

- Per component, container and variable. A variable with the same name
  replaces the common value; a new one is added; every other variable and
  container stays as declared. A container may get its first variables from
  an override; it must exist exactly once (regular or init container).
- There is no deletion. A variable only some environments need belongs in
  their files, not in the common declarations. An empty mapping (`{}`) has no
  effect, but the component and container it names must still exist.
- Values are text, as in `config.defaults.yaml`: `Enabled: true` and
  `MaxRows: 500` reach the container as `true` and `500`, `''` is an empty
  value and `'null'` is the text `null`. A missing value (`Name:`, `Name:
  null` or `Name: ~`) is refused.
- A name that differs from a common one only in case is refused, as within
  one file; there is no rule for which spelling wins.
- A component entry holds only `ENVIRONMENT`. Images, manifests, `MOUNTS`,
  file sources and settings cannot be overridden. Every other rule above
  applies to the merged variables: declared secrets of the component,
  identity's API secret lines, settings placeholders, manifest `env` and
  `envFrom`, the database password check.
- Errors name the file, component, container and variable, never a value.

Before anything is written, the build checks each overridden component with
what its declarations decide: names and placeholder syntax, declared secrets
and generated Secret names, `@@CLIENT_ID@@` without `client.yaml`, and the
containers in its manifests. A container whose name is itself a `@@NAME@@`
setting is known only with the operator's settings, so while a component has
one, its container checks happen at validate and install. An empty entry
(`{}`) for a container without common `ENVIRONMENT` is not compiled into the
bundle, so there it must name exactly one container written literally in the
manifests, or the build refuses it. Setting values,
credentials and the database check always belong to the installation. Only a
component whose variables the environment changes gets a rewritten
`config.defaults.yaml` (comments are not kept, every value keeps its text).

The build environment is chosen when the bundles are built, not at the
installation. The bundle's `config.defaults.yaml` holds the merged
`ENVIRONMENT`, and its `bundle.yaml` the dependencies and API secret lines
derived from it, so the installation needs neither the source checkout nor
`config/prod1.yaml`. Settings and credentials are still the operator's
`config.yaml` and delivered files, as without an environment.

`--environment <name>` takes lowercase letters, digits and inner hyphens, a
letter first; `dev` and `images` are refused because `config/dev.yaml` and
`config/images.yaml` have other meanings. A missing file is an error, and so
is any top-level key other than `components:` and `overrides:`. Without
`--environment` the common declarations are built unchanged.

#### The components of an environment

`components:` (backlog 85) lists the environment's components; without it the
environment has the whole catalog. `bundles.yaml` stays the catalog of every
component and the gateway/Identity roles:

```yaml
# config/prod2.yaml
components: [platform, identity, app2]
overrides:
  app2:
    ENVIRONMENT:
      backend:
        Logging__LogLevel__Default: Debug
```

- Only the listed components get a bundle and images; the others' manifests
  are not read and their credentials are not needed. Order and dependencies
  follow the catalog's rules. `current-bundles.txt` names exactly the listed
  components' bundles.
- An unknown or repeated ID is refused, and so is an empty list ("list at
  least one component, or omit `components`").
- Nothing is added: a missing dependency stops the build with both names,
  for example `config/prod2.yaml: app2 requires identity (it has
  client.yaml); add identity to components`. Every component requires the
  gateway when the catalog has one.
- `overrides:` keeps its meaning for the listed components; an override of a
  component that is not listed is refused (also `{}`).
- `./build-bundle.sh --environment prod2 app2` builds only app2 within prod2;
  a component outside the list is refused. `./build-rpms.sh --environment
  prod2` wraps exactly the archives `dist/prod2/current-bundles.txt` names and
  refuses a list that no longer matches the environment, so an archive an
  earlier, larger set left in `dist/prod2/` is never delivered.

An optional API, one only some environments have, keeps Identity's
`ApiResources__<n>__*` lines out of Identity's `config.defaults.yaml`: each
environment that lists the API adds them as an override of Identity, with its
own `<n>` numbering. An Identity line naming a component that is not listed
is refused ("no listed component owns ..."). Such a product always builds
with an environment: without one, the API runs unregistered and Identity
refuses its calls. In the demo, app3 is that API: its lines are in
`config/whoami.yaml` (platform, identity and app3) and, for dev, in
`config/dev.yaml.example`'s overrides.

The selection never uninstalls anything. A component a later delivery leaves
out keeps running until the runtime user uninstalls it with its own release's
`./deploy.sh uninstall` ([manual](PRODUCTION-INSTALL.md#7-everyday-tasks));
an API goes first, because install refuses an Identity release without the
line of an installed API. The output of an environment goes to its own directory,
`dist/<name>/` with its `current-bundles.txt` (staging in
`build/bundle-<name>/`); `./build-rpms.sh --environment <name>` wraps those
bundles into `dist/<name>/rpm/`. One build never removes another's files.

The directories exist because prod1 and prod2 can contain different bytes for
the same component version. On one installation a version still has exactly
one content: if app1 1.4.0 from `dist/prod1/` is installed and the prod1
overrides change, deliver app1 1.4.1, not a rebuilt 1.4.0: `./build-rpms.sh`
never replaces an existing RPM, and the administrator command refuses a
package with the same name and version but other content.

Troubleshooting: a misspelled name stops the build before anything is
written, naming the file and the place (in a component with a container
named by a `@@NAME@@` setting, a misspelled container with variables stops
`validate` and `install` instead):

```text
ERROR: config/prod1.yaml: overrides.app1.ENVIRONMENT.ap: the component must have exactly one container named ap; it has 0
ERROR: config/prod1.yaml: overrides.app9: app9 is not a component in bundles.yaml; listed: platform, identity, app1, app2, app3, help
```

Correct the container or component name in the environment file (container
names are in the component's manifests, component IDs in `bundles.yaml`) and
run the build again.

### Files with secrets: `MOUNTS`

`MOUNTS` puts single files into a container without `volumes` or
`volumeMounts` in the manifest. Each line is a path in the container and one
of two kinds of source:

| Source | Example | What arrives in the container |
| --- | --- | --- |
| Component file | `sql/10-roles.sql` | The file under `components/<id>/files/`, **rendered**: `@@...@@` is filled in at install |
| Secret file | `'@@secret:orders-trust-chain/ca.crt@@'` | One key of the component's own `SECRET_FILES` Secret, **unchanged**: the same bytes as the delivered or generated file |

A complete example: the `migrate` init container gets SQL that creates a
role with a generated password (rendered) and the CA certificate it uses to
reach the database (unchanged), and the `web` container gets the same CA
certificate:

```yaml
# components/orders/config.defaults.yaml
SECRET_FILES:
  orders-database-password:
  - path: credentials/database
    generate:
    - password
  orders-trust-chain:
  - path: cert                # <state>/orders/cert/ca.crt, delivered
# Files mounted into each container. They come with the release; a component
# file's @@...@@ is filled in at install. Never copied to config.yaml.
MOUNTS:
  migrate:
    /sql/10-roles.sql: sql/10-roles.sql                       # component file
    /run/secrets/ca.crt: '@@secret:orders-trust-chain/ca.crt@@'  # secret file
  web:
    /etc/ssl/certs/orders-ca.pem: '@@secret:orders-trust-chain/ca.crt@@'
```

```sql
-- components/orders/files/sql/10-roles.sql
ALTER ROLE @@DB_USER@@ PASSWORD '@@secret:orders-database-password/password@@';
```

Component files:

- The placeholders are those of `ENVIRONMENT`: a setting or this component's
  own declared secret, with the same text rules for the substituted value.
  The rest of the file is copied as written; it must be UTF-8 text.
- A container's component files go into the Secret
  `<component>-<container>-files`, mounted from the Pod volume
  `<container>-files`.

Secret files:

- The source is exactly one whole reference `@@secret:<secret-id>/<key>@@` to
  the component's own `SECRET_FILES`; nothing else may be around it. The
  existing Secret is mounted itself (no copy): no substitution, decoding or
  trimming, so a binary file such as a PFX or a final newline arrives as
  delivered. The key is a file name of the source (or a `generate` name).
  `validate`, `prepare` and `install` check it before anything is written;
  `init-config` does not, because credentials may be delivered after it.
- Each Secret gets one Pod volume `<secret-id>-mount`, shared by the
  containers of that Pod; the same key may be mounted at several paths and in
  several containers. The mount counts as a use of the Secret.

For both, the platform adds the volumes and mounts each file read-only
(`subPath`) at its path, in regular and init containers alike; nobody writes
the volume names. `validate` reads no secret content and shows:

```text
[OK] orders/migrate: MOUNTS -> /sql/10-roles.sql, /run/secrets/ca.crt (Secret orders-migrate-files: orders-database-password; unchanged from Secret orders-trust-chain)
[OK] orders/web: MOUNTS -> /etc/ssl/certs/orders-ca.pem (unchanged from Secret orders-trust-chain)
```

- Refused before anything is written, naming the `MOUNTS` line: a container
  that is not exactly one container of the component, a path that is not
  absolute, a path the manifest already mounts, a Pod volume already named
  `<container>-files` or `<secret-id>-mount`; for a component file, a file
  outside `files/` or missing, two files with the same file name in one
  container, unknown settings, undeclared or another component's secrets;
  for a secret file, text around the reference, a Secret not in
  `SECRET_FILES`, another component's Secret, and (from `validate`,
  `prepare` and `install`) a key its sources do not provide:

  ```text
  components/orders/config.defaults.yaml: MOUNTS.web./etc/ssl/certs/orders-ca.pem: orders-trust-chain has no key ca.pem; it provides ca.crt. Fix the key, or deliver a file named ca.pem in orders-trust-chain's source
  ```
- The demo: app1's `seed-database` init container gets
  `/seed-secret/020-report-role.sql`, which creates the login `todo_report`
  with the generated `app1-report-password`; the acceptance run logs in with it.
- `init-config` does not copy `MOUNTS`, and the operator's `config.yaml` may
  not contain it. A file the operator owns, or a directory tree, is a
  `VOLUME_FILES` or `SECRET_FILES` source instead.

### API secrets

An API backend and Identity must hold the same secret. The API declares it
like any other secret, and both sides name it:

```yaml
# components/orders/config.defaults.yaml
SECRET_FILES:
  orders-api-secret:                 # shared with identity
  - path: credentials/api-secret
    generate: [value]
ENVIRONMENT:
  backend:
    Authentication__ApiSecret: '@@secret:orders-api-secret/value@@'

# components/identity/config.defaults.yaml
ENVIRONMENT:
  app:
    ApiResources__0__Name: orders-api
    ApiResources__0__Scopes__0: orders
    ApiResources__0__ApiSecrets__0__Value: '@@secret:orders-api-secret/value@@'
```

- The identity line is the declaration: a component is an API when identity's
  `ApiResources__<n>__ApiSecrets__0__Value` line names one of its secrets
  (Identity is Duende). The secret ID starts with the API's ID, so the owner
  is visible in the name. The reference is the whole value, each API has one
  line and its own `<n>`, all in one container.
- The API's config must declare that secret and key; install refuses it before
  any write otherwise. It is generated like any other `generate` source and
  kept byte for byte; both sides receive it unchanged.
- The platform delivers identity's lines in the Secret `<identity>-apis`,
  which it injects into that container. It holds only the lines of installed
  APIs; until the API is installed, identity's resource has no secret and
  stays inactive. No component declares that name.
- When identity is built, the mapping `{API: {index, secret}}` is compiled into
  its `bundle.yaml` (`api_secrets`). The installed, rendered identity's mapping
  is the only one: an API it does not list is refused ("install the identity
  release that lists it first") and an identity release that drops an
  installed API is refused. A newer identity may move an API to another `<n>`;
  the values follow by API.
- `validate` shows each link without values:

  ```text
  [OK] API secret app3-api-secret/value: declared by app3, delivered to identity ApiResources__0__ApiSecrets__0__Value while app3 is installed
  ```

Requirements on the application code, shown in the demo:

- Identity hashes each API secret exactly once while loading it,
  Base64(SHA-256(UTF-8(value))), which Duende compares. It leaves an API
  resource without a secret inactive (that API is not installed yet) and stops
  on an empty secret without printing it.
- The API's health check must not need a successful introspection: the API
  restarts before Identity when the secret changes.

The registration is a private (0700) directory `apis/<id>/` in state holding
`value` (0600). An Identity that is installed separately has only
`<identity>-apis` replaced in its installed YAML (published atomically; added
if missing), then restarts. If that YAML cannot be read, install stops with the
pending record intact: restore the file from backup and run
`./deploy.sh install` from the same bundle again.

To reuse an existing value, write it to the declared path (the demo's
`credentials/api-secret/value`) as the runtime account before the first
install: mode 0600, one line, no trailing newline, not through shell history.
Rotating means replacing that file and installing the API again: the API
restarts first, then Identity; the same bundle version is enough, because
every install renders again. Uninstalling the API, or
installing an API release built while identity had no line for it, removes
its value from `<identity>-apis`; identity's name and scopes for it stay and
the resource is inactive.

## Converting a service

1. Add the component's ID to the list in `bundles.yaml` and create
   `components/<id>/VERSION` and `manifests/`.
2. Write `components/<id>/config.defaults.yaml`: settings and `SECRET_FILES`
   at the top, each container's variables under `ENVIRONMENT` (with
   `@@CLIENT_ID@@`/`@@CLIENT_BASE_PATH@@` for an app with `client.yaml`), and
   files with passwords under `MOUNTS`. A PostgreSQL database reads its
   password from the file `POSTGRES_PASSWORD_FILE` names: the variable holds a
   public path, never the password, which stays in a `SECRET_FILES` file. Both
   the variable and the file can be declared in `config.defaults.yaml`
   (backlogs 82 and 83; demo app2):

   ```yaml
   # config.defaults.yaml
   SECRET_FILES:
     orders-database-password:
     - path: credentials/database
       generate:
       - password
   ENVIRONMENT:
     db:
       POSTGRES_PASSWORD_FILE: /run/secrets/database/password
   MOUNTS:
     db:
       /run/secrets/database/password: '@@secret:orders-database-password/password@@'
   ```

   ```yaml
   # manifests/40-postgres.yaml, container db (no password variable or volume)
   volumeMounts:
   - name: data
     mountPath: /var/lib/postgresql/data      # a PersistentVolumeClaim
   ```

   Declare `POSTGRES_PASSWORD_FILE` either in `ENVIRONMENT` or in the
   container's manifest `env`, never both. The same database password
   protection applies in both cases. The database checks follow either mount to the same claim, Secret and key
   (`deploy.postgres_binding`): an existing database volume without the
   password file still stops before a new password is generated. Mounting the
   Secret as the directory `/run/secrets/database` in the manifest (demo app1)
   works as before.
3. Declare each secret in `SECRET_FILES` with its path (and `generate:` for a
   generated one) and use `@@secret:<id>/<key>@@`.
4. Add `route.conf` for a path behind the gateway, `client.yaml` for OIDC
   sign-in, and for an API Identity must authenticate a declared secret named
   on identity's `ApiResources__<n>__ApiSecrets__0__Value` line (and the two
   code requirements above).
5. An init container that needs the database waits for it first, then runs
   idempotent steps. The database manifest has a lower number, but that only
   orders submission, not readiness, and `pg_isready` does not prove that
   credentials or migrations work:

   ```yaml
   metadata:
     name: orders-web
     annotations:
       io.podman.annotations.init.container.type: always
   spec:
     initContainers:
     - name: wait-for-database
       image: localhost/demo-postgres:17.11       # the database image has pg_isready
       imagePullPolicy: Never
       command: ["sh", "-c", "for i in $(seq 1 60); do pg_isready -h orders-postgres -p 5432 -t 2 && exit 0; sleep 2; done; echo 'database did not answer' >&2; exit 1"]
     - name: migrate
       ...
   ```

6. Run `./deploy.sh validate` and read the derived lines, then
   `dev/dev.sh up`. app3 is the converted example to copy.

## Secret values in ENVIRONMENT and MOUNTS

A secret reaches a container in one of three ways. `@@secret:<id>/<key>@@` in
an `ENVIRONMENT` line or a `MOUNTS` component file is substituted into text
that the platform renders into the generated Secrets
(`<component>-<container>-env-secret`, `<component>-<container>-files`); the
rules below apply to that value. A `MOUNTS` line whose whole source is
`@@secret:<id>/<key>@@` mounts the `SECRET_FILES` Secret's file itself,
unchanged; nothing below applies to it. A manifest may also mount or
reference a `SECRET_FILES` Secret directly (`secretName`, `secretKeyRef`). No config file can define other composed
Secrets: `SECRET_TEMPLATES` in a config file is refused.

`@@NAME@@` reads this component's effective text or integer setting (including
`PUBLIC_ORIGIN`/`HTTPS_PORT` from the gateway); `@@secret:<id>/<key>@@` reads a
file key of this component's `SECRET_FILES`, including a generated one. A
declared source without `generate` may be supplied by the operator after
`init-config`; it must exist before install. `validate` and `install` report a
missing source file without reading or printing its contents. Substitution is
one pass: no references to other values, recursive expansion, expressions or
commands.

The renderer removes trailing LF bytes from a secret input, matching PostgreSQL's
`file_env`; it never rewrites the source file. Substituted values containing
semicolons, single or double quotes, control characters, leading/trailing
whitespace, or placeholder markers (`@@`) are refused without including their
values in diagnostics; the text around them (a connection string, SQL in a
`MOUNTS` file) may contain anything. Generated alphanumeric passwords satisfy
this rule. The renderer does not escape for connection strings, URLs or other
target formats. An existing database password failing the rule must be changed
through a coordinated database-role/password-file/client rotation or recovery
procedure (backlog 2/3), never by deleting the file and letting install
regenerate it.

`validate` checks the placeholders and file-key declarations without reading
credentials. Secret bytes are checked only during materialization after
database preflight and permitted generation. Derived values have no separate
persistent source: config plus the original password file are authoritative.
Every install recomputes values; a systemd restart uses the last installed YAML.
A new release can add a setting or a `SECRET_FILES` ID in its
`config.defaults.yaml`: an existing installation whose `config.yaml` lacks it
uses the release's value, without writing the file; the operator's values win.

The output is an Opaque Secret in the existing 0600 install YAML. Base64 is not
encryption; protect YAML, source files, Podman storage and backups. Environment
values are visible to the service user/root through `podman inspect`, process
environments and child processes. `MOUNTS` files avoid the extra environment
copy but still require suitable container ownership/modes. No new credential
files, network services, SELinux exceptions or fapolicyd trust rules are needed.

## Reaching the public origin from a container

A backend calls Duende (or any routed service) through the public origin, as in
Kubernetes. Inside the product network the public host name resolves to the
proxy:

1. `PUBLIC_ORIGIN` gives the derived `PUBLIC_HOSTNAME`.
2. The platform proxy Pod sets `hostname: '@@PUBLIC_HOSTNAME@@'`
   (`components/platform/manifests/80-proxy.yaml`).
3. Podman registers that host name with the proxy's internal address in the
   network's DNS (aardvark-dns; rootless:
   `$XDG_RUNTIME_DIR/containers/networks/aardvark-dns/<network>`).
4. Other containers resolve the name there and connect to nginx on
   `HTTPS_PORT` inside the network. `IP_ADDRESS` (the Pod's `hostIP`) only
   publishes the port on the host for browsers; containers never use it.

By default Podman copies the host's `/etc/hosts` into every container, and
`/etc/hosts` is read before DNS. A host line such as
`127.0.0.1 <public host name>` (common on developer VDIs, or added for a local
browser) would then send each container to its own loopback. Pods therefore
use `quadlet/containers-hosts.conf`, passed through the process environment
variable `CONTAINERS_CONF_OVERRIDE`. It sets `[containers] base_hosts_file =
"none"` and `no_hosts = false`: Podman generates localhost and container entries
without copying the host's lines. This replaces `--no-hosts`, which left some
images without `/etc/hosts` and made localhost depend on external DNS in the
lab. Public host names still resolve through the product network's DNS.

Podman rewrites `/etc/hosts` each time a container starts, so every starting
command must select the override. Dev selects the absolute source-tree path
only for its own commands, never in the calling shell:

- `dev/dev.sh up` (`kube play`);
- `dev/dev.sh restart <pod>...` (`podman pod restart`). A plain
  `podman pod restart` or `podman pod start` would copy the host's lines in again.

Installed components restart through `systemctl --user restart <unit>`, which
inherits the override from the unit.

An installed unit's `[Service] Environment=` selects the immutable copy in
that component's own release. The internal Quadlet token
`@@PODMAN_HOSTS_CONFIG@@` resolves to that file, with systemd path escaping;
it cannot come from component config. Bundles include the file in their
checksums. Relocating a bundle before install resolves its new path; retain
the installed release while its unit uses it, as required for release code.
The normal system/user configuration is still loaded first. No user's
`containers.conf` or config directory is edited. The project's invocation
selects its own `CONTAINERS_CONF_OVERRIDE`; it does not merge an inherited
extra-override file. Pod `spec.hostAliases` remains refused by the shared
validation/bundle guard so aliases cannot override public-origin network DNS.

Install new bundles for all affected components when updating an existing
installation; upgrading only an app does not rewrite its owners' units. No installed
release is modified in place.

The `--no-hosts` version passed the six-scenario matrix, but three PROD
containers could not resolve localhost. The replacement passed focused whoami
46/46 and normal 125/125 at `e99c6be`, with operator-reported manual DEV/PROD
localhost and loopback checks. DEV restart requires the explicit policy above;
`dev/dev.sh restart` supplies it.
The failed first attempt and the successful scope are recorded in
[latest results](../acceptance/RESULTS.md).

Symptom of a container that cannot reach the public origin: the backend
rejects every token with `IDX10204` (no expected issuer, because the discovery
document could not be fetched) and `WWW-Authenticate: ... The issuer '...' is
invalid`, often without `IDX20803`. Check from the backend Pod:

```sh
podman exec <backend-container> getent hosts <public host name>   # proxy's internal address
podman inspect <proxy-container> --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

## Trusting the environment's CA in a backend

A backend that signs in through Duende is an OIDC client: it calls Duende
server to server (discovery, keys, token exchange) through the public HTTPS
origin and must trust the CA that issued the proxy certificate. As in the
original Kubernetes installation, mount the public chain from one Secret as two
single files in the system certificate directory; .NET on Linux reads every
file there, and `subPath` adds the files without hiding the image's own CAs.
The chain holds public certificates only and signs nothing. Demo `app3`
(backlog 71) uses this pattern; its
[verification](../acceptance/RESULTS.md)
also records the internal alternative and what it needs.

Component config (the Secret name must start with the component ID; the
original `<product>-ingress-trust-chain` is refused). The two files are
`MOUNTS` secret files of the `backend` container, so the manifest has no
volume for them:

```yaml
SECRET_FILES:
  billing-ingress-trust-chain:
  - path: cert            # <state>/billing/cert/root.crt and ca.crt
MOUNTS:
  backend:
    /etc/ssl/certs/myproduct-root.pem: '@@secret:billing-ingress-trust-chain/root.crt@@'
    /etc/ssl/certs/myproduct-ca.pem: '@@secret:billing-ingress-trust-chain/ca.crt@@'
```

The mount file names are free text; only the Secret name has a prefix rule.

Provide the files from the **environment's own CA**, never from the source
checkout. `dev/generate-certificates.sh` creates one CA per root, and the demo
PKI has one level, so its CA is both the root and the only issuing CA. In dev,
after `dev/demo-credentials.sh` (or your own dev provisioning, outside generic
`dev/dev.sh`):

```sh
install -d -m 0700 build/dev/billing/cert
install -m 0644 build/dev/PKI/private/ca.crt build/dev/billing/cert/root.crt
install -m 0644 build/dev/PKI/private/ca.crt build/dev/billing/cert/ca.crt
```

In the lab, as the runtime user after `init-config billing`:

```sh
install -d -m 0700 /var/lib/myproduct/state/billing/cert
install -m 0644 /var/lib/myproduct/state/PKI/private/ca.crt /var/lib/myproduct/state/billing/cert/root.crt
install -m 0644 /var/lib/myproduct/state/PKI/private/ca.crt /var/lib/myproduct/state/billing/cert/ca.crt
```

`validate` and `install` name a missing file before anything is written. The
backend must call Duende with the host name in `web.crt` (the one in
`PUBLIC_ORIGIN`). `subPath` with a Secret volume under `podman kube play` is
verified separately on the lab host; see
[trust chain verification](../acceptance/RESULTS.md).

Checking the chain from inside the backend container: `openssl s_client` does
not find a CA mounted under `/etc/ssl/certs` by an ordinary file name (it uses
the bundle and hashed names), so it reports `num=20`/`21` even when .NET trusts
the chain. Name the file explicitly:

```sh
h=<public host name>
openssl s_client -connect "$h:<HTTPS_PORT>" -servername "$h" -verify_hostname "$h" \
  -CAfile /etc/ssl/certs/myproduct-root.pem </dev/null 2>&1 | grep 'Verify return code'
```

`0 (ok)` is expected. `62` (hostname mismatch) means the web certificate was
issued for an earlier `PUBLIC_ORIGIN`: in dev, `dev/demo-credentials.sh` and
`dev/generate-certificates.sh platform <host>` refuse such a retained
certificate and say to remove `web.crt` and `web.key` so a new one is issued
from the same CA. In production the operator replaces the provided web
certificate.

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
`@@secret:<id>/<file>@@` is refused with a pointer to `ENVIRONMENT`.
Keep private input in `SECRET_FILES`, not ordinary public config.

ConfigMap public text does not use the Secret recipe's character restrictions:
quotes, semicolons and multi-line text remain valid. There is no recursive
expansion or escape syntax for `@@`; malformed markers or markers remaining in
a substituted value are refused. Dollar syntax such as `${HTTPS_PORT}`, `$host`
and shell/nginx templates is preserved verbatim.

Outside ConfigMap `data`, `ENVIRONMENT` and `MOUNTS` files, fields such as container
`env.value`, images, names, volume bindings and ConfigMap metadata still require
whole-value placeholders. Validation is shared by initialization, validate and
rendering before generation or host commands. Config changes take effect at
the component's next install; a plain restart uses the installed YAML.

The demo's platform ConfigMap supplies `PUBLIC_ENDPOINT` from
`PUBLIC_HOSTNAME` and `HTTPS_PORT`. The acceptance health check verifies both the
rendered value and `printenv PUBLIC_ENDPOINT` inside the consuming proxy. It
follows the ConfigMap reference, so the same check covers the renamed `shop`
gateway and all six scenarios without generic deploy-code changes.

## Image versions: `config/images.yaml`

Shared registry addresses and image versions are set in one file at the root
of the source checkout, and each manifest says where it uses them:

```yaml
# config/images.yaml
ARTIFACTORY_1: artifactory1.example.test/docker
ARTIFACTORY_2: artifactory2.example.test:8443/docker-remote
POSTGRES_VER: '17.11'
```

```yaml
# components/orders/manifests/40-postgres.yaml
    image: '@@ARTIFACTORY_1@@/postgres:@@POSTGRES_VER@@'
# components/orders/manifests/60-web.yaml
    image: '@@ARTIFACTORY_2@@/team/orders:@@COMPONENT_VERSION@@'
```

- Names use `A-Z`, `0-9` and `_` and start with a letter; the
  [reserved configuration names](#reserved-configuration-names) are refused.
  Values are
  nonempty text: quote a value YAML would read as a number (`'17.11'`). A
  value may hold a registry host with port and path, not only a tag.
- `@@COMPONENT_VERSION@@` is built in: the component's own `VERSION`, for an
  image released together with its component.
- Several registries are ordinary variables. Changing one changes only the
  images that use it; literal images are never changed.
- Placeholders work only in the `image` of `containers` and
  `initContainers`. An image variable anywhere else in a manifest is refused,
  and so is an image name that is not in `config/images.yaml`: settings,
  `config/dev.yaml` and the operator's `config.yaml` never fill an image.
  Plain literal images need no variables and no file.
- The resolved image must not contain `@@`, whitespace or a URL scheme
  (`https://`); give only the registry host and path.
- Every reader of source manifests resolves the same way: `./deploy.sh
  validate`, `prepare`, `dev/dev.sh up`, `dev/pull-images.sh`,
  `dev/build-images.sh` and `./build-bundle.sh`. A bundle's manifests are
  written from the resolved documents (YAML comments are not kept) and its
  `images.txt` lists the same images. `config/images.yaml` is not shipped;
  production config never holds image values.

To change an image, edit `config/images.yaml` (or `VERSION` for a
`@@COMPONENT_VERSION@@` image), then run `dev/pull-images.sh` and
`dev/dev.sh up`. A release whose images changed is delivered with a new
component `VERSION`: the publication refuses a changed archive for a version
that already exists.

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
/var/lib/<product>/state/
├── <id>/config.yaml        authoritative config (init-config, then you)
├── metadata/<id>.json      compiled descriptor, written before registrations
├── installed/<id>          last completed version; retained during retries
├── routes/<id>.conf        registered routes
├── clients/<id>/           registered public client files
├── apis/<id>/              registered API: index, and value for the owner (private)
└── pending-operation.json  install attempt/owners or scoped uninstall work
```

Quadlets live in `/var/lib/<product>/config/containers/systemd/` and Podman
storage in `/var/lib/<product>/storage/`; see
[the production layout](../README.md#config-secrets-and-persistence).

`installed/<id>` without `metadata/<id>.json` is an error. Metadata without the
marker is an unfinished install that a retry completes. Removing a component
from a new source catalog never changes installed state; only an explicit
uninstall from that component's bundle does.

Run `./deploy.sh status` (or `status --json`) from any same-product component
bundle as the runtime account to inspect this state without reading config or
credentials. Rows follow installed descriptor dependencies and show the completion
marker's version, the product-prefixed unit and its systemd state. Missing markers
and a marker older than its metadata are shown as incomplete; JSON keeps both
`version` and `recorded_version`. A component with a pending attempt is incomplete
even when the versions match and its old service is active. The install record is
saved after image verification, before installed metadata or service files change,
and cleared only after the completion marker is durably written, including
installs with no registration owners. Pending install/uninstall work remains visible
even after the selected component's metadata has been removed, and is never
acknowledged by status. The installation root and bootstrap file must already be
prepared; status runs no init-config, Podman or lifecycle operation.

Exit 0 means all listed components are complete and active, the set is nonempty,
and no operation is pending. Other status findings return 1; invalid CLI arguments
return 2. See [command/output details](../README.md#installed-component-status).

## Demo provisioning

Generic tools never create certificates or demo users. For the shipped demo:

```sh
./dev/build-images.sh && ./dev/pull-images.sh
dev/demo-credentials.sh && ./deploy.sh validate && dev/dev.sh up
```

After adding or changing a component, run `./deploy.sh validate` first: it
reports the first finding of every component (file, document or container and
the declaration it expected) without writing anything or calling Podman.

`dev/demo-credentials.sh` runs `dev/generate-certificates.sh` for the six
demo components and copies the demo CA to app3's trust chain. Another product prepares its own credentials in
`build/dev/<id>/` (dev) or `/var/lib/<product>/state/<id>/` (production) before
prepare or install.

## Example: add a service with an external image

Add `components/reports/VERSION` with its release version:

```text
1.0.0
```

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

The image may use [image variables](#image-versions-configimagesyaml)
instead, such as `'@@REGISTRY@@/team/reports:@@COMPONENT_VERSION@@'`.

Add `components/reports/route.conf`:

```nginx
location /reports/ {
    set $reports_upstream reports-web:8080;
    proxy_pass http://$reports_upstream;
}
```

Add its ID to the list in `bundles.yaml` (the gateway, `route.conf` and its
dependency are derived):

```yaml
components: [platform, identity, app1, app2, app3, help, reports]
```

No Python or shell file changes. `./deploy.sh prepare` and `dev/dev.sh up` start
it; `./build-bundle.sh` pulls the image, saves it in
`dist/<product>-reports-<version>-offline.tar.gz` and lists it in
`dist/current-bundles.txt`; `./build-bundle.sh reports` builds only that bundle
and leaves the list unchanged. On the target: `./deploy.sh init-config reports`,
prepare any credentials, then `./deploy.sh install` from that bundle. Installing
it restarts `reports` and `platform`.

A worker without a gateway needs only the manifest and its ID in the list.

## Example: remove a service

1. Stop the dev product while the service is still rendered: `dev/dev.sh down`.
   This stops only what the last prepare rendered and keeps volumes.
2. Remove its ID from the catalog list and `components/<id>/` (and identity's
   `ApiResources__<n>__ApiSecrets__0__Value` line if it was an API). A remaining reference fails before any write and names the declaration.
3. `./deploy.sh validate`, `dev/dev.sh up` and `./build-bundle.sh`. The service is gone from
   `build/install.yaml`, the dev route/client imports and
   `dist/current-bundles.txt`. Older archives stay in `dist/` for hosts that
   still run the service; `current-bundles.txt` names only the current product.
4. On a target, keep the service's earlier bundle and run `./deploy.sh uninstall`
   from it (`--delete-data` also deletes its volumes and private state). Other
   components and their registrations stay.

Dev data volumes of a removed service are not deleted; remove them with
`podman volume rm <id>-...` when they are no longer needed.
