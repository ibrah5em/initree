# Code Style Rules

Applies to all code in the repo. Mechanical style — formatting, import order, line length — is the
linter's job, not this file's. This file is for the judgment a linter can't enforce. If a rule here
could be a lint rule, move it to the linter.

## 1. Tools own the mechanics
- The formatter and linter are the source of truth. Don't hand-format, and don't argue with them.
- Python → `ruff` (format + lint). Go → `gofmt` + `go vet`. JS/TS → `prettier` + `eslint`. Shell → `shellcheck`. C# → `dotnet format`.
- Run them before committing. A diff that only reformats unrelated code is noise — keep it out.

## 2. Naming
- Names say intent. No `data`, `tmp`, `obj`, `mgr`, `do_stuff`.
- Booleans read as questions: `is_ready`, `has_token`, `should_retry`.
- Match the domain words already in use (slot, layer, capability, recipe). Don't invent a synonym for a thing that already has a name.
- Abbreviate only when the abbreviation *is* the known term (`ci`, `id`, `url`), never to save typing.

## 3. Functions
- One function, one job. If you reach for a comment to mark a section inside a function, that's two functions.
- Guard clauses over nesting. Return early; keep the happy path at the left margin.
- Push side effects — I/O, network, file writes — to the edges. Keep the core logic pure where you can.

## 4. Errors
- Fail loud at the boundary, degrade quietly inside. Validate inputs where they enter; past the gate, trust them.
- Raise specific types with messages that say what was expected and what was found — `no provider for required key 'container.image_name'`, not `validation failed`.
- Never swallow an exception silently. No bare `except:` or catch-all that hides the cause.

## 5. Types
- Type everything that crosses a function boundary. Python: full hints, `pyright`/`mypy` clean. Use pydantic for data that needs validating, dataclasses for plain records.
- Go: small interfaces; accept interfaces, return concrete types; wrap errors with `%w` and context.
- TS: `strict` on; no `any` without a comment saying why it has to be there.

## 6. Comments
- Voice, and what not to write: see `tone.md`. Short version — explain the *why*, not the *what*.
- Comment the reasoning behind an edge case or a non-obvious choice. Skip comments that just narrate the next line.

## 7. Abstraction
- Don't abstract on first use. Rule of three: write it twice, extract on the third. Premature abstraction is harder to undo than duplication.
- Architecture composes; code shouldn't grow speculative layers "for later". Build for what's in front of you.
- Delete dead code and commented-out blocks. Git remembers them so the file doesn't have to.

## 8. Dependencies
- Justify every new one — it's a long-term cost, not a convenience.
- Prefer the stdlib when it's enough (`graphlib` over a graph package, `pathlib` over `os.path`). Add a library when it earns its place, not by reflex.

## 9. Imports & structure
- Group imports: stdlib, third-party, local. Absolute imports. No wildcard imports.
- One module, one responsibility. Keep the public surface small — export what callers need, hide the rest.

## 10. Tests
- Arrange, act, assert. One behavior per test. Name the test for the behavior it checks, not the function it calls.
- Test the failure paths, not just the happy one. The cases that should be *rejected* matter as much as the ones that pass.
