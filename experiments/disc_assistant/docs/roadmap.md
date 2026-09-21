# Disc Assistant roadmap

The software MVP is complete within its [accepted contract](reference/mvp.md).
Use [current status](status.md) for shipped behavior and evidence. This page
identifies future work; older implementation milestones are preserved in the
[design history](reports/2026-09-21-design-history.md).

| Workstream | Authority and next boundary |
| --- | --- |
| Physical acceptance | [Issue #23](https://github.com/eudj1n/snowsky-disc-qemu/issues/23). Preserve the original cohort, measure a separately identified candidate, then agree thresholds. |
| Speech quality and platform performance | [Issue #24](https://github.com/eudj1n/snowsky-disc-qemu/issues/24). Deferred; use identical frozen recordings for future comparisons and distinguish plumbing from accuracy. |
| Controller extraction | [Resolved quality review and remaining decisions](../../../docs/development/reports/2026-09-21-python-quality.md#remaining-repository-split-decisions). The package exists; a repository destination, publication and consumer versioning need a separate decision. |
| Future interaction/retrieval | Learned arbitration, semantic retrieval, fine-tuning, dialogue, compound planning, wake word/VAD and recommendations require separately agreed scope and evaluation. |
| Hardware | A possible dock is a later product direction, without present hardware or audio acceptance claims. |

Do not duplicate issue checklists here. Update the current status when behavior
changes and add a dated report when new evidence is obtained. A completed software
checkpoint does not automatically enable learned execution or broaden firmware support.
