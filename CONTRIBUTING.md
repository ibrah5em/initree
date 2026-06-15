# Contributing to initree

Thanks for taking a look. The most useful contribution here is usually a new **layer** — a language,
framework, container, ci, deploy, or notify backend — because that's how the project gets broader
without getting heavier. Engine fixes and docs are just as welcome.

Before anything else, read the contract. It's the source of truth and it's small:

- [`docs/01-layer-contract-and-lifecycle.md`](docs/01-layer-contract-and-lifecycle.md) — the manifest schema and the five-phase lifecycle
- [`docs/02-generalization-proof.md`](docs/02-generalization-proof.md) — why composition holds across two unrelated stacks
- [`docs/03-capability-registry-v1.md`](docs/03-capability-registry-v1.md) — the locked capability vocabulary
- [`docs/04-layer-authoring-guide.md`](docs/04-layer-authoring-guide.md) — how to write a layer, start to finish

`CLAUDE.md` is the short version of the architecture and the non-negotiable invariants.

## Setup

You need Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ibrah5em/initree
cd initree
uv sync
uv run initree new demo --recipe python+fastapi+docker+gh-actions+vps-ssh --out /tmp/demo
```

## The checks

Run all four before you open a PR. CI runs the same set on every PR.

```bash
uv run pytest
uv run ruff check src tests layers
uv run ruff format
uv run pyright
```

The formatter and linter own mechanical style — don't hand-format and don't fight them. The judgment
a linter can't enforce is in [`.claude/rules/code-style.md`](.claude/rules/code-style.md).

## Adding a layer

Start from [`docs/04-layer-authoring-guide.md`](docs/04-layer-authoring-guide.md) — it walks a
recipe-only layer, an owning layer, and the injection-vs-recipe call. The short version:

- A layer is a folder under `layers/<id>/` with a `layer.yaml` manifest and its templates.
- Provide only keys in your slot's namespace. Consume **capability** keys (`container.exposed_port`),
  never tool-named ones (`docker.port`) — that's what keeps slots swappable.
- Each file has exactly one owning layer. Contribute to a file you don't own only through an
  injection point its owner declares.
- Add a fixture or slice test that exercises it. A new engine behaviour gets a test that fails first.

If you use Claude Code, the repo ships a `/new-layer <slot> <id>` skill that scaffolds a conformant
layer, and `/check-contract` to review changes against the invariants. Both are optional.

## Commits and PRs

The full workflow is in [`.claude/rules/git.md`](.claude/rules/git.md); the essentials:

- **Conventional commits:** `feat|fix|refactor|docs|test|chore(scope): message`. Explain the *why* in
  the body for `feat`, `fix`, and `refactor`.
- **Atomic:** one concern per commit. Keep infrastructure changes out of feature commits.
- **One PR per commit.** Branch off the latest `main` (`type/short-description`), push, open the PR
  with `gh pr create --fill`, and it squash-merges. `main` stays linear — no merge commits, no
  force-pushes to `main`.
- **`[skip ci]`** in the commit subject when a change only touches Markdown or static docs.
- **No secrets.** Never stage `.env`, keys, or credentials.

Open an issue first if you're planning something large, so we can agree on the shape before you build
it.
