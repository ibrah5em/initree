---
name: check-contract
description: >
  Review the current uncommitted changes for initree contract conformance. Use when the user types
  /check-contract or asks to verify a layer or engine change against the contract before committing
  or merging.
agent: contract-guardian
---

# Contract conformance review

Review the current uncommitted changes against the initree contract. Hand this to the
contract-guardian agent, which is read-only and owns the checklist.

The guardian should:

1. Run `git diff HEAD` and `git status` to see what changed.
2. Walk its full checklist — namespace ownership, per-slot MUST keys, single-file ownership, the
   injection-vs-recipe boundary, deferred-token usage (no raw `$CI_*` / `${{ secrets.X }}` /
   hardcoded secrets in recipes), private-vs-shared keys, the engine's four resolve checks if `src/`
   changed, and the versioning policy for any added/renamed capability key.
3. Report findings grouped as 🔴 Critical / 🟡 Warning / 🟢 Suggestion, each with the file, the rule,
   and the fix.

Do not modify any files — this is a review only.
