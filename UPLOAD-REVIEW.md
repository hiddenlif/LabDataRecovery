# Upload review

## Included

Only the screening-evidence-recovery task, its maintained application, frozen candidate and reference, validated 0.7.3 verifier, shared application regression checks, synthetic fixtures and selected calibration evidence. The public task export contains 92 files. Original solver final payload bytes are retained, including their synthetic migration databases. Verified archives retain final payloads and intermediate source states; readable source patches support review without duplicate working trees.

## Excluded

Other standalone tasks and portfolios, prior task revisions, duplicate development fixtures and verifier builds, raw model streams, host Git history, authentication, caches, virtual environments and unrelated client work. Do not infer unavailable historical artifacts from retained historical receipt manifests. See evidence/PORTABILITY.md.

## Checks

- Pattern scan found no credential matches, risky Docker settings or prompt-injection indicators in proposed files.
- Text inspection found no local personal paths or the private task-authoring guidance.
- No symlinks or files larger than 25 MiB were selected.
- Candidate and reference bytes match their original bound manifests; the reference patch is reconstructible.
- Application tests and the full reference are executed again from this standalone package; actual upload-validation receipts are recorded separately from historical calibration.
- SHA256SUMS.json binds the distributed files, excluding local runtime outputs and Git metadata.

These checks are scoped evidence. Credential-pattern absence is not a universal security guarantee. Candidate execution remains isolated from the protected verifier supervisor. The draft PR and CI report actual validation rather than claimed production status or percentage coverage.
