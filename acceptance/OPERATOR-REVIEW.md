# Operator review baseline for backlog 65–67

Historical baseline date: 2026-10-24. The first table refers to `7ef9671`;
the current item 65 assessment is recorded separately below. This is **not a lab
run**. Requirements are in the separate
[operator review](../docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review).
The [item 65 plan](../docs/HOST-SETUP-PLAN.md) describes future behavior; it is not
an executable manual and does not resolve these findings until implemented.

| Assessment | Result | Scope |
| --- | --- | --- |
| AI literal walkthrough | Findings; current manual cannot be followed independently by the intended audience | Current production guide, initial preparation/install, checks, upgrade and interruption/retry |
| Human trial without oral assistance | Not performed; outstanding verification | Must use the final manual on a fresh test host with a person with limited Linux experience |
| Product/unit tests | Not run for this documentation change | No new runtime behavior |
| Acceptance-harness tests | Not run for this documentation change | New same-procedure/SSH gates in 65–67 are requirements, not implemented tests |
| Real Podman/systemd verification | Not run for this change | Prior lab/manual results do not verify the future procedure or prove usability |

Documentation checks: 196 local links/heading targets across the four changed
documents checked successfully; whitespace, code fences and `git diff --check`
passed. This verifies document consistency, not execution of manual commands.

## Current item 65 AI walkthrough (2026-10-24)

Result: the supported declared-baseline path has no identified missing execution
step after the fixes below. This is a static AI assessment plus local execution
of manual-block regressions, not real server execution or human approval.
Reviewed working-tree guide SHA256:
`db9a2a9bb7de9ee4725ce7fb71f9ff437ea52ac8189ff2ae16d9b133c2475ef7`; implementation branch `feature/65-host-setup`,
based on `f52b797`. The earlier table and literal walkthrough below are a
**historical baseline** against `7ef9671`, not a claim about the rewritten guide.
Current local evidence is in [HOST-SETUP.md](HOST-SETUP.md).

The literal path now starts with a complete trusted delivery/value checklist,
explicit administrator SSH, private unprivileged upload directory, one checked
tool bootstrap and one `setup` invocation. It then switches through actual
runtime SSH, reinitializes the public worksheet in that session, runs init-layout,
config/credential steps, validate/install and concrete HTTPS/status/journal
checks. Retry instructions name the account, retained state and exact repeated
block. No remembered shell functions, implicit exports, inferred dependency order
or required instructions from other documents are needed for this example.

Findings corrected during this walkthrough:

- Added the administrator login command; merely labelling a step "server" did
  not show a limited-experience reader how to reach it.
- Removed sudo from upload-directory creation. Staging untrusted inputs needs
  no privileged directory ownership operation.
- Credential conflict exits are confined to a subshell and print the public
  filename and next action instead of silently logging out the operator.
- PFX and PEM selection now happens once in the worksheet and drives both
  transfer and installation, in the same sequence. PFX no longer first demands
  the demo's PEM/user-password inputs; a runnable regression checks PFX placement,
  retention and safe mismatch diagnostics.
- The cache remedy reports a missing baseline setting rather than silently
  stopping at grep. The harness permits it only for that exact sole preflight
  failure and refuses unrelated failures.
- The HTTP harness gates require exactly 204/200, not just successful curl exit.
- Ordinary journal checks project only timestamp/unit/priority metadata; MESSAGE
  contents need not be displayed or shared to verify log access.
- Setup/retirement pipelines use pipefail, so a failed gzip cannot become an
  apparently successful empty Python invocation.

