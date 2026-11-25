"""ExacerbAlert ML utilities (research prototype, not clinically validated).

Modules
    config       load and resolve ml/config.yaml
    data         load feature/label tables and join them one-to-one
    labels       apply the documented label policy (unknown is never negative)
    events       event lists and post-event exclusion
    diagnostics  aggregate-only explanations of label coverage
    features     predictor selection, leakage guards, fit-on-train filters
    splits       participant-grouped cross-validation splits
    dataset      assemble the modelling dataset (X, y, groups)

Privacy: no function in this package prints or returns participant IDs in
summaries or error messages. Summaries contain counts only.
"""

__version__ = "0.1.0"
