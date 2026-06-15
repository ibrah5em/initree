# initree

[![PyPI](https://img.shields.io/pypi/v/initree.svg)](https://pypi.org/project/initree/)
[![Python](https://img.shields.io/pypi/pyversions/initree.svg)](https://pypi.org/project/initree/)
[![CI](https://github.com/ibrah5em/initree/actions/workflows/ci.yml/badge.svg)](https://github.com/ibrah5em/initree/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-initree-blue.svg)](https://ibrah5em.github.io/initree/)

**Compose a project from layers, not from templates.**

Every "universal scaffolder" eventually dies the same way: someone wants Go instead of Python, GitLab
instead of GitHub, Kubernetes instead of a VPS — and now you maintain a template for every
combination. N languages × M CI systems × K deploy targets. The grid explodes and the project rots.

initree refuses to play that game. It ships small, independent **layers** — language, framework,
container, ci, deploy, notify — and builds your project by composing them. Breadth is N + M + K
layers you add up, never N × M × K templates you maintain.

```bash
# same six slots, two completely different stacks — you recompose the recipe, nothing else
initree new api --recipe python+fastapi+docker+gh-actions+vps-ssh
initree new api --recipe go+gin+docker+gitlab-ci+k8s+slack
```

The trick is that layers never talk to each other directly. They exchange data over a typed
**capability bus**. The deploy layer asks for `container.exposed_port` — it has never heard of Docker.
So swapping `docker` → `podman`, or `gh-actions` → `gitlab-ci`, changes that one layer and touches
nothing else.

## Install

```bash
uv tool install initree      # or: pipx install initree
```

`initree` is now on your PATH. To try it without installing anything:

```bash
uvx initree new myapp --recipe python+fastapi+docker+gh-actions+vps-ssh
```

## Quick start

A recipe is slot layers joined by `+`. `initree new <name> --recipe <recipe>` validates the
composition first, prompts for each layer's inputs, then writes the project.

```bash
initree new myapp --recipe go+gin+docker+gitlab-ci+k8s+slack
```

```text
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

You get a working Go service, a multi-stage Dockerfile, Kubernetes manifests, a GitLab pipeline that
builds and deploys, and a Slack notification on success — each from a layer that knows nothing about
the others.

`INITREE_SECRETS.md` is a provisioning checklist built from the secret *purposes* the recipe's layers
declare — for this recipe: registry credentials and a Slack webhook URL. No secret value ever enters
the build. The file tells you what to set in your CI store, and why, before the first deploy.

## Recipes are subsets, not fixed tuples

Pick one layer per slot you actually need. `notify` is optional — drop `slack` and the rest is
identical. The shipped layers:

| slot      | layers                    |
|-----------|---------------------------|
| language  | `python`, `go`            |
| framework | `fastapi`, `gin`          |
| container | `docker`                  |
| ci        | `gh-actions`, `gitlab-ci` |
| deploy    | `vps-ssh`, `k8s`          |
| notify    | `slack`                   |

Want a stack that isn't here? Add one layer, not a whole new template. See
[`docs/authoring.md`](docs/authoring.md).

## CLI

```text
initree new NAME --recipe RECIPE [options]

  --recipe TEXT       slot layers joined by '+'   (required)
  --out PATH          output directory            (default: ./<name-slug>)
  --set KEY=VALUE     seed a context key directly; repeatable, skips its prompt
  --no-input          take input defaults instead of prompting
  --no-finalize       skip finalize hooks (chmod, git init, formatters)
  --layers-dir PATH   load layers from here       (default: the bundled layers)
```

`--set` is how you script a non-interactive build:

```bash
initree new myapp --recipe python+fastapi+docker+gh-actions+vps-ssh \
  --no-input --set app.port=9000 --set deploy.vps.host=deploy@1.2.3.4
```

## How it works

The engine runs five global phases. Within each, layers run in topological order, one at a time:

1. **resolve** — load the manifests and prove the recipe is buildable *before any file is written*:
   no two layers own the same file, every required `consumes` has a provider, every injection target
   exists, and the dependency graph is acyclic. An invalid recipe is rejected here, cleanly.
2. **prompt** — collect each layer's `inputs`.
3. **compute** — resolve every `provides` (`${namespace.key}` interpolation), then freeze the bus.
4. **emit** — render each layer's owned templates, then splice injected fragments into their owner's
   file at the declared anchor.
5. **finalize** — per-layer hooks.

Two rules keep it honest. **Each file has exactly one owning layer** — the only way another layer
adds to a file is through a named injection point the owner declares (a dependency line in
`pyproject.toml`, a step in a CI workflow). And **a layer binds to a capability, never to a tool** —
there is no `docker.*` on the shared bus, only `container.*`. That is what makes a slot swappable.

The full contract is the source of truth, locked at v1. Read it as a site at
[ibrah5em.github.io/initree](https://ibrah5em.github.io/initree/), or in the repo:

- [`docs/lifecycle.md`](docs/lifecycle.md) — the manifest schema and lifecycle, worked through one slice
- [`docs/generalization.md`](docs/generalization.md) — the same engine across two unrelated stacks, and why the graph stays acyclic
- [`docs/registry.md`](docs/registry.md) — the locked capability vocabulary
- [`docs/authoring.md`](docs/authoring.md) — how to write your own layer

## Develop

```bash
uv sync
uv run pytest
uv run ruff check src tests layers
uv run pyright
```

## License

MIT — see [`LICENSE`](LICENSE).
</content>
</invoke>
