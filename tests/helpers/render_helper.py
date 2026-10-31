"""Render-level test helper: validate, materialize and optionally write imports.

Product code calls the steps separately (deploy.check_manifests, then
render.materialize) so the database preflight runs between validation and
generation. Tests that only exercise rendering use this shortcut.
"""

from deployment import common
from deployment.render import (
    effective_config,
    effective_documents,
    load_config,
    materialize,
    write_file_archives,
)


def materialize_and_render(
    files_dir=None,
    write_archives=True,
    config_path=None,
    manifests=None,
    component=None,
    extra_volumes=None,
    extra_secrets=(),
):
    """Validate, create allowed missing secrets, render YAML and optionally write imports."""
    config_path = config_path or (common.ROOT / "config.yaml")
    if not config_path.exists():
        raise common.DeployError(f"Missing {config_path}")
    files_dir = files_dir or common.BUILD / "files"
    config = load_config(config_path)
    if component:
        config = effective_config(config, config_path, component)
    documents = effective_documents(
        config,
        config_path,
        manifests or (common.ROOT / "manifests"),
        component,
        extra_volumes or {},
        [doc["metadata"]["name"] for doc in extra_secrets],
    )
    text, volumes = materialize(
        config,
        config_path,
        documents,
        files_dir,
        extra_volumes,
        component,
        extra_secrets,
    )
    if write_archives:
        write_file_archives(volumes, files_dir)
    return text
