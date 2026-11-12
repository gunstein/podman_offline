"""Image references from config/images.yaml and @@COMPONENT_VERSION@@ (backlog 63).

A generic two-component product with images from two registries. The expected
images are written out here, never computed with the resolver under test.
"""

import shutil

import bundle
import yaml
from deployment import catalog, common, deploy
from deployment import render as rendering

from helpers.product_fixture import ProductFixture, pod

VARIABLES = (
    "ARTIFACTORY_1: artifactory1.example.test/docker\n"
    "ARTIFACTORY_2: artifactory2.example.test:8443/docker-remote\n"
    "POSTGRES_VER: '17.11'\n"
)


def web_pod():
    """Init and regular containers; templated and literal references mixed."""
    document = pod("web-server", "@@ARTIFACTORY_2@@/team/web:@@COMPONENT_VERSION@@")
    spec = document["spec"]
    spec["initContainers"] = [
        {
            "name": "migrate",
            "image": "@@ARTIFACTORY_1@@/postgres:@@POSTGRES_VER@@",
            "imagePullPolicy": "Never",
        }
    ]
    spec["containers"].append(
        {
            "name": "sidecar",
            "image": "registry.example.test/tools/sidecar:3",
            "imagePullPolicy": "Never",
        }
    )
    return document


PRODUCT = {
    "web": {"manifests": [web_pod()]},
    "worker": {
        "manifests": [
            pod("worker-db", "@@ARTIFACTORY_1@@/postgres:@@POSTGRES_VER@@"),
            pod("worker-job", "@@ARTIFACTORY_2@@/team/worker:@@COMPONENT_VERSION@@"),
        ]
    },
}

WEB_IMAGES = [
    "artifactory1.example.test/docker/postgres:17.11",
    "artifactory2.example.test:8443/docker-remote/team/web:1.0.0",
    "registry.example.test/tools/sidecar:3",
]
WORKER_IMAGES = [
    "artifactory1.example.test/docker/postgres:17.11",
    "artifactory2.example.test:8443/docker-remote/team/worker:2.0.0",
]


class ImageVariableTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.write_product(PRODUCT)
        (self.source / "components/worker/VERSION").write_text("2.0.0\n")
        self.variables = self.source / "config/images.yaml"
        self.variables.parent.mkdir()
        self.variables.write_text(VARIABLES)

    def manifests(self, component):
        return self.source / "components" / component / "manifests"

    def images(self, component):
        return bundle.manifest_images(self.manifests(component))

    def refused(self, message, images=None, env=None):
        """Write web's manifest with these images/env and expect load to fail."""
        document = web_pod()
        container = document["spec"]["containers"][0]
        if images is not None:
            container["image"] = images
        if env is not None:
            container["env"] = [{"name": "VALUE", "value": env}]
        path = self.manifests("web") / "10-resources.yaml"
        path.write_text(yaml.safe_dump(document))
        with self.assertRaises(common.DeployError) as caught:
            rendering.load_manifest(path)
        self.assertIn(message, str(caught.exception))
        return str(caught.exception)

    def test_variables_and_component_version_resolve_for_each_component(self):
        self.assertEqual(self.images("web"), WEB_IMAGES)
        self.assertEqual(self.images("worker"), WORKER_IMAGES)

    def test_changing_one_registry_changes_only_its_images(self):
        self.variables.write_text(
            VARIABLES.replace("artifactory2.example.test:8443", "mirror.example.test")
        )
        self.assertEqual(
            self.images("web"),
            [
                "artifactory1.example.test/docker/postgres:17.11",
                "mirror.example.test/docker-remote/team/web:1.0.0",
                "registry.example.test/tools/sidecar:3",
            ],
        )
        self.assertEqual(
            self.images("worker"),
            [
                "artifactory1.example.test/docker/postgres:17.11",
                "mirror.example.test/docker-remote/team/worker:2.0.0",
            ],
        )

    def test_bundle_ships_resolved_manifests_and_matching_image_list(self):
        sources = {
            path: path.read_bytes() for path in self.source.rglob("manifests/*.yaml")
        }
        releases = self.build_and_unpack()
        for name, expected in (("web", WEB_IMAGES), ("worker", WORKER_IMAGES)):
            release = releases[name]
            self.assertEqual(
                (release / "images/images.txt").read_text().split(), expected
            )
            text = release / "components" / name / "manifests/10-resources.yaml"
            self.assertNotIn("@@", text.read_text())
            self.assertEqual(
                bundle.manifest_images(release / "components" / name / "manifests"),
                expected,
            )
            self.assertFalse((release / "config/images.yaml").exists())
        # Source manifests are unchanged byte for byte.
        self.assertEqual({path: path.read_bytes() for path in sources}, sources)

    def test_isolated_bundle_installs_without_source_or_variables_file(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        for name in ("web", "worker"):
            self.install(releases[name])
        documents = list(
            yaml.safe_load_all(catalog.component_paths("web")[2].read_text())
        )
        spec = next(doc for doc in documents if doc["kind"] == "Pod")["spec"]
        self.assertEqual(
            sorted(
                container["image"]
                for container in spec["initContainers"] + spec["containers"]
            ),
            WEB_IMAGES,
        )

    def test_dev_prepare_renders_resolved_images(self):
        deploy.prepare()
        text = (common.BUILD / "install.yaml").read_text()
        images = sorted(
            {
                container["image"]
                for doc in yaml.safe_load_all(text)
                if doc["kind"] == "Pod"
                for group in ("initContainers", "containers")
                for container in doc["spec"].get(group, [])
            }
        )
        self.assertEqual(images, sorted(set(WEB_IMAGES + WORKER_IMAGES)))

    def test_literal_references_need_no_variables_file(self):
        self.variables.unlink()
        path = self.manifests("web") / "10-resources.yaml"
        path.write_text(yaml.safe_dump(pod("web-server", "localhost/web:1")))
        self.assertEqual(self.images("web"), ["localhost/web:1"])

    def test_placeholder_without_variables_file_is_refused(self):
        self.variables.unlink()
        self.refused("@@ARTIFACTORY_2@@, which is not in config/images.yaml")

    def test_unknown_name_is_refused_with_the_container(self):
        message = self.refused(
            "@@NO_SUCH@@, which is not in config/images.yaml",
            images="@@NO_SUCH@@/web:1",
        )
        self.assertIn("container 'main'", message)
        self.assertIn("10-resources.yaml", message)

    def test_names_outside_images_yaml_are_not_a_fallback(self):
        (self.source / "components/web/config.defaults.yaml").write_text(
            "WEB_TAG: '1'\n"
        )
        (self.source / "config/dev.yaml").write_text("DEV_TAG: '1'\n")
        for name in ("WEB_TAG", "DEV_TAG"):
            self.refused(
                "@@" + name + "@@, which is not in config/images.yaml",
                images="localhost/web:@@" + name + "@@",
            )

    def test_duplicate_variable_is_refused(self):
        self.variables.write_text("A: x\nA: y\n")
        with self.assertRaises(yaml.YAMLError) as caught:
            rendering.load_manifest(self.manifests("web") / "10-resources.yaml")
        self.assertIn("duplicate key 'A'", str(caught.exception))

    def test_invalid_variables_files_are_refused(self):
        for text, message in (
            ("POSTGRES_VER: 17.11\n", "quote numbers"),
            ("EMPTY: ''\n", "nonempty text value"),
            ("lower: x\n", "is not a variable name"),
            ("COMPONENT_VERSION: '1'\n", "reserved name"),
            ("- x\n", "must map NAME: value"),
        ):
            with self.subTest(text=text):
                self.variables.write_text(text)
                with self.assertRaises(common.DeployError) as caught:
                    rendering.load_manifest(self.manifests("web") / "10-resources.yaml")
                self.assertIn(message, str(caught.exception))

    def test_invalid_resolved_references_are_refused(self):
        for value, message in (
            ("https://artifactory.example.test", "has a URL scheme"),
            ("artifactory.example.test/a b", "not a valid reference"),
            # A stray @@ in config/images.yaml is a malformed placeholder; an
            # escaped one is a literal @@, which no image reference may hold.
            ("artifactory@@example", "malformed placeholder"),
            ("artifactory@@@@example", "gives no valid reference"),
        ):
            with self.subTest(value=value):
                self.variables.write_text("ARTIFACTORY_2: '" + value + "'\n")
                self.refused(message, images="@@ARTIFACTORY_2@@/web:1")

    def test_image_variable_outside_an_image_field_is_refused(self):
        self.refused(
            "@@POSTGRES_VER@@ is an image variable", env="version @@POSTGRES_VER@@"
        )

    def test_name_both_image_variable_and_setting_is_refused(self):
        (self.source / "components/web/config.defaults.yaml").write_text(
            "POSTGRES_VER: '16'\n"
        )
        with self.assertRaises(common.DeployError) as caught:
            rendering.load_manifest(self.manifests("web") / "10-resources.yaml")
        self.assertIn("POSTGRES_VER is both an image variable", str(caught.exception))

    def test_settings_outside_images_keep_their_meaning(self):
        (self.source / "components/web/config.defaults.yaml").write_text(
            "GREETING: hello\n"
        )
        path = self.manifests("web") / "10-resources.yaml"
        document = web_pod()
        document["spec"]["containers"][0]["env"] = [
            {"name": "GREETING", "value": "@@GREETING@@"}
        ]
        path.write_text(yaml.safe_dump(document))
        resolved = rendering.load_manifest(path)[0]["spec"]["containers"][0]
        self.assertEqual(
            resolved["env"], [{"name": "GREETING", "value": "@@GREETING@@"}]
        )
        deploy.prepare()
        self.assertIn("value: hello", (common.BUILD / "install.yaml").read_text())

    def test_component_version_needs_the_version_file(self):
        (self.source / "components/web/VERSION").unlink()
        self.refused("@@COMPONENT_VERSION@@ needs the component's VERSION file")
