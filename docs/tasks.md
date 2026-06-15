# initree — task list

The whole project as a flat checklist, in roughly the order it gets built. `[x]` is done (in the
repo now), `[ ]` is still ahead. Each line is one task; the section headers are just signposts, the
numbers run straight through.

Status today: the five lifecycle phases are wired end to end, every injection format and the
compute-hook escape hatch are implemented, the recipe machinery (`render_recipe` +
`{{TOKEN}}` resolution) is in `recipe.py`, and the build emits an `INITREE_SECRETS.md`
provisioning checklist from the secret purposes its recipes declare. Both slices now build for real
from the shipped layers under `layers/`. Slice 1 (`python+fastapi+docker+gh-actions+vps-ssh`) is a
deployable FastAPI service; slice 2 (`go+gin+docker+gitlab-ci+k8s+slack`) is the generalization
proof made concrete — a compiled language, a multi-stage container, a second CI dialect, a
namespaced deploy target, and an optional notify slot, all through the same engine and the same
docker manifest (`tests/test_slice1.py` and `tests/test_slice2.py` prove each end to end). The one
engine addition slice 2 needed was a backend-branching template conditional (`initree:if` in
`emit`), so docker's single owned Dockerfile renders multi-stage for go and single-stage for python
without the engine learning either stack. Both slices now have a byte-exact golden test
(`tests/test_golden_slice1.py` / `tests/test_golden_slice2.py`) locking their whole emitted tree
against `tests/golden/` — the concrete form of the docs/01 §6 and docs/02 §7 render proofs. The CLI
entry point now has its own smoke test (`tests/test_cli_smoke.py`) driving `initree new` over both
real recipes into a temp dir with no fixtures — the slice tests call `build()` directly, this proves
the production binary path. The release work is now in: the wheel bundles its layers and the registry
so an installed `initree` runs from any cwd (proven by installing into a clean venv and building both
recipes), the package carries an MIT license and full PyPI metadata at `0.1.0`, CI runs ruff +
pyright + pytest on every PR, and a release workflow publishes to PyPI on a `v*` tag via Trusted
Publishing. The one remaining step is owner-only: configure the trusted publisher on PyPI, then push
`v0.1.0` to cut the first release.

## Foundations

1. [x] Lock the contract — `docs/01` lifecycle, `docs/02` generalization proof, `docs/03` registry v1
2. [x] `.claude/` tooling — agents (layer-author, contract-guardian, engine-dev), skills, registry data
3. [x] Scaffold the package — layout, `pyproject.toml`, deps, ruff + pyright, resolve fixtures

## Engine core

4. [x] Manifest models (pydantic) + recipe loaders (`load_recipe`, `load_selected`, `source_dir`)
5. [x] Capability registry loaded as data (`registry.py`), not hardcoded
6. [x] `resolve` — the four static checks + topological order
7. [x] `compute` — capability bus + `${...}` resolution, then freeze
8. [x] `emit` — template render + injection splicing (`toml-array`, `text-block`, `line`)
9. [x] `finalize` — run per-layer finalize hooks
10. [x] `prompt` — collect each layer's inputs onto the bus seed
11. [x] `cli` — `initree new` wiring resolve → prompt → compute → emit → finalize

## Finish the engine

12. [x] `yaml-seq` injection — ruamel round-trip splice (drop the `UnsupportedInjectionFormat` pin)
13. [x] `json-array` injection — for JSON dependency files (e.g. `package.json`), when a layer needs it
14. [x] `compute` hook runner — replace the current hard refusal of `:hook` provides
15. [x] ci recipe rendering — `recipe.render_recipe` turns a `*_recipe` command list into native script lines
16. [x] `{{TOKEN}}` resolution at the ci render — `{{IMAGE}}`, `{{SHA}}`, `{{SECRET:..}}`, `{{SECRET_FILE:..}}` (`recipe.resolve_tokens`)
17. [x] `INITREE_SECRETS.md` generation from declared secret purposes — token scan over the frozen bus (the deploy-input cluster section, e.g. the k8s pull-secret, is deferred to the k8s layer #26 where a real consumer exists)

## Real layers — slice 1 (`python+fastapi+docker+gh-actions+vps-ssh`)

18. [x] `python` — language slot (owns `pyproject.toml`, exposes `runtime.dependencies`)
19. [x] `fastapi` — framework slot (provides `app.*`, injects its deps)
20. [x] `docker` — container slot (provides `container.*` + `container.build_recipe`)
21. [x] `gh-actions` — ci slot (the assembler: renders recipes, resolves tokens)
22. [x] `vps-ssh` — deploy slot (consumes `container.*`, provides `deploy.apply_recipe`)

## Real layers — slice 2 (`go+gin+docker+gitlab-ci+k8s+slack`)

23. [x] `go` — language slot (owns `go.mod`/`.gitignore`, compiled: build_cmd/artifact/run_base_image)
24. [x] `gin` — framework slot (same `app.*` keys as fastapi, injects its dep into `go.mod`)
25. [x] `gitlab-ci` — ci slot (second assembler: same `consumes`, GitLab dialect + `stages`/`script`)
26. [x] `k8s` — deploy slot (consumes the same `container.exposed_port`, owns `k8s/**`)
27. [x] `slack` — notify slot (optional, owns no files, recipe-only)
28. [x] reuse `docker` unchanged across both slices — manifest byte-identical; only the owned
        Dockerfile branches (multi-stage) via the new `emit` `initree:if` conditional

## End-to-end proof

29. [x] Golden test: slice 1 builds and matches the rendered output in `docs/01` §6
30. [x] Golden test: slice 2 builds and matches the rendered output in `docs/02` §7
31. [x] CLI smoke test: `initree new` into a temp dir on a real recipe, no fixtures

## Release

32. [x] README usage on real recipes + a layer-authoring guide (`docs/04`)
33. [x] Repo CI — ruff + pyright + pytest on every PR (`.github/workflows/ci.yml`)
34. [x] Package for PyPI — self-contained wheel, MIT license, metadata, version `0.1.0`, and a
        Trusted-Publishing release workflow. First publish is one `git tag v0.1.0` away once the PyPI
        trusted publisher is configured (owner-only).
