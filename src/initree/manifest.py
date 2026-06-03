"""Pydantic models for layer.yaml + recipe loading.

This is the contract surface as code: the shape of a layer manifest (docs/01 §1) and the
locked capability type vocabulary (docs/03 §2). No resolve logic lives here — the four static
checks and the topological order are resolve.py's job. This module only parses and validates the
*shape* of each manifest; whether a set of manifests forms a buildable recipe is decided later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

# The locked vocabularies (docs/03 §2, §11). Kept as Literals so a typo in a manifest fails loud
# at parse time rather than silently slipping past resolve.
CapabilityType = Literal["string", "int", "bool", "list", "map", "recipe"]
InjectionFormat = Literal["toml-array", "yaml-seq", "text-block", "line", "json-array"]
InjectionOrder = Literal["alpha", "declared", "priority"]


class _Manifest(BaseModel):
    # Unknown fields are a manifest authoring error, not something to tolerate.
    model_config = ConfigDict(extra="forbid")


class RequiredSlot(_Manifest):
    slot: str
    one_of: list[str] | None = None


class Requires(_Manifest):
    slots: list[RequiredSlot] = Field(default_factory=list)


class Provide(_Manifest):
    key: str
    type: CapabilityType
    # A capability literal, a "${...}" template, or ":hook". resolve never reads it; compute does.
    value: Any = None


class Consume(_Manifest):
    key: str
    required: bool = False
    # Used only when not required and the key is absent. resolve never reads it.
    default: Any = None


class Input(_Manifest):
    key: str
    prompt: str
    type: CapabilityType
    default: Any = None


class InjectionPoint(_Manifest):
    id: str
    file: str
    format: InjectionFormat
    anchor: str
    order: InjectionOrder = "declared"


class Inject(_Manifest):
    into: str
    format: InjectionFormat
    order: int | None = None
    items: list[str] | None = None
    template: str | None = None


class Hooks(_Manifest):
    compute: str | None = None
    finalize: str | None = None


class Layer(_Manifest):
    apiVersion: str
    id: str
    slot: str
    name: str
    description: str | None = None
    requires: Requires | None = None
    provides: list[Provide] = Field(default_factory=list)
    consumes: list[Consume] = Field(default_factory=list)
    inputs: list[Input] = Field(default_factory=list)
    owns: list[str] = Field(default_factory=list)
    injection_points: list[InjectionPoint] = Field(default_factory=list)
    injects: list[Inject] = Field(default_factory=list)
    hooks: Hooks | None = None

    @classmethod
    def from_yaml(cls, path: Path) -> Layer:
        data = YAML(typ="safe").load(path.read_text())
        return cls.model_validate(data)


def load_recipe(recipe_dir: Path) -> list[Layer]:
    """Load every ``<id>/layer.yaml`` under ``recipe_dir`` into Layer models.

    Deserialization only — this does not decide whether the recipe is buildable. That is
    resolve.resolve()'s job. Loaded in sorted path order so callers see a deterministic input.
    """
    manifests = sorted(recipe_dir.glob("*/layer.yaml"))
    if not manifests:
        raise FileNotFoundError(f"no '<id>/layer.yaml' manifests found under {recipe_dir}")
    return [Layer.from_yaml(path) for path in manifests]
