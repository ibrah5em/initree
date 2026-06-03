# initree — generalization proof (slice 2)

Recipe: `go + gin + gitlab-ci + docker + k8s + slack`
(language + framework + ci + container + deploy + notify)

This document applies the **exact schema from the v1 contract** to a stack that differs from
slice 1 in every dimension, and shows where the capability-key ontology holds, where the stress
test refined it, and that **the engine's rules change by zero**.

---

## 0. What this slice deliberately breaks vs slice 1

| dimension | slice 1            | slice 2                    | new concept introduced |
|-----------|--------------------|----------------------------|------------------------|
| language  | python (interpreted) | go (compiled, multi-stage) | build step, binary artifact |
| framework | fastapi            | gin                        | — |
| ci        | gh-actions (`jobs.steps`) | gitlab-ci (`stages` + `script`) | different pipeline structure |
| container | docker             | docker (**reused, unchanged**) | — |
| deploy    | vps-ssh (one host) | k8s (namespaces, replicas, pull secrets) | namespaces, cluster secrets |
| notify    | (none)             | slack (optional)           | optional slot |

`docker` is **reused from slice 1 with an identical manifest**. A production-ready container layer
declares the build keys as *optional* consumes, so it handles both interpreted and compiled
languages; for python they were absent, for go they are populated, and the Dockerfile template
branches single-stage vs multi-stage. The contract surface did not change — the inputs did.

---

## 1. The headline finding: two kinds of content, two existing primitives

The single-CI slice hid a distinction that a second CI makes unavoidable:

- **Format-stable content → `injects` (injection).**
  A dependency line has the same *shape* regardless of backend. The same injection primitive that
  wrote into `pyproject.toml` (`format: toml-array`) writes into `go.mod` (`format: text-block`):
  different file structure, identical primitive, different `format`/`anchor`. This is the injection
  format generalizing to a GitLab-class structural difference.

- **Backend-specific structure → `provides`/`consumes` (recipe-passing).**
  A CI job's keywords differ (`steps:`/`run:` vs `stage:`/`script:`). A portable layer therefore
  **cannot author the job block** — it provides a CI-agnostic *recipe* (a list of shell commands
  with deferred tokens), and the CI layer, sole owner of CI-native syntax, renders it. The same
  recipe yields GitHub `run:` or GitLab `script:` with zero change to the contributor.

Slice 1 had `docker`/`vps-ssh` *inject* CI fragments. That worked only because the fragments held
GitHub syntax and there was one CI. Generalizing proves **CI structure and secret syntax are
CI-private**, so they live inside the CI layer, fed by recipes. The fix is a re-allocation of the
same primitives (`provides`/`consumes` instead of `injects` for that one case) — no new field, no
new phase.

---

## 2. Two-tier interpolation (this is what keeps it portable)

| token | resolved by | when | example |
|-------|-------------|------|---------|
| `${context.key}` | the **engine** | `compute` phase (scaffold time) | `${app.port}` → `8080` |
| `{{IMAGE}}` | the **ci layer** | its `emit` render | → `$REGISTRY/myapp:$CI_COMMIT_SHA` |
| `{{SECRET:purpose}}` | the **ci layer** | its `emit` render | → `$CI_REGISTRY_PASSWORD` |
| `{{SECRET_FILE:purpose}}` | the **ci layer** | its `emit` render | → path to a file-type CI variable |

`${...}` is the capability bus (already resolved, concrete, CI-agnostic). `{{...}}` are **deferred
runtime tokens** that only the CI layer may resolve, because only it knows the runtime's native
syntax. This two-tier split is *layer behaviour* (like a template conditional), not an engine rule.

---

## 3. The five manifests (same schema)

### 3.1 `go` — slot: language
Compiled: provides a build command, an artifact path, and a separate runtime base image, so the
container layer can do a multi-stage build. Owns `go.mod` and exposes the dependency injection point.

