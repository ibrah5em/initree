# initree capability registry — v1

Status: **the public contract.** This is the vocabulary every layer reads from and writes to the
shared context. It is versioned and governed by the stability policy in §11.

Relationship to the other documents:
- the **layer manifest schema** (`apiVersion: initree.dev/v1`) defines the *shape* of a `layer.yaml`.
- the **slice walkthroughs** (python/fastapi/docker/gh-actions/vps and go/gin/gitlab-ci/k8s/slack)
  are worked examples.
- **this registry** defines the *meaning* of the keys those layers exchange. The manifest schema and
  this registry version independently.

---

## 1. Core concepts

**Capability key.** A namespaced `namespace.key` value on the shared context. A consumer binds to the
key, never to the layer that produced it — so swapping the producing layer (docker → podman,
gh-actions → gitlab-ci) requires no change to any consumer.

**Namespace ownership.** Each namespace has exactly one authoritative *provider slot* (§3). Only that
slot's layer may provide that namespace's keys. This is what makes capability-binding enforceable.

**Conformance.** Each key carries a level for its owner slot:
- **MUST** — a conformant layer of that slot is required to provide it. Consumers may rely on it.
- **SHOULD** — recommended; consumers must tolerate absence with a documented fallback.
- **MAY** — optional; provided only when meaningful (e.g. compiled-language build keys).

**Two-tier interpolation.**
- `${namespace.key}` — a context value, resolved by the **engine** at `compute` (scaffold time).
  Always concrete and backend-agnostic.
- `{{TOKEN}}` — a **deferred runtime token**, resolved only by the **ci slot** at its render (§7),
  because only it knows the runtime's native syntax. Used for secrets and the commit SHA.

**Shared vs private.** Keys in this registry are the shared contract. A layer's own inputs and state
live under `namespace.<backend>.*` (e.g. `deploy.k8s.namespace`) and are **never** consumed by other
layers (§9).

---

## 2. Type vocabulary

| type | meaning |
|------|---------|
| `string` | UTF-8 string |
| `int` | integer |
| `bool` | true/false |
| `list<string>` | ordered list of strings |
| `map<string,string>` | string→string mapping |
| `recipe` | `list<string>` of shell commands that **may** contain `{{TOKEN}}`s. Backend-agnostic; rendered into a CI job by the ci slot. |

---

## 3. Namespace ownership map

| namespace | provider | purpose |
|-----------|----------|---------|
| `project.*` | engine (seeded) | project identity |
| `git.*` | engine (seeded) | repo facts |
| `runtime.*` | **language** slot | language toolchain + build recipe inputs |
| `app.*` | **framework** slot | how the application starts and is checked |
| `container.*` | **container** slot | the built image |
| `registry.*` | **container** slot | where the image is published |
| `ci.*` | **ci** slot | the pipeline system |
| `deploy.*` | **deploy** slot | the deployment target (common facts only) |
| `notify.*` | **notify** slot (optional) | outbound notifications |

---

## 4. Engine-seeded keys (always present)

### `project.*`
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `project.name` | string | MUST | human-readable project name | `myapp` |
| `project.slug` | string | MUST | filesystem/DNS-safe name | `myapp` |
| `project.dir` | string | MUST | absolute output directory | `/home/me/myapp` |

### `git.*`
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `git.is_repo` | bool | MUST | whether `project.dir` is already a git repo | `false` |

> There is deliberately **no** `git.sha` at scaffold time. The commit SHA is a CI-runtime concept;
> recipes obtain it via the `{{SHA}}` token or implicitly inside `{{IMAGE}}` (§7).

---

## 5. `runtime.*` — provided by the **language** slot

| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `runtime.language` | string | MUST | language id | `python` / `go` |
| `runtime.version` | string | MUST | language version | `3.12` / `1.22` |
| `runtime.base_image` | string | MUST | OCI image for build (and run, if single-stage) | `python:3.12-slim` / `golang:1.22` |
| `runtime.install_cmd` | string | MUST | command that fetches dependencies | `uv sync --frozen` / `go mod download` |
| `runtime.run_base_image` | string | MAY | final-stage image for compiled languages | `gcr.io/distroless/static-debian12` |
| `runtime.build_cmd` | string | MAY | compile step (compiled languages only) | `CGO_ENABLED=0 go build -o /out/server ...` |
| `runtime.artifact` | string | MAY | built artifact path (compiled languages only) | `/out/server` |

Presence of `runtime.build_cmd` + `runtime.artifact` is the signal a container layer uses to choose a
multi-stage build. Interpreted languages omit them.

---

## 6. `app.*` — provided by the **framework** slot

| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `app.port` | int | MUST | port the application process listens on | `8000` / `8080` |
| `app.start_command` | string | MUST | command that starts the app inside the image | `uvicorn app.main:app --host 0.0.0.0 --port 8000` / `/server` |
| `app.healthcheck_path` | string | SHOULD | HTTP health endpoint path | `/health` / `/healthz` |

> Framework-internal details (ASGI module path, Go entrypoint package, etc.) are **private inputs**
> that *derive* `app.start_command`. They are not shared keys — `app.start_command` carries
> everything a downstream layer needs.

---

## 7. `container.*` and `registry.*` — provided by the **container** slot

### `container.*`
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `container.runtime` | string | MUST | container tool id | `docker` / `podman` |
| `container.image_name` | string | MUST | unqualified image name (used for resource/labels) | `myapp` |
| `container.exposed_port` | int | MUST | port the container exposes (usually = `app.port`) | `8000` / `8080` |
| `container.build_recipe` | recipe | MUST | backend-agnostic build/push commands (tokens allowed) | see below |

### `registry.*`
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `registry.host` | string | SHOULD | registry host/path prefix | `registry.gitlab.com/myapp` |
| `registry.image_name_base` | string | SHOULD | **untagged** reference = `host/image_name` | `registry.gitlab.com/myapp` |

`registry.*` is SHOULD, not MUST: a build-and-run-locally container layer may not push. If
`registry.image_name_base` is absent, the ci slot must not assume a registry.

Example `container.build_recipe`:
```yaml
- 'docker login -u {{SECRET:registry_user}} -p {{SECRET:registry}} ${registry.host}'
- 'docker build -t {{IMAGE}} .'
- 'docker push {{IMAGE}}'
```

---

## 8. `ci.*`, `deploy.*`, `notify.*`

### `ci.*` — provided by the **ci** slot
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `ci.provider` | string | MUST | ci system id | `gh-actions` / `gitlab-ci` |

The ci slot is the terminal assembler (runs last; §10). It provides little because it *consumes*
recipes from the other slots and is the sole resolver of `{{...}}` tokens.

### `deploy.*` — provided by the **deploy** slot
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `deploy.target` | string | MUST | deploy backend id | `vps` / `kubernetes` |
| `deploy.summary` | string | MUST | one-line human description; the **only** channel through which backend internals surface to others | `kubernetes · ns/prod · 2 replicas` |
| `deploy.apply_recipe` | recipe | MUST | backend-agnostic deploy commands (tokens allowed) | `[ 'kubectl apply -k k8s/ -n prod', ... ]` |
| `deploy.url` | string | SHOULD | live URL if known (may be empty) | `https://app.example.com` |

### `notify.*` — provided by the **notify** slot (optional slot)
| key | type | conformance | description | example |
|-----|------|-------------|-------------|---------|
| `notify.send_recipe` | recipe | MUST-if-present | backend-agnostic notification command (tokens allowed) | `[ 'curl -sf -X POST ... {{SECRET:slack_webhook}}' ]` |

---

## 9. Recipe tokens (deferred `{{...}}`)

Resolved by the **ci** slot at its render. A non-ci layer that needs a runtime value emits one of
these tokens; it must never emit CI-native syntax directly.

| token | the ci slot resolves it to | meaning |
|-------|----------------------------|---------|
| `{{IMAGE}}` | `${registry.image_name_base}` + `:` + native short SHA | fully-qualified image ref for this run |
| `{{SHA}}` | native short commit SHA reference | e.g. `$CI_COMMIT_SHORT_SHA`, `${{ github.sha }}` |
| `{{SECRET:purpose}}` | native masked-variable reference | e.g. `$CI_REGISTRY_PASSWORD` |
| `{{SECRET_FILE:purpose}}` | native file-type-variable path | e.g. `$KUBE_CONFIG` (a path) |

---

## 10. Secret purposes

Secret **values never enter the context.** The only cross-layer secret vocabulary is the set of
logical *purposes* below, referenced through the `{{SECRET:...}}` / `{{SECRET_FILE:...}}` tokens.
The engine compiles every purpose it observes into a provisioning checklist (`INITREE_SECRETS.md`).

| purpose | token form | meaning | typical native (GitLab / GitHub / cluster) |
|---------|------------|---------|--------------------------------------------|
| `registry` | `{{SECRET:registry}}` | registry password/token (push) | `$CI_REGISTRY_PASSWORD` / `${{ secrets.REGISTRY_TOKEN }}` |
| `registry_user` | `{{SECRET:registry_user}}` | registry username (push) | `$CI_REGISTRY_USER` |
| `kubeconfig` | `{{SECRET_FILE:kubeconfig}}` | cluster credentials (file) | `$KUBE_CONFIG` (path) |
| `slack_webhook` | `{{SECRET:slack_webhook}}` | Slack incoming webhook URL | `$SLACK_WEBHOOK` |

