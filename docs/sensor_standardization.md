# ExacerbAlert -- Sensor Data Standardization

## 1. Project Overview

ExacerbAlert is a collaborative healthcare machine learning project
focused on COPD-related monitoring and analysis.

This stage focuses on standardizing the TOLIFE Clinical Health Indices
Dataset V1.0, which contains sensor data collected from 74 participants
across Germany and Spain.

The objective is to prepare consistent, structured sensor datasets for
subsequent preprocessing and machine learning stages.

## 2. Dataset Structure

The dataset contains eight sensor streams:

  Sensor   Description
  -------- ------------------------------
  BRI      Breathing Rate Index
  EI       Environmental Index
  MI       Mobility Index
  PEI      Pulmonary Efficiency Index
  PRVI     Pulse Rate Variability Index
  SHRI     Sleeping Heart Rate Index
  SII      Sound Intensity Index
  SQI      Sleep Quality Index

Participant distribution:

-   Germany: 34 participants
-   Spain: 40 participants
-   Total: 74 participants

## 3. Standardization Methodology

The following operations were performed:

-   Loaded participant and country information.
-   Inspected sample CSV files from all eight sensor streams.
-   Created a reusable function to load and standardize sensor files.
-   Converted timestamps into UTC-aware datetime values.
-   Added `Participant_ID`, `Country` and `Sensor` columns.
-   Processed each sensor independently across available participants.
-   Combined participant records separately for each sensor.
-   Aligned differing column structures during consolidation.
-   Saved standardized datasets in Parquet format.
-   Validated the resulting datasets.

## 4. Standardization Results

A total of 583 available participant sensor files were processed,
producing 91,794 sensor records.

  Sensor        Participants      Records   Columns
  ----------- -------------- ------------ ---------
  BRI                     74        9,866        10
  EI                      74       19,732        22
  MI                      74        9,908        14
  PEI                     74        9,907        14
  PRVI                    65        2,917        18
  SHRI                    74        9,866        10
  SII                     74       19,732        10
  SQI                     74        9,866        12
  **Total**                    **91,794** 

## 5. Validation

The standardized datasets were checked for:

-   Expected row counts and participant coverage.
-   Timestamp data types and UTC timezone consistency.
-   Required identification and validity columns.
-   Missing-value counts.
-   Duplicate participant-timestamp combinations.
-   Earliest and latest timestamps.
-   Original CSV versus standardized Parquet row counts.

All eight sensors passed the original CSV versus Parquet row-count
comparison.

All eight sensors contained the required identification and validity
columns.

No unexpected record loss was identified.

## 6. Dataset Limitations and Observations

### Missing sensor files

Nine PRVI files were unavailable:

-   Germany: 6 participants.
-   Spain: 3 participants.

The other seven sensor streams contained files for all 74 participants.

### Missing values

Missing values were observed in:

  Sensor     Missing cells
  -------- ---------------
  BRI                    3
  PEI                  970
  PRVI               8,436
  SQI               19,738

These counts represent missing cells, not missing records.

### Duplicate timestamps

Duplicate participant-timestamp combinations:

  Sensor     Duplicate combinations
  -------- ------------------------
  EI                             70
  PRVI                          195
  SII                            70

These records were retained.

### Schema differences

PRVI showed schema variations across participant files.

SQI contained additional columns named `use_time` and
`duration_movements`.

The meanings of these additional columns were not established from the
available documentation.

Missing columns were aligned during consolidation.

### Sampling and monitoring

-   Sensor streams have different sampling frequencies.
-   Monitoring periods vary across sensors.
-   Long monitoring gaps were observed.

## 7. Data Preservation Rules

This stage performed structural standardization only.

The following operations were intentionally not performed:

-   Missing-value imputation.
-   Duplicate record removal.
-   Invalid or zero-value record removal.
-   Outlier removal.
-   Feature scaling or normalization.
-   Modification of original raw CSV files.

Original measurements and available validity flags were preserved.

## 8. Output Files

The standardized outputs are stored under:

`data/interim/standardized/`

Expected structure:

``` text
data/interim/standardized/
├── participants_info.csv
├── validation_summary.csv
├── schema_summary.csv
├── schema_audit_summary.csv
└── sensors/
    ├── BRI.parquet
    ├── EI.parquet
    ├── MI.parquet
    ├── PEI.parquet
    ├── PRVI.parquet
    ├── SHRI.parquet
    ├── SII.parquet
    ├── SQI.parquet
    ├── sensor_load_summary.csv
    └── missing_sensor_files.csv
```

## 9. Scope of This Stage

The output of this stage is structurally standardized sensor data.

It is intended for subsequent preprocessing, data quality handling,
feature engineering and machine learning workflows.

Missing values, duplicate timestamps and other observed limitations
remain documented for later stages.

## 10. Detailed Schema Audit

The original CSV schemas were compared across all available participants
for each sensor.

  -----------------------------------------------------------------------
  Sensor          Distinct original   Original columns       Consolidated
                            schemas                               columns
  -------------- ------------------ ------------------ ------------------
  BRI                             1                  7                 10

  EI                              1                 19                 22

  MI                              1                 11                 14

  PEI                             1                 11                 14

  PRVI                            2                 15                 18

  SHRI                            1                  7                 10

  SII                             1                  7                 10

  SQI                             2                  9                 12
  -----------------------------------------------------------------------

All original columns were preserved in the consolidated datasets.

PRVI and SQI each contained two distinct original schemas. Their column
differences were retained during consolidation.

Three additional metadata columns were added to each dataset:
`Participant_ID`, `Country` and `Sensor`.

## 11. Information Sources and Evidence Classification

This section distinguishes information documented by the project or
dataset source from findings measured during this standardization work
and details whose meanings remain unverified.

### 11.1 Project and dataset context

The project repository identifies the dataset as the TOLIFE Clinical
Health Indices Dataset V1.0 and links to its Zenodo record:

https://zenodo.org/records/16642439

The project README identifies the dataset version and source. The
participant counts, country distribution, sensor file counts, row
counts, missing-value counts, duplicate counts, timestamp checks and
schema audit results in this report are results recorded during the
actual dataset inspection and standardization process.

The original dataset README was not available for this work. Therefore,
this report does not attribute additional technical definitions or
measurement semantics to the dataset creators unless independently
verified.

### 11.2 Findings observed in the actual dataset

The following are empirical findings from the available CSV files and
the standardized outputs:

-   74 participants were represented in the participant inventory: 34
    from Germany and 40 from Spain.
-   583 participant-sensor CSV files were available.
-   Nine PRVI files were unavailable.
-   The consolidated sensor datasets contain 91,794 records in total.
-   Missing cells were observed in BRI, PEI, PRVI and SQI.
-   Duplicate participant-timestamp combinations were observed in EI,
    PRVI and SII.
-   PRVI and SQI each had two distinct original column schemas.
-   All original CSV row counts matched the corresponding standardized
    Parquet row counts.
-   The detailed schema audit confirmed that all original columns were
    represented in the consolidated datasets.

These statements describe the files inspected for this project; they are
not claims that every possible version or distribution of the dataset
has identical contents.

### 11.3 Unknown or unverified interpretations

The meanings of the SQI columns `use_time` and `duration_movements` were
not established from the documentation available to this project. They
were retained as original columns without assigning a meaning.

No clinical interpretation is assigned here to missing values, duplicate
timestamps, long monitoring gaps or validity-flag values. Their
implications should be assessed in a later stage using authoritative
dataset documentation and appropriate domain guidance.

No undocumented column meaning or clinical assumption was used to alter
the original measurements during standardization.
