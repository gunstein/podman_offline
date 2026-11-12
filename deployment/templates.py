"""Scoped text substitution for Secret recipes, ConfigMap data and Quadlet names.

Three placeholder sources: @@NAME@@ a setting, @@secret:<id>/<key>@@ a
Secret's key, and @@$NAME@@ a variable of the process environment
(environment_value; backlog 86). Every pass is one pass: inserted text is
never read as a placeholder.

The recipes (config["SECRET_TEMPLATES"], Secret name -> key -> text) come only
from ENVIRONMENT and MOUNTS (environment.with_recipes, mounts.with_recipes) in
the transient effective config; no config file may contain them. Validation
only needs names and config, not credential bytes. Materialization uses the
already loaded file Secrets, so no derived credential has its own file.
"""

import base64
import re
import unicodedata

import yaml

from . import common

TOKEN = re.compile(r"@@(.*?)@@", re.DOTALL)
CONFIG_NAME = re.compile(r"[A-Z0-9_]+\Z")
SECRET_REF = re.compile(r"secret:([a-z0-9-]+)/([-._a-zA-Z0-9]+)\Z")
# @@$NAME@@: a variable of the process environment (backlog 86).
ENVIRONMENT_NAME = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)\Z")


def environment_name(inner, where):
    """The NAME of @@$NAME@@ (inner is the text between the @@)."""
    match = ENVIRONMENT_NAME.fullmatch(inner)
    if not match:
        raise common.DeployError(
            f"{where}: invalid environment variable in @@$...@@; use @@$NAME@@ with "
            "letters, digits and _, not starting with a digit"
        )
    return match[1]


def environment_value(name, where):
    """The value of one referenced variable, as text; never shown in a message.

    Only this name is read from common.ENVIRON. A value is text and is never
    read as a placeholder, so one containing @@ is refused.
    """
    if name not in common.ENVIRON:
        raise common.DeployError(
            f"{where}: environment variable {name} is not set; export it in the "
            f"shell that runs this command (export {name}=...), then run the "
            "command again"
        )
    value = common.ENVIRON[name]
    if "@@" in value:
        raise common.DeployError(
            f"{where}: environment variable {name} contains @@; its value is used "
            "as plain text, so remove the @@"
        )
    return value


def environment_text(text, where):
    """text with its @@$NAME@@ references resolved; other placeholders stay.

    One pass: a resolved value is never read again (environment_value).
    """

    def replacement(match):
        if not match[1].startswith("$"):
            return match[0]
        return environment_value(environment_name(match[1], where), where)

    return TOKEN.sub(replacement, text)


def declarations(config):
    """Check recipe shape and resource collisions without opening any file."""
    recipes = config.get(common.SECRET_TEMPLATES, {})
    if not isinstance(recipes, dict):
        raise common.DeployError("Secret recipes must be a map of Secret names")
    for name, values in recipes.items():
        if not isinstance(name, str) or not common.ID.fullmatch(name):
            raise common.DeployError(f"Invalid Secret name {name!r}")
        if any(
            name in config.get(group, {})
            for group in (common.SECRET_FILES, common.VOLUME_FILES)
        ):
            raise common.DeployError(
                f"Secret {name} (from ENVIRONMENT or MOUNTS) has the same name "
                "as a SECRET_FILES or VOLUME_FILES ID; rename that ID"
            )
        if not isinstance(values, dict) or not values:
            raise common.DeployError(f"Secret {name} must have at least one key")
        for key, text in values.items():
            if not isinstance(key, str) or not common.SECRET_KEY.fullmatch(key):
                raise common.DeployError(f"Secret {name} has an invalid key")
            if not isinstance(text, str):
                raise common.DeployError(f"Secret {name} key {key} must be text")
    return recipes


def reference(match, where):
    """Classify one placeholder without including arbitrary text in diagnostics.

    (group, field): a Secret's (ID, key), or (None, name) for a setting; an
    environment variable is (None, "$NAME"), which config_value resolves.
    """
    name = match[1]
    secret = SECRET_REF.fullmatch(name)
    if secret:
        return secret[1], secret[2]
    if CONFIG_NAME.fullmatch(name):
        return None, name
    if name.startswith("$"):
        return None, "$" + environment_name(name, where)
    raise common.DeployError(f"{where}: unknown or nested placeholder")


def tokens(text, where):
    """Check syntax and expose names for declaration-only dependency checks."""
    if "@@" in TOKEN.sub("", text):
        raise common.DeployError(f"{where}: malformed placeholder")
    return [(match,) + reference(match, where) for match in TOKEN.finditer(text)]


def substitute(text, resolve, where):
    """One non-recursive pass; the caller supplies the allowed sources/policy."""
    tokens(text, where)

    def replacement(match):
        return resolve(*reference(match, where))

    result = TOKEN.sub(replacement, text)
    if "@@" in result:
        raise common.DeployError(f"{where}: unresolved placeholder marker")
    return result


def config_value(config, name, where):
    """Only string/integer inputs can participate in composed text.

    "$NAME" (reference) is the process environment's variable, not a setting.
    """
    if name.startswith("$"):
        return environment_value(name[1:], where)
    value = config.get(name)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise common.DeployError(
            f"{where}: Missing {name} or non-text/integer config input"
        )
    return str(value)


def config_text(text, config, where):
    """Compose public text without access to file contents or Secret values."""

    def resolve(group, field):
        if group is not None:
            raise common.DeployError(
                f"{where}: secret placeholder is forbidden in ConfigMap data; use ENVIRONMENT"
            )
        return config_value(config, field, where)

    return substitute(text, resolve, where)


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
    """Check recipes using names and config only, never credential bytes."""
    for name, values in declarations(config).items():
        for key, text in values.items():
            where = f"Secret {name} key {key}"

            def resolve(group, field, where=where):
                if group is None:
                    value = config_value(config, field, where)
                    check_text(value, where, field)
                    return value
                available = source_keys.get(group)
                # As in render.secret_keys/check_secret_keys, None means unknown
                # keys until the operator supplies the declared file source.
                if group not in config.get(common.SECRET_FILES, {}) or (
                    available is not None and field not in available
                ):
                    raise common.DeployError(
                        f"{where}: missing declared source SECRET_FILES.{group}/{field}"
                    )
                return "declared"  # Check the actual bytes only after materialization.

            substitute(text, resolve, where)


def references(config):
    """Source Secrets used only by a recipe still count as consumed resources."""
    return {
        ("Secret", group)
        for name, values in declarations(config).items()
        for key, text in values.items()
        for _, group, _ in tokens(text, f"Secret {name} key {key}")
        if group is not None
    }


def documents(config, file_documents):
    """Compose Opaque Secrets from already loaded file bytes, with no writes/logs."""
    sources = {doc["metadata"]["name"]: doc["data"] for doc in file_documents}
    result = []
    for name, values in declarations(config).items():
        data = {}
        for key, text in values.items():
            where = f"Secret {name} key {key}"

            def resolve(group, field, where=where):
                source = field if group is None else f"SECRET_FILES.{group}/{field}"
                if group is None:
                    value = config_value(config, field, where)
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
                return value

            value = substitute(text, resolve, where)
            data[key] = base64.b64encode(value.encode("utf-8")).decode("ascii")
        doc = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name},
            "type": "Opaque",
            "data": data,
        }
        if len(yaml.safe_dump(doc)) > common.MAX_SECRET_SIZE:
            raise common.DeployError(f"Secret {name} is too large for a Podman secret")
        result.append(doc)
    return result
