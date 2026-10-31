"""A backend that trusts the environment's CA through two subPath mounts (backlog 70).

The original Kubernetes installation mounts a public CA chain from one Secret as
two single files in /etc/ssl/certs. The same declaration must validate and
render here: one SECRET_FILES source with both files, one secret volume and two
volumeMounts that each select one key with subPath.
"""

import base64
import copy
from pathlib import Path
from unittest import mock

import yaml
from deployment import common, deploy, validation

from helpers.product_fixture import PEM, ProductFixture

COMPONENT = "billing"
SECRET = COMPONENT + "-ingress-trust-chain"


def backend(secret=SECRET, keys=("root.crt", "ca.crt")):
    """The backend Pod: two single-file mounts of one Secret volume."""
    names = {"root.crt": "root", "ca.crt": "ca"}
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": COMPONENT + "-backend"},
        "spec": {
            "containers": [
                {
                    "name": "server",
                    "image": "localhost/billing-backend:1",
                    "imagePullPolicy": "Never",
                    "volumeMounts": [
                        {
                            "name": "trust-chain",
                            "mountPath": "/etc/ssl/certs/myproduct-"
                            + names[key]
                            + ".pem",
                            "subPath": key,
                            "readOnly": True,
                        }
                        for key in keys
                    ],
                }
            ],
            "volumes": [
                {
                    "name": "trust-chain",
                    "secret": {
                        "secretName": secret,
                        "items": [{"key": key, "path": key} for key in keys],
                    },
                }
            ],
        },
    }


class TrustChainTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.defaults = {"SECRET_FILES": {SECRET: [{"path": "cert"}]}}
        self.product = {
            COMPONENT: {
                "defaults": self.defaults,
                "manifests": [backend()],
            }
        }
        self.write_product(self.product)
        self.cert = common.BUILD / "dev" / COMPONENT / "cert"

    def provide_chain(self, names=("root.crt", "ca.crt")):
        """The dev provisioning copies the environment's CA under both names."""
        self.cert.mkdir(parents=True, exist_ok=True)
        for name in names:
            (self.cert / name).write_text(PEM)

    def rendered(self):
        return [
            doc
            for doc in yaml.safe_load_all((common.BUILD / "install.yaml").read_text())
            if doc is not None
        ]

    def test_chain_renders_one_secret_and_two_single_file_mounts(self):
        self.provide_chain()
        validation.validate()
        deploy.prepare()
        documents = self.rendered()
        secret = next(doc for doc in documents if doc["kind"] == "Secret")
        self.assertEqual(secret["metadata"]["name"], SECRET)
        self.assertEqual(
            {
                key: base64.b64decode(value).decode()
                for key, value in secret["data"].items()
            },
            {"root.crt": PEM, "ca.crt": PEM},
        )
        pod = next(doc for doc in documents if doc["kind"] == "Pod")
        self.assertEqual(
            pod["spec"]["containers"][0]["volumeMounts"],
            backend()["spec"]["containers"][0]["volumeMounts"],
        )

    def test_secret_named_after_the_product_is_refused(self):
        # The original name <product>-ingress-trust-chain is not a component prefix.
        product = copy.deepcopy(self.product)
        product[COMPONENT]["defaults"] = {
            "SECRET_FILES": {"myproduct-ingress-trust-chain": [{"path": "cert"}]}
        }
        product[COMPONENT]["manifests"] = [backend("myproduct-ingress-trust-chain")]
        self.write_product(product)
        self.provide_chain()
        with self.assertRaisesRegex(common.DeployError, "must start with billing-"):
            deploy.prepare()
        self.assertFalse((common.BUILD / "install.yaml").exists())

    def test_missing_chain_file_is_named_before_anything_is_written(self):
        self.provide_chain(("root.crt",))
        with self.assertRaisesRegex(common.DeployError, "ca.crt"):
            deploy.prepare()
        self.assertFalse((common.BUILD / "install.yaml").exists())
        self.assertEqual(
            sorted(path.name for path in self.cert.iterdir()), ["root.crt"]
        )

    def test_validate_reads_no_chain_contents(self):
        self.provide_chain()
        original = Path.open

        def checked(path, *args, **kwargs):
            if self.cert in path.parents:
                raise AssertionError("validate read a chain file")
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "open", checked):
            validation.validate()
