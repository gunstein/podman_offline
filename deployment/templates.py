"""Declared Secret text recipes; never expand ordinary manifest values.

Validation only needs names and config, not credential bytes. Materialization
uses the already loaded file Secrets, so no derived credential has its own file.
"""

import base64
import re
import unicodedata

import yaml

from . import common

TOKEN = re.compile(r"@@(.*?)@@", re.DOTALL)
CONFIG_NAME = re.compile(r"[A-Z0-9_]+\Z")
SECRET_REF = re.compile(r"secret:([a-z0-9-]+)/([-._a-zA-Z0-9]+)\Z")


def declarations(config):
    """Check recipe shape and resource collisions without opening any file."""
    recipes = config.get(common.SECRET_TEMPLATES, {})
    if not isinstance(recipes, dict):
        raise common.DeployError("SECRET_TEMPLATES must be a map of Secret IDs")
    for name, values in recipes.items():
        if not isinstance(name, str) or not common.ID.fullmatch(name):
            raise common.DeployError("Invalid Secret ID in SECRET_TEMPLATES")
        if any(
            name in config.get(group, {})
            for group in (common.SECRET_FILES, common.VOLUME_FILES)
        ):
            raise common.DeployError(
                f"SECRET_TEMPLATES.{name} collides with a file resource"
            )
        if not isinstance(values, dict) or not values:
            raise common.DeployError(
                f"SECRET_TEMPLATES.{name} must be a nonempty key map"
            )
        for key, text in values.items():
            if not isinstance(key, str) or not common.SECRET_KEY.fullmatch(key):
                raise common.DeployError(
                    f"SECRET_TEMPLATES.{name} has an invalid Secret key"
                )
            if not isinstance(text, str):
                raise common.DeployError(f"SECRET_TEMPLATES.{name}.{key} must be text")
    return recipes


def tokens(text, where):
    """Parse placeholders once; never include untrusted template text in errors."""
    if "@@" in TOKEN.sub("", text):
        raise common.DeployError(f"{where}: malformed placeholder")
    found = []
    for token in TOKEN.finditer(text):
        name = token[1]
        secret = SECRET_REF.fullmatch(name)
        if secret:
            found.append((token, secret[1], secret[2]))
        elif CONFIG_NAME.fullmatch(name):
            found.append((token, None, name))
        else:
            raise common.DeployError(f"{where}: unknown or nested placeholder")
    return found


def check_text(value, where, source):
    """Reject ambiguous input rather than pretend to escape every target format."""
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise common.DeployError(f"{where}: invalid UTF-8 text from {source}") from None
    if (
        value != value.strip()
        or any(c in ";\"'" or unicodedata.category(c) == "Cc" for c in value)
        or "@@" in value
    ):
        raise common.DeployError(f"{where}: unsafe substituted text from {source}")


def validate(config, source_keys):
    """Check references and public input values; source_keys contains names only."""
    for name, values in declarations(config).items():
        for key, text in values.items():
            where = f"SECRET_TEMPLATES.{name}.{key}"
            for _, group, field in tokens(text, where):
                if group is None:
                    value = config.get(field)
                    if isinstance(value, bool) or not isinstance(value, (str, int)):
                        raise common.DeployError(
                            f"{where}: Missing {field} or non-text/integer config input"
                        )
                    check_text(str(value), where, field)
                elif group not in config.get(common.SECRET_FILES, {}) or field not in (
                    source_keys.get(group) or set()
                ):
                    raise common.DeployError(
                        f"{where}: missing declared source SECRET_FILES.{group}/{field}"
                    )


def references(config):
    """Source Secrets used only by a recipe still count as consumed resources."""
    return {
        ("Secret", group)
        for name, values in declarations(config).items()
        for key, text in values.items()
        for _, group, _ in tokens(text, f"SECRET_TEMPLATES.{name}.{key}")
        if group is not None
    }


def documents(config, file_documents):
    """Compose Opaque Secrets from already loaded file bytes, with no writes/logs."""
    sources = {doc["metadata"]["name"]: doc["data"] for doc in file_documents}
    result = []
    for name, values in declarations(config).items():
        data = {}
        for key, text in values.items():
            where = f"SECRET_TEMPLATES.{name}.{key}"
            parts, end = [], 0
            for token, group, field in tokens(text, where):
                source = field if group is None else f"SECRET_FILES.{group}/{field}"
                if group is None:
                    value = str(config[field])
                else:
                    try:
                        value = (
                            base64.b64decode(sources[group][field])
                            .decode("utf-8")
                            .rstrip("\n")
                        )
                    except (KeyError, UnicodeError, ValueError):
                        raise common.DeployError(
                            f"{where}: missing or invalid UTF-8 source {source}"
                        ) from None
                    if not value:
                        raise common.DeployError(f"{where}: empty source {source}")
                check_text(value, where, source)
                parts.extend((text[end : token.start()], value))
                end = token.end()
            parts.append(text[end:])
            data[key] = base64.b64encode("".join(parts).encode("utf-8")).decode("ascii")
        doc = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name},
            "type": "Opaque",
            "data": data,
        }
        if len(yaml.safe_dump(doc)) > common.MAX_SECRET_SIZE:
            raise common.DeployError(
                f"SECRET_TEMPLATES.{name} is too large for a Podman secret"
            )
        result.append(doc)
    return result
