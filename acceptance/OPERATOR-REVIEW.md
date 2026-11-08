# Operator review baseline for backlog 65–67

## Backlog 68 trial procedure: AI verification on the lab VMs (2026-11-08)

An AI agent ran the trial procedure in [backlog 68](../BACKLOG.md#68-human-operator-trial-on-a-fresh-vm)
on `c5bab2f`: the delivery built on DEV, two ISO media attached to PROD as a
CD (`/dev/sr0`), PROD from `clean-agent` with `produser` created and
`subj_cache_size = 4099` left as found. It typed the manual's commands over
SSH with a pseudo-terminal (not the console from paper), answered the
prompts, edited `fapolicyd.conf` with `vi`, and followed the manual's rule
after Ctrl+C. **This verifies the procedure, not an operator: it is not the
human trial.**

| Task | Result |
| --- | --- |
| Find and mount the medium (`lsblk`, `mount`, `ls`), both media | passed; `sr0`, type `rom`, by size |
| Tools with `dnf` | passed |
| First `myproduct-admin`: preflight stop on `subj_cache_size`, fixed with `vi` (`/^subj_cache_size`, `cc...`, Esc, `:wq`) and the restart, then a full run | passed |
| Unchanged repeat, credentials, `umount` | passed |
| Runtime user in a fresh SSH login, first `myproduct` with Ctrl+C during platform's install, then `myproduct` again | completed; HTTPS 200 (`/help/`, checked with the delivery's CA) |
| Status, upgrade to help 0.4.14 from the second medium, retirement of 0.4.13, journal, reboot and `myproduct` in a fresh login | passed; HTTPS 200 |
| Setting change, tools repair, credentials with `scp` | not run |

Findings and what followed:

1. Ctrl+C printed two Python tracebacks (product). Fixed in `40b37c4`: a
   short `ERROR: Interrupted; run the same command again to continue`.
2. `[OK]` lines from `init-layout` and `init-config` asked for steps that
   `myproduct` does itself (product). Fixed in `40b37c4`.
