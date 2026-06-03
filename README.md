# initree

A composition orchestrator for project scaffolding. It builds a project by composing small,
independent **layers** (language, framework, container, ci, deploy, notify) that exchange data
through a typed capability bus — so breadth comes from composing N+M+K layers, not from maintaining
N×M×K templates.

```
initree new myapp --recipe go+gin+docker+gitlab-ci+k8s+slack
```

## Status

Contract locked at v1 (see `docs/`). The engine is built phase by phase against fixtures:
**resolve** → compute → emit → finalize. `resolve` is the buildability proof — it validates a recipe
(no `owns` overlap, every required `consumes` has a provider, every `injects.into` matches a declared
point, the graph is acyclic) before a single file is written.

## Layout

- `docs/` — the locked contract (source of truth)
- `src/initree/` — the engine (`manifest`, `resolve`, `context`, `emit`, `lifecycle`, `cli`)
- `tests/fixtures/` — valid and deliberately-broken recipes that drive resolve TDD

## Develop

```
uv sync
uv run pytest
```
