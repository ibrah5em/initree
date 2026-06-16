# initree — roadmap

Where the project is and where it's headed. For how 0.1.0 came together task by task, the git history
and [`CHANGELOG.md`](https://github.com/ibrah5em/initree/blob/main/CHANGELOG.md) are the record;
this file looks forward.

## Shipped — 0.1.0

The engine and the first ten layers, on PyPI.

- The five-phase lifecycle (`resolve` → `prompt` → `compute` → `emit` → `finalize`) over a typed
  capability bus, with `resolve` proving a recipe is buildable before any file is written.
- Ten layers across six slots: `python`/`go`, `fastapi`/`gin`, `docker`, `gh-actions`/`gitlab-ci`,
  `vps-ssh`/`k8s`, `slack`.
- Two reference recipes locked byte-for-byte by golden tests.

## Shipped — 0.2.0

Thirteen layers and a sharper CLI, on PyPI.

- [x] Repo hygiene — refreshed `CLAUDE.md`, added `CHANGELOG.md`, `CONTRIBUTING.md`, issue templates.
- [x] Docs restructure — descriptive filenames + an index, and an mkdocs site at
      [ibrah5em.github.io/initree](https://ibrah5em.github.io/initree/).
- [x] Engine introspection — `initree list` (slots and layers), `initree new --dry-run` (prove
      buildability and preview the tree without writing), a `--version` flag, and sharper `resolve`
      errors (nearest-match on an unknown layer id, the owning slot for a missing key).
- [x] Breadth — `podman` (proves the docker→podman swap touches no other layer) and `node` +
      `express` (a third stack that exercises the `json-array` `package.json` injection), on the back
      of a `runtime.image_prep` capability that makes the single-stage container language-agnostic.

## Later

- More layers as they're requested: a fly.io or render deploy, a discord notify, circleci, rust/axum.
  Each is a clean PR, not a new template — that's the whole point.
- Third-party layer discovery beyond `--layers-dir`.

## How work lands

One concern per PR, squash-merged, `main` stays linear. A new engine behaviour gets a test that fails
first. The details are in [`CONTRIBUTING.md`](https://github.com/ibrah5em/initree/blob/main/CONTRIBUTING.md).
