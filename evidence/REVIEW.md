# Task 11 recovery-r4: implemented revision and three fresh pilots

R4 is implemented, packaged and run against three fresh strong-solver sessions. The reference passes all 185 cases in the validated verifier 0.7.3. All three final solver payloads pass the eight new focused checks. Two omit preserved-record inventories for unaffected and blocked studies; one completes the full profile. The three-cycle long-horizon target remains unmet.

| Attempt | Wall time | Full private result | First captured recovery, new checks | First captured 8/8 new checks |
|---|---:|---:|---|---:|
| 1 | 593.39s | 179/185 | 7/8 at 280.20s | 397.13s |
| 2 | 576.23s | 185/185 | 7/8 at 133.09s | 161.31s |
| 3 | 469.85s | 179/185 | 8/8 at 165.30s | 165.30s |

Intermediate scores are post-exit measurements, never solver feedback. They use the unchanged eight-case evolution profile in 0.7.2; final full scores use 0.7.3. An eight-case pass is not evidence of complete functional completion at that point. Wall time includes model latency and shared-host effects; three containers ran concurrently and these are not isolated performance measurements. Each requested gpt-6-astra at high effort with the same 1,200-second cap. All exited successfully without timeout, and all solver containers were removed.

## Revision and actual work

The same three live defects remain: numerical-projection input deduplication, scheduler reuse without dataset identity, and report collapse of distinct equal-dose bindings. The issue now reports operator symptoms. The recovery guide is 357 words and states product/interface guarantees instead of the old stepwise decision recipe.

The public checkout has 92 files and 29 Python modules. Candidate source is 2,300 physical lines; reference source is 2,387. The r3 reference was 2,351. The scientific model and dependencies are unchanged. The task adds three public resources: format metadata, recovery-ledger documentation and a partial consistency checker. It introduces no synthetic code-volume padding.

The supplied public database has 40 synthetic studies and the independent evolution fixture 48. Older fixtures remain in the full regression suite. New histories include:

| Mechanism | Actual solver obligation | Evidence and consequence |
|---|---|---|
| Retained codec compatibility | Propagate source codec into normalization and preserve original bytes | Legacy snapshot boundaries parse under current syntax but bind a different physical state; independent expected normalized inputs catch this |
| Partial prior recovery | Verify and adopt existing appended datasets; reconcile wrong queued pins without duplication | Preview provenance retains the mappings and original submission context |
| Later valid publication | Reconstruct older suppressed evidence while retaining later current evidence | New jobs, refresh/analyze/review, exact retries and subsequent imports exercise current selection separately from revision allocation |
| Journal order | Use durable history across misleading display clocks | Clocks are regression coverage, not a claimed primary horizon trigger |
| Stored-versus-live repair | Reconcile existing suppressed deliveries after fixing future operations | Public consistency diagnostics exercise actual database state |

The reference and all solvers keep historical datasets, runs, decisions and worker state. On the public database each solver actually recovers 18 studies, leaves 12 unaffected and blocks 10. They append 20 datasets, reconcile 24 delivery links and move 24 waiting jobs, adopting four existing preview datasets. Their support for safely retained later direct imports is a valid extension of the conservative reference, which blocks four additional studies. Different counts are not automatically wrong.

## Decisions missed and repair cycles

The predeclared strict cycle requires execution contradicting an implemented semantic decision, followed by a repair to that decision. No additional execution-forced semantic cycle is established in these trajectories. Each has one broad initial investigation/repair episode. None demonstrates the requested three cycles.

| Trigger | Attempt 1 | Attempt 2 | Attempt 3 |
|---|---|---|---|
| Live fix alone leaves stored damage | Anticipated | Anticipated | Anticipated |
| Codec compatibility | Anticipated before migration | Anticipated before migration | Anticipated before migration |
| Adopt partial recovery and repair pins | Anticipated; temporary repeat-provenance error later corrected | Anticipated; temporary repeat-provenance error later corrected | Anticipated |
| Preserve later current evidence | Anticipated | Anticipated | Anticipated |
| Journal ordering | Anticipated | Anticipated | Anticipated |