Command burden is measured as operator submissions/pasted blocks, separately
from internal automatic host actions. The guide has 19 uniquely named executable
blocks. Per ordinary task: upload-directory 1 command; tool bootstrap 1 pasted
command with its fixed Python body; host setup 1 pasted selection/invocation
block; runtime bootstrap 1 command; each component validate/install 1 block with
2 CLI commands; gateway public config 1 block with init-config, a fixed editor
snippet and private input-directory creation; each component credential import
1 fixed block; each endpoint check 1 command; status/log inspection 3 commands.
Transfers are one block per public/private delivery (two scp calls when Identity
is included). Login is 1 SSH command per role/session, followed by the same public
worksheet. The ordinary example needs 1 public worksheet edit, no manual edits
to Python/shell internals, and no password entry into command lines. These are
static procedure counts, not observed human performance or machine timings.

Tool/workflow simplifications implemented: one setup replaces manual key pinning,
per-bundle publication, journal creation and host-script invocation; init-layout
replaces manual bootstrap-file creation. Per-component runtime orchestration
remains 66. The fixed initial root bootstrap is still a substantial code block,
and external credential delivery still requires role/machine switches. These
are explicit usability risks to assess in the human trial; an approved OS package
can provision the trusted tool, but new package delivery is not claimed here.
A larger file or fewer pasted blocks alone does not establish easier operation.

The human trial is still **not performed / outstanding**. No time, mistakes or
questions are invented. The original assisted run remains evidence of difficulty;
it cannot approve this new manual. The focused SSH scenario is implemented but
unrun, and the full reboot/upgrade flow in 67 is still pending. Neither code review,
local tests nor this AI walkthrough establishes customer usability.

## AI literal walkthrough

Reviewed [docs/PRODUCTION-INSTALL.md](../docs/PRODUCTION-INSTALL.md) as present at
`7ef9671`, unchanged in this documentation work. Its SHA256 is
`794b8d42f0e996c0f469a9a81f7a2ab2ace8fb7e29ae78aec75803e311612d50`.
The target reader has limited Linux experience and no internal architecture
knowledge. No installation commands were executed. Starting assumptions are only
those stated in the guide: an OL9 server, listed packages/security services,
existing administrator and non-sudo runtime accounts, and the example product.
Do not silently assume that transfer artifacts, independent digests, certificates
or configuration values have already been obtained and assigned to shell variables.

The first blocker is step 1: it requires the operator to obtain and install the
authenticated release tool through README and use an undefined
`$nokkel_sha256`. The guide does not supply a complete artifact/substitution
checklist and executable sequence. The remaining rows are conditional reading
of later steps, not a claim to have executed past that blocker.

| Step/check | Finding from the literal procedure | Required correction/owner |
| --- | --- | --- |
| 1: prerequisites before changes | Packages/security state are asserted in prose, journal changes occur immediately, and the cache check can merely print an instruction and continue. The no-sudo check comes in step 2, after release publication. | 65: run preflight first, stop on missing prerequisites, give the exact remedy and continuation with account/machine. State any checks that necessarily occur after authentication. |
| 1: transfer and substitutions | Server and laptop actions share one code block; scp is commented out. `admin@server`, archive versions, digests and file locations are not all in the substitution table. The release tool is not in the shown transfer list. | 65: one complete delivery/value checklist, a consistent example and separate copyable steps for each machine/account. |
| 1–2: sequence and terminology | Tool bootstrap requires README; terms such as fapolicyd subject cache and independent key/tool hashes require interpretation to determine the next action. Detailed architecture appears before the executable path. | 65: put all required actions in the manual and define terms only as needed to act; move design detail to references. |
| 3–5: configuration and credentials | `vi` assumes editing/saving knowledge. Certificate paths are placeholders without a complete delivery step. STS publication must be reconstructed from platform's command; PFX password/provisioning steps require another guide. The external example's fields must be inferred. | 65: explicit public-value editing instructions, complete selected PEM/PFX path and exact per-component commands; 66: a public entry point that determines order and stops clearly for required input. |
| 5: installing several components | The guide tells the operator to follow the dependencies in `bundles.yaml`, rather than supplying the ordered procedure. | 66: execute the declared order through the documented install-set command; no manual dependency reconstruction. |
| 6: account switches and fresh sessions | The text says reboot checks run "without logging in" while showing sudo commands requiring an administrator session. After a new runtime login it uses the earlier `sms_podman` shell function without recreating it. | 65/67: say explicitly that only runtime login must wait, show administrator/runtime SSH transitions and use commands valid in a fresh session. |
| 6: expected results | Several commands have useful expected results, but the STS endpoint uses "expected status" instead of a concrete success criterion; the demo 404/200 alternative is described separately. | 65: one example with known endpoints and exact results for each step. |
| 7 and troubleshooting: failure/retry | A new login loses `release_tool`; upgrade relies on reconstructing step 1. "Correct the cause" and "inspect" do not always give an action and continuation command. Safe repetition is described for some commands, not the complete interrupted procedure. | 65–67: explicit recovery checkpoints, safe-repeat classification and next command, tested from a new process/SSH session. |
| Troubleshooting: sensitive data | The guide discourages some unsafe actions but provides journal/audit commands without a clear boundary for what diagnostic output may be shared. This review does not establish that those outputs contain secrets. | 65: bounded safe diagnostics for common failures; no requirement to show credentials or send unfiltered logs. |
| Overall command burden | The operator must coordinate multiple documents, role switches, transfers, shell functions and edits. A complete per-task command count cannot be established without inventing missing steps. | 65/66: consolidate setup/install and then measure commands/edits/switches for the complete written path. More explanation alone is insufficient. |

