"""Write a self-contained source product and drive it through the real lifecycle.

A product here is only YAML and component files: a catalog in bundles.yaml and
one directory per component. No generic Python or shell file is changed to
add, rename or remove a component, which is what these tests demonstrate.
Podman/systemd are recorded instead of run; everything else is real.
"""

import os
import shutil
import subprocess
import tarfile
import tempfile
import warnings
from pathlib import Path
from unittest import mock

import bundle
import yaml
from deployment import common, deploy

from helpers.deploy_fixture import DeployFixture

REPO = Path(__file__).resolve().parents[2]
PEM = "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n"


def pod(name, image, volumes=(), env=None, **spec):
    """A minimal Pod with one container mounting the named claims or secrets."""
    container = {"name": "main", "image": image, "imagePullPolicy": "Never"}
    if env:
        container["env"] = [{"name": key, "value": value} for key, value in env.items()]
    pod_volumes = []
    for volume in volumes:
        kind, claim = volume.split(":", 1)
        source = (
            {"persistentVolumeClaim": {"claimName": claim}}
            if kind == "pvc"
            else {"secret": {"secretName": claim}}
        )
        pod_volumes.append(dict(name=claim, **source))
    container["volumeMounts"] = [
        {"name": volume["name"], "mountPath": "/mnt/" + volume["name"]}
        for volume in pod_volumes
    ]
    body = dict(spec, containers=[container], volumes=pod_volumes)
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name},
        "spec": body,
    }


