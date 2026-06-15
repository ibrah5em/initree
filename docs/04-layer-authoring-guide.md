# initree — layer authoring guide

How to write a layer. This is the practical companion to the spec: `docs/01` is the manifest schema
and lifecycle, `docs/03` is the capability vocabulary. Read those for *why*; read this for *how*.

A layer is a folder with a `layer.yaml` and, usually, a `templates/` tree. The engine reads only the
manifest to plan a build — templates and hooks come into play later. The whole job of a layer is to
declare what it reads (`consumes`), what it writes to the bus (`provides`), which files it owns, and
where it injects into files it doesn't.

## Start from a scaffold

Don't write the manifest from a blank file. Either run the scaffolder:

```
/new-layer notify discord
```

or copy the shipped layer closest to what you want (`layers/slack` for a recipe-only notifier,
`layers/k8s` for a deploy layer that owns files, `layers/go` for a compiled language). The shipped
layers under `layers/` are the reference implementations — they conform, so they're the best template.

## A first layer: recipe-only notifier

The simplest real layer owns no files and provides one recipe. Here's a Discord notifier, slot
`notify`, modeled on `slack`:

```yaml
apiVersion: initree.dev/v1
id: discord
slot: notify
name: Discord deploy notification
description: Recipe-only notifier. Owns nothing; consumes deploy.summary optionally.

consumes:
  - { key: project.name, required: true }
  - { key: deploy.summary, required: false, default: "a new version" }

provides:
  - key: notify.send_recipe
    type: recipe
    value:
      - "curl -sf -X POST -H 'Content-type:application/json' --data '{\"content\":\"${project.name} deployed — ${deploy.summary}\"}' {{SECRET:discord_webhook}}"

owns: []
```

Three things to notice, because they're the whole model:

- **It provides only in its slot's namespace.** `notify` provides `notify.*` and nothing else. A
  layer that writes outside its namespace fails `resolve`. The ownership map is `docs/03` §3.
- **It consumes capability keys, not tool keys.** `deploy.summary` is the same whether the deploy
  layer is `k8s` or `vps-ssh`. The notifier never knows which.
- **The runtime secret is a token, not a value.** `{{SECRET:discord_webhook}}` is deferred — the ci
  slot resolves it to a native masked variable at its render. The webhook value never enters the bus.
  A new secret purpose has to be added to the registry (`docs/03` §10) and it shows up automatically
  in the generated `INITREE_SECRETS.md`.

That's a complete, buildable layer. Drop it in `layers/discord/` and use it:

```
initree new myapp --recipe go+gin+docker+gitlab-ci+k8s+discord
```

## When a layer owns files

Most layers write files. List them as exclusive globs under `owns`, and put the source under
`templates/` — the tree is rendered 1:1 into the output, with `${namespace.key}` resolved against the
frozen bus.

```yaml
owns:
  - "Dockerfile"
  - ".dockerignore"
```

```
layers/docker/
├── layer.yaml
└── templates/
    ├── Dockerfile
    └── .dockerignore
```

Rules that `resolve`/`emit` enforce:

- **Exactly one owner per file.** If two layers' `owns` globs overlap, `resolve` rejects the recipe.
- **A template can only write where its layer owns.** A rendered path outside `owns` is an `emit`
  error, even if the file exists in `templates/`.
- **`owns` is a right, not an obligation.** A layer can own a glob and only sometimes write into it.

Inside a template, two interpolation tiers coexist and don't collide:

- `${namespace.key}` — resolved by the engine at `compute`. Concrete, backend-agnostic.
- `{{TOKEN}}` — left untouched by the engine; only the ci slot resolves these.

There's also a backend conditional for templates a single layer renders differently per stack:

```
# initree:if runtime.build_cmd
... multi-stage build, only emitted when the key is present ...
# initree:else
... single-stage ...
# initree:endif
```

`docker` uses exactly this to render multi-stage for compiled languages and single-stage for
interpreted ones, from one owned `Dockerfile`, without the engine knowing either stack.

