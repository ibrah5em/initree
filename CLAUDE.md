# initree

A **composition orchestrator** for project scaffolding. Not a template zoo. `initree` builds a
project by composing small, independent **layers** (language, framework, container, CI, deploy,
notify) that exchange data through a typed **capability bus**. The whole bet is that breadth comes
from *composing N+M+K layers*, never from maintaining N×M×K templates — which is the trap that
killed every "universal scaffolder" before it.

```
initree new myapp --recipe python+fastapi+docker+gh-actions+vps-ssh
initree new myapp --recipe go+gin+docker+gitlab-ci+k8s+slack
```

Same primitives, recompose the recipe. A consumer binds to a **capability key**
(`container.exposed_port`), never to the tool that produced it — so swapping docker→podman or
gh-actions→gitlab-ci touches no other layer.

---

## Non-negotiable invariants (the engine MUST enforce these)

These are the rules. If a change violates one, it is wrong regardless of how convenient it is.

1. **Capability, not implementation.** Consumers reference capability keys
   (`namespace.key`), never tool-named keys. There is no `docker.*` or `gitlab.*` in the shared
   contract — only `container.*`, `ci.*`, etc. (full vocabulary in `docs/03`).
2. **Namespace ownership.** Each namespace has exactly one authoritative provider *slot*
   (`runtime.*`←language, `app.*`←framework, `container.*`/`registry.*`←container, `ci.*`←ci,
   `deploy.*`←deploy, `notify.*`←notify). A layer may only provide keys in its slot's namespace.
3. **Single-ownership is absolute.** Each file has exactly one owning layer. The *only* way another
   layer contributes to a file is a named **injection point** the owner explicitly declares.
4. **Validate before generating.** `resolve` rejects an invalid recipe before any file is written:
   no `owns` overlap, every required `consumes` has an upstream `provides`, every `injects.into`
   matches a declared injection point, and the dependency graph is acyclic.
5. **Injection vs recipe boundary.** Use **injection** for content whose *format is backend-stable*
   (a dependency line). Use a **recipe** (a backend-agnostic command list passed over the bus) for
   content whose *structure is backend-specific* (a CI job block). A portable layer never authors a
   CI job's keywords; it provides a recipe and the CI layer renders it.
6. **Two-tier interpolation.** `${namespace.key}` is resolved by the engine at `compute` (concrete,
   backend-agnostic). `{{TOKEN}}` (`{{IMAGE}}`, `{{SHA}}`, `{{SECRET:purpose}}`,
   `{{SECRET_FILE:purpose}}`) is a deferred runtime token resolved **only** by the ci layer at its
   render. Secret *values* never enter the bus.
7. **CI is the terminal layer.** It consumes every other layer's recipes, so it sorts last. Non-CI
   layers never consume CI-runtime refs (SHA, secrets) — that is what keeps the graph acyclic and
   prevents a `docker ↔ ci` cycle.

---

## Architecture in brief

- **Slot** = a role (language, framework, container, ci, deploy, notify). A recipe selects one layer
  per slot it needs; the set is a subset, not a fixed tuple (e.g. `notify` is optional).
- **Layer** = a folder with `layer.yaml` (the declarative contract surface) + templates + rare hooks.
- **Capability bus** = a namespaced key/value store. Layers `provides` (write) and `consumes` (read).
- **Lifecycle** (5 phases, engine-global; layers run in topological order, each uninterrupted):
  1. `resolve` — load manifests, run the four static checks above, compute topological order. *No
     files written. This is the buildability proof.*
  2. `prompt` — collect each layer's `inputs` in topo order.
  3. `compute` — each layer resolves its `provides` (evaluate `${...}`); after this the bus is
     **frozen**.
  4. `emit` — (a) render every `owns` template against the frozen bus; (b) resolve injections by
     splicing all `injects` fragments into their owner's file at the declared anchor. Injection runs
     *after* compute, so a later-sorted contributor still lands in an earlier owner's file.
  5. `finalize` — per-layer hooks (`chmod +x`, `git init`, `go mod tidy`, format).

Full detail: `docs/01-layer-contract-and-lifecycle.md`. The generalization proof across two
unrelated stacks (and the cycle reasoning): `docs/02-generalization-proof.md`. The locked public
vocabulary: `docs/03-capability-registry-v1.md`.

---

## Current state

- **Contract: locked at v1.** The docs in `docs/` are the source of truth.
- **Engine: built and shipped.** `initree` is on PyPI at `0.1.0`. All five lifecycle phases run end
  to end, and both reference recipes build for real from the layers under `layers/`.

