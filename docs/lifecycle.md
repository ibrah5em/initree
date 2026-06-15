# initree — layer contract & lifecycle (v1)

Worked through one concrete slice: `python + fastapi + docker + gh-actions + vps`.

The goal of this document is to show the actual data structures that prove the orchestrator
is buildable — specifically (1) how a value is `provided` by one layer and `consumed` by
another, and (2) how strict file ownership coexists with safe cross-layer injection.

---

## 0. The three rules that keep this from becoming Yeoman

1. **Consumers bind to capability keys, not implementations.**
   `vps-ssh` reads `container.exposed_port`, never `docker.port`. Swapping `docker` → `podman`
   (which provides the same capability key) requires zero changes to any consumer. This is the
   single property that makes the engine generalize across stacks.

2. **The composition graph is validated statically, before any file is touched.**
   The `resolve` phase rejects an invalid recipe up front. This is the buildability proof and
   the exact failure mode Yeoman could not prevent ("the sub-generator didn't return the value").

3. **Single-ownership is absolute. Injection points are the only sanctioned holes.**
   A layer may write a file only if it `owns` it. The one exception is a named `injection_point`
   that the owner *explicitly declares* — and contributions there are additive (append-only),
   never overwriting.

---

## 1. The manifest schema (the entire contract surface)

Every layer is a folder containing `layer.yaml` (declarative contract) plus templates and,
rarely, hooks. `layer.yaml` is the only thing the engine reads to plan a build.

```yaml
# layer.yaml
apiVersion: initree.dev/v1
id: <string>            # unique layer id, e.g. "fastapi"
slot: <string>          # role this fills: language | framework | container | ci | deploy | notify | ...
name: <string>
description: <string>

# --- ordering / dependency -------------------------------------------------
# Ordering is normally DERIVED from `consumes` -> `provides` edges. Use this
# block only for ordering or pinning that data flow does not already express.
requires:
  slots:
    - slot: <string>          # a slot that must be present in the recipe
      one_of: [<id>, ...]     # optional: restrict which layer may fill it

# --- context bus -----------------------------------------------------------
provides:                     # keys this layer WRITES into the shared context
  - key: <namespaced.key>     # namespace by CAPABILITY/slot, never by tool id
    type: <int|string|bool|list|map>
    value: <literal | "${...}" template | ":hook">   # resolved during `compute`
consumes:                     # keys this layer READS from the shared context
  - key: <namespaced.key>
    required: <bool>          # required: true is enforced at `resolve`
    default: <value>          # used only when not required and absent

# --- user inputs (prompts) -------------------------------------------------
inputs:
  - key: <namespaced.key>     # lands in the context like a provided value
    prompt: <string>
    type: <type>
    default: <value>

# --- files this layer OWNS (strict, exclusive globs) -----------------------
owns:
  - "<glob>"

# --- injection points this layer EXPOSES in files it owns ------------------
injection_points:
  - id: <namespaced.id>       # contributors target this id
    file: <path>              # a file in `owns`
    format: <toml-array | yaml-seq | text-block | line>
    anchor: <locator>         # TOML key path, YAML path, or marker name
    order: <alpha | declared | priority>

# --- fragments this layer INJECTS into points OTHER layers expose ----------
injects:
  - into: <injection_point.id>       # must match some layer's injection_points.id
    format: <toml-array | yaml-seq | text-block | line>
    order: <int>                     # optional priority within the point
    items: [<string>, ...]           # for array/line formats
    template: |                      # for block/seq formats; may use ${context}
      <fragment>

# --- optional lifecycle hooks (escape hatch; most layers need none) --------
hooks:
  compute: <path>             # only if a provided value needs real computation
  finalize: <path>            # e.g. chmod +x, git init, run a formatter
```

Two namespaces are **seeded by the engine** before any layer runs, so layers can rely on them:

