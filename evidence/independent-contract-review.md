# Independent affected-scope contract review

Reviewer: `/root/r4_contract_review`, an independent Codex subagent that did not author these tests. Actual model override was not requested or supplied; the tool did not expose a separate resolved model identifier. This is a source review, not an executed correctness or difficulty gate. No tests, fixture generation, model pilots or application commands were run by this reviewer.

Scope: candidate ISSUE and recovery/interface/ledger/instrument profile documents; public consistency checker; fixture builder; evolution verifier; inherited recovery verifier and called migration helpers; relevant parser, ingestion, repository and job selection code; runner and source transfer configuration.

## Finding requiring disposition before calibration

`reference/src/truegate/repository.py` now permits `latest_dataset` to select an older allocated revision via a completed recovery event, which correctly addresses the mixed-publication case. However, `show` exposes the maximum allocated revision as `current_revision` (line 139), while `review` requires the selected dataset's own revision (line 121). In a mixed study the valid current delivery can remain revision 2 after an older delivery is reconstructed as revision 3. A client that refreshes show, analyzes the current dataset, then submits a review using the exposed current revision receives a conflict despite no intervening mutation.

The new evolution test exercises a real new job submission, so verifies current evidence selection, but does not exercise show → current run → review. Decide and document whether review uses the allocation/concurrency token or the selected dataset revision, make the reference interface coherent, and add this real client sequence. Retain the maximum allocation token for ingestion concurrency as required. This is a reference compatibility issue and a missing regression, not an observed solver failure.

## Forward mapping of changed obligations

| Obligation enforced by evolution tests | Public basis | Assessment |
| --- | --- | --- |
| Legacy exclusive boundary converts to inclusive normalized binding | `docs/instrument-profiles.json`: boundary minus one and codec selection from source descriptor | Derivable without hidden format convention. |
| Reject unsupported retained codec rather than guess | Profiles enumerate supported codecs; evidence recovery requires a unique safe result, otherwise blocked | Supported. |
| Preserve later valid publication as current | Evidence recovery explicitly says a later valid publication remains current when older evidence is reconstructed | Supported; checked through job submission, preserving implementation freedom. |
| Correct waiting-work pins by original submission context | Evidence recovery says queued work must use evidence available at submission; ledger declares journal authority | Supported. |
| Adopt verified partial revisions without duplicating them | Ledger specifies preview schema and adoption of matching revisions; recovery says not to undo valid earlier progress | Supported. |
| Preserve staged/completed work and existing raw evidence | Evidence recovery preservation paragraph and produced-result rule | Supported. |
| Backup, dry-run purity, semantic plan agreement and idempotence | Evidence recovery interface and repeated-run clauses | Supported. |

The fixture oracle constructs expected normalized records and transfer history from the original in-memory records before legacy encoding, including exact source bytes and manifest. It does not derive expected historical binding contents from the recovery parser. This gives the legacy drift assertion an independent expected value. It remains a synthetic construction, not evidence that real instruments use this interchange format.

## Reverse mapping and limits

The new tests directly check recovery outcomes for supported legacy, partial progress, mixed publication and unknown codec cases; current selection via new work; preservation; repeat safety; and backup/preview semantics. They do not newly verify every existing documented interface guarantee. In particular, mixed-study review concurrency needs the regression above, and this reader has not certified all inherited tests or arbitrary future mutations after a completed recovery.

The public checker honestly describes itself as partial and returns violations separately from unresolved studies. Its independent legacy normalization makes a mis-threaded descriptor observable even when the application's first parse succeeds. Its exit status only reflects definite violations; callers must also inspect unresolved entries. It is not an acceptance oracle.

The candidate already contains the legacy conversion in `instrument_files.parse`; its ingestion/resolution callers omit the codec descriptor. A capable reader can find and repair that propagation statically. Thus codec drift can cause an execution-discovered contradiction, but no claim that it necessarily forces an additional repair cycle is justified before pilot trajectories are inspected. The ledger deliberately states timestamp authority; clock skew is chiefly regression coverage here.

This review does not certify the full skill extraction/checker gate, numerical path-stress execution, frozen byte bindings or pilot readiness. Those were outside the delegated read-only, no-test scope and must not be reported as passed by this note.

## Disposition after reference repair

The reference now checks the supplied review revision against the campaign's maximum allocated revision, agreeing with `show.current_revision`, while independently requiring the reviewed run to belong to the selected current dataset. This resolves the concrete mismatch identified above without making the older reconstructed evidence current.

`test_mixed_history_refresh_analyze_review_and_subsequent_import` exercises the actual client sequence: refresh show, analyze, review with the exposed token, repeat the exact current input without losing the review, import changed input to retire that review, and submit new work against the changed input. Read-only inspection confirms that the assertions cover the identified failure and subsequent current-selection behavior. The parent reports 8/8 focused checks passing in image `0.7.1`; this reviewer did not execute or independently inspect those receipts.