Attempts 1 and 2 initially score 7/8 on the new checks because repeat validation can reject an already recovered study after publication pointers move. Their later snapshots score 8/8. The trace shows those edits before an execution failure demonstrating that contradiction; they are latent intermediate errors corrected proactively, not credited execution-driven cycles. Attempt 3's first captured recovery already scores 8/8.

The only recorded failing self-authored pytest invocation is attempt 2's assertion that no backup WAL sidecar exists after opening the backup. It replaces that assertion with a stronger standalone-file readability check. This is a test-assumption correction, not a recovery-decision miss. Git-status errors arise from the deliberately history-free checkout and do not count either.

The genuine final omission in attempts 1 and 3 is reporting: each public report lists 18 of 40 preserved runs and 18 of 40 review decisions. Twelve unaffected and ten blocked studies have empty preservation inventories. Database records remain intact. Six full-profile failures share this single cause; do not describe them as six distinct missed decisions or as lost scientific provenance. Attempt 2 lists all 40 correctly.

An unprivileged, network-disabled read-only probe reproduces those counts in `report-inventory-probe/results.json`. Report-only changes on separate author diagnostic copies pass the affected nine migration and eight evolution checks. Those copies receive no solver credit and never replace the frozen final payloads.

## Verifier fairness and validation

The original 0.7.1 verifier and receipts remain preserved. An independent reader found inherited constraints that r4's public goals no longer supported: forced blocking of later direct imports, a specific publication-order allocation of consecutive revisions, and forbidding additional truthful first-apply audit events. Version 0.7.2 accepts safe alternatives while preserving content, pin, backup, repeat and historical-state checks. Three actual alternative implementations each pass the affected 17-case battery in both 0.7.2 and validated 0.7.3.

Final pilot grading then exposed an incomplete inherited scheduler fixture: it inserted a dataset without an import/publication event, yet expected it to become current. That is not a valid test of r4's journal-based current selection. Version 0.7.3 creates the corrected revision through the real import API. This failure is excluded from solver misses. Full final scores above come from actual fresh 0.7.3 executions, not edited or merged receipts. These disclosed calibration corrections limit any claim of preregistered difficulty measurement; the public task and solver workspaces never changed and no private feedback reached the solvers.

Focused deliberate wrong-design controls reject current-parser-only recovery, skipping prior recovery, duplicating prior recovery, revision-based current selection, timestamp ordering and live-only repair. An alternative recovered-ID implementation passes. Those negative controls are bound to their eight-case 0.7.1 receipts; they are not presented as full-suite results. The reference passes both the original release and the validated full profile. The reference patch reconstructs every reference file.

## Evidence and disposition

- `calibration-plan.json`: prospective cycle definition and run protocol.
- `trial-01` through `trial-03`: exposure probes, CLI traces, commands, source states, untouched final payloads and answers.
- `trial-*-validated-receipt`, `trial-*-validated-grade.json`: full final grading and explicit human-review limits.
- `state-results.json`, `state-receipts`: post-exit focused snapshot scores.
- `independent-contract-review.md`, `verifier-correction.json`, `scheduler-fixture-correction.json`: independent review and disclosed corrections.
- `frozen-release.json`, `validated-verifier/frozen-verifier.json`, `posttrial-bindings.json`: exact task and verifier bindings.

Exposure audits show no private paths available or forbidden command mentions. Authentication stayed ephemeral in the solver runtime. Model network traffic was not audited. The original r3 task, user-edited review and its before-copy are preserved.

R4 is a runnable repair-and-migration exercise with real verifier discrimination and observed report omissions. The new core mechanisms were handled before they forced additional repair cycles. Keep its long-horizon status provisional; a sub-100-percent full pass rate caused by report incompleteness does not establish the intended difficulty. The maintained application now matches all 29 reference modules and passes its 43 public tests. Human maintainer acceptance remains pending. No GitHub upload occurred.
