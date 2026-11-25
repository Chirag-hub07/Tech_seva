# ExacerbAlert ML pipeline

Research prototype for predicting a documented moderate or severe COPD
exacerbation within the next seven days from daily sensor features
(TOLIFE COPD dataset V1.0). **It is not a clinically validated prediction or
diagnostic system and must not be used for clinical decisions.**

This directory is independent of the notebooks and of any database
credentials. It reads only the local processed Parquet/CSV files.

## Status

| Stage | State |
|---|---|
| Configuration, data loading, label policy, post-event exclusion | Implemented |
| Predictor allowlist, leakage guards, fit-on-train feature filters | Implemented |
| Participant-grouped cross-validation splits | Implemented |
| Synthetic-data tests | Implemented |
| Feature-exclusion register, nested grouped CV, evaluation, final fit, prediction | Implemented; **tested on synthetic data only** |
| Training on the real data | **Not run yet** (must be run locally by the project owner) |

## Layout

```
ml/
  config.yaml              all paths, column names, policies, thresholds, seeds
  check_data.py            read-only, aggregate-only data check (no training)
  audit_features.py        feature audit (aggregate-only output, outside the project)
  verify_temporal.py       recompute rolling/baseline features and compare (backward-looking check)
  diagnose_rolling_std.py  diagnosis of rolling-std mismatches
  train.py                 nested participant-grouped cross-validation (no final model)
  fit_final.py             final model, only after a complete cross-validation run
  predict.py               score a feature table with a final model (output outside the project)
  exacerbalert_ml/
    config.py              configuration loading
    data.py                load tables, normalise keys, one-to-one join
    labels.py              label policy (unknown never becomes negative silently)
    events.py              event lists, days-since-event, post-event exclusion
    diagnostics.py         aggregate explanation of event-file participants without positives
    features.py            predictor allowlist, leakage guards, fit-on-train filters
    splits.py              participant-grouped repeated K-fold and inner splits
    dataset.py             assemble X / y / groups for modelling
    exclusions.py          conservative feature-exclusion register (audit + temporal inputs)
    models.py              leakage-guarded Pipelines: dummy, logistic regression, RF, HGB
    evaluate.py            metrics, threshold selection, calibration, event-level, bootstrap
    training.py            nested CV engine, holdout split, final fit (in memory)
    runner.py              run orchestration and aggregate-only outputs
    utils.py               seeds, hashes, environment metadata, run folders
  tests/                   synthetic data only (no patient data)
```

## Setup and commands

Use the project environment (`environment.yml` on Windows or
`environment.macos.yml` on Apple Silicon); it already contains pandas, numpy,
pyarrow, scikit-learn and PyYAML. No additional packages are required.

Run the tests (synthetic data only):

```bash
cd ml
python -m unittest discover -s tests -v
```

or, from the project root, `PYTHONPATH=ml python -m pytest ml/tests -q`.

Run the read-only data check on the real local data (prints counts only,
writes nothing, trains nothing). With `event_source: raw` it needs the raw
event files under `data/raw/TOLIFE_COPD_Dataset/index`:

```bash
python ml/check_data.py
```

## Training

### Feature exclusions (before any fold is fitted)
`train.py` refuses to start unless both audit inputs exist:
`feature_exclusions.feature_audit_dir` (output of `audit_features.py`, whose
summary must report `label_policy=original`) and
`feature_exclusions.temporal_verification_csv` (output of
`verify_temporal.py --all`). A predictor is **excluded by default** if:

* its name matches a calendar/time pattern, or a time-in-study proxy pattern;
* it is listed in `feature_exclusions.explicit` (the 5 rolling-std features
  flagged MISMATCH, pending diagnosis);
* it is absent from the feature audit, the audit excluded it, or the audit
  gave it a blocking review reason (high target correlation, calendar/time,
  event/outcome name, time-in-study proxy, correlation with days in study);
* it is a rolling/baseline feature whose temporal status is not `PASS`,
  including features that were never checked.