> A single logical purpose can map to multiple physical stores. `registry` is a CI masked variable on
> the push side **and** a cluster `imagePullSecret` (a deploy-private input, e.g.
> `deploy.k8s.pull_secret`) on the pull side. One handle, two manifestations, rendered by two layers.

New purposes must be added to this table and follow the naming rule (§12).

---

## 11. Canonical injection points

An `injects.into` target must match either one of these canonical ids or an id a layer declares in its
own `injection_points`. The id is shared vocabulary; the `format` is owner-specific.

| id | declared by | typical file | formats seen | semantics |
|----|-------------|--------------|--------------|-----------|
| `runtime.dependencies` | language | `pyproject.toml` / `go.mod` / `package.json` | `toml-array` / `text-block` / `json-array` | additive dependency entries; owner runs a tidy/lock in `finalize` |
| `runtime.ignore` | language | `.gitignore` | `line` | additive ignore patterns |

Injection is the right tool only when the contributed content's **format is backend-stable** (a
dependency is a dependency). Content whose **structure is backend-specific** (CI job blocks) is passed
as a `recipe` capability instead and rendered by the ci slot — never injected.

---

## 12. Private (non-shared) keys

A layer's own inputs and internal state live under `namespace.<backend>.*` and are **out of the shared
contract**. They MUST NOT be consumed by other layers.

| example | owner | note |
|---------|-------|------|
| `deploy.k8s.namespace` | k8s | namespace; surfaces to others only via `deploy.summary` |
| `deploy.k8s.replicas` | k8s | replica count |
| `deploy.k8s.pull_secret` | k8s | cluster image-pull secret name |
| `deploy.vps.host` | vps-ssh | target host |

---

## 13. Per-slot conformance summary (the author checklist)

**language** — MUST provide `runtime.language`, `runtime.version`, `runtime.base_image`,
`runtime.install_cmd`. MAY provide `runtime.run_base_image`, `runtime.build_cmd`, `runtime.artifact`.
SHOULD own its dependency manifest and declare the `runtime.dependencies` injection point.

**framework** — MUST provide `app.port`, `app.start_command`. SHOULD provide `app.healthcheck_path`.
MUST `require` a language slot (with `one_of` if it only supports some). Typically injects into
`runtime.dependencies`.

**container** — MUST provide `container.runtime`, `container.image_name`, `container.exposed_port`,
`container.build_recipe`. SHOULD provide `registry.host`, `registry.image_name_base`. MUST consume
`runtime.base_image`, `runtime.install_cmd`, `app.start_command`, `app.port`. MAY consume
`runtime.build_cmd`, `runtime.artifact`, `runtime.run_base_image`.

**ci** — MUST provide `ci.provider`. MUST own its pipeline file and be the sole resolver of `{{...}}`
tokens. MUST consume `container.build_recipe`, `deploy.apply_recipe`, `registry.image_name_base`,
`runtime.install_cmd`. SHOULD consume `notify.send_recipe` (optional). Runs last in topological order.

**deploy** — MUST provide `deploy.target`, `deploy.summary`, `deploy.apply_recipe`. SHOULD provide
`deploy.url`. MUST consume `container.exposed_port`, `container.image_name`,
`registry.image_name_base`. Keeps backend specifics under `deploy.<backend>.*`.

**notify** (optional slot) — MUST provide `notify.send_recipe` if present. MAY consume
`deploy.summary`, `deploy.url`, `project.name`.

---

## 14. Naming rules

- Keys are `namespace.key`, lowercase `snake_case`.
- A namespace names a **capability domain**, never a tool: `container.*`, not `docker.*`.
- Backend-private keys: `namespace.<backend>.key` — outside shared scope.
- Recipe tokens are `{{UPPER}}` or `{{UPPER:arg}}`.
- Secret purposes are lowercase `snake_case` and listed in §10.

---

## 15. Reserved namespaces

Claimed for future shared capabilities — do **not** use these for private keys or unrelated purposes:

`db.*`, `cache.*`, `queue.*`, `observability.*`, `test.*`, `env.*`, `docs.*`, and `secrets.*`
(reserved as a non-bus namespace — secrets flow only as tokens, never as context values).

---

## 16. Versioning & stability policy

This registry is versioned (**v1**). A layer declares the registry version it targets; the engine
warns on a mismatch.

**Non-breaking (minor bump):**
- add a new MAY/SHOULD key, or a new namespace;
- add a secret purpose, a recipe token, or a canonical injection point.

**Breaking (major bump):**
- add a MUST key to an existing slot, or raise a key from SHOULD/MAY to MUST;
- rename, remove, or retype any key;
- change a token's or purpose's meaning.

**Deprecation:** mark a key `deprecated: <version>`, keep it functional for one major version, and
document its replacement.
