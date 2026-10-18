# Engineering and scientific decisions

## Scientific context

The screening workflow connects assay interpretation to provenance rather than treating a fitted potency as sufficient evidence. Plate-local vehicle and positive controls, sample-standard-deviation Z-prime checks, unclipped normalized inhibition, bounded four-parameter fits and conservative curve eligibility are documented in application/docs/scientific-methods.md. Counter and viability evidence remain unresolved when the data cannot support a clear interpretation. The local potency interval is an approximation with stated limitations.

Transfer reconstruction carries measured volume, solute amounts, operation revisions and ancestry through the physical sequence. Equal final concentrations can still have different source evidence or measurement bindings. That is why a numerical-projection cache key is insufficient for immutable scientific input identity. It is also why reports must retain every observation rather than grouping equal-dose wells away.

## Module boundaries

| Concern | Modules | Coupling exercised by this task |
|---|---|---|
| Parsing and source provenance | instrument_files, ingestion, ingest_resolution | Descriptor-selected decoding must agree at staging, publication and recovery |
| Physical reconstruction | transfer_history, dispensing, calibration | Corrections change contents, binding state and input identity |
| Persistence and review | database, repository | Immutable datasets coexist with allocation tokens, current evidence and historical acceptance |
| Recoverable analysis | jobs | Dataset identity, queued pins, worker leases, staged results and publication fencing |
| Recovery | recovery | Evidence validation, prior progress, safe planning, backup and atomic apply |
| Export | reporting | Consistent snapshots and complete per-well JSON/HTML/CSV evidence |

## Container boundaries

The application image is a small non-root Python runtime. Hash-pinned dependencies and a digest-pinned base make its inputs explicit. No compiler toolchain is shipped. The verifier image has a different role: a protected supervisor runs checks while candidate commands execute under separate unprivileged UIDs. Its runtime has no network and receives a read-only copy of the candidate plus a protected receipt volume. The Docker socket is never passed into candidate execution.

SQLite is the actual database for this application. Transactions and durable journals provide the recovery semantics being tested. The repository does not present this local-file security boundary as a distributed or multi-user service.

## Verifier design and review

The checker compares full reconstructed inputs, fingerprints, state transitions and command results. It tests both preserved state and changed state, including failure/rollback paths. Deliberately incomplete designs are rejected by focused checks; alternative ID choices, allocation orders and valid recovery policies are not forced to imitate the reference.

An independent contract review corrected inherited assumptions that no longer followed from the public task. A scheduler fixture was repaired to establish new evidence through the real import API. Those corrections are retained alongside the calibration evidence, so an artificial grader failure cannot be mistaken for meaningful agent difficulty.

Passing 185 cases establishes the tested behavior, not universal correctness, production deployment or percentage coverage. The three solver attempts demonstrate real task execution and a report-completeness omission; they do not establish the intended three-cycle horizon.

CI uses `ubuntu-24.04-arm` to match the recorded Linux ARM64 execution architecture. GitHub documents this standard runner for private repositories in its [hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