def postgres(component):
    """A PostgreSQL Pod using the supported password/data mount layout."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": component + "-postgres"},
        "spec": {
            "containers": [
                {
                    "name": "db",
                    "image": "localhost/postgres:17",
                    "imagePullPolicy": "Never",
                    "env": [
                        {"name": "POSTGRES_USER", "value": "@@DB_USER@@"},
                        {
                            "name": "POSTGRES_PASSWORD_FILE",
                            "value": "/run/secrets/database/password",
                        },
                    ],
                    "volumeMounts": [
                        {"name": "data", "mountPath": "/var/lib/postgresql/data"},
                        {"name": "password", "mountPath": "/run/secrets/database"},
                    ],
                }
            ],
            "volumes": [
                {
                    "name": "data",
                    "persistentVolumeClaim": {"claimName": component + "-data"},
                },
                {
                    "name": "password",
                    "secret": {
                        "secretName": component + "-database-password",
                        "items": [{"key": "password", "path": "password"}],
                    },
                },
            ],
        },
    }


def claim(name):
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": name},
        "spec": {"accessModes": ["ReadWriteOnce"]},
    }


def route(component, path, upstream):
    return (
        f"location {path}/ {{\n"
        f"    set ${component.replace('-', '_')}_upstream {upstream};\n"
        f"    proxy_pass http://${component.replace('-', '_')}_upstream;\n"
        "}\n"
    )


def client(client_id, base_path):
    return {
        "id": client_id,
        "base_path": base_path,
        "scopes": ["openid", "profile", client_id],
        "certificate": "credentials/client/client.crt",
    }


# A product with none of the demo component names. orders and inventory are
# two independent apps; their OIDC client IDs and base paths are application
# settings, not component IDs. "role" names the catalog's gateway/identity.
RENAMED = {
    "gateway": {
        "role": "gateway",
        "catalog": {},
        "defaults": {"PUBLIC_ORIGIN": "https://shop.test:9443", "HTTPS_PORT": 9443},
        "manifests": [
            pod(
                "gateway-proxy",
                "localhost/gateway:1",
                ["pvc:gateway-routes"],
                {"PORT": "@@HTTPS_PORT@@"},
                hostname="@@PUBLIC_HOSTNAME@@",
            )
        ],
    },
    "login-service": {
        "role": "identity",
        "catalog": {},
        "manifests": [
            pod(
                "login-service-server",
                "localhost/login:1",
                ["pvc:login-service-clients"],
                {"ISSUER": "@@PUBLIC_ORIGIN@@"},
            )
        ],
        "route": route("login-service", "/login", "login-service-server:8080"),
    },
    "orders": {
        "catalog": {},
        "defaults": {
            "DB_USER": "orders",
            "SECRET_FILES": {
                "orders-database-password": [
                    {"path": "credentials/database", "generate": ["password"]}
                ],
                "orders-client": [{"path": "credentials/client"}],
            },
        },
        "manifests": [
            claim("orders-data"),
            postgres("orders"),
            pod(
                "orders-web",
                "localhost/shop-app:1",
                ["secret:orders-client", "secret:orders-database-password"],
                {"APP_ID": "orders-web", "BASE_PATH": "/orders"},
            ),
        ],
        "route": route("orders", "/orders", "orders-web:8000"),
        "client": client("orders-web", "/orders"),
        "credentials": {"credentials/client/client.crt": PEM},
    },
    "inventory": {
        "catalog": {},
        "defaults": {
            "SECRET_FILES": {"inventory-client": [{"path": "credentials/client"}]}
        },
        "manifests": [
            pod(
                "inventory-web",
                "localhost/shop-app:1",
                ["secret:inventory-client"],
                {"APP_ID": "inventory", "BASE_PATH": "/stock"},
            )
        ],
        "route": route("inventory", "/stock", "inventory-web:8000"),
        "client": client("inventory", "/stock"),
        "credentials": {"credentials/client/client.crt": PEM},
    },
    "manual": {
        "catalog": {},
        "manifests": [pod("manual-web", "registry.example.test/team/manual:2")],
        "route": route("manual", "/manual", "manual-web:8080"),
    },
}

# One worker with no gateway, Identity, public URL, database, certificates,
# config files or apps directory.
WORKER = {
    "worker": {
        "catalog": {},
        "manifests": [pod("worker-job", "registry.example.test/team/worker:1")],
    }
}

DEMO_NAMES = ("platform", "identity", "app1", "app2", "help")


class ProductFixture(DeployFixture):
    """A source checkout, its dist/ output, unpacked releases and a target home."""

    def setUp(self):
        super().setUp()
        self.source = self.root / "source"
        self.releases = self.root / "releases"
        self.product_name = "myproduct"  # product: in the generated bundles.yaml
        self.volumes = set()
        self.process.side_effect = self.host_command
        temporary_directory = tempfile.TemporaryDirectory

        def staging(*args, **kwargs):
            if kwargs.get("dir") == "/run/user/1000":
                kwargs["dir"] = str(self.root)
            return temporary_directory(*args, **kwargs)

        self.stack.enter_context(
            mock.patch.object(tempfile, "TemporaryDirectory", side_effect=staging)
        )

    def host_command(self, arguments, **kwargs):
        """Record Podman/systemd; save writes an archive, volumes come from self.volumes."""
        args = list(map(str, arguments))
        status = 0
        if args[:2] == ["podman", "save"]:
            Path(args[args.index("-o") + 1]).write_bytes(b"recorded image archive")
        elif args[:3] == ["podman", "volume", "exists"]:
            status = 0 if args[-1] in self.volumes else 1
        return subprocess.CompletedProcess(args, status, b"", b"")

    def commands(self):
        return [list(map(str, call[0][0])) for call in self.process.call_args_list]

    def restarts(self):
        return [
            args[-1][len(self.product_name + "-") : -len(".service")]
            for args in self.commands()
            if args[:3] == ["systemctl", "--user", "restart"]
        ]

    def use_root(self, root):
        """Point the deploy package at a source checkout or an unpacked release."""
        common.ROOT = root
        common.BUILD = root / "build"
        common.QUADLET_TEMPLATE = root / "quadlet/template.kube"
        bundle.ROOT = root
        bundle.STAGE = root / "build/bundle"
        bundle.DIST = root / "dist"

    def write_product(self, product, version="1.0.0"):
        """Write the generic tool files plus only YAML/component files for a product."""
        self.source.mkdir(exist_ok=True)
        for name in ("deploy.sh", "README.md"):
            shutil.copy2(REPO / name, self.source / name)
        for name in ("deployment", "scripts", "quadlet"):
            if not (self.source / name).exists():
                shutil.copytree(
                    REPO / name,
                    self.source / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        roles = {spec["role"]: name for name, spec in product.items() if "role" in spec}
        self.write_catalog(
            {name: spec["catalog"] for name, spec in product.items()}, **roles
        )
        for name, spec in product.items():
            self.write_component(name, spec)
            (self.source / "components" / name / "VERSION").write_text(version + "\n")
        self.use_root(self.source)

    def write_catalog(self, entries, gateway=None, identity=None):
        """Write bundles.yaml in the source form.

        Without gateway/identity arguments the current file's gateway and
        identity are kept, so a test can edit only the component entries.
        """
        path = self.source / "bundles.yaml"
        document = {"product": self.product_name}
        roles = {"gateway": gateway, "identity": identity}
        if gateway is None and identity is None and path.is_file():
            current = yaml.safe_load(path.read_text())
            roles = {key: current.get(key) for key in roles}
        document.update({key: value for key, value in roles.items() if value})
        document["components"] = entries
        path.write_text(yaml.safe_dump(document, sort_keys=False))

    def write_component(self, name, spec):
        directory = self.source / "components" / name
        (directory / "manifests").mkdir(parents=True, exist_ok=True)
        if not (directory / "VERSION").exists():
            (directory / "VERSION").write_text("1.0.0\n")
        (directory / "manifests/10-resources.yaml").write_text(
            yaml.safe_dump_all(spec["manifests"], sort_keys=False)
        )
        if "defaults" in spec:
            (directory / "config.defaults.yaml").write_text(
                yaml.safe_dump(spec["defaults"])
            )
        if "route" in spec:
            (directory / "route.conf").write_text(spec["route"])
        if "client" in spec:
            (directory / "client.yaml").write_text(yaml.safe_dump(spec["client"]))
        if "api" in spec:
            (directory / "api.yaml").write_text(yaml.safe_dump(spec["api"]))

    def provide_credentials(self, product, base):
        """Externally prepared credentials; generic tools never create these."""
        for name, spec in product.items():
            for relative, text in spec.get("credentials", {}).items():
                path = base / name / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)

    def build_and_unpack(self):
        """Build every catalog bundle, then unpack them where no source exists."""
        self.use_root(self.source)
        bundle.build()
        current = (self.source / "dist/current-bundles.txt").read_text().split()
        self.releases.mkdir(exist_ok=True)
        unpacked = {}
        for archive_name in current:
            path = self.source / "dist" / archive_name
            # Archives built by this test; keep the Python 3.6 extract API.
            with tarfile.open(str(path)) as archive:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    archive.extractall(str(self.releases))
            release = self.releases / archive_name[: -len("-offline.tar.gz")]
            unpacked[deploy.catalog.load_bundle_descriptor(release)["name"]] = release
        return unpacked

    def install(self, release, configure=None):
        """init-config, optional operator edit, then install from an unpacked release."""
        self.use_root(release)
        name = deploy.bundle_descriptor()["name"]
        deploy.init_config(name)
        if configure:
            configure(common.STATE / name)
        self.process.reset_mock()
        deploy.install()
        return self.restarts()

    def files_under(self, directory):
        return sorted(
            str(path.relative_to(directory))
            for path in directory.rglob("*")
            if path.is_file()
        )

    def environment(self):
        """Keep HOME consistent with the patched service-user home."""
        return mock.patch.dict(os.environ, {"HOME": str(common.HOME)})