Conclusion: the AI assessment has findings under all relevant parts of the
operator checklist; some individual role labels, expected results and retention
notes are useful, but they do not make the complete path self-contained.
The new requirements are separate from the code-understandability review. No
claim about implementation correctness follows from this static walkthrough.

The 65 plan was adjusted in response: the canonical bootstrap is now part of
the one production manual, not a separate required procedure, and acceptance
must use the same bootstrap/setup and real SSH path. This is a planning fix,
not evidence that the current guide has been simplified. The final AI review
must be repeated against the actual implemented/manual revision.

## Human trial: outstanding verification

No qualifying unassisted trial was performed for this change. The
[2026-10-23 assisted manual run](PRODUCTION-LAYOUT.md#manual-run-as-produser-over-ssh-2026-10-23)
was useful evidence of difficulty and runtime behavior; it required step-by-step
help and does not count as a pass of the new human criterion. No completion time,
error count or participant experience is inferred from that record.

Arrange a fresh disposable test host at the manual's declared OS/account baseline,
with the documented delivery available. Give a person with limited Linux
experience the final manual and its single substitution sheet. The observer
records events without coaching. If the operator needs help, record the stop and
explanation; do not quietly correct state or convert an assisted run into a pass.

| Task | Required observations |
| --- | --- |
| 65: transfer, tool bootstrap, first setup and runtime SSH | Where each command is run, prerequisite diagnosis/remedy, time, errors, stops, command/edit/account-switch counts, ability to identify success without explanation |
| 65: repeat and interrupted setup continuation | Exact command chosen from the manual, retained work, ambiguity after a new session and any assistance |
| 66: install a set and supply public config/credentials | Whether order and required input are clear, no need to disclose secrets, successful repeat and continuation after a partial installation failure |
| 67: status/logs, logout/reboot, fresh SSH, upgrade and retire | Correct account/host at each step, readable service logs without sudo, startup before runtime login, retained config/credentials and clear completion criteria |

For each task record manual and code revision, host starting state, relevant
experience (without personal identifying details), start/end time, active time
and machine waits where measurable, actual commands/edits, error and stop events,
questions/explanations and final outcome. Record no passwords, private keys or
unfiltered secret-bearing output. Retest affected tasks unassisted after fixes.

Until this trial is completed, the report must continue to say **human operator
verification outstanding**. Automated first/repeat/interruption/SSH coverage and
its harness tests must be reported independently. Passing them cannot prove that
this manual is easy or quick for the target audience.