```yaml
apiVersion: initree.dev/v1
id: go
slot: language
name: Go module base
inputs:
  - { key: runtime.version, prompt: "Go version", type: string, default: "1.22" }
  - { key: app.entrypoint, prompt: "main package path", type: string, default: "./cmd/server" }
provides:
  - { key: runtime.language, value: "go" }
  - { key: runtime.version, value: "${runtime.version}" }
  - { key: runtime.base_image, value: "golang:${runtime.version}" }            # build stage
  - { key: runtime.run_base_image, value: "gcr.io/distroless/static-debian12" } # final stage
  - { key: runtime.install_cmd, value: "go mod download" }
  - { key: runtime.build_cmd, value: "CGO_ENABLED=0 go build -o /out/server ${app.entrypoint}" }
  - { key: runtime.artifact, value: "/out/server" }
owns:
  - "go.mod"
  - ".gitignore"
injection_points:
  - { id: runtime.dependencies, file: go.mod, format: text-block, anchor: "require-block", order: declared }
```

### 3.2 `gin` — slot: framework
Pins to go. Produces the **same `app.*` contract** fastapi did (`app.port`, `app.start_command`,
`app.healthcheck_path`) — the keys are identical, only the values differ. Injects its dependency
into `go.mod` (owned by `go`) via `text-block` — the same `injects` primitive, a different format.

```yaml
apiVersion: initree.dev/v1
id: gin
slot: framework
name: Gin HTTP service
requires:
  slots: [ { slot: language, one_of: [go] } ]
inputs:
  - { key: app.port, prompt: "App port", type: int, default: 8080 }
consumes:
  - { key: runtime.language, required: true }
provides:
  - { key: app.port, value: "${app.port}" }
  - { key: app.start_command, value: "/server" }       # the built binary in the final image
  - { key: app.healthcheck_path, value: "/healthz" }
owns:
  - "cmd/**"
  - "internal/**"
injects:
  - into: runtime.dependencies        # writes into go.mod, owned by `go`
    format: text-block
    template: |
      github.com/gin-gonic/gin v1.10.0
```

### 3.3 `docker` — slot: container  (REUSED FROM SLICE 1, UNCHANGED)
Optional build keys (absent for python, present for go) select a multi-stage Dockerfile via a
template conditional. Provides a **CI-agnostic build recipe** with deferred `{{...}}` tokens —
this replaces slice 1's CI injection.

```yaml
apiVersion: initree.dev/v1
id: docker
slot: container
name: Docker image
inputs:
  - { key: registry.host, prompt: "Image registry host", type: string,
      default: "registry.gitlab.com/${project.slug}" }
consumes:
  - { key: runtime.base_image, required: true }
  - { key: runtime.install_cmd, required: true }
  - { key: app.start_command, required: true }
  - { key: app.port, required: true }
  - { key: runtime.build_cmd, required: false }         # compiled languages only
  - { key: runtime.artifact, required: false }
  - { key: runtime.run_base_image, required: false }
provides:
  - { key: container.image_name, value: "${project.slug}" }
  - { key: container.exposed_port, value: "${app.port}" }          # same key vps-ssh & k8s consume
  - { key: registry.image_name_base, value: "${registry.host}/${container.image_name}" }  # UNtagged
  - key: container.build_recipe                                    # CI-agnostic; tokens deferred
    type: list
    value:
      - 'docker login -u {{SECRET:registry_user}} -p {{SECRET:registry}} ${registry.host}'
      - 'docker build -t {{IMAGE}} .'
      - 'docker push {{IMAGE}}'
owns:
  - "Dockerfile"
  - ".dockerignore"
```

Note `registry.image_name_base` is **untagged** (no commit SHA). The SHA is a CI-runtime concept;
baking it into a bus value would force `docker` to consume a CI ref and create a `docker ↔ ci`
cycle. The CI layer composes the tag from `image_name_base` + its own native SHA var. See §6.

### 3.4 `k8s` — slot: deploy
Namespaces, replicas, and the pull-secret name are **private inputs**. They appear only in
k8s-owned manifests and its own deploy recipe. The layer surfaces facts to others **only** through
the common capability keys `deploy.summary` / `deploy.url`. It consumes the very same
`container.exposed_port` that `vps-ssh` consumed in slice 1.