```jsonc
// engine-provided context (always present)
{
  "project.name": "myapp",
  "project.slug": "myapp",
  "project.dir":  "/abs/path/myapp",
  "git.is_repo":  false
}
```

(Note: a build-time `git.sha` is deliberately NOT provided — image tags are resolved at CI
runtime via `${{ github.sha }}`, not baked in at scaffold time. See §4 image flow.)

---

## 2. The five layer manifests

Trimmed to the contract-relevant fields. Templates referenced by `owns` are summarized in §6.

### 2.1 `python` — slot: language

Owns the packaging manifest and exposes a dependency injection point for frameworks/tools.

```yaml
apiVersion: initree.dev/v1
id: python
slot: language
name: Python project base
inputs:
  - { key: runtime.version, prompt: "Python version", type: string, default: "3.12" }
  - { key: runtime.package_manager, prompt: "Package manager", type: string, default: "uv" }
provides:
  - { key: runtime.language, type: string, value: "python" }
  - { key: runtime.version, type: string, value: "${runtime.version}" }
  - { key: runtime.package_manager, type: string, value: "${runtime.package_manager}" }
  - { key: runtime.install_cmd, type: string, value: "uv sync --frozen" }
owns:
  - "pyproject.toml"
  - ".python-version"
  - ".gitignore"
injection_points:
  - id: runtime.dependencies          # frameworks/tools add their deps here
    file: pyproject.toml
    format: toml-array
    anchor: "[project].dependencies"
    order: alpha
```

### 2.2 `fastapi` — slot: framework

Pins to python. Produces the **app contract** (`app.*`) the rest of the stack reads.
Adds its own dependencies via the injection point `python` exposed.

```yaml
apiVersion: initree.dev/v1
id: fastapi
slot: framework
name: FastAPI service
requires:
  slots:
    - { slot: language, one_of: [python] }    # not expressible via consumes alone
inputs:
  - { key: app.module, prompt: "ASGI app path", type: string, default: "app.main:app" }
  - { key: app.port, prompt: "App port", type: int, default: 8000 }
consumes:
  - { key: runtime.language, required: true }
  - { key: runtime.version, required: true }
provides:
  - { key: app.port, type: int, value: "${app.port}" }
  - { key: app.module, type: string, value: "${app.module}" }
  - { key: app.start_command, type: string,
      value: "uvicorn ${app.module} --host 0.0.0.0 --port ${app.port}" }
  - { key: app.healthcheck_path, type: string, value: "/health" }
owns:
  - "app/**"
  - "tests/**"
injects:
  - into: runtime.dependencies        # writes into pyproject.toml, owned by python
    format: toml-array
    items:
      - "fastapi>=0.110"
      - "uvicorn[standard]>=0.29"
```

### 2.3 `docker` — slot: container

Consumes the `app.*` contract, produces the `container.*` capability. The port is consumed
here (as `app.port`) and re-provided at the container level (`container.exposed_port`).

```yaml
apiVersion: initree.dev/v1
id: docker
slot: container
name: Docker image
consumes:
  - { key: runtime.version, required: true }      # base image tag
  - { key: runtime.install_cmd, required: true }
  - { key: app.start_command, required: true }    # CMD
  - { key: app.port, required: true }             # EXPOSE
provides:
  - { key: container.runtime, type: string, value: "docker" }
  - { key: container.image_name, type: string, value: "${project.slug}" }
  - { key: container.exposed_port, type: int, value: "${app.port}" }
owns:
  - "Dockerfile"
  - ".dockerignore"
injects:
  - into: ci.job.build.steps          # build/push step, into the workflow gh-actions owns
    format: yaml-seq
    order: 10
    template: |
      - name: Build and push image
        run: |
          docker build -t ${{ secrets.REGISTRY }}/${container.image_name}:${{ github.sha }} .
          docker push ${{ secrets.REGISTRY }}/${container.image_name}:${{ github.sha }}
```

### 2.4 `gh-actions` — slot: ci