A feature is re-admitted only through `feature_exclusions.cleared_after_review`
with a written reason, and the register records what it would otherwise have
been excluded for. The 3 high-target-correlation features stay excluded from
the primary model. They are to be evaluated separately, as a non-primary
analysis, only after they have been verified as backward-looking. Every
decision is written to `feature_register.csv`.

### Design
* Outer: repeated participant-stratified grouped K-fold (`splits`).
* Inner: grouped K-fold on the outer-training participants only. It chooses
  hyper-parameters by inner out-of-fold PR-AUC, and the alert threshold on
  the same predictions (highest threshold reaching the target sensitivity).
  The model is then refitted on the outer-training rows and scores the outer
  test participants once.
* All outer and inner splits are built before any model is fitted. If the
  configured design is infeasible the run stops (`ERROR [validation_design]`);
  the design is never weakened automatically.
* Models are `dummy_prior` (no-information baseline; it alerts on every day),
  logistic regression (elastic net, `saga`), random forest and histogram
  gradient boosting. Class weights, imputation, scaling and the missingness,
  constant and duplicate filters are inside each Pipeline, so they are fitted
  on training rows only.
* Analyses: `primary` (original labels, 14-day washout), `washout_none`,
  `washout_28`, and `tolife_absent_file_negative`. The last is
  **assumption-dependent** and must never be reported as primary.

### Outputs (aggregates only)
Each run writes a new folder `ml/outputs/runs/<UTC time>_<label>/` and never
overwrites an earlier one. It contains:

* `report.md`, `run_metadata.json` (environment, input SHA-256 hashes, command),
  `config_used.yaml`, `feature_register.csv`, `selected_features.txt`;
* per analysis: `model_comparison.csv` (mean/sd across all outer folds of all
  seeds, plus the between-seed SD of the per-seed means),
  `model_comparison_by_repeat.csv` (per model and seed),
  `cv_metrics_by_split.csv`, `split_summary.csv`,
  `pooled_oof_metrics_repeat1.csv` (pooled out-of-fold metrics of the first
  repeat with participant-bootstrap 95% intervals, event-level metrics,
  calibration slope/intercept), `calibration_<model>.csv`,
  `confusion_matrix_pooled_repeat1.csv`.

The metrics are precision, recall (sensitivity), specificity, F1, ROC-AUC,
PR-AUC, Brier score, the confusion matrix and calibration. Event-level, an
event counts as detected if any modelled day in the 7 days before it raised
an alert. Lead time and false alerts per participant-week are also reported.

No participant IDs, dates or row-level predictions are written. With the
holdout disabled (the default) every report states that there is **no
independent final test set**.

### Final model and prediction
`fit_final.py --run-dir <run> --model <name>` refuses unless that run
completed the primary analysis **and** all sensitivity analyses with the full
configured design, the model was cross-validated there, and the input hashes
and feature register are unchanged. It tunes on grouped inner folds of all
development participants and refits on all of them. It then saves
`final_model_<name>/model.joblib` and `input_schema.json`, which holds the
predictors, threshold and provenance. The artifact has no performance
estimate of its own. `predict.py` writes patient-level predictions, so it
only accepts an output path outside the project.

## Methodological decisions

### 1. Event files and the label policy
Only 24 of the 74 participants have an `exacerbations.csv` file. **It has not
been verified from the dataset documentation whether a missing file means
that no exacerbations occurred, or only that no event data are available.**
The pipeline therefore does not assume that a missing file means zero events.

The original label file is never modified. A `target` column is derived under
`target.label_policy`:

* `original` (**default, conservative**): `target` equals
  `exacerbation_within_7d` exactly as produced by notebook 06. Every row of a
  participant without an event file stays unknown (`unknown_no_event_file`)
  and is dropped before modelling. Known labels therefore come only from the
  24 participants with event files:
  * 1 = a documented Moderate/Severe event in (Date, Date + 7 days];
  * 0 = no documented event in that window, with full follow-up. This assumes
    each existing event file is complete over the participant's follow-up.
* `tolife_v1_absent_file_negative` (**not used; kept for a future, documented
  decision only**): treats a missing file as "no recorded events". Rows of
  participants without an event file become 0 only when the whole window
  (Date, Date + 7 days] lies on or before their last feature date. It must
  not be enabled unless the dataset documentation confirms that meaning.

