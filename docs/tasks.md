# initree — task list

The whole project as a flat checklist, in roughly the order it gets built. `[x]` is done (in the
repo now), `[ ]` is still ahead. Each line is one task; the section headers are just signposts, the
numbers run straight through.

Status today: the five lifecycle phases are wired end to end, every injection format and the
compute-hook escape hatch are implemented, the recipe machinery (`render_recipe` +
`{{TOKEN}}` resolution) is in `recipe.py`, and the build emits an `INITREE_SECRETS.md`
provisioning checklist from the secret purposes its recipes declare. Slice 1 now builds for real:
`python+fastapi+docker+gh-actions+vps-ssh` composes five shipped layers under `layers/` into a
deployable FastAPI service (`tests/test_slice1.py` proves it end to end). The gh-actions ci layer is
the terminal assembler — its compute hook renders the consumed recipes through the GitHub dialect,
the sole place `{{...}}` tokens resolve, and splices the steps into the workflow it owns. Next is
slice 2 (the go/gitlab-ci/k8s/slack swap) and the golden tests.

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

## Real layers — slice 1 (`python+fastapi+docker+gh-actions+vps`)

18. [x] `python` — language slot (owns `pyproject.toml`, exposes `runtime.dependencies`)
19. [x] `fastapi` — framework slot (provides `app.*`, injects its deps)
20. [x] `docker` — container slot (provides `container.*` + `container.build_recipe`)
21. [x] `gh-actions` — ci slot (the assembler: renders recipes, resolves tokens)
22. [x] `vps-ssh` — deploy slot (consumes `container.*`, provides `deploy.apply_recipe`)

## Real layers — slice 2 (`go+gin+docker+gitlab-ci+k8s+slack`)

23. [ ] `go` — language slot
24. [ ] `gin` — framework slot
25. [ ] `gitlab-ci` — ci slot (second assembler, proves the ci swap)
26. [ ] `k8s` — deploy slot
27. [ ] `slack` — notify slot (optional, owns no files)
28. [ ] reuse `docker` unchanged across both slices (the swap-radius proof)

## End-to-end proof

29. [ ] Golden test: slice 1 builds and matches the rendered output in `docs/01` §6
30. [ ] Golden test: slice 2 builds and matches the rendered output in `docs/02` §7
31. [ ] CLI smoke test: `initree new` into a temp dir on a real recipe, no fixtures

## Release

32. [ ] README usage on real recipes + a layer-authoring guide
33. [ ] Repo CI — ruff + pyright + pytest on every PR
34. [ ] Package and publish to PyPI (bump version off `0.0.0`)