Owns the workflow file and **declares the two injection points** that the container and deploy
layers fill. It has no data dependency on the deploy layer — injection is resolved at `emit`,
independent of layer order (see §5).

```yaml
apiVersion: initree.dev/v1
id: gh-actions
slot: ci
name: GitHub Actions pipeline
consumes:
  - { key: runtime.version, required: true }      # test/lint matrix
  - { key: runtime.install_cmd, required: true }
owns:
  - ".github/workflows/ci.yml"
injection_points:
  - id: ci.job.build.steps
    file: .github/workflows/ci.yml
    format: yaml-seq
    anchor: "jobs.build.steps"
    order: priority
  - id: ci.job.deploy.steps
    file: .github/workflows/ci.yml
    format: yaml-seq
    anchor: "jobs.deploy.steps"
    order: priority
```

### 2.5 `vps-ssh` — slot: deploy

Consumes only **capability** keys (`container.*`), so it is indifferent to whether docker or
podman produced them. Owns the deploy script (single-owned) and injects the deploy step into
the CI workflow it does not own.

```yaml
apiVersion: initree.dev/v1
id: vps-ssh
slot: deploy
name: Deploy to VPS over SSH
inputs:
  - { key: deploy.host, prompt: "VPS host (user@ip)", type: string }
consumes:
  - { key: container.image_name, required: true }
  - { key: container.exposed_port, required: true }     # <- the port, two hops from fastapi
provides:
  - { key: deploy.target, type: string, value: "vps" }
owns:
  - "deploy/deploy.sh"
injects:
  - into: ci.job.deploy.steps         # writes into .github/workflows/ci.yml, owned by gh-actions
    format: yaml-seq
    order: 20
    template: |
      - name: Deploy over SSH
        run: |
          ssh ${deploy.host} \
            "docker pull ${{ secrets.REGISTRY }}/${container.image_name}:${{ github.sha }} && \
             docker run -d --restart=always \
               -p 80:${container.exposed_port} \
               ${{ secrets.REGISTRY }}/${container.image_name}:${{ github.sha }}"
```

---

## 3. The context bus, end to end

The bus is a single namespaced key/value store. Each layer reads what it `consumes` and writes
what it `provides`. A `${...}` value may reference another context key; the engine resolves these
in dependency order during `compute`, then freezes the store.

### 3.1 Resolved context after `compute` (with provenance)

```jsonc
{
  // engine-seeded
  "project.name":           "myapp",
  "project.slug":           "myapp",

  // written by: python (language)
  "runtime.language":       "python",
  "runtime.version":        "3.12",
  "runtime.package_manager":"uv",
  "runtime.install_cmd":    "uv sync --frozen",

  // written by: fastapi (framework)   -- consumes runtime.*
  "app.module":             "app.main:app",
  "app.port":               8000,
  "app.start_command":      "uvicorn app.main:app --host 0.0.0.0 --port 8000",
  "app.healthcheck_path":   "/health",

  // written by: docker (container)    -- consumes app.* + runtime.*
  "container.runtime":      "docker",
  "container.image_name":   "myapp",
  "container.exposed_port": 8000,

  // written by: vps-ssh (deploy)      -- consumes container.*
  "deploy.target":          "vps"
}
```

### 3.2 The port, traced through three layers

| key                      | written by | value         | read by                |
|--------------------------|------------|---------------|------------------------|
| `app.port`               | fastapi    | `8000`        | docker                 |
| `container.exposed_port` | docker     | `${app.port}` | vps-ssh                |

- `fastapi` declares `provides: app.port = 8000` (from a user input, default 8000).
- `docker` declares `consumes: app.port (required)` → renders `EXPOSE 8000`; then
  `provides: container.exposed_port = "${app.port}"`.
- `vps-ssh` declares `consumes: container.exposed_port (required)` → renders `-p 80:8000`.

