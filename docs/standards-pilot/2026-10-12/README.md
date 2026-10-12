# First warning-only consumer baseline

Owner: @4444J99; implementation and finding disposition: Codex pilot lane.

The merged toolkit commit `a5cdf48e9f255cb407a1ae69be62397f1151847d` supplies the first advisory module. This dated, reproducible baseline inspects the eleven tracked workflow files at Engine revision `3cfb12c7db85456373cd94efe0480ac5bf79436b`. Plan check names come from the existing CI matrix and aggregate gate. The plan digest is SHA-256 of compact, sorted JSON before adding `plan_digest`. The module binds hashes to the bytes actually parsed.

## Findings and disposition

Permission declarations and mutable action references produce WARN. These are retained for contextual review; existing privileged automation is not disabled or globally downgraded to manufacture green. Execution remains NOT_VERIFIABLE because no authenticated execution receipt was supplied. A successful historical CI run does not silently become a normalized receipt. Public workflow source is the only acquired material in this directory.

## Reproduce and verify

With Python 3.12 and pinned PyYAML 6.0.3, check out the toolkit at the recorded commit and run its `python -m ges.warning_pilot` with a reconstructed snapshot and adjacent `plan.json`, and a fresh output path. Compare parsed report content and input digests with `report.json`; verify every size and SHA-256 in `manifest.json`. Reconstruct the snapshot using the shape in `snapshot-manifest.json`: read each listed UTF-8 blob with `git show REVISION:PATH`, place it in the files data map, and serialize with two-space JSON indentation plus one newline. Verify each blob and the complete snapshot hash before inspection. Existing output files are intentionally not overwritten. Raw workflow bodies remain in their existing source owner rather than being duplicated in this evidence directory.

## Onboarding and rollback gate

This PR retains local advisory evidence; it activates no workflow, does not alter required checks or branch settings, and does not start the seven-day observation clock. Hosted integration must use the approved thin reusable-workflow architecture, pin an accepted immutable version, preserve required contexts, measure added execution against the two-minute target, and demonstrate artifact retrieval and rollback before consumer acceptance. Full artifact inspection, privileged trigger dataflow, checker protection and restoration remain unevaluated by this module.

Next owner: Codex pilot lane. Next bounded implementation: the shared reusable wrapper and its positive/adversarial fixtures, followed by this consumer's isolated warning-only integration PR. No additional repository, spending, enforcement activation or historical-hold release is inferred. Roll back any eventual integration through its PR rail and preserve these receipts.
