# ci-lab

A standing repository for validations whose result is a set of readings: measurements that a design
depends on, checks of a toolchain or target row, probes of a platform, and checks of a consumer
against a change in another repository. It publishes nothing. Validations that produce artefacts
belong in [build-lab](https://github.com/speak-agent/build-lab).

`main` holds only these rules, the pull-request template and one guard workflow. No validation lives
on `main`; each one is a temporary pull request based on it.

## How a validation is run

1. Branch from `main` as `v/<yyyy-mm-dd>-<topic>`.
2. Add one workflow, `.github/workflows/<topic>.yml`, and the probes it runs under `probes/<topic>/`.
   Nothing outside these two paths changes.
3. Open a draft pull request titled `[validation] <question>` and fill in the template: the question,
   the decision it informs, the rows, and the criterion.
4. Push again only after every job of the previous run has finished, and keep only the jobs whose
   question is still open.
5. When the readings are recorded where the decision is made, list each run id and what it measured
   under "Runs", close the pull request without merging, and keep the branch, so that a record can
   cite the workflow at the commit that produced a reading.

## Resource rules

Concurrency is limited per account, not per repository: on the Free plan 20 jobs at once, of which at
most 5 run on macOS, shared by every repository of this account. The guard workflow checks the first
five rules on every pull request.

1. A validation workflow is triggered by `pull_request` or `workflow_dispatch`, never by `push`,
   `schedule` or a release.
2. It declares a workflow-level `concurrency` group that names `github.ref` or `github.head_ref`.
3. Every job declares `timeout-minutes` (at most 360). A step that can hang declares its own.
4. A pull request runs at most 3 macOS legs in total, across all of its workflows.
5. A macOS job does not use `actions/upload-artifact`: an upload that hung was cancelled together with
   the job's whole log. Readings go to the log and to `$GITHUB_STEP_SUMMARY`.
6. A cache key starts with the topic, so that two validations never restore each other's state.
7. No secrets are used, and nothing is published to another repository: no release, no index pull
   request, no mirror upload.

## How a probe reports

- Each reading is one line, `READING <id>: <value>`, written to the log and appended to
  `$GITHUB_STEP_SUMMARY`.
- A probe runs with `set +e` around the command it measures and records that command's exit status as
  a reading. A step fails only when the probe itself could not run, so that "the platform said no" and
  "the probe is broken" remain distinguishable.
- A reading names its row: runner image and version, toolchain and version, target.
- Compute a value into a variable before printing it; a `case` nested inside `$(...)` inside a string
  has truncated a reading before.

## What a validation does not do

It does not gate another repository's CI, and it is not a release channel. A reading that changes a
decision is cited by run id in the record of that decision.
