"""Render actual component defaults and manifests without running containers."""

import base64
import stat
from pathlib import Path

import yaml
from render_helper import materialize_and_render
from test_deploy import DeployFixture

from deployment import render as rendering

REPO = Path(__file__).resolve().parent.parent


class CredentialDeliveryTests(DeployFixture):
    def defaults(self, component):
        return rendering.merge_config(
            REPO / "config/common.defaults.yaml",
            REPO / "components" / component / "config.defaults.yaml",
        )

    def test_apps_deliver_independent_private_files_only_to_backend_as_secrets(self):
        keys = {}
        for component in ("app1", "app2"):
            config = self.defaults(component)
            prefix = "home/" + component + "/"
            path = self.write(prefix + "config.yaml", yaml.safe_dump(config), 0o600)
            for name in ("todo-client.key", "todo-client.crt", "ca.crt"):
                self.write(prefix + "credentials/todo/" + name, component + name, 0o600)
            files = path.parent / "files"

            def render(files=files, path=path, component=component):
                return materialize_and_render(
                    files,
                    config_path=path,
                    manifests=REPO / "components" / component / "manifests",
                    component=component,
                )

            documents = list(yaml.safe_load_all(render()))
            secret = next(
                doc
                for doc in documents
                if doc["metadata"]["name"] == component + "-signing"
            )
            self.assertEqual(secret["kind"], "Secret")
            self.assertEqual(
                set(secret["data"]),
                {"session-key", "todo-client.key", "todo-client.crt", "ca.crt"},
            )
            before = {}
            for name, value in secret["data"].items():
                source = path.parent / "credentials/todo" / name
                before[name] = source.read_bytes()
                self.assertEqual(base64.b64decode(value), before[name])
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o600)
            keys[component] = before["session-key"]
            self.assertEqual(len(keys[component]), 32)
            self.assertEqual(
                {
                    doc["metadata"]["name"]
                    for doc in documents
                    if doc["kind"] == "PersistentVolumeClaim"
                },
                {component + "-data"},
            )
            self.assertFalse(list(files.glob("*.tar")))
            pod = next(
                doc
                for doc in documents
                if doc["metadata"]["name"] == component + "-todo"
            )
            volume = next(
                v for v in pod["spec"]["volumes"] if v["name"] == "certificates"
            )
            self.assertEqual(volume["secret"]["secretName"], component + "-signing")
            self.assertEqual(volume["secret"]["defaultMode"], 0o400)
            self.assertEqual(
                {item["key"]: item["path"] for item in volume["secret"]["items"]},
                {name: name for name in before},
            )
            backend, frontend = pod["spec"]["containers"]
            self.assertIn(
                {
                    "name": "certificates",
                    "mountPath": "/certificates",
                    "readOnly": True,
                },
                backend["volumeMounts"],
            )
            self.assertFalse(frontend.get("volumeMounts"))
            # The database and backend still consume the same password Secret.
            database = next(
                doc
                for doc in documents
                if doc["metadata"]["name"] == component + "-postgres"
            )
            for spec in (pod["spec"], database["spec"]):
                password = next(v for v in spec["volumes"] if v["name"] == "password")
                self.assertEqual(
                    password["secret"]["secretName"], component + "-database-password"
                )
            self.assertEqual(render(), yaml.safe_dump_all(documents, sort_keys=False))
            for name, value in before.items():
                self.assertEqual(
                    (path.parent / "credentials/todo" / name).read_bytes(), value
                )
        self.assertNotEqual(keys["app1"], keys["app2"])

    def test_identity_has_no_unused_api_secret_or_environment_delivery(self):
        config = self.defaults("identity")
        self.assertEqual(
            [
                str(path.relative_to(self.root))
                for path in rendering.generated_secret_paths(config, self.root)
            ],
            ["credentials/identity-db/password"],
        )
        self.assertEqual(
            set(config["SECRET_FILES"]),
            {"identity-signing", "identity-database-password", "identity-demo-users"},
        )
        path = self.write("home/identity/config.yaml", yaml.safe_dump(config), 0o600)
        rendering.generate_secrets(config, path.parent)
        self.assertFalse((path.parent / "credentials/app").exists())
        manifest = rendering.load_yaml_all(
            REPO / "components/identity/manifests/50-identity.yaml"
        )[0]
        self.assertEqual(
            manifest["spec"]["containers"][0]["envFrom"],
            [{"configMapRef": {"name": "identity-settings"}}],
        )
        # Real API scopes, client-certificate authentication and token signing remain.
        application = (REPO / "apps/identity/Program.cs").read_text()
        self.assertNotIn("ApiSecrets", application)
        for operation in (
            "AddInMemoryApiScopes",
            "AddJwtBearerClientAuthentication",
            "AddSigningCredential",
        ):
            self.assertIn(operation, application)
