---
name: new-layer
description: >
  Scaffold a new, conformant initree layer. Use when the user types /new-layer or asks to add a layer
  for a slot — language, framework, container, ci, deploy, or notify. Examples: "add a rust layer",
  "add a fly.io deploy layer", "/new-layer deploy fly-io".
argument-hint: "<slot> <id>"
agent: layer-author
---

# Scaffold a new layer: $ARGUMENTS

Create a conformant layer for the given `<slot> <id>` (e.g. `deploy fly-io`, `language rust`). Hand
the work to the layer-author agent, which owns the conformance rules.

Steps:

1. Parse `$ARGUMENTS` into `<slot>` and `<id>`. If either is missing or `<slot>` is not one of
   language | framework | container | ci | deploy | notify, ask for it.
2. Consult the `capability-registry` skill for the MUST / SHOULD / MAY keys this slot must provide,
   the namespace it owns, and the canonical injection points.
3. Copy `.claude/skills/new-layer/layer.template.yaml` to `layers/<id>/layer.yaml` and fill it in:
   - `slot: <slot>`, `id: <id>`;
   - `provides` — every MUST key for the slot (SHOULD keys too unless justified), values as `${...}`
     templates or literals; recipes as command lists using `{{...}}` only for runtime tokens;
   - `consumes` — capability keys this layer reads (mark `required` correctly);
   - `inputs` — anything the user must supply; put backend-specific inputs under `<slot>.<id>.*`;
   - `owns` — file globs this layer alone writes (must not overlap any sibling);
   - `injection_points` — places other layers may contribute to files this layer owns;
   - `injects` — contributions into other layers' declared points (format-stable content only).
4. Create `layers/<id>/templates/` with a template for each owned file, using `${...}` for bus
   values and `{{...}}` only inside recipes.
5. Run the layer-author self-check and report it. Do not leave any MUST key unprovided.

If this is a deploy or container layer, remember: backend-specific structure (CI jobs, kubectl
invocations) is expressed as a **recipe** the ci layer renders — never injected as a CI job block,
and never with raw `$CI_*` / `${{ secrets.X }}`.
