# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-16

### Added

- `podman` container layer — a drop-in for `docker` on the same `container.*` contract, the concrete
  proof that swapping the container slot touches no other layer. A swap-radius test locks the delta
  to the container slot (#65).
- `node` (language) + `express` (framework) — a third stack, and the first to exercise the
  `json-array` `package.json` dependency injection the engine supported but no layer used (#67).
- `runtime.image_prep` capability, so a single-stage container build splices the language's own
  image setup instead of the container layer hardcoding it (#66).
- `initree new --dry-run` resolves and renders the recipe into a throwaway directory, reports the
  file tree it would write, and leaves the destination untouched.
- `initree list` shows the available layers grouped by slot.
- `initree --version` prints the installed version.

### Changed

- `vps-ssh` pulls and runs the image with `container.runtime` rather than a hardcoded `docker`, in
  both the deploy recipe and the manual deploy script, so a docker→podman swap reaches the host
  (#63, #64).
- The container single-stage build no longer bakes in python's `uv` setup; the language carries it
  through `runtime.image_prep`, leaving the container layer language-agnostic (#66).
- `resolve` errors now point at the fix: a missing required key names the slot that provides it,
  and an unknown layer id in a recipe suggests the closest available layer.
- CI layers derive their test and deploy jobs from capabilities on the bus instead of hardcoding
  them per language and deploy target, so `gh-actions` and `gitlab-ci` no longer carry stack-coupled
  job blocks (#48, closes #44).

### Fixed

- The ghcr image base now includes the registry owner segment, so pushes are no longer rejected
  (#47, closes #45).
- `k8s` emits an empty `deploy.url` when there is no ingress host, instead of leaving a dangling
  `https://` in the Slack notification (#46, closes #43).

## [0.1.0] - 2026-06-15

First public release.

### Added

- The composition engine: a five-phase lifecycle (`resolve` → `prompt` → `compute` → `emit` →
  `finalize`) over a typed capability bus, with `resolve` proving a recipe is buildable before any
  file is written (no `owns` overlap, every required `consumes` has a provider, every injection
  target exists, the graph is acyclic).
- `initree new <name> --recipe <recipe>` with `--out`, `--set`, `--no-input`, `--no-finalize`, and
  `--layers-dir`.
- Ten layers across six slots: `python`/`go` (language), `fastapi`/`gin` (framework), `docker`
  (container), `gh-actions`/`gitlab-ci` (ci), `vps-ssh`/`k8s` (deploy), `slack` (notify).
- Capability registry v1, loaded as data so the vocabulary stays the single source of truth.
- Two-tier interpolation: `${namespace.key}` resolved by the engine at `compute`, `{{TOKEN}}`
  (`{{IMAGE}}`, `{{SHA}}`, `{{SECRET:purpose}}`, `{{SECRET_FILE:purpose}}`) deferred to the ci layer
  at render. Secret values never enter the bus.
- Injection formats: `toml-array`, `text-block`, `line`, `yaml-seq`, `json-array`.
- `INITREE_SECRETS.md`, generated from the secret purposes a recipe's layers declare — a
  provisioning checklist, never a secret value.
- A self-contained wheel that bundles the layers and the registry, so an installed `initree` runs
  from any working directory. MIT licensed, published to PyPI via Trusted Publishing.

[Unreleased]: https://github.com/ibrah5em/initree/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ibrah5em/initree/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ibrah5em/initree/releases/tag/v0.1.0
