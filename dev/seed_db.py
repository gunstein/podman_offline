"""dev/seed-db.sh: run a local SQL file in one component's dev database (backlog 81).

    dev/seed-db.sh <component> <sql file>

The SQL runs through `podman exec` in the component's running PostgreSQL
container, which ./dev/dev.sh up started from build/install.yaml. Nothing is
rendered, prepared or written here: the component's source manifests give
only its Pod names; the prepared build/install.yaml gives the database
container. Inside the container a fixed script uses the container's own
POSTGRES_USER, POSTGRES_DB and POSTGRES_PASSWORD_FILE.

psql's messages are never shown: they can contain seed data. A failure shows
a fixed text, the file and, for an SQL error, the line psql reports.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deployment import catalog, common, deploy
from deployment import render as rendering

# Runs in the database container. Each check has a status of its own, distinct
# from psql's (0-3) and podman's (125-127). PGHOSTADDR pins the address that
# -h names; PGDATABASE keeps the name literal (a -d value can be a
# connection string).
SCRIPT = """\
command -v cat >/dev/null 2>&1 && command -v psql >/dev/null 2>&1 || exit 127
[ -n "${POSTGRES_USER:-}" ] || exit 10
[ -n "${POSTGRES_DB:-}" ] || exit 11
[ -n "${POSTGRES_PASSWORD_FILE:-}" ] || exit 12
password=$(cat -- "$POSTGRES_PASSWORD_FILE") || exit 13
[ -n "$password" ] || exit 13
unset PGSERVICE
PGPASSWORD=$password PGDATABASE=$POSTGRES_DB PGCONNECT_TIMEOUT=5 PGHOSTADDR=127.0.0.1
export PGPASSWORD PGDATABASE PGCONNECT_TIMEOUT PGHOSTADDR
exec psql --no-psqlrc -w -h 127.0.0.1 -U "$POSTGRES_USER" \\
  --set ON_ERROR_STOP=1 --single-transaction --file=- >/dev/null
"""

# The first SQL error psql reports for --file=-; NOTICE and WARNING lines
# have the same prefix and are never used.
ERROR_LINE = re.compile(r"^psql:<stdin>:([1-9][0-9]*): ERROR:", re.MULTILINE)

UP = "run ./dev/dev.sh up"
IMAGE = "the database image must provide sh, cat and psql"
MISSING = "is not set in {container}; the database container must declare it"
# The message for each failed status; {container} is the database container.
FAILURES = {
    125: "podman cannot run a command in {container}; " + UP,
    126: "the command cannot start in {container}; " + IMAGE,
    127: "the command cannot start in {container}, or cat or psql is missing; " + IMAGE,
    10: "POSTGRES_USER " + MISSING,
    11: "POSTGRES_DB " + MISSING,
    12: "POSTGRES_PASSWORD_FILE " + MISSING,
    13: "the password file in {container} is missing, unreadable or empty; "
    "restore the existing credential, then " + UP + "; never generate a new one",
    1: "psql failed",
    2: "the connection or authentication failed; check that {container} is "
    "running and accepts its credential",
}


def component_pods(component):
    """The literal Pod names of the component's source manifests."""
    _, _, components = catalog.catalog_components(common.ROOT)
    if component not in components:
        raise common.DeployError(
            f"{component} is not a component in {common.ROOT / 'bundles.yaml'}"
        )
    directory = common.ROOT / "components" / component / "manifests"
    pods = []
    for path in sorted(directory.glob("*.yaml")):
        documents = rendering.load_yaml_all(path)
        found = [
            doc
            for doc in documents
            if isinstance(doc, dict) and doc.get("kind") == "Pod"
        ]
        for doc in found:
            name = (doc.get("metadata") or {}).get("name")
            if isinstance(name, str) and "@@" in name:
                raise common.DeployError(
                    f"{path}: the Pod name {name} is a placeholder; seed-db supports "
                    "only literal Pod names"
                )
        # Every name starts with "<component>-": a source Pod renamed to
        # another component's name cannot select that component's database.
        rendering.check_component_names(found, component, path)
        pods += [doc["metadata"]["name"] for doc in found]
    return pods


def database_container(component):
    """The one running database container of the component: <pod>-<container>."""
    pods = component_pods(component)
    install = common.BUILD / "install.yaml"
    if not install.is_file():
        raise common.DeployError(f"{install} is missing; {UP}")
    documents = [doc for doc in rendering.load_yaml_all(install) if doc is not None]
    prepared = {
        (doc.get("metadata") or {}).get("name"): (doc, spec)
        for doc, spec in rendering.pod_specs(documents, str(install))
    }
    # envFrom with a Secret: only the key names, as for ENVIRONMENT recipes.
    secret_keys = {
        common.SECRET_TEMPLATES: {
            doc["metadata"]["name"]: sorted(
                set(doc.get("data") or {}) | set(doc.get("stringData") or {})
            )
            for doc in documents
            if isinstance(doc, dict) and doc.get("kind") == "Secret"
        }
    }
    found = []
    for pod in pods:
        if pod not in prepared:
            raise common.DeployError(f"Pod {pod} is not in {install}; {UP}")
        doc, spec = prepared[pod]
        # Ordinary containers only: a finished init container may carry the
        # same binding.
        for container in spec.get("containers", []):
            environment = deploy.environment_entries(container, documents, secret_keys)
            if deploy.postgres_binding(doc, spec, "containers", container, environment):
                found.append(pod + "-" + container["name"])
    if len(found) != 1:
        raise common.DeployError(
            f"{component} has {len(found)} PostgreSQL database containers "
            f"({', '.join(found) or 'none'}); seed-db supports exactly one"
        )
    return found[0]


def failure(status, stderr, container):
    """The fixed message for a failed run; captured text never reaches it."""
    if status == 3:
        line = ERROR_LINE.search(stderr)
        where = f" at line {line[1]}" if line else ""
        return f"the SQL failed{where}; fix the SQL; its changes were rolled back"
    if status in FAILURES:
        return FAILURES[status].format(container=container)
    return f"unexpected status {status}"


def seed(component, sql):
    """Run the SQL file in the component's database; return the exit status."""
    container = database_container(component)
    try:
        source = sql.open("rb")
    except OSError:
        raise common.DeployError(f"Cannot read {sql}") from None
    with source:
        try:
            result = subprocess.run(
                ["podman", "exec", "-i", container, "sh", "-c", SCRIPT],
                stdin=source,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError:
            raise common.DeployError("podman is not installed") from None
    if result.returncode:
        stderr = result.stderr.decode("utf-8", "replace")
        message = failure(result.returncode, stderr, container)
        print(
            f"ERROR: seeding {component} from {sql} failed: {message}", file=sys.stderr
        )
        return 1
    print(f"[OK] seeded {component} from {sql}")
    return 0


def main(arguments=None):
    parser = argparse.ArgumentParser(
        prog="dev/seed-db.sh",
        description="Run a local SQL file in one component's running dev database.",
    )
    parser.add_argument("component", help="the catalog component ID, such as identity")
    parser.add_argument("sql", type=Path, help="the SQL file to run")
    options = parser.parse_args(arguments)
    try:
        return seed(options.component, options.sql)
    except common.DeployError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