## Adding to a file you don't own: injection vs recipe

You can't write into another layer's file directly. There are two sanctioned ways to contribute, and
picking the right one is the call authors get wrong most often:

**Injection** — when the content's *format is backend-stable*. A dependency line is a dependency line
regardless of CI system. The owner declares a named `injection_points` entry; contributors target its
`id`. `fastapi` adds its deps into the `pyproject.toml` that `python` owns:

```yaml
# in python (the owner)
injection_points:
  - id: runtime.dependencies
    file: pyproject.toml
    format: toml-array
    anchor: "[project].dependencies"
    order: alpha

# in fastapi (the contributor)
injects:
  - into: runtime.dependencies
    format: toml-array
    items: ["fastapi>=0.110", "uvicorn[standard]>=0.29"]
```

Injection is additive — it never overwrites. Formats: `toml-array`, `yaml-seq`, `json-array`,
`text-block`, `line`. The target `id` must be a canonical point (`docs/03` §11) or one the owner
declares.

**Recipe** — when the content's *structure is backend-specific*. A CI job block is written in GitLab
or GitHub keywords; a portable layer must never author those. Instead it provides a `recipe` (a
backend-agnostic command list, tokens allowed) over the bus, and the ci slot renders it into native
job syntax. This is why `container.build_recipe`, `deploy.apply_recipe`, and `notify.send_recipe`
exist:

```yaml
provides:
  - key: container.build_recipe
    type: recipe
    value:
      - 'docker login -u {{SECRET:registry_user}} -p {{SECRET:registry}} ${registry.host}'
      - 'docker build -t {{IMAGE}} .'
      - 'docker push {{IMAGE}}'
```

The test: if you'd write different keywords for GitHub vs GitLab, it's a recipe. If the line is the
same either way, it's an injection. Default to recipe when unsure.

## Values that need computing: the compute hook

Most `provides` are literals or `${...}` templates the engine evaluates. When a value genuinely can't
be expressed that way, set its value to `:hook` and ship a `hooks.compute` script. The engine runs it
with the bus-so-far exported as `INITREE_<UPPER_SNAKE>` env vars, and reads back a JSON object whose
keys are exactly the `:hook` keys the layer declared.

```yaml
provides:
  - { key: ci.job.build.steps, type: string, value: ":hook" }
hooks:
  compute: hooks/render_jobs.py
```

The ci layers use this to turn the recipes they consume into native script lines. A `.py` compute
hook runs under the engine's own interpreter, so it can `import initree.recipe`. Reach for a hook
only when declaration can't do it — most layers need none.

`hooks.finalize` is the other hook: it runs last, for side effects like `chmod +x`, `git init`, or a
formatter (`go mod tidy`).

## Test it

`resolve` is your fast feedback loop — it rejects a bad layer before any file is written. Point the
CLI at your working tree and build a recipe that includes the layer:

```
initree new scratch --layers-dir layers --recipe go+gin+docker+gitlab-ci+k8s+discord --no-input
```

`resolve` will tell you precisely what's wrong: an `owns` overlap, a required `consumes` with no
provider, an `injects.into` that matches no declared point, or a dependency cycle. For a layer that's
part of a slice, add it to the byte-exact golden tests under `tests/golden/` so its output is locked.

## Before you open a PR

Run the conformance check for your slot — the per-slot MUST/SHOULD/MAY list is `docs/03` §13. Quick
gut check:

- Provides land only in your slot's namespace; private state is under `namespace.<backend>.*` and
  consumed by nobody else.
- You consume capability keys, never tool-named ones — no `docker.*`, no `gitlab.*`.
- Backend-specific structure goes out as a recipe; only backend-stable format is injected.
- Any new secret purpose, recipe token, or injection point is added to the registry and follows the
  versioning policy (`docs/03` §16).

Then `/check-contract` runs the contract-guardian over your changes.
