# initree docs

The locked contract, plus how to build on it. New here? Read top to bottom — each builds on the last.

- [Lifecycle & layer contract](lifecycle.md) — the manifest schema and the five-phase lifecycle, worked through one slice.
- [Generalization proof](generalization.md) — the same engine across two unrelated stacks, and why the dependency graph stays acyclic.
- [Capability registry](registry.md) — the locked vocabulary: capability keys, recipe tokens, secret purposes, injection points.
- [Authoring layers](authoring.md) — write your own layer, start to finish.
- [Roadmap](roadmap.md) — what's shipped and what's next.

The first three are the source of truth, locked at v1. Section numbers in those docs (`§N`) are stable — the engine's source cites them as `docs/<name> §N` to trace a check back to the rule it enforces.
