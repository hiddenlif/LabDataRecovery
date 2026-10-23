# Study data

Inputs are UTF-8 JSON objects with `kind` and a nonempty `records` array. Record identifiers are unique within a dataset. Duplicate object keys and nonfinite numbers are rejected. Object key order is irrelevant to the input fingerprint; array order remains part of the imported record. Importing the same current content is idempotent. Returning to older content creates a new revision.

## Screening

`kind` is `screening`. Each row contains `id`, `plate`, `well`, `assay`, `role`, and numeric `signal`. Assay is `primary`, `counter`, `viability`, or `orthogonal`. Role is `sample`, `vehicle`, or `positive`. Every physical `(plate, well)` is unique. Plate identifiers are scoped to a dataset, not to an assay or compound. A plate contains only one assay.

Sample rows additionally contain `compound`, `dose`, and `dose_unit`. Supported concentration units are `M`, `mM`, `uM`, `µM`, `μM`, and `nM`, with case significant. Different plates may reuse well names. Compound identifiers may recur across assays and campaigns.

Optional `telemetry` is an array of dispensing events with `plate`, `well`, integer `revision` starting at 1, and `status` (`ok`, `failed`, `cancelled`). Successful events contain `actual_dose` and `dose_unit`. Events can arrive out of order. The highest revision for a physical well determines its current status. Exact duplicate events are allowed; contradictory events at the same revision are errors. Telemetry may only reference sample wells in the dataset. Telemetry requirements are scoped to plates represented in the telemetry: every sample on such a plate needs an event, while uninstrumented plates use nominal doses. Plate diagnostics report dispense_mode as calibrated or nominal. Missing, failed, cancelled, and zero-dose transfers are excluded and recorded. Without telemetry, nominal doses are used and identified as such.

No additional correction factor is applied to an actual concentration. Raw data and telemetry remain in the exported input snapshot.

## Method comparison

`kind` is `bridge`. Rows contain `id`, `donor`, `sample`, `method`, `value`, and `unit`. A sample identifier is local to its donor. Repeated rows with different record IDs are technical replicates. The policy selects the two method labels. Unknown methods are errors.

Compatible units are `fraction` and `%`, or `ng/mL`, `ug/mL`, and `µg/mL`. Mixing the fraction and mass families is an error. Method means must be positive for a log-ratio comparison. Missing counterparts and nonpositive pair means are excluded with a reason.

## Stability

`kind` is `stability`. Rows contain `id`, `batch`, `time`, `time_unit`, `value`, and positive `weight`. Times accept `h`, `hours`, `min`, and `days`; internal times are hours. The weight is proportional to inverse measurement variance, not a replicate count. Values must be on one consistent measurement scale. Distinct record IDs represent independent measurements.

## Rare events

`kind` is `rare_events`. Rows contain `id`, `batch`, `level`, integer `events`, positive integer `total`, and `expected_fraction`. Events cannot exceed total. An expected fraction of zero identifies a blank. Each positive-sample batch needs matched blank measurements. All records sharing a level label must share its expected fraction. Different record IDs are independent acquisitions.

The application assumes Bernoulli event classifications within an acquisition. It does not estimate compensation, gate placement, classification error, or overdispersion from raw flow-cytometry files.


Campaign envelopes and their identity rules are described in [campaign identity](campaign-identity.md). Durable worker execution is described in [analysis jobs](analysis-jobs.md).
