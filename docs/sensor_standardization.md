
# ExacerbAlert – Sensor Data Standardization

## 1. Project Overview

ExacerbAlert is a collaborative healthcare machine learning project
focused on COPD-related monitoring and analysis.

This stage focuses on standardizing the TOLIFE Clinical Health
Indices Dataset V1.0, which contains sensor data collected from
74 participants across Germany and Spain.

The objective is to prepare consistent, structured sensor datasets
for subsequent preprocessing and machine learning stages.

## 2. Dataset Structure

The dataset contains eight sensor streams:

| Sensor | Description |
|---|---|
| BRI | Breathing Rate Index |
| EI | Environmental Index |
| MI | Mobility Index |
| PEI | Pulmonary Efficiency Index |
| PRVI | Pulse Rate Variability Index |
| SHRI | Sleeping Heart Rate Index |
| SII | Sound Intensity Index |
| SQI | Sleep Quality Index |

Participant distribution:
- Germany: 34 participants
- Spain: 40 participants
- Total: 74 participants

## 3. Standardization Methodology

The following operations were performed:

1. Loaded participant and country information.
2. Inspected sample CSV files from all eight sensor streams.
3. Created a reusable function to load and standardize sensor files.
4. Converted timestamps into UTC-aware datetime values.
5. Added Participant_ID, Country and Sensor columns.
6. Processed each sensor independently across available participants.
7. Combined participant records separately for each sensor.
8. Aligned differing column structures during consolidation.
9. Saved standardized datasets in Parquet format.
10. Validated the resulting datasets.

## 4. Standardization Results

A total of 583 available participant sensor files were processed,
producing 91,794 sensor records.

| Sensor | Participants | Records | Columns |
|---|---:|---:|---:|
| BRI | 74 | 9,866 | 10 |
| EI | 74 | 19,732 | 22 |
| MI | 74 | 9,908 | 14 |
| PEI | 74 | 9,907 | 14 |
| PRVI | 65 | 2,917 | 18 |
| SHRI | 74 | 9,866 | 10 |
| SII | 74 | 19,732 | 10 |
| SQI | 74 | 9,866 | 12 |
| **Total** | | **91,794** | |

## 5. Validation

The standardized datasets were checked for:

- Expected row counts and participant coverage.
- Timestamp data types and UTC timezone consistency.
- Required identification and validity columns.
- Missing-value counts.
- Duplicate participant-timestamp combinations.
- Earliest and latest timestamps.
- Original CSV versus standardized Parquet row counts.

All eight sensors passed the original CSV versus Parquet
row-count comparison.

All eight sensors contained the required identification
and validity columns.

No unexpected record loss was identified.

## 6. Dataset Limitations and Observations

### Missing sensor files

Nine PRVI files were unavailable:
- Germany: 6 participants.
- Spain: 3 participants.

The other seven sensor streams contained files for all 74 participants.

### Missing values

Missing values were observed in:
- BRI: 3
- PEI: 970
- PRVI: 8,436
- SQI: 19,738

These counts represent missing cells, not missing records.

### Duplicate timestamps

Duplicate participant-timestamp combinations:
- EI: 70
- PRVI: 195
- SII: 70

These records were retained.

### Schema differences

- PRVI showed schema variations across participant files.
- SQI contained additional columns named use_time and
  duration_movements.
- The meanings of these additional columns were not established
  from the available documentation.
- Missing columns were aligned during consolidation.

### Sampling and monitoring

- Sensor streams have different sampling frequencies.
- Monitoring periods vary across sensors.
- Long monitoring gaps were observed.

## 7. Data Preservation Rules

This stage performed structural standardization only.

The following operations were intentionally not performed:

- Missing-value imputation.
- Duplicate record removal.
- Invalid or zero-value record removal.
- Outlier removal.
- Feature scaling or normalization.
- Modification of original raw CSV files.

Original measurements and available validity flags were preserved.

## 8. Output Files

The standardized outputs are stored under:

data/interim/standardized/

Expected structure:

- participants_info.csv
- validation_summary.csv
- schema_summary.csv
- sensors/
  - BRI.parquet
  - EI.parquet
  - MI.parquet
  - PEI.parquet
  - PRVI.parquet
  - SHRI.parquet
  - SII.parquet
  - SQI.parquet
  - sensor_load_summary.csv
  - missing_sensor_files.csv

## 9. Scope of This Stage

The output of this stage is structurally standardized sensor data.

It is intended for subsequent preprocessing, data quality
handling, feature engineering and machine learning workflows.

Missing values, duplicate timestamps and other observed
limitations remain documented for later stages.


## 10. Detailed Schema Audit

The original CSV schemas were compared across all available
participants for each sensor.

Results:

| Sensor | Original Schemas | Original Columns | Consolidated Columns |
|---|---:|---:|---:|
| BRI | 1 | 7 | 10 |
| EI | 1 | 19 | 22 |
| MI | 1 | 11 | 14 |
| PEI | 1 | 11 | 14 |
| PRVI | 2 | 15 | 18 |
| SHRI | 1 | 7 | 10 |
| SII | 1 | 7 | 10 |
| SQI | 2 | 9 | 12 |

All original columns were preserved in the consolidated datasets.

PRVI and SQI each contained two distinct original schemas.
Their column differences were retained during consolidation.

Three additional metadata columns were added to each dataset:
Participant_ID, Country and Sensor.
