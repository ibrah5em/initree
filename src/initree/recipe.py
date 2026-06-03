"""recipe — render *_recipe command lists into native ci script lines (docs/01 §6, docs/02 §7).

A *recipe* is a ``list<string>`` of backend-agnostic shell commands a non-ci layer puts on the bus
(``container.build_recipe``, ``deploy.apply_recipe``, ``notify.send_recipe``). The commands may
carry deferred ``{{...}}`` tokens — and only the ci slot may resolve those, because only it knows
the runtime's native syntax (docs/03 §1, §9). This module is what the ci layer calls at its emit
render to turn a consumed recipe into the script lines it splices into its pipeline file.

Two tiers, one already gone: by the time a recipe reaches here it has been through compute, so its
``${namespace.key}`` references are concrete (resolved against the frozen bus). What remains is the
``{{TOKEN}}`` tier:

    {{IMAGE}}               -> <registry.image_name_base>:<short-sha>
    {{SHA}}                 -> the native short-commit-sha reference
    {{SECRET:purpose}}      -> the native masked-variable reference
    {{SECRET_FILE:purpose}} -> the native file-type-variable path

The token *grammar* is engine-owned — it is the locked vocabulary in docs/03 §9. The *native
strings* each token maps to are ci-private (``$CI_COMMIT_SHA`` vs ``${{ github.sha }}``), so the
engine never authors them. The caller (a ci layer) supplies them as a :class:`Dialect`; this module
only parses tokens and substitutes what the dialect returns.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# A deferred runtime token: {{ ... }} with optional surrounding space. Disjoint from the engine
# ${...} tier (no leading $) by construction. Captured broadly — the inner text is validated against
# the four locked forms below — so a malformed token (a typo, or a layer wrongly hand-writing
# ci-native syntax like ${{ github.sha }}) is rejected, not silently passed through. The [^{}] class
# stops a match from spanning brace pairs.
_TOKEN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

_SECRET = "SECRET:"
_SECRET_FILE = "SECRET_FILE:"


class RecipeError(Exception):
    """Base for every recipe-render failure. Raised on an unknown token or a missing dependency."""


class UnknownTokenError(RecipeError):
    """A `{{...}}` token is not one of the four locked forms (docs/03 §9) — an authoring error."""


class MissingImageBaseError(RecipeError):
    """A recipe uses `{{IMAGE}}` but no `registry.image_name_base` is on the bus to compose it."""


@dataclass(frozen=True)
class Dialect:
    """How one ci backend renders deferred `{{...}}` tokens into its native syntax.

    Pure data, supplied by the ci layer — the engine ships no backend specifics. ``short_sha`` is
    the runtime's short-commit reference; it stands in for ``{{SHA}}`` and forms the tag of
    ``{{IMAGE}}``. A secret purpose renders through a convention (``secret_prefix`` + the uppercased
    purpose + ``secret_suffix``) unless the layer overrides it explicitly — which is how predefined
    variables (GitLab's ``CI_REGISTRY_*``) are expressed. The same convention covers file-type
    variables; a backend whose file syntax differs supplies ``secret_files`` overrides.
    """

    provider: str
    short_sha: str
    secrets: Mapping[str, str] = field(default_factory=dict)
    secret_files: Mapping[str, str] = field(default_factory=dict)
    secret_prefix: str = "$"
    secret_suffix: str = ""
    image_base_key: str = "registry.image_name_base"

    def secret(self, purpose: str) -> str:
        return self.secrets.get(purpose, self._convention(purpose))

    def secret_file(self, purpose: str) -> str:
        return self.secret_files.get(purpose, self._convention(purpose))

    def _convention(self, purpose: str) -> str:
        return f"{self.secret_prefix}{purpose.upper()}{self.secret_suffix}"


def render_recipe(commands: Sequence[str], dialect: Dialect, bus: Mapping[str, Any]) -> list[str]:
    """Resolve every `{{...}}` token in each command of a recipe; return the native script lines.

    One output line per input command; a multi-line command keeps its newlines. The caller (the ci
    layer template) owns indentation and how the lines splice into the pipeline file. Raises a
    RecipeError subclass on an unknown token or an unresolvable `{{IMAGE}}`.
    """
    return [resolve_tokens(command, dialect, bus) for command in commands]


def resolve_tokens(text: str, dialect: Dialect, bus: Mapping[str, Any]) -> str:
    """Substitute every deferred `{{...}}` token in `text` with the dialect's native reference."""

    def replace(match: re.Match[str]) -> str:
        return _resolve_one(match.group(1).strip(), dialect, bus)

    return _TOKEN.sub(replace, text)


@dataclass(frozen=True)
class SecretRef:
    """A secret a recipe declares through a token: its logical purpose and whether it is file-type.

    ``is_file`` separates ``{{SECRET_FILE:purpose}}`` (a path to a file-type variable) from
    ``{{SECRET:purpose}}`` (a masked variable). The provisioning report groups by it.
    """

    purpose: str
    is_file: bool


def scan_secrets(commands: Iterable[str]) -> list[SecretRef]:
    """Collect the secrets a recipe declares, deduplicated, in first-seen order.

    Reads the same ``{{...}}`` grammar :func:`resolve_tokens` substitutes, but keeps only the two
    secret forms — ``{{IMAGE}}``/``{{SHA}}`` name no secret. It feeds ``INITREE_SECRETS.md``, an
    observer over the frozen bus, so it stays lenient: an unknown or malformed token is the ci
    render's to reject (loudly, via resolve_tokens), not this scan's to police.
    """
    seen: set[SecretRef] = set()
    refs: list[SecretRef] = []
    for command in commands:
        for match in _TOKEN.finditer(command):
            ref = _secret_ref(match.group(1).strip())
            if ref is not None and ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def _secret_ref(token: str) -> SecretRef | None:
    """Classify one token's inner text as a secret reference, or None if it names no secret.

    `SECRET_FILE:` is tested before `SECRET:` so the longer prefix wins. An empty purpose
    (`{{SECRET:}}`) yields None — a malformed token names nothing to provision, and the ci render is
    where it is rejected.
    """
    if file_purpose := _strip_prefix(token, _SECRET_FILE):
        return SecretRef(purpose=file_purpose, is_file=True)
    if purpose := _strip_prefix(token, _SECRET):
        return SecretRef(purpose=purpose, is_file=False)
    return None


def _resolve_one(token: str, dialect: Dialect, bus: Mapping[str, Any]) -> str:
    if token == "IMAGE":
        return _image(dialect, bus)
    if token == "SHA":
        return dialect.short_sha
    if (purpose := _purpose(token, _SECRET_FILE, dialect)) is not None:
        return dialect.secret_file(purpose)
    if (purpose := _purpose(token, _SECRET, dialect)) is not None:
        return dialect.secret(purpose)
    raise UnknownTokenError(
        f"{dialect.provider}: recipe contains '{{{{{token}}}}}', which is not a known token "
        "({{IMAGE}}, {{SHA}}, {{SECRET:purpose}}, {{SECRET_FILE:purpose}})"
    )


def _purpose(token: str, prefix: str, dialect: Dialect) -> str | None:
    """The purpose a `SECRET:`/`SECRET_FILE:` token names, or None if it carries a different prefix.

    `SECRET_FILE:` is tested before `SECRET:` by the caller, so the two never collide. An empty
    purpose (`{{SECRET:}}`) is a malformed token, not a missing branch — hence loud, not None.
    """
    purpose = _strip_prefix(token, prefix)
    if purpose is None:
        return None
    if not purpose:
        raise UnknownTokenError(
            f"{dialect.provider}: recipe token '{{{{{token}}}}}' names no secret purpose"
        )
    return purpose


def _strip_prefix(token: str, prefix: str) -> str | None:
    """The text after `prefix` (whitespace-stripped) if `token` carries it, else None.

    An empty purpose returns ``""`` (falsy), not None, so callers can tell "wrong prefix" apart from
    "this prefix, no purpose": resolve_tokens rejects the empty case, scan_secrets skips it.
    """
    if not token.startswith(prefix):
        return None
    return token[len(prefix) :].strip()


def _image(dialect: Dialect, bus: Mapping[str, Any]) -> str:
    base = bus.get(dialect.image_base_key)
    if base is None:
        raise MissingImageBaseError(
            f"{dialect.provider}: recipe uses {{{{IMAGE}}}} but '{dialect.image_base_key}' is not "
            "on the bus; the container layer must provide a registry image base to tag an image"
        )
    return f"{base}:{dialect.short_sha}"