3. Repeated `myproduct-admin` printed firewalld's `Warning:
   ALREADY_ENABLED` (product). Fixed in `40b37c4`.
4. The procedure's own defects (CA key on the medium, `grep` without
   `sudo`, unclear cross-references) were found and fixed during the runs;
   [backlog 68](../BACKLOG.md#68-human-operator-trial-on-a-fresh-vm) has the
   corrected procedure.
5. The lab token may not change a VM's CD (`VM.Config.CDROM`, HTTP 403); the
   observer swaps the CD in the Proxmox web UI.
6. Open finding 3 below stays: the manual says to change the line and save
   but gives no `vi` keys.

Not measured: time per task (the agent recorded estimates only). The
`40b37c4` fixes have local tests; no lab run yet.

## Backlog 69 WP5: AI walkthrough of the RPM manual (2026-11-07)

Manual: [docs/PRODUCTION-INSTALL.md](../docs/PRODUCTION-INSTALL.md), SHA256
`4bc9ab08b770646231ee87e8b3ffd512d1f4d88c4f8f715cf9640482b14201a4`, on the
RPM branch (backlog 69 WP1-WP6). WP6 added step IDs for the lab, the `/mnt`
row of the example table and blocks for the `scp` alternative and the tools
reinstall, which were inline text, and the note and stop row for delivered
credentials of an installed component (`myproduct <component>`, found by
the first `--rpm-manual` runs); the commands, counts and findings below are
unchanged. This replaces the `release.py` manual for
operators; WP6 removed that procedure with the `release.py` flow (last in
`fd3a311`). The sections after this one are historical and
refer to that earlier manual.

| Assessment | Result | Scope |
| --- | --- | --- |
| AI literal walkthrough | Findings; seven fixed in this change, five open (below) | First installation, credentials, upgrade, retirement, status/reboot, setting change, interruption and the stops table, tools repair |
| Human trial without oral assistance | **Not performed; outstanding verification** (backlog 68) | Printed manual only, fresh OL9 VM, one person holding both accounts, console and SSH variants |
| Product/unit tests | `test_manual` (commands parse with the real parsers, prompts are the tools' questions, cited sections exist, the admin "next" line) and the existing admin/runtime tests | Drift between manual and tools; not the procedure |
| Real lab evidence | `rpm-manual-3bff57b` (P1) and `rpm-manual-p2-3bff57b` (P2) ran every executed manual block literally, with typed answers and a real SSH login, including the stops, an interruption, upgrade, retirement and the tools repair | Not mounting a medium or `umount` (the lab copies the delivery to a directory) |

Method: static reading of the manual from its stated prerequisites, in
order, without filling gaps from source code or earlier chat; the expected
lines and messages were then compared with the tools' code. No command was
executed on a host for this walkthrough.

**Counts** (typed characters include Enter; the example values; accepting
every suggestion):

| Task | Commands | Typed characters | Account switches | Medium |
| --- | ---: | ---: | ---: | --- |
| First installation on a new server, two roles | 10 | 282 | 1 | mount, umount |
| Upgrade with a new delivery, no new credentials | 8 | 137 | 1 | mount, umount |
| Remove old releases right after an upgrade | 5 | 89 | 0 | mount, umount |
| Status check, also after a reboot | 1 | 10 | 0 | none |
| Fix the fapolicyd cache stop, then repeat step 3 | 3 + a `vi` edit | 97 + the edit | 0 | none |
| Tools repair (same version), then repeat step 3 | 3 | 144 | 0 | mounted |

Manual edits: none for ordinary tasks; one `vi` edit to change a setting or
for the cache stop. If the public-address suggestion is wrong, typing it adds
about 32 characters. The longest line is the tools reinstall (92 characters
before Enter); the one-time tools installation is 90, both with `'*'`. The
`scp` alternative is one command of 74 typed characters including Enter, run
from the laptop folder that holds the delivered component folders; no
complete `scp`-based task is counted here, and its account switch is the
laptop login, not the one in the table. For comparison, the `release.py` manual's operator
blocks were 8 811 characters in 186 lines, mostly pasted, for platform and
identity; the RPM manual's counts do not grow with the number of components.

**Findings fixed in this change:**

1. `prepare-host.sh` printed `[OK] next, as <account>: create
   ~/.<product>/<product>.env ...`, a manual step that `<product>` now does
   itself (`init-layout`); an operator would have created the file by hand.
   Removed.
2. The admin command's last line named the releases directory but not the
   command to run; it now ends `and run <product>`, as the manual shows.
3. `<product>` sent the operator to "the troubleshooting section of the
   manual", which does not exist; it now names "If a command stops", and the
   stops table has its row (`status reports an incomplete or inactive
   component`).
4. Messages name the system, security and account administrator, roles the
   manual did not define; "Who does what" now does.
5. The prerequisites did not say that the runtime user must know how to log
   in (password or SSH key).
6. `mount` on a medium that is already mounted prints an error; the manual
   now says to continue.
7. Step 3 gave no expectation of duration; it now says large releases can
   take several minutes. The root and wrong-account messages of `<product>`
   share one row in the stops table.

**Review follow-up (2026-11-08)**, from the code review of `b435bec`: the
`scp` block now says which laptop folder it runs in; an upgrade without
credentials still unmounts the medium; "already mounted" continues only when
`ls /mnt` shows the delivery; the "older releases kept" row names the
administrator and what to do when it repeats; a release folder without its
package stops every later step 3, and the tool and the manual both say to ask
the supplier before deleting anything. The counts above are unchanged except
where stated.

**Open findings (not fixed here):**

1. Finding the medium with `lsblk` needs judgement (size, `sdb1` versus
   `sr0`). Remedy candidate: the supplier labels the medium, and the manual
   shows a sample `lsblk` output.
2. The one-time tools command is 90 characters with quoting and a glob;
   phase 2 adds key import. Mistyping is safe (dnf stops) but likely.
3. Changing a setting needs `vi` and YAML (`config.yaml`), beyond the target
   audience. Decided on 2026-11-07 (product owner): it stays the documented
   `config.yaml` edit; no setting command is built now (known gap, item 69).
4. "Install the named package from the OS media" assumes the system
   administrator can do that offline; the manual only declares it as that
   person's prerequisite.
5. Mounting a medium and `umount` were run on a host only by the AI
   verification of the trial procedure (2026-11-08, above), not by a
   person. The typed prompts, the tools repair and a real SSH login running `myproduct`
   passed in `--rpm-manual` (WP6).

Interruption/retry trace: every numbered step is safe to repeat. `dnf install`
of installed tools does nothing, the admin command installs only what is
missing and repeats host preparation idempotently, `--credentials` keeps
identical files and refuses different ones before copying, and `<product>`
resumes the pending component first. A failure names who acts and the
repeated command. Diagnostics to share are the printed `[OK]`/`WARNING:`/
`ERROR:` lines and `journalctl -t myproduct` (start and result lines only).

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

Result: **findings; customer usability is not established**. The earlier claim
that no execution steps were missing was too strong. Review at `15f6e4b` found
that manual failure behavior differed from the harness and that host diagnostics
could hide the corrective action. The targeted fixes below have local regression
evidence; that does not establish that all operator steps or failure cases are
resolved. This assessment combines static walkthrough with local manual-block
tests, not a successful real-server run or human approval.
The guide reviewed at `2d36d71` had SHA256:
`953744f079c6846cc9fb27936f07cee7790ac65019765986298dd42373a7cb14`; implementation branch `feature/65-host-setup`,
based on `f52b797`. The earlier table and literal walkthrough below are a
**historical baseline** against `7ef9671`, not a claim about the rewritten guide.
Current local evidence is in `acceptance/HOST-SETUP.md` (removed in WP6; in git history at `fd3a311`).

The literal path now starts with a complete trusted delivery/value checklist,
explicit administrator SSH, private unprivileged upload directory, one checked
tool bootstrap and one `setup` invocation. It then switches through actual
runtime SSH, reinitializes the public worksheet in that session, runs init-layout,
config/credential steps, validate/install and concrete HTTPS/status/journal
checks. Retry instructions name the account, retained state and exact repeated
block. No remembered shell functions, implicit exports, inferred dependency order
or required instructions from other documents are needed for this example.

Review follow-up at `15f6e4b`:

- The pasted gateway config block now stops on init-config failure before any
  config edit or credential-directory creation. Transfer/status blocks also own
  their failure handling. Harness worksheet setup and SSH no longer add stronger
  shell options; the literal-block regression executes plain Bash and verifies
  unchanged existing config after failure.
- Interrupted init-layout no longer publishes an empty final file. The same
  runtime command retries from a new process; any partial temporary file is not
  used. Existing valid files and concurrently published settings are retained.
- Host-script failures expose fixed phase/reason/action diagnostics. For example,
  overlapping subordinate IDs direct the administrator to resolve /etc/subuid and
  /etc/subgid safely, then repeat the manual's setup command. Unknown/private
  child output is withheld rather than becoming shareable diagnostic text.

These address the three concrete review findings. The success and interruption
paths were re-traced: explicit administrator preparation precedes runtime login,
manual blocks stop themselves, and retry uses retained state. Broader difficulty,
correctness of the real host flow and human comprehension remain open.

Findings corrected during the original walkthrough:

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
it cannot approve this new manual. After the first preflight failure at `8559a2a`,
all nine corrected-flow scenarios passed at `2d36d71`
(lab evidence in `acceptance/HOST-SETUP.md`, removed in WP6; in git history at `fd3a311`).
The full reboot/upgrade SSH flow in 67 is still pending. Neither code review,
local tests nor this AI walkthrough establishes customer usability.

## English-only repository follow-up (2026-10-24)

The repository language is English, including code identifiers, comments,
filenames, documentation and diagnostics. This requirement is now explicit in
`AGENTS.md`. The production manual and Norwegian backlog task text were translated;
historical task requirements, status, item headings, inline code references and
fenced examples were preserved. The operator's quoted feedback is labelled as
a translation. Unicode fixture data uses escapes with unchanged Python values.

The translated guide SHA256 is
`c00ccf7260e260752b583faa4042bf74f0adb174160454fedfa935febd8f1020`.
Comparison against `2d36d71` confirms all 19 operator step IDs and executable
blocks are unchanged apart from English placeholder/error text. All 20 shell
blocks pass Bash syntax checking. The same machine/account transitions,
prerequisites, failure stops and retry rules remain in the English procedure.
The literal manual failure/credential regressions run against the translated
blocks; no new operator flow or runtime behaviour is introduced.

Local verification: 94 focused product tests and all 266 acceptance-harness tests
passed. Changed test formatting/lint, relative links and `git diff --check` passed.
These are local results. The supplied nine-scenario lab series passed on
`2d36d71`, before this translation; it does not establish human usability of
the English manual. No lab run or VM reset was performed for the translation.
Unassisted human verification remains outstanding.

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

Tracked explicitly by [backlog item 68](../BACKLOG.md#68-human-operator-trial-on-a-fresh-vm).

No qualifying unassisted trial was performed for this change. The
[2026-10-23 assisted manual run](RESULTS.md)
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
