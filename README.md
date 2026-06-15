# initree

A composition orchestrator for project scaffolding. It builds a project by composing small,
independent **layers** — language, framework, container, ci, deploy, notify — that exchange data
through a typed capability bus. Breadth comes from composing N+M+K layers, not from maintaining
N×M×K templates.

```
initree new myapp --recipe go+gin+docker+gitlab-ci+k8s+slack
```

Swap one slot and nothing else moves. A consumer binds to a capability key (`container.exposed_port`),
never to the tool that produced it, so docker→podman or gh-actions→gitlab-ci touches no other layer.

## Install

```
uv tool install initree      # or: pipx install initree
```

Then `initree` is on your PATH. To run it without installing:

```
uvx initree new myapp --recipe python+fastapi+docker+gh-actions+vps-ssh
```

## Usage

A recipe is slot layers joined by `+`. `initree new <name> --recipe <recipe>` validates the
composition, prompts for each layer's inputs, then writes the project.

Slice 1 — a deployable FastAPI service:

```
initree new myapp --recipe python+fastapi+docker+gh-actions+vps-ssh
```

Slice 2 — a Go service on a second CI dialect with a namespaced deploy and an optional notifier:

```
initree new myapp --recipe go+gin+docker+gitlab-ci+k8s+slack
```

What the Go recipe writes:

```
created ./myapp
  order: go -> gin -> docker -> k8s -> slack -> gitlab-ci
  + .gitignore
  + go.mod
  + cmd/server/main.go
  + internal/handler/handler.go
  + .dockerignore
  + Dockerfile
  + k8s/deployment.yaml
  + k8s/kustomization.yaml
  + k8s/service.yaml
  + .gitlab-ci.yml
  secrets: INITREE_SECRETS.md (provision before first deploy)
```

`INITREE_SECRETS.md` is a provisioning checklist generated from the secret purposes the recipe's
layers declare (registry credentials, an SSH key, a Slack webhook). No secret value ever enters the
build — the file tells you what to set, where.

### Recipes are subsets, not fixed tuples

Pick one layer per slot you need. `notify` is optional; drop it and the rest is unchanged. The
shipped layers:

| slot      | layers                |
|-----------|-----------------------|
| language  | `python`, `go`        |
| framework | `fastapi`, `gin`      |
| container | `docker`              |
| ci        | `gh-actions`, `gitlab-ci` |
| deploy    | `vps-ssh`, `k8s`      |
| notify    | `slack`               |

### CLI

```
initree new NAME --recipe RECIPE [options]

  --recipe TEXT       slot layers joined by '+'   (required)
  --out PATH          output directory            (default: ./<name-slug>)
  --set KEY=VALUE     seed a context key directly; repeatable, skips its prompt
  --no-input          take input defaults instead of prompting
  --no-finalize       skip finalize hooks (chmod, git init, formatters)
  --layers-dir PATH   load layers from here       (default: the bundled layers)
```

`--set` is how you script a build: `--no-input --set app.port=9000 --set deploy.host=user@host`.

## How it works

The engine runs five global phases; layers run in topological order, each uninterrupted:

1. **resolve** — load manifests, prove the recipe is buildable (no `owns` overlap, every required
   `consumes` has a provider, every injection target exists, the graph is acyclic), compute order.
   No files written.
2. **prompt** — collect each layer's `inputs`.
3. **compute** — resolve every `provides` (`${namespace.key}` interpolation), then freeze the bus.
4. **emit** — render each layer's owned templates, then splice injected fragments into their owner's
   file at the declared anchor.
5. **finalize** — per-layer hooks.

Each file has exactly one owning layer. The only way another layer adds to a file is a named
injection point the owner declares. The full contract lives in `docs/`:

- `docs/01-layer-contract-and-lifecycle.md` — the manifest schema and the lifecycle, worked through one slice
- `docs/02-generalization-proof.md` — the same engine across two unrelated stacks, and why the graph stays acyclic
- `docs/03-capability-registry-v1.md` — the locked capability vocabulary
- `docs/04-layer-authoring-guide.md` — how to write your own layer

## Develop

```
uv sync
uv run pytest
uv run ruff check src tests
uv run pyright
```

## License

MIT — see `LICENSE`.