`vps-ssh` never references `app.port` or anything docker-specific. It only knows the
**container capability**. That is what makes the deploy layer reusable across container backends.

---

## 4. Image name / tag flow (the second value)

`container.image_name` is known at scaffold time (`myapp`); the **tag** is not — it is the git
SHA at CI runtime. So the scaffold flows only the *name* through the bus, and both the build step
and the deploy step compose the full reference with the same CI expression `${{ github.sha }}`.

```
docker  provides  container.image_name = "myapp"
   |
   +--> docker  injects build step   -> docker build -t .../myapp:${{ github.sha }} .
   +--> vps-ssh injects deploy step  -> docker run  ... .../myapp:${{ github.sha }}
```

Tag coherence between build and deploy is guaranteed by the CI runtime (same workflow run,
same `github.sha`), not by the scaffolder. The scaffolder's only job is to flow `image_name`
to every layer that needs it — which the bus does.

---

## 5. The lifecycle

The engine runs global phases. Within a phase, layers are processed in **topological order**
derived from `requires.slots` + the implicit `consumes → provides` edges. Each layer's hook (if
any) runs uninterrupted ("layer as a function"), never interleaved with another layer's phases.

```
recipe: python + fastapi + docker + gh-actions + vps
topological order: python -> fastapi -> docker -> { gh-actions, vps-ssh }
```

(`gh-actions` and `vps-ssh` are unordered relative to each other: neither consumes the other's
output. Their relationship is owner/contributor, resolved at `emit` — see phase 4.)

### Phase 1 — `resolve`  (no user code, no files)
Builds the layer set and validates the whole graph. **Buildability is proven here.** Checks:
- every `requires.slots` is satisfied, and every `one_of` pin holds (fastapi requires python);
- **no two layers' `owns` globs overlap** → else hard error;
- **every `consumes.required` key has a `provides` from an upstream layer** → else hard error
  (e.g. "vps-ssh requires `container.exposed_port`, no provider in recipe");
- **every `injects.into` matches a declared `injection_points.id`** → else hard error;
- the dependency graph is acyclic → else hard error.

### Phase 2 — `prompt`
Walks layers in topo order, collects each layer's `inputs`. Answers land in the context, so a
later prompt can default off an earlier answer or an already-provided value.

### Phase 3 — `compute`
Runs each layer in topo order. For each: resolve its `provides` values (evaluate `${...}`
against the current context, or call `hooks.compute`), write them into the bus. After this phase
the context is **complete and frozen** — no value changes after this point.

### Phase 4 — `emit`
Two ordered passes:
- **4a. write owned files.** Render every `owns` template against the frozen context and write
  it. Exactly one writer per file (single-ownership enforced).
- **4b. resolve injections.** For each `injection_points` entry, gather all `injects` across all
  layers that target its `id`, order them (`order`), render each fragment against the frozen
  context, and splice into the owner's file at `anchor`. Content outside the point is untouched.

Because injection happens *after* every layer has computed, a contribution from a layer that runs
later in topo order (vps-ssh) still lands correctly in a file owned by an earlier layer
(gh-actions). Injection is order-independent.

### Phase 5 — `finalize`
Runs any `hooks.finalize` in topo order (e.g. `chmod +x deploy/deploy.sh`, `git init`,
`uv lock`, run a formatter).

---

## 6. Rendered output (the proof)

What the engine writes for this recipe. Values that flowed through the bus are annotated.

### `pyproject.toml` — owned by `python`, dependencies INJECTED by `fastapi`
```toml
[project]
name = "myapp"
requires-python = ">=3.12"          # runtime.version
dependencies = [
    # >>> initree:inject runtime.dependencies
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    # <<< initree:inject runtime.dependencies
]
```

### `Dockerfile` — owned by `docker`
```dockerfile
FROM python:3.12-slim               # runtime.version
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen                # runtime.install_cmd
COPY . .
EXPOSE 8000                         # app.port  (consumed)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]   # app.start_command
```

