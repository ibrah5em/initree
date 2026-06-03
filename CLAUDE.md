# initree

A **composition orchestrator** for project scaffolding. Not a template zoo. `initree` builds a
project by composing small, independent **layers** (language, framework, container, CI, deploy,
notify) that exchange data through a typed **capability bus**. The whole bet is that breadth comes
from *composing N+M+K layers*, never from maintaining N×M×K templates — which is the trap that
killed every "universal scaffolder" before it.

```
initree new myapp --recipe python+fastapi+docker+gh-actions+vps
initree new myapp --recipe go+gin+gitlab-ci+docker+k8s+slack
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

## Current state & build order

- **Contract: locked at v1.** The three docs in `docs/` are the source of truth.
- **Engine: not built yet.** This is the work. Build in this order, TDD against fixtures:
  1. **`resolve`** first — the manifest loader + the four static checks + topological order. It must
     *reject* the failing fixtures (cycle, owns-overlap, missing provider, recipe missing a required
     container) and *accept* the full recipe with order `go→gin→docker→k8s→slack→ci`.
  2. **`compute`** — context resolution with `${...}` interpolation (cycle-safe over key refs).
  3. **`emit`** — template render + injection splicing (single-ownership enforced).
  4. **`finalize`** — hooks.

The `resolve` checks map almost line-for-line onto the registry: §3 ownership, §13 per-slot
conformance, §11 injection-point ids. Load the registry as **data**
(`.claude/skills/capability-registry/capabilities.yaml`) rather than hardcoding it, so the vocabulary
stays the single source of truth.

---

## Engine stack (recommended; override if you prefer Go/Rust — the contract is language-agnostic)

Python is the best fit for a validate-and-template engine and is the chosen implementation language:

- **pydantic v2** — the `layer.yaml` schema + validation with precise, user-facing errors (exactly
  what `resolve` needs to reject bad layers clearly).
- **`graphlib.TopologicalSorter`** (stdlib) — topological order *and* `CycleError` (catches the
  `docker↔ci` cycle for free).
- **jinja2** (or a small custom resolver) — `${...}` context interpolation. Keys are flat, so a
  regex resolver with ref-cycle detection is also viable.
- **tomlkit** — `toml-array` injection that preserves formatting/comments (e.g. `pyproject.toml`).
- **ruamel.yaml** — round-trip `yaml-seq` injection.
- **typer**/**click** — the CLI. Package with `uv` (PyPI-ready).

---

## Intended repo layout

```
initree/
├── CLAUDE.md
├── docs/                      # the locked contract (source of truth)
├── .claude/                   # agents + skills + rules (see below)
├── src/initree/
│   ├── manifest.py            # pydantic models for layer.yaml + the capability schema
│   ├── resolve.py             # the four static checks + topological order
│   ├── context.py             # the capability bus + ${...} resolution
│   ├── emit.py                # template render + injection splicing
│   ├── lifecycle.py           # orchestrates resolve→prompt→compute→emit→finalize
│   └── cli.py
├── layers/                    # the layers themselves; one dir per layer
│   └── <id>/layer.yaml + templates/
└── tests/
    └── fixtures/              # valid + deliberately-broken recipes (drive resolve TDD)
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