No remaining changed-scope blocker was found in this follow-up. Minor wording tension remains between the older architecture document's phrase "revision they inspected" and the recovery guide's explicit statement that allocated revisions are concurrency tokens independent of evidence age. The existing show-returned token and the latter rule make the tested refresh flow derivable. A future editorial clarification can explicitly name `show.current_revision` as the review token, but should preserve this interface guarantee rather than prescribe a recovery algorithm.

## Extended inherited recovery contract review

This extension independently reads all of `checks/test_15_recovery_migration.py`, its called helpers and the original fixture builder against the rewritten r4 documents. It does not inspect solver trajectories or results. It supersedes the earlier limited no-blocker statement for the expanded scope.

### Blocking carryover: later direct input

The inherited `later_direct` construction is a suppressed, completely retained second delivery followed by an ordinary successful import. The imported replacement changes a recorded signal and has its own complete immutable dataset and ordinary `imported` journal event. The earlier queued job has its submission event before this direct import. The builder marks this case blocked solely because the r3 recovery policy excluded later direct imports, not because its evidence is damaged.

Under the r4 public contract, a valid implementation can reconstruct the earlier suppressed delivery, point its session and pre-import waiting work at the reconstructed input, preserve all existing evidence and completed work, and leave the later direct input current. Current selection can be derived from journal order and existing immutable dataset identity. No new physical interpretation is needed. The r4 guide no longer states that this history must be blocked, and the generic unique-safe-result clause does not impose that exclusion.

Nevertheless `check_plan` requires `blocked` for every case whose old oracle has `blocked: true`. This rejects the valid implementation above, including dry-run and follow-up apply assertions. The public checker's decision to return this category as unresolved is an explicit limitation of a partial diagnostic, not a binding instruction that the implementation must decline recovery. This inherited policy needs a new r4 disposition before interpreting results as solver failures. Prefer a behavior-based check permitting safe recovery with preserved later direct current evidence; if a deliberate exclusion is retained, disclose the exact support boundary as a policy rather than calling the existing evidence ambiguous.

### Other inherited recipe constraints needing disposition

1. `assert_apply` requires recovered dataset revisions to equal `previous + offset`, where offset is the old oracle's session publication order. The r4 guide states monotonic allocated concurrency tokens and explicitly separates them from evidence age. It does not require consecutive allocation or publication-order allocation. A solution can allocate two missing historical datasets in another deterministic order and still select current evidence and pin all jobs correctly. Test revision uniqueness, new allocations above the prior allocation maximum, and stable preview/apply mappings; do not demand the author's allocation recipe unless made an intentional public interface requirement.
2. `assert_apply` requires exactly one new event per recovered study and every new event to be the completion action. The public guide requires a durable completion event per reconciled study, preservation of existing events, and no duplicate events on repeats. It does not forbid additional legitimate first-apply audit events. Requiring exactly the completion event and no others is an inherited internal layout constraint. Check one valid completion event per recovered study and no duplicate changes on repeat; evaluate additional events for truthful audit content rather than rejecting them categorically.

### Remaining test15 forward/reverse obligation inventory

| Test/helper obligation | Public derivation or disposition |
| --- | --- |
| Every campaign appears once; version and report fields | Recovery command emits studies with campaign entries and fixed version; duplicate/missing campaigns cannot represent the requested study reconciliation faithfully. |
| Recover complete suppressed deliveries; healthy studies unaffected | Reconcile retained deliveries while preserving existing evidence and valid progress. |
| Block missing raw bytes or missing queued submission context | Preserve source integrity; do not invent missing provenance; admit only uniquely determined safe results; journal is authority. |
| Block every later direct import | Unsupported r3 policy carryover, as detailed above. |
| Session and waiting-job report mappings agree with actual repair | Specified mapping fields, retained evidence identity and report/execution agreement. |
| Preserve run and decision mapping lists, with `action: preserved` | Explicit output schema and preservation rules. |
| Preserve campaigns, existing datasets, jobs outside allowed pins, source bytes, attempts, events, completed worker state | Explicit preservation and produced-result guarantees. |
| Reconstructed content and canonical hash match retained input | Full evidence identity, retained bytes and integrity records, documented input canonicalization. |
| One additional dataset for each unique suppressed complete input in these fixtures | New immutable corrected evidence and no duplicated valid progress. Exact counts are justified for these no-prior-progress fixtures, subject to the later-direct classification correction. |
| Allocate consecutive revisions in publication order | Unsupported allocation recipe carryover, as detailed above. |
| Clear current review after current evidence changes | Correction lifecycle and current-review identity; these ordinary recovered cases have no review of recovered input. |
| Exactly one completion event and no other new audit events | Completion event required; forbidding other legitimate audit records is unsupported. |
| Scheduler identity includes dataset, policy and engine | Durable job protocol explicitly defines that submission identity. |
| Export distinct equal-dose wells and complete transfer bindings | Recovery guide requires distinct report rows; transfer-history evidence/export contract identifies record-level rows. |
| Dry run has null backup and no writes | Explicit recovery interface. |
| Readable consistent backup equals logical pre-apply state | Explicit consistent independent backup requirement. Logical state comparison permits SQLite header differences. |
| Preview/apply agree except unreserved target IDs | Explicit semantic agreement and no preview ID reservation. Tests compare mapping content and hashes. |
| Repeat reports prior mappings and already-recovered status, with no mutations | Explicit recovery repeat contract. |
| Parsed cache mutation and timestamp changes cannot redirect recovery | Derived caches may be stale; journal is durable ordering authority. |
| Missing or existing backup fails without mutation | Explicit new-destination apply requirement and atomicity. Contract-error exit 2 follows retained CLI error documentation. |
| Triggered mutation failure rolls back, preserves pre-apply backup, and a clean retry succeeds | Explicit whole-apply rollback and pre-mutation backup requirement. |
| Compute/publish repaired jobs retain their own historical transfer state and export original input | Queued evidence at submission, pinned jobs and historical evidence/export contracts. |