```yaml
apiVersion: initree.dev/v1
id: k8s
slot: deploy
name: Deploy to Kubernetes
inputs:
  - { key: deploy.k8s.namespace, prompt: "Namespace", type: string, default: "default" }
  - { key: deploy.k8s.replicas, prompt: "Replicas", type: int, default: 2 }
  - { key: deploy.k8s.pull_secret, prompt: "Image pull secret (cluster)", type: string, default: "regcred" }
  - { key: deploy.k8s.host, prompt: "Ingress host (optional)", type: string, default: "" }
consumes:
  - { key: container.exposed_port, required: true }      # <- identical key to slice 1's vps-ssh
  - { key: container.image_name, required: true }
  - { key: registry.image_name_base, required: true }
provides:
  - { key: deploy.target, value: "kubernetes" }
  - { key: deploy.summary, value: "kubernetes · ns/${deploy.k8s.namespace} · ${deploy.k8s.replicas} replicas" }
  - { key: deploy.url, value: "https://${deploy.k8s.host}" }     # empty string if no host given
  - key: deploy.apply_recipe                                     # CI-agnostic; {{IMAGE}} deferred
    type: list
    value:
      - 'kustomize edit set image app={{IMAGE}} && cd ..'        # run from k8s/ in CI
      - 'kubectl apply -k k8s/ -n ${deploy.k8s.namespace}'
      - 'kubectl rollout status deployment/${project.slug} -n ${deploy.k8s.namespace}'
owns:
  - "k8s/**"
```

### 3.5 `slack` — slot: notify  (optional, owns no files)
Consumes the common `deploy.summary` **optionally** (`required: false`). A pure recipe provider —
demonstrates that a layer may own zero files and that optional capabilities degrade gracefully.

```yaml
apiVersion: initree.dev/v1
id: slack
slot: notify
name: Slack deploy notification
consumes:
  - { key: project.name, required: true }
  - { key: deploy.summary, required: false, default: "a new version" }
  - { key: deploy.url, required: false, default: "" }
provides:
  - key: notify.send_recipe
    type: list
    value:
      - "curl -sf -X POST -H 'Content-type: application/json' \
         --data '{\"text\":\"✅ ${project.name} deployed — ${deploy.summary} ${deploy.url}\"}' \
         {{SECRET:slack_webhook}}"
owns: []
```

### 3.6 `gitlab-ci` — slot: ci  (the assembler; runs LAST)
Consumes every backend-agnostic recipe and renders `.gitlab-ci.yml` in GitLab's structure, using
GitLab-native secret syntax. It does **not** declare injection points for the build/deploy jobs —
it renders them itself from the consumed recipes. (`gh-actions` differs only in its template and
its `{{...}}` → native mapping; its `consumes` list is identical.)

```yaml
apiVersion: initree.dev/v1
id: gitlab-ci
slot: ci
name: GitLab CI pipeline
consumes:
  - { key: runtime.install_cmd, required: true }         # test job
  - { key: registry.image_name_base, required: true }
  - { key: container.build_recipe, required: true }
  - { key: deploy.apply_recipe, required: true }
  - { key: notify.send_recipe, required: false }          # optional notify stage
owns:
  - ".gitlab-ci.yml"
# token map (layer behaviour, not engine schema):
#   {{IMAGE}}           -> ${registry.image_name_base}:$CI_COMMIT_SHA
#   {{SECRET:x}}        -> $X   (a GitLab CI/CD variable, name uppercased)
#   {{SECRET_FILE:x}}   -> $X   (a file-type CI/CD variable -> a path)
```

---

## 4. Deep dive A — Kubernetes namespaces

A namespace is a Kubernetes-only idea. It never becomes a shared capability key.

```
deploy.k8s.namespace   (private INPUT on the k8s layer, default "default")
   │
   ├─ used in  k8s/deployment.yaml, k8s/service.yaml   (files k8s OWNS)
   ├─ used in  deploy.apply_recipe                     (kubectl ... -n <ns>)
   └─ surfaced to others ONLY via the common key:
         deploy.summary = "kubernetes · ns/prod · 2 replicas"   (slack consumes this)
```

`slack` writes "deployed — kubernetes · ns/prod · 2 replicas" without ever knowing what a namespace
is. The principle: **backend-specific concepts stay private; they reach consumers only through
common capability keys.** Swapping `k8s → nomad` changes `deploy.summary`'s value and the recipe;
`slack` is untouched.

---

## 5. Deep dive B — Secrets (one credential, two stores)

No secret value and no CI-native secret syntax ever enters the capability bus. Layers express
secret *needs* as deferred `{{SECRET:purpose}}` tokens in their recipes; the CI layer resolves each
to its native reference and the engine compiles every purpose it observes into a checklist.

The registry credential is the instructive case — **one logical credential, two physical stores**:

