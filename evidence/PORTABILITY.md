# Evidence portability

Receipts, solver final payloads and application source states are preserved from actual runs. Original local workspace names in historical narrative refer to the Task 11 R4 calibration workspace. The primary validated verifier is now `validation/`; the author reference is `reference/` and public checkout is `task/candidate/`.

Historical paths such as `trial-01-validated-receipt` map to `evidence/receipts/trial-01`, and `trial-01/final` maps to `evidence/trials/trial-01/final`. Focused state receipts live under `evidence/state-receipts`. Extracted commands and their returned outputs are included per trial. Source-state folders include the application source files only; they are not copies of every transient file captured during execution. Portable run.json files explicitly record their extraction scope. Raw model streams, old verifier builds, duplicate working copies and complete transient snapshots remain local.

Original hash manifests may enumerate local artifacts excluded from this distribution. Their retained receipts are historical evidence, not a claim that every historical artifact is shipped. Package-level SHA256SUMS.json binds the actual distributed files. The current candidate and reference preserve their source bytes. The repository task manifest adjusts title and relative navigation; the original task manifest remains in this folder for provenance.

The scientific fixtures and final recovery databases are synthetic. Model authentication, host Git history, client files, other task snapshots, caches and virtual environments are excluded. 

The standalone evaluator uses the package-specific local image tag `truegate-screening-evidence-verifier:0.7.3`. The underlying check source remains bound by its preserved hashes. `tools/build_verifier.py` records the actual rebuilt image identity for local grading.


Complete final payloads are stored as `evidence/trials/trial-NN/final.tar.gz`, with every member verified against the recorded final manifest. Intermediate application source files are stored in `source-states.tar.gz`; their inventory describes the exact archived members. `application.patch` provides a directly reviewable source diff for each solver. Archive member timestamps and owners are normalized for reproducibility. Extract using `python3 tools/extract_evidence.py trial-01 final /absolute/new/directory`.
