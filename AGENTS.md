# Instructions for repository work

Use English for all repository content: code identifiers, comments, filenames,
documentation, command output, error messages and test descriptions.

Before changes or code review, read [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).
Use its relevant product contracts and lifecycle checks when planning,
implementing and reviewing work. Read the selected backlog item's instructions
as well; planned behavior is not evidence that a feature already exists.

For code changes, review both the diff and the affected end-to-end flow. Challenge
demo-specific assumptions with focused fixtures. Complete the guide's
understandability review before declaring implementation complete. Keep work
scoped: unrelated known gaps belong in the backlog, not incidental refactoring.

In the final report identify contracts checked, actual test results, verification
gaps and the understandability review outcome. Separate product/unit tests,
acceptance-harness tests and real Podman/systemd verification. Never substitute
older lab results for verification of the current change. `acceptance/RESULTS.md`
holds only the latest real results; older evidence stays in the git history.

Keep the guide's contracts and known-gap references current when behavior changes.
Add meaningful regression coverage for fixed gaps; documentation alone is not a
regression gate. Use existing test/CI conventions. For documentation-only changes,
check consistency, relative links and `git diff --check`; runtime tests are not
required unless the documentation change depends on unverified runtime behavior.

## Simplicity is an acceptance criterion

Optimize for an operator with limited Linux experience and a developer
with basic Python knowledge. A working solution is not complete if its
ordinary use or maintenance requires unnecessary concepts or steps.

- Implement current, explicitly supported requirements. Do not add
  flexibility, extension points or configuration for hypothetical needs.
- Prefer one supported way to perform each ordinary task. Additional
  modes, fallbacks and automatic detection need a concrete current use case.
- Keep one authoritative source for each value. Do not persist information
  that can be reliably obtained from existing authoritative state unless
  correctness or recovery requires it.
- Before the first customer installation, do not add migration code,
  old-format detection or compatibility aliases.
- Prefer explicit data and ordinary control flow. Introduce an abstraction
  when it makes the current code easier to understand or change, not merely
  to prepare for future reuse.
- Validate at the boundary where information becomes trusted. Reuse shared
  checks; additional checks must protect a distinct failure boundary.
- Preserve required security, data retention and interruption/retry behavior.
  Simplify how these requirements are met rather than silently weakening them.
- Treat proposed mechanisms in plans as proposals unless explicitly decided.
  Distinguish required outcomes from implementation choices.

For each new configuration file, setting, persistent state record, operating
mode or architectural abstraction, briefly identify the current requirement
it serves and why a simpler existing mechanism is insufficient.

Before declaring completion, review one ordinary operator task and one likely
developer change. Identify unnecessary steps, files, concepts and indirection.
Remove unnecessary additions within scope; report unrelated cleanup separately.

The final report must briefly state:
- what became simpler;
- what complexity was added and why it is necessary;
- what relevant behavior was verified.

Do not optimize for minimum line count or minimum diff at the expense of
clarity. Do not introduce a framework or a new review document to satisfy
these instructions.
