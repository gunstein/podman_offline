import copy

from helpers.deploy_fixture import document
from helpers.product_fixture import RENAMED


def broken_orders(case):
    """Return orders manifests with one declaration error and the expected message."""
    documents = copy.deepcopy(RENAMED["orders"]["manifests"])
    web = documents[2]["spec"]
    container = web["containers"][0]
    if case == "misplaced env":
        web["env"] = [
            {
                "name": "APP_CONNECTIONSTRING",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "orders-database-password",
                        "key": "password",
                    }
                },
            }
        ]
        return documents, r"10-resources.yaml: spec\.env is not allowed here"
    if case == "undefined mount":
        container["volumeMounts"].append({"name": "nowhere", "mountPath": "/x"})
        return documents, "undefined volume: .nowhere."
    if case == "missing reference":
        web["volumes"].append({"name": "extra", "secret": {"secretName": "orders-x"}})
        return documents, "Secret 'orders-x', but it does not exist"
    if case == "duplicate resource":
        documents.append(document("ConfigMap", "orders-data", data={}))
        return documents, "'orders-data' is defined more than once"
    if case == "online pull policy":
        container["imagePullPolicy"] = "IfNotPresent"
        return documents, "imagePullPolicy: Never"
    if case == "unreplaced placeholder":
        container.setdefault("env", []).append(
            {"name": "USER", "value": "x-@@DB_USER@@"}
        )
        return documents, "Unreplaced"
    raise AssertionError(case)


CASES = (
    "misplaced env",
    "undefined mount",
    "missing reference",
    "duplicate resource",
    "online pull policy",
    "unreplaced placeholder",
)
