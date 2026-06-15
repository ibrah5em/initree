---
name: capability-registry
description: >
  Consult whenever adding, using, renaming, or reviewing any initree capability key (a namespace.key
  like app.port, container.exposed_port, deploy.summary), a recipe token ({{IMAGE}}, {{SHA}},
  {{SECRET:purpose}}), a secret purpose, or an injection-point id. Use whenever authoring or editing
  a layer manifest, or writing engine code that touches the shared context vocabulary. This is the
  authoritative summary of capability registry v1.
---

# initree capability registry — v1 (working summary)

This is the public vocabulary every layer reads from and writes to the shared context. The full
reference with examples is `docs/registry.md`; the machine-readable mirror is
`capabilities.yaml` in this skill directory (load it as data in the engine rather than hardcoding).

## Namespace ownership (a layer may only provide keys in its slot's namespace)

| namespace | provider slot |
|-----------|---------------|
| `project.*`, `git.*` | engine (seeded) |
| `runtime.*` | language |
| `app.*` | framework |
| `container.*`, `registry.*` | container |
| `ci.*` | ci |
| `deploy.*` | deploy |
| `notify.*` | notify (optional slot) |

## Keys (conformance is for the owning slot)

**runtime.*** (language): `runtime.language` MUST, `runtime.version` MUST, `runtime.base_image` MUST,
`runtime.install_cmd` MUST, `runtime.test_cmd` SHOULD, `runtime.run_base_image` MAY,
`runtime.build_cmd` MAY, `runtime.artifact` MAY.

**app.*** (framework): `app.port` (int) MUST, `app.start_command` MUST, `app.healthcheck_path` SHOULD.
Framework-internal module/entrypoint paths are PRIVATE inputs, not shared keys.

**container.*** (container): `container.runtime` MUST, `container.image_name` MUST,
`container.exposed_port` (int) MUST, `container.build_recipe` (recipe) MUST.
**registry.*** (container): `registry.host` SHOULD, `registry.image_name_base` (untagged) SHOULD.

**ci.*** (ci): `ci.provider` MUST. (CI is the terminal assembler; it mostly consumes recipes.)

**deploy.*** (deploy): `deploy.target` MUST, `deploy.summary` MUST, `deploy.apply_recipe` (recipe)
MUST, `deploy.url` SHOULD, `deploy.runtime_image` MAY (the image the ci deploy job runs in). Backend
specifics live under `deploy.<backend>.*` (PRIVATE).

**notify.*** (notify, optional): `notify.send_recipe` (recipe) MUST-if-present.

## Two-tier interpolation

- `${namespace.key}` — resolved by the **engine** at `compute`. Concrete, backend-agnostic.
- `{{TOKEN}}` — deferred, resolved **only** by the ci layer at its render:
  - `{{IMAGE}}` → `${registry.image_name_base}` + `:` + native short SHA
  - `{{SHA}}` → native short commit SHA reference
  - `{{SECRET:purpose}}` → native masked-variable reference
  - `{{SECRET_FILE:purpose}}` → native file-type-variable path

Secret **values never enter the context**. Recipes carry only the tokens above.

## Secret purposes (the only secret vocabulary that crosses layers)

`registry`, `registry_user`, `kubeconfig` (file), `slack_webhook`. New purposes go in the registry
and follow snake_case. One logical purpose can map to two physical stores (e.g. `registry` is a CI
variable on push and a cluster `imagePullSecret` on pull).

## Canonical injection points

`runtime.dependencies` (declared by language; deps injected; format per language — `toml-array`,
`text-block`, `json-array`), `runtime.ignore` (`.gitignore`, `line`). The id is shared vocabulary;
the `format` is owner-specific. Injection is for **format-stable** content only — backend-specific
structure is a recipe.

## Naming & the injection-vs-recipe rule

- `namespace.key`, lowercase `snake_case`; namespace = capability domain, never a tool.
- Private inputs/state: `namespace.<backend>.*`, never consumed cross-layer.
- **Injection** = format-stable content (dependency lines). **Recipe** = backend-specific structure
  (CI jobs, deploy commands). When unsure, choose recipe.

## Adding or changing a capability key (versioning, `docs/registry` §16)

- Non-breaking (minor): add a MAY/SHOULD key, a new namespace, a secret purpose, a recipe token, or
  a canonical injection point.
- Breaking (major): add a MUST key to an existing slot, raise a key to MUST, or rename/remove/retype
  any key. Deprecate first; keep one major; document the replacement.

When you add or change a key, update **both** `docs/registry.md` and
`capabilities.yaml` in this directory so the vocabulary stays the single source of truth.