This expanded review identifies real instruction-to-verifier issues even if the author reference passes. It makes no claim about any solver's behavior. Resolution must be versioned and frozen before an unqualified r4 calibration result is published; previous receipts remain historical evidence for their tested contracts.

## Disposition of separately versioned verifier correction

Read-only review of `corrected-verifier/checks/test_15_recovery_migration.py` and `verifier-correction.json` confirms that the three inherited constraints have been relaxed in the intended directions. The original public task and original verifier remain separately retained; the correction disclosure identifies the author exposure boundary and does not portray the repair as preregistered.

Safe later-direct recovery now receives the same normalized-input, fingerprint, session-pointer, queued-job and immutable-state checks as other recoveries. Its new waiting work must select the later preexisting direct dataset through the real CLI. Conservative blocked handling remains accepted. The corrected oracle supplies expected reconstructed input for each later-direct case; this reader inspected the five entries and confirmed nonempty mappings for their suppressed sessions. The changes therefore do not simply waive those records' correctness checks.

New historical revisions must match their reported revisions, exceed the prior maximum and be distinct within the repaired study. This removes publication-order allocation and consecutiveness as implementation prescriptions. Required completion events remain exactly one per recovered study, while other first-apply events are permitted. Existing datasets/events and worker/review evidence still receive the inherited preservation checks. Repeat handling now includes studies safely recovered despite the old later-direct blocked flag.

No new changed-scope overrestriction or blocking implementation error was found in these corrections. The fresh-job assertion is deliberately placed after preservation checks, so its intentional new job/event does not invalidate the pre-repair preservation comparison. The metadata's reported alternate-implementation passes and parent-reported full-reference work are not independently rerun or certified by this source review.

Remaining scope limit: allowing additional first-apply audit events does not independently prove that every such event's narrative is truthful. This is a general audit-completeness limit, not a reason to reimpose the discarded author-specific event layout. Calibration claims should continue to distinguish these corrected verifier results from receipts produced under the earlier frozen verifier.

## Additional inherited fixture and report classification

No solver traces or outcomes were inspected for this classification. The questions were checked against the frozen public text and the inherited scheduler fixture.

### Scheduler fixture currentness is incomplete

`test_scheduler_submission_identity_includes_the_dataset` directly inserts revision 2 into `datasets` with no corresponding ordinary import or publication journal event, then requires a new submission to choose that row. Although this matched the older maximum-revision selector, it is not a complete ordinary workflow under r4. The journal is now the durable ordering authority and allocation tokens need not describe evidence age. A valid implementation that uses journaled import/publication authority can leave the earlier genuine import current and decline to infer currentness from this orphan row. The task does not instruct it to repair this artificial non-journaled state.

The clean correction is to construct the changed revision through `client.import_data`, assert that the returned dataset is different from the original input, and require a distinct job pinned to that returned dataset. This preserves the actual scheduling identity obligation while removing the unsupported currentness assumption. If the intent is to isolate scheduler verification from import implementation, a low-level fixture must also supply the complete legitimate import journal provenance; merely giving the SQL row a larger allocation number is insufficient. Failure of the original orphan-row fixture is a verifier artifact, not independent evidence of a scheduler defect.

### Preserved-record inventories apply to unaffected studies

The report schema says each study entry includes `runs` and `decisions`, then specifically directs: "Preserve runs as `run`, `dataset`, `action: preserved`, and decisions as `decision`, `run`, `action: preserved`." This is a report-shape instruction, separate from the earlier instruction to preserve database rows. The natural interface interpretation is an inventory of the existing records preserved for each reported study, including unaffected studies with direct-import-only provenance. "Blocked and unaffected entries have empty changes" does not turn their existing runs and decisions into changes or remove those inventory fields' meaning.

Accordingly, returning empty inventories for a study that has existing runs and decisions is an incomplete preservation report under the stated interface. It is distinct from losing, modifying or repointing those underlying database rows. Report the defect narrowly; do not inflate it into destroyed provenance, failed scientific reconstruction or evidence of additional repair cycles.

The public wording does not literally say "all" existing runs and decisions, which leaves a small editorial ambiguity. A future public revision should explicitly say that preserved inventories include unaffected and blocked studies while change mappings remain empty. That future clarification cannot be used retrospectively as additional evidence for the present contract. This review's classification rests on the existing named inventory fields and explicit preserved-item representation.
