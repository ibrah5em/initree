# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `initree --version` prints the installed version.

### Changed

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

[Unreleased]: https://github.com/ibrah5em/initree/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ibrah5em/initree/releases/tag/v0.1.0
