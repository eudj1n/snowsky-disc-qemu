# ADR 0001: component and documentation ownership

Accepted by the owner on 2026-09-21. Implemented as three sequential PRs:
experiment boundaries, document ownership, then editorial consolidation.

## Context

`research/` mixed firmware-analysis tools with runnable application projects.
Root `docs/` held 69 flat Markdown pages, including 25 Assistant pages; several
status documents combined current contracts with superseded plans and dated runs.
Controller may later move to its own repository, so its manuals need a clear owner.

## Decision

- `research/` owns Ghidra and diagnostic investigation tools. `experiments/` owns
  independently launched browser, diskOS and Assistant projects. Component tests
  follow their owner; cross-component acceptance remains under `tests/`.
- A README records each experiment's maturity and verified scope. Directory
  placement alone does not promote support. NLU remains an Assistant subsystem;
  offline evaluation is separate from runtime interpretation and locale templates.
- Component manuals live in that component's `docs/`. Root `docs/` owns shared
  protocol facts, repository architecture, development policy and decisions, with
  one index connecting all owners. Shared curated screenshots remain in `docs/images/`.
- Controller owns its API/setup/bridge documentation; shared wire evidence stays
  in `docs/protocol/` and research reports. Copy Controller code, tests, license
  and owned manuals when extraction is separately agreed. No reverse application
  dependency or package publication is introduced by this layout.

## Document lifecycle

| Kind | Maintained purpose |
| --- | --- |
| Component README | Scope, maturity, minimal start and navigation; avoid duplicating the manual. |
| Guide | Current task instructions and examples. |
| Reference / architecture | Current contracts, configuration, ownership and rationale. |
| `status.md` | Current capabilities, limits, pause conditions and links to evidence. |
| `evaluation/` | Reproducible methods, cohorts and scoring boundaries. |
| `reports/` | Dated findings, source revisions, successes, failures and acceptance evidence. |
| Issue | Actionable backlog, discussion and completion checklist. |
| ADR | An accepted cross-component decision and its consequences. |

Use these subdirectories when the component needs them; do not create an empty
hierarchy for a one-page manual. Use descriptive lowercase hyphenated filenames.
Each maintained fact has one canonical owner; indexes link rather than copy it.
A guide can briefly state a contract's practical effect and link to its authority.

Dates on reports describe the evidence/checkpoint or explicitly identified
archival snapshot. Preserve candidate IDs, failures, disputed gold and scope.
Historical “next steps” do not authorize work or override current pause conditions.
Keep accepted aggregate/corpus payloads byte-identical during structural changes;
repair documentation navigation without rewriting measurements.

## Consequences and checks

Source moves update imports, resource paths, launchers, build contexts, CI test
inventory and isolation checks together. Document moves update local links and
AGENTS guidance. Local target checking runs as `python3 -m ci.docs` in CI;
when sections move, preserve their headings in reports and retarget deep links.
Git history retains former document paths; do not maintain duplicate live manuals.

The three PRs do not change firmware/protocol behavior, service bindings, Docker
identities, private data locations or acceptance policy. Root launcher and Docker
ownership are explicitly deferred to [issue #29](https://github.com/eudj1n/snowsky-disc-qemu/issues/29).
See [validation](../development/reports/2026-09-21-repository-refactor.md).