```
logical handle: "registry"
   │
   ├─ PUSH side (CI):     container.build_recipe uses  {{SECRET:registry}}
   │                       gitlab-ci renders ->  $CI_REGISTRY_PASSWORD   (a CI/CD variable)
   │
   └─ PULL side (cluster): k8s/deployment.yaml uses  imagePullSecrets: [{ name: regcred }]
                            (regcred is a k8s Secret, an INPUT on the k8s layer)
```

Two manifestations of the same credential, rendered by two different layers in their native forms,
coordinated by one logical handle. The engine emits a provisioning report from the observed
purposes:

```text
# INITREE_SECRETS.md  (engine-generated from declared {{SECRET:...}} tokens + k8s inputs)
Provision before first deploy:
  [GitLab CI/CD variables]
    - CI_REGISTRY_USER, CI_REGISTRY_PASSWORD   (purpose: registry login)   <- {{SECRET:registry}}
    - SLACK_WEBHOOK   (file or masked)         (purpose: slack notify)     <- {{SECRET:slack_webhook}}
    - KUBE_CONFIG     (file-type)              (purpose: cluster access)
  [Kubernetes cluster]
    - secret/regcred  in namespace prod        (purpose: image pull)
      kubectl create secret docker-registry regcred --docker-server=... -n prod
```

No engine rule was added — reading declared tokens to produce a report is engine behaviour over
declared data, the same kind of thing `resolve` already does with `consumes`.

---

## 6. Deep dive C — GitLab's different structure, and why CI is the last layer

GitHub Actions and GitLab CI are structurally different files:

```
GitHub:  jobs: { build: { steps: [ {uses:...}, {run:...} ] }, deploy: { needs: build, steps:[...] } }
GitLab:  stages: [test, build, deploy, notify]
         build_image: { stage: build, script: [ ... ] }
```

Both layers consume the **identical** recipe keys (`container.build_recipe`, `deploy.apply_recipe`,
`notify.send_recipe`) and render their own structure. The contributor (`docker`, `k8s`, `slack`)
authors no CI structure at all — it only supplies shell commands with deferred tokens.

This is also why `gitlab-ci` is **last in topological order**: it consumes everyone's recipes, so
every other layer is upstream of it (`go → gin → docker → k8s → slack → gitlab-ci`). The order is
acyclic precisely because the boundary forbids non-CI layers from consuming CI-runtime refs (SHA,
secrets). Had `docker` consumed a CI-provided SHA while `gitlab-ci` consumed `docker`'s recipe, the
graph would contain a `docker ↔ gitlab-ci` cycle and `resolve` would reject the recipe. The
capability/recipe boundary is what keeps the graph a DAG.

---

## 7. Rendered output (the proof)

### `go.mod` — owned by `go`, dependency INJECTED by `gin` (text-block)
```go
module myapp

go 1.22

require (
    // >>> initree:inject runtime.dependencies
    github.com/gin-gonic/gin v1.10.0
    // <<< initree:inject runtime.dependencies
)
```
(`finalize: go mod tidy` reconciles transitive requires.) Same `injects` primitive as
`pyproject.toml` in slice 1 — only `format` changed from `toml-array` to `text-block`.

### `Dockerfile` — owned by `docker`, multi-stage selected by optional build keys
```dockerfile
FROM golang:1.22 AS build          # runtime.base_image
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download                # runtime.install_cmd
COPY . .
RUN CGO_ENABLED=0 go build -o /out/server ./cmd/server   # runtime.build_cmd

FROM gcr.io/distroless/static-debian12     # runtime.run_base_image
COPY --from=build /out/server /server      # runtime.artifact
EXPOSE 8080                                 # app.port  (from gin)
ENTRYPOINT ["/server"]                      # app.start_command
```

### `k8s/deployment.yaml` + `k8s/service.yaml` — owned by `k8s`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: myapp, namespace: prod }     # deploy.k8s.namespace
spec:
  replicas: 2                                   # deploy.k8s.replicas
  selector: { matchLabels: { app: myapp } }
  template:
    metadata: { labels: { app: myapp } }
    spec:
      imagePullSecrets: [ { name: regcred } ]   # deploy.k8s.pull_secret  (PULL-side credential)
      containers:
        - name: myapp
          image: registry.gitlab.com/myapp:latest   # set by CI via `kustomize edit set image`
          ports: [ { containerPort: 8080 } ]    # container.exposed_port  <- app.port from gin
          readinessProbe: { httpGet: { path: /healthz, port: 8080 } }  # app.healthcheck_path
