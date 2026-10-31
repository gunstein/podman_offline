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