### `deploy/deploy.sh` — owned by `vps-ssh` (single-owned, not injected into)
```bash
#!/usr/bin/env bash
set -euo pipefail
IMAGE="${REGISTRY}/myapp:${1:?tag required}"   # container.image_name
docker pull "$IMAGE"
docker run -d --restart=always -p 80:8000 "$IMAGE"   # container.exposed_port
```

### `.github/workflows/ci.yml` — owned by `gh-actions`, build+deploy steps INJECTED
```yaml
name: ci
on: { push: { branches: [main] } }
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen        # runtime.install_cmd
      - run: uv run pytest
      # >>> initree:inject ci.job.build.steps   (from: docker, order 10)
      - name: Build and push image
        run: |
          docker build -t ${{ secrets.REGISTRY }}/myapp:${{ github.sha }} .
          docker push ${{ secrets.REGISTRY }}/myapp:${{ github.sha }}
      # <<< initree:inject ci.job.build.steps
  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      # >>> initree:inject ci.job.deploy.steps   (from: vps-ssh, order 20)
      - name: Deploy over SSH
        run: |
          ssh user@1.2.3.4 \
            "docker pull ${{ secrets.REGISTRY }}/myapp:${{ github.sha }} && \
             docker run -d --restart=always \
               -p 80:8000 \
               ${{ secrets.REGISTRY }}/myapp:${{ github.sha }}"
      # <<< initree:inject ci.job.deploy.steps
```

The `8000` in `-p 80:8000` originated in the `fastapi` manifest and reached the workflow via
`app.port → container.exposed_port`. The `myapp` came from `docker`'s `container.image_name`.
`vps-ssh` hardcoded neither.

---

## 7. Why this is buildable — and why the swap works

- **The engine never gets harder as layers multiply.** It only ever talks to one manifest shape.
  Adding a 20th notifier reuses the same `provides`/`consumes`/`injects` contract. Engine
  complexity is flat in the number of layers; only the *contract surface* grows, and only when a
  genuinely new kind of data must flow.

- **Most layers are pure manifest, no code.** Every layer above uses zero hooks — `provides`
  values are literals or `${...}` templates the engine evaluates. That low barrier is what lets a
  community contribute layers, which is how breadth ("all languages and projects") is reached
  without you maintaining the combinatorial explosion.

- **The swap is real, not aspirational.** Replace the recipe's `docker` with a `podman` layer
  that declares the same capability keys:

  ```yaml
  id: podman
  slot: container
  provides:
    - { key: container.runtime, value: "podman" }
    - { key: container.image_name, value: "${project.slug}" }
    - { key: container.exposed_port, value: "${app.port}" }
  owns: ["Containerfile"]
  injects: [ { into: ci.job.build.steps, format: yaml-seq, template: "..." } ]
  ```

  `vps-ssh`, `gh-actions`, `fastapi`, and `python` change by **zero lines**. The consumer never
  knew it was docker. That is the whole thesis, reduced to a diff.

---

## 8. Open questions to pressure-test next

1. **Injection format coverage.** `toml-array` and `yaml-seq` cover this slice. A `text-block`
   (e.g. shell `.env`) and `line` (e.g. `.gitignore`) format round out the common cases. Is a
   structured-merge format ever needed, or is append-only enough? (Append-only is the safe
   default; defer merge.)
2. **Conflict semantics within a point.** Two layers inject into `ci.job.build.steps`. Order is
   `priority`; what about de-duplication if both add the same step?
3. **Capability key registry.** `app.port`, `container.exposed_port`, etc. are the public API.
   Should these be a versioned, documented schema (so layer authors target a stable vocabulary),
   or discovered ad hoc? A small registry is probably worth it early.
4. **Optional capabilities.** A `notify` layer is optional; how does a deploy layer optionally
   wire in `notify.send` only if a notifier is present? (`consumes` with `required: false` +
   conditional template, likely.)