---
apiVersion: v1
kind: Service
metadata: { name: myapp, namespace: prod }
spec:
  selector: { app: myapp }
  ports: [ { port: 80, targetPort: 8080 } ]     # targetPort = container.exposed_port
```

### `.gitlab-ci.yml` — owned by `gitlab-ci`, jobs RENDERED from consumed recipes
```yaml
stages: [test, build, deploy, notify]

test:
  stage: test
  image: golang:1.22
  script:
    - go mod download            # runtime.install_cmd
    - go test ./...

build_image:
  stage: build
  image: docker:27
  services: [docker:27-dind]
  script:                        # rendered from container.build_recipe; {{...}} -> GitLab native
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD registry.gitlab.com/myapp
    - docker build -t registry.gitlab.com/myapp:$CI_COMMIT_SHA .
    - docker push registry.gitlab.com/myapp:$CI_COMMIT_SHA

deploy:
  stage: deploy
  image: bitnami/kubectl:latest
  script:                        # rendered from deploy.apply_recipe
    - cd k8s && kustomize edit set image app=registry.gitlab.com/myapp:$CI_COMMIT_SHA && cd ..
    - kubectl apply -k k8s/ -n prod                       # deploy.k8s.namespace
    - kubectl rollout status deployment/myapp -n prod
  variables: { KUBECONFIG: $KUBE_CONFIG }                 # file-type CI variable

notify:
  stage: notify
  when: on_success
  script:                        # rendered from notify.send_recipe (omitted entirely if no slack)
    - curl -sf -X POST -H 'Content-type: application/json'
        --data '{"text":"✅ myapp deployed — kubernetes · ns/prod · 2 replicas https://..."}'
        $SLACK_WEBHOOK
```

The `8080` in every rendered artifact originated in the `gin` manifest and reached the Kubernetes
`containerPort`, the `Service.targetPort`, the readiness probe, and the `Dockerfile` EXPOSE — via
`app.port → container.exposed_port`, the same key path slice 1 used to write a VPS `-p 80:8000`.

---

## 8. Proof: the swap radius, and what the engine had to change

### What changed to go from slice 1 to slice 2

| layer | change |
|-------|--------|
| `python` → `go` | new language layer (compiled: adds build_cmd/artifact/run_base_image) |
| `fastapi` → `gin` | new framework layer; **same `app.*` keys**, different values |
| `gh-actions` → `gitlab-ci` | new CI layer; **same `consumes`**, different template + token map |
| `vps-ssh` → `k8s` | new deploy layer; **consumes the same `container.exposed_port`** |
| `docker` | **unchanged manifest** (optional build keys now populated) |
| `slack` | new optional notify layer |

### Engine rules touched
- new manifest fields: **0**
- new lifecycle phases: **0**
- changes to `resolve` validation (owns-overlap, consumes/provides, inject-target, acyclicity): **0**
- changes to the injection mechanism: **0** (only `format`/`anchor` values differ per layer)

### The swap, reduced to a diff
Replace the deploy backend `k8s → nomad` (declares the same `deploy.*` common keys and consumes
`container.exposed_port`): `gin`, `go`, `docker`, `gitlab-ci`, and `slack` change by **zero lines**.
Replace the CI `gitlab-ci → gh-actions`: every other layer changes by **zero lines**. The consumer
never knew which backend produced the capability key. That is rule #1, generalized — and the only
thing the test added to the design was a sentence telling layer authors *which* primitive to reach
for: injection for format-stable content, recipes for backend-specific structure.

---

## 9. Carried-forward open questions

1. **Recipe token vocabulary.** `{{IMAGE}}`, `{{SECRET:x}}`, `{{SECRET_FILE:x}}` cover this slice.
   Is `{{SHA}}` (raw) ever needed directly, or is it always inside `{{IMAGE}}`?
2. **List-valued capability merging.** `slack` consumes `deploy.summary` as a scalar. If multiple
   notify layers existed, do their recipes simply each become a job (no merge needed)? (Likely yes —
   each is an independent recipe; the CI layer renders one job per notify recipe.)
3. **Capability key registry (still the top priority).** `app.port`, `container.exposed_port`,
   `deploy.summary`, the `{{SECRET:purpose}}` purposes — these are the public vocabulary every layer
   author targets. They should be a versioned, documented schema before the ecosystem opens.
