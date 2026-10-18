# README outline

1. **Engineering problem:** correct screening evidence across ingestion, queued analyses, reports and retained-data recovery.
2. **Capabilities demonstrated:** multi-module Python changes, SQLite transactions and immutable evidence, Docker, deterministic regression checks and independent verifier review.
3. **Architecture:** diagram showing source bytes, ingestion, immutable datasets, jobs, scientific analysis, reporting and recovery.
4. **Reproduce:** one verifier build, unprivileged public tests, prepared candidate, complete private evaluation and an explicit grade.
5. **Testing design:** provenance, staged work, codec compatibility, partial recovery, rollback, backup, repeat safety and deliberately incomplete implementations.
6. **Measured results:** reference 185/185; solver attempts 179/185, 185/185 and 179/185; distinguish report omissions from data loss.
7. **Review and limits:** private/public exposure boundary, verifier corrections, human acceptance and unproven three-cycle horizon.
8. **CI and maintenance:** real GitHub Actions workflow, pinned dependencies, clean commits and a draft PR with validation details.
9. **Navigation and troubleshooting:** runnable paths, Docker/architecture assumptions and local rebuild identity.

Claims should remain factual. This is research software with synthetic data. Directory depth, production deployment, percentage coverage and universal resistance to shortcuts are not inferred from test counts.