In every policy, `unknown_incomplete_followup` rows remain unknown, positives
are unchanged, and unknown rows are never treated as negative.

**Consequence:** models are trained and validated only on participants who
have event files. Performance on participants without event files is not
estimated.

### 2. Event-file participants without positive labels
`diagnostics.explain_event_participants_without_positives` classifies every
event of such participants. It reports counts only, under these reasons:
* the event falls on or before the first feature date;
* the event falls more than 7 days after the last feature date;
* the severity is not counted as positive;
* the date cannot be parsed;
* the participant has no feature rows.

A feature row on day d can only be positive for an event e with d < e <= d + 7.

### 3. Prediction-time assumption
Predictions for day d are made at the **end of day d**, after that day's
sensor data are complete. Features may use data up to and including day d;
rolling and baseline features use only earlier days (`shift(1)` in notebook
04). The target window is (d, d + 7]. Features whose dictionary `Time_Window`
implies future data are rejected (`LeakageError`). A deployed system must not
issue the day-d prediction before day-d data are available.

### 4. Post-event exclusion
Rows on the day of a documented event and the following
`post_event.primary_washout_days` (default 14) days are excluded from the
**primary pre-event analysis**, because they describe a participant already
exacerbating or recovering. Sensitivity analyses use no exclusion and 28 days.

Events come from `post_event.event_source`:

* `raw` (**default**): every event in the raw `exacerbations.csv` files under
  `paths.raw_event_index_dir`. If that directory is missing, the pipeline
  stops with an error; it never silently falls back to the incomplete list.
* `labels`: events referenced by `matched_event_date`. This is a lower bound,
  because events that no feature row can predict (for example on or before a
  participant's first feature date) are missing.

Participants without an event file contribute no events, so no rows of theirs
are excluded as post-event. Under the default `original` policy all their rows
are unknown and dropped anyway.

### 5. Predictors and leakage guards
Predictors come from an allowlist: the columns documented in
`feature_dictionary.csv`, minus banned columns. `Participant_ID`, `Date`, the
target, `label_status`, the matched event date and severity, and any name
matching the banned patterns can never be predictors. `LeakageGuard` enforces
this again inside every model pipeline. Missingness (>95% in the training
fold), constant and exact-duplicate filters are scikit-learn transformers
fitted on training folds only.

Feature sets: `all`; `compact` (a pre-specified family-based subset);
`compact_no_time_proxies` (without provisional time-in-study proxies such as
`*_baseline_count`).

### 6. Validation strategy
* Participant-grouped, participant-stratified K-fold (stratified by "has at
  least one positive row"). Every participant is entirely in training or
  entirely in validation. **Daily rows are never split randomly.**
* 5 outer folds, repeated with 5 seeds, because few participants contribute
  positive rows. Results must be reported as distributions across repeats.
* Inner participant-grouped splits on training participants only, for
  tuning and threshold selection. Thresholds are never chosen on validation
  participants.
* There is no separate held-out test set; the participant count is too small.
  The estimates are internal cross-validation estimates.

### 7. Cross-validation versus the final artifact
No final model is fitted on all participants until cross-validation and all
sensitivity analyses are complete and reviewed. The cross-validated
performance estimates describe the modelling *procedure*; the final fitted
artifact is a separate object, refitted later with the chosen configuration,
and it has no independent performance estimate of its own.

## Privacy
* No function prints participant IDs, dates or rows. Summaries and error
  messages contain counts only.
* `ml/outputs/` (fold assignments, models) is git-ignored because it may
  contain participant-level information.
* Never commit data files, outputs or credentials.

## Known limitations
* Only 19 participants contribute positive rows, and the 203 positive rows
  correspond to about 39 documented events. Rows are not independent.
* The meaning of a missing event file is unverified, so the 50 participants
  without event files contribute no labels under the default policy.
* Known labels come only from participants with event files; negatives assume
  those files are complete over follow-up. A documented event is not proof of
  a clinically confirmed exacerbation, and no documented event is not proof of
  its absence.
* Same-day features assume end-of-day prediction.
* Time-in-study proxy features need verification on the real data.
