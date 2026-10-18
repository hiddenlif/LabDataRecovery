# Shared calibration uncertainty

Screening inputs may carry an optional top-level `calibration` object. Without it, existing fits and decisions retain their meaning. This feature propagates documented concentration uncertainty into screening review; it does not validate an assay or establish clinical confidence.

## Model and identity

`calibration` contains a trimmed nonempty `revision`, `sources`, `nodes`, and `bindings`. IDs are trimmed nonempty strings, at most 200 characters. Sources and nodes have unique IDs. The limits are 128 sources, 4096 nodes and 100000 bindings.

Each source is `{ "id": "stock-assay", "log_sd": 0.15 }`. Its perturbation is independent, normal, zero-mean in natural-log concentration units. Standard deviations are finite and nonnegative. Sharing an ID means sharing the same random variable, even across campaigns; separate IDs are independent.

A root node has `id`, positive `concentration`, supported concentration `unit`, and `loadings` mapping source IDs to finite coefficients. A child has `id`, `parent`, positive finite dilution `ratio`, and `loadings`. Roots cannot have a ratio; children cannot have concentration or unit. Every parent and source must exist; cycles, duplicate nodes and nonfinite resolved values are errors. Empty loadings are valid.

A child's central concentration is its parent's concentration times its ratio. Its source loadings are its parent's cumulative loadings plus its own. Thus the same source on two ancestry edges adds before variance is computed. Sources can cancel with opposite signed coefficients. Graph and binding order do not matter.

A flat binding is `{ "record_id": "measurement-1", "node": "dose-1" }`. It must name one existing sample, at most once, and an existing node. Controls cannot be bound. In a campaign envelope, each binding also names `campaign`; resolve the pair `(campaign,record_id)` before analysis. The shared graph remains top-level. Nested per-campaign calibration is rejected rather than silently ignored.

Existing dispensing exclusions and plate QC are applied first. For an eligible sample with telemetry, the graph's central dose must agree with its resolved actual dose to relative tolerance 1e-9. For an eligible nominal sample, the graph supplies its dose. A missing binding makes that compound/assay channel `calibration_unresolved` with a null interval. It must not silently become zero uncertainty. Failed or excluded wells do not make otherwise usable channels unresolved. Malformed graphs are rejected even if a node is unused.

## Numerical contract

For each fitted channel, let `x_i` be the natural log of the central concentration and `L_is` its cumulative loading for source `s`. Concentration uncertainty is `x_i + sum_s L_is delta_s`, with independent `delta_s` of variance `log_sd_s^2`.

Use the existing increasing four-parameter response fit, with parameters `(bottom, top, logIC50, slope)`. At the central fit, form its response Jacobian `J` with respect to those four parameters, and `d_i`, its response derivative with respect to `x_i`. The local Gauss-Newton parameter sensitivity to source `s` is the least-squares solution of:

```
J sensitivity_s = -d * L_s
```

The third component `g_s` is the sensitivity of logIC50. Calibration log variance is `sum_s (g_s * log_sd_s)^2`. Add the existing response-fit logIC50 variance, assuming independence. Report a two-sided log-normal interval `exp(logIC50 +/- z * sqrt(total variance))`, where `z` is the standard-normal quantile for `(1 + uncertainty_confidence)/2`. The policy default is 0.95 and must be strictly between 0.5 and 1. Equivalent numerical methods are welcome; tests allow numerical tolerance.

This is a first-order local approximation, not nonlinear Monte Carlo, a posterior distribution, or an exact finite-error guarantee. It inherits the existing fit's identifiability checks. If interval log endpoints are outside (-700,700) or nonfinite, return `uncertainty_unbounded` with a null interval rather than serializing infinity. Any variance or sensitivity component that overflows is null in that unbounded result. Rank-deficient sensitivity systems remain `poor_identifiability`.

A common coefficient of one on every observation must give `g=1`: shifting all log doses shifts logIC50 equally. Independent per-well errors with the same marginal variance generally give a different total. Unit conversions cannot change physical results. Zero calibration error leaves central fit variance; changing confidence changes interval width, not the central estimate.

Fitted channels expose `log_ic50_variance` and `uncertainty` containing `method: first_order_log_dose`, `confidence`, `fit_log_variance`, `calibration_log_variance`, and `source_sensitivity` keyed by every source ID (including zero contributions). The result exposes calibration revision, method and confidence. Observations retain existing actual-dose/source evidence.

## Review and history

For calibration-enabled inputs, a primary point estimate within the potency window whose upper interval exceeds `max_ic50_um` adds `primary_potency_uncertain` and requires follow-up. Existing nuisance-assay rules use the propagated marginal intervals; this is not a joint selectivity probability. Existing orthogonal confirmation rules remain in force. Unresolved primary calibration yields insufficient evidence, never a supported review.

Input fingerprints bind the entire calibration model, including its revision. Changed calibration creates a new stored input revision and a distinct pinned job, even when central doses stay unchanged. Jobs already submitted retain the earlier graph and policy. Old reports preserve their original model, intervals and review context. Export displays calibration revision, method and variance components, labels the approximation, and retains the entire input in the snapshot. Preserve all existing JSON import, instrument ingestion, analysis, job, review and report behavior.