The phases live in `src/initree/`: `resolve` (the four static checks + topological order), `compute`
(the capability bus + `${...}` resolution, then freeze), `emit` (template render + injection
splicing), `prompt`, and `finalize`, orchestrated by `lifecycle.py` behind the `cli.py` entry point.
Recipe rendering and `{{TOKEN}}` resolution are in `recipe.py`; secret-purpose collection in
`secrets.py`. The capability registry is loaded as **data**
(`.claude/skills/capability-registry/capabilities.yaml`), not hardcoded, so the vocabulary stays the
single source of truth — the `resolve` checks map line-for-line onto it (§3 ownership, §13 per-slot
conformance, §11 injection-point ids).

Ten layers ship across the six slots: `python`/`go` (language), `fastapi`/`gin` (framework),
`docker` (container), `gh-actions`/`gitlab-ci` (ci), `vps-ssh`/`k8s` (deploy), `slack` (notify). Two
reference recipes are locked byte-for-byte by golden tests:
`python+fastapi+docker+gh-actions+vps-ssh` (slice 1) and `go+gin+docker+gitlab-ci+k8s+slack`
(slice 2 — the generalization proof). What's next is in `docs/roadmap.md`; keep the TDD habit, a new
engine behaviour gets a fixture or slice test that fails first.

---

## Engine stack

Python, with:

- **pydantic v2** — the `layer.yaml` schema + validation with precise, user-facing errors (what
  `resolve` needs to reject bad layers clearly).
- **`graphlib.TopologicalSorter`** (stdlib) — topological order *and* `CycleError` (catches the
  `docker↔ci` cycle for free).
- **jinja2** — template rendering in `emit`. `${...}` context interpolation is a small custom flat
  resolver in `context.py` (regex + ref-cycle detection), not jinja.
- **tomlkit** — `toml-array` injection that preserves formatting/comments (e.g. `pyproject.toml`).
- **ruamel.yaml** — round-trip `yaml-seq` injection.
- **typer** — the CLI. Packaged with `uv`/`hatchling`.

---

## Repo layout

```
initree/
├── CLAUDE.md
├── docs/                      # the locked contract (source of truth) + roadmap.md
├── .claude/                   # agents + skills + rules (see below)
├── src/initree/
│   ├── manifest.py            # pydantic models for layer.yaml + recipe loaders
│   ├── registry.py            # loads the capability registry as data
│   ├── resolve.py             # the four static checks + topological order
│   ├── context.py             # the capability bus + ${...} resolution
│   ├── prompt.py              # collect each layer's inputs onto the bus seed
│   ├── recipe.py              # render recipes + resolve {{TOKEN}}s (ci layer)
│   ├── secrets.py             # INITREE_SECRETS.md from declared secret purposes
│   ├── emit.py                # template render + injection splicing
│   ├── finalize.py            # per-layer finalize hooks
│   ├── lifecycle.py           # orchestrates resolve→prompt→compute→emit→finalize
│   ├── resources.py           # locate bundled layers + registry (checkout or wheel)
│   └── cli.py
├── layers/                    # the 10 shipped layers; one dir per layer (layer.yaml + templates/)
└── tests/
    ├── fixtures/              # valid + deliberately-broken recipes (drive resolve)
    └── golden/                # byte-exact snapshots of both slices' emitted trees
```

---

## `.claude/` tooling

**Subagents** (`.claude/agents/`) — isolated, role-scoped workers. Auto-dispatched by description,
or invoke with `@layer-author`, `@contract-guardian`, `@engine-dev`.
- **layer-author** — writes conformant layers (manifests + templates). Has the `capability-registry`
  skill.
- **contract-guardian** — read-only reviewer; enforces the invariants above. Use before committing.
- **engine-dev** — implements the engine phases in the stack above. Has the `capability-registry`
  skill.

**Skills** (`.claude/skills/`) — invocable with `/` and auto-loaded when relevant. (Custom commands
merged into skills in Claude Code 2026; this repo uses skills, not legacy `.claude/commands/`.)
- **`/new-layer <slot> <id>`** — scaffolds a conformant layer; delegates to `layer-author`.
- **`/check-contract`** — reviews current changes for conformance; delegates to `contract-guardian`.
- **capability-registry** — auto-loads whenever a capability key, token, secret purpose, or
  injection-point id is touched. The vocabulary's authoritative summary + machine-readable mirror.


---

## Conventions

- Capability keys: `namespace.key`, lowercase `snake_case`; namespace = capability domain, never a
  tool name.
- A layer's private inputs/state live under `namespace.<backend>.*` (e.g. `deploy.k8s.namespace`) and
  are **never** consumed by another layer — cross-layer needs go through common keys
  (`deploy.summary`).
- Adding/renaming a capability key follows the versioning policy in `docs/03` §16 (adding an optional
  key is non-breaking; adding a MUST key or renaming is breaking).
- When in doubt about whether something is an injection or a recipe, default to **recipe** if its
  structure differs across backends.
