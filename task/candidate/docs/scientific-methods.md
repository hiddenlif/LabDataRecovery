# Analysis methods and limits

These are explicit models for the application. They must be assessed against a study's intended use before real decisions are made.

## Screening evidence

Each plate uses its own mean vehicle signal V and positive-control signal P. Normalized inhibition is 100(V-signal)/(V-P); observations are not clipped. Three or more controls of each type are required. Control separation uses Z-prime = 1 - 3(SD_vehicle + SD_positive)/abs(V-P), with sample standard deviations. Reversed controls or inadequate separation exclude the plate's sample observations.

Four-parameter curves are fitted independently to each compound and assay with ordinary least squares over individual valid wells. The increasing model is bottom + (top-bottom)/(1 + exp(-slope*(log(dose)-log(IC50)))). Fits use bounded parameters and several initial slopes. The top and bottom remain estimated. Fitted IC50 is the midpoint between the fitted asymptotes. A curve must bracket 50% normalized inhibition, cover the configured number of distinct doses, meet the residual threshold, and have an identifiable Jacobian to be reported as fitted. This check is deliberately conservative; a partial curve may carry useful information without providing a trustworthy fitted potency.

The approximate 95% log-potency interval comes from residual variance times the inverse Jacobian information matrix. It is a local linear approximation, not a profile-likelihood interval, and is not reported for ill-conditioned fits. Its adequacy depends on the model and noise assumptions.

The primary assay must fall within the selected potency window. Counter and viability activity are flagged when their lower potency bound is within the configured multiple of the primary upper bound. An unbracketed nuisance curve only counts as clear of that window when its tested range reaches beyond the required margin. Missing or poorly resolved evidence remains unresolved. Orthogonal activity supports review but does not prove specificity. No mathematical deconvolution of the primary signal or biological potency correction is claimed.

Scientific background: [Assay Guidance Manual, interference and orthogonal assays](https://www.ncbi.nlm.nih.gov/books/NBK553584/) and [luciferase interference](https://www.ncbi.nlm.nih.gov/books/NBK374281/). These references inform the workflow; no reference text or code is bundled.

## Donor-paired method comparison

Convert compatible units first. Average technical replicates within `(donor, sample, method)`. For each complete positive-valued pair, compute log(candidate mean / reference mean). Average the sample log ratios within each donor, then average donors equally. Exponentiation gives the geometric method ratio. Neither extra technical replicates nor extra samples from one donor increase that donor's weight.

For the interval, sort donors by identifier and resample whole donors with replacement using NumPy's default PCG64 generator and the recorded seed. Take the mean log ratio in each bootstrap draw and exponentiate linear-interpolated percentile endpoints. Equivalence is supported only when the entire interval lies within the configured ratio bounds. Report excluded pairs, donor counts, per-donor estimates and leave-one-donor-out sensitivity. This estimator describes paired donor-level ratios and does not replace a full precision or agreement study.

## Batch stability

For each batch fit value = intercept + slope*time by weighted least squares. Use residual variance sum(weight*residual^2)/(n-2) and covariance residual_variance*(X'WX)^-1. The one-sided lower mean-response bound at time t is fitted_mean(t) - t_quantile*sqrt([1,t] covariance [1,t]'). The Student-t quantile uses the configured confidence and n-2 degrees of freedom.

Find the first time the lower bound falls below the configured limit. If it already fails at time zero, supported duration is zero. The evaluation cap is the lesser of the requested maximum duration and maximum observed time times the allowed extrapolation factor. A study's supported duration is the minimum across batches, and all limiting batches are retained. Any insufficient batch makes the overall result incomplete. Batches are never silently pooled. The bound concerns a mean response, not individual-product survival or a tolerance interval.

## Rare-event qualification

Pool blank counts and acquisition totals within each batch. A sample's net fraction is max(0, sample rate - matched blank rate). Each binomial interval uses exact equal-tailed Clopper-Pearson bounds. For k=0 the lower endpoint is zero; for k=n the upper endpoint is one. The endpoints otherwise use Beta(k,n-k+1) and Beta(k+1,n-k) quantiles.

Allocate alpha=(1-confidence)/(number of nonblank acquisitions + number of matched blank batches) to each unique interval. The corrected interval is [max(0, sample_lower-blank_upper), max(0, sample_upper-blank_lower)]. This conservative simultaneous construction retains uncertainty in the blank, including a blank with zero observed events.

A batch/level needs the configured replicate count, all corrected intervals within its accuracy band, and a sample CV of net fractions within the precision limit. A level qualifies only when every sample batch qualifies at that level. A candidate quantification limit must qualify together with every higher represented level. A disconnected passing island does not establish a quantifiable range. The reported limit remains a candidate; specificity, matrix effects, gates, and intended use require separate assessment.

