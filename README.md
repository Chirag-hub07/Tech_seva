# TechSeva
# ExacerbAlert
## COPD Exacerbation Early-Warning System

**ExacerbAlert** is a healthcare-focused research and software development project aimed at identifying potential Chronic Obstructive Pulmonary Disease (COPD) exacerbations using physiological sensor measurements, clinical assessments, historical patient information, and machine learning.

The project aims to develop an early-warning system that analyzes patient data, estimates the likelihood of an upcoming exacerbation, and generates alerts to support timely awareness and intervention.

The system combines data preprocessing, feature engineering, relational database management, machine learning, backend development, and frontend visualization into a unified application.

> **Project Status:** Data preprocessing and database development have been completed for the current stage. Machine learning development, backend implementation, frontend development, and system integration are the remaining development stages.

**Disclaimer:** ExacerbAlert is a research and demonstration prototype. It is not a clinically validated diagnostic system and must not be used as a replacement for professional medical advice, diagnosis, or treatment.

---

# Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Project Objectives](#3-project-objectives)
4. [Dataset Description](#4-dataset-description)
5. [Technology Stack](#5-technology-stack)
6. [Project Architecture](#6-project-architecture)
7. [Repository Structure](#7-repository-structure)
8. [Data Preprocessing and Feature Engineering](#8-data-preprocessing-and-feature-engineering)
9. [Exacerbation Label Generation](#9-exacerbation-label-generation)
10. [Model Dataset Preparation](#10-model-dataset-preparation)
11. [Database Design](#11-database-design)
12. [Machine Learning Development](#12-machine-learning-development)
13. [Backend Development](#13-backend-development)
14. [Frontend Development](#14-frontend-development)
15. [Development Environment Setup](#15-development-environment-setup)
16. [Running the Project](#16-running-the-project)
17. [Data Management and Security](#17-data-management-and-security)
18. [Team Contributions](#18-team-contributions)
19. [Current Development Status](#19-current-development-status)
20. [Future Scope](#20-future-scope)
21. [Repository Information](#21-repository-information)

---

# 1. Project Overview

Chronic Obstructive Pulmonary Disease (COPD) is a chronic respiratory condition that can involve episodes of worsening respiratory symptoms, commonly referred to as exacerbations.

Identifying the possibility of an upcoming exacerbation is important because timely awareness may help patients and healthcare professionals take appropriate action.

ExacerbAlert aims to use historical patient information and physiological measurements to identify patterns associated with upcoming exacerbation events.

The project follows a data-driven approach:

- Collect and organize patient information.
- Process physiological sensor measurements.
- Clean and standardize the collected data.
- Generate meaningful features.
- Associate observations with exacerbation events.
- Prepare a labelled dataset for supervised machine learning.
- Train and evaluate predictive models.
- Integrate the selected model into a backend application.
- Display predictions and alerts through a frontend interface.

The intended prediction horizon for the initial machine learning task is **seven days**.

---

# 2. Problem Statement

COPD exacerbations can lead to worsening symptoms and may require medical attention.

Traditional approaches often rely on patients recognizing symptoms or reporting changes after they have occurred.

ExacerbAlert explores whether historical physiological measurements and clinical information can help identify patterns that precede an exacerbation.

The central research question is:

**Can patient information available at a particular prediction time be used to estimate whether a COPD exacerbation will occur within the following seven days?**

The project approaches this as a supervised machine learning problem using historical sensor data, engineered features, and exacerbation event records.

The intended output is a prediction that can be used by the application to support an early-warning workflow.

---

# 3. Project Objectives

The major objectives of ExacerbAlert are:

### Data Engineering

- Explore and understand the original COPD dataset.
- Organize patient, clinical, sensor, and exacerbation information.
- Clean and standardize the collected data.
- Validate participant mappings and timestamps.
- Handle missing and invalid records appropriately.

### Feature Engineering

- Extract meaningful information from physiological sensor measurements.
- Generate statistical and temporal features.
- Calculate changes in measurements over time.
- Maintain a feature dictionary documenting the engineered variables.
- Validate feature calculations.

### Machine Learning

- Create labels for the seven-day exacerbation prediction task.
- Prepare a model-ready dataset.
- Train multiple supervised classification algorithms.
- Evaluate models using appropriate classification metrics.
- Select and save a suitable prediction pipeline.

### Database Development

- Design a relational database schema.
- Store patient information.
- Store sensor measurements.
- Store clinical assessments.
- Store exacerbation events.
- Prepare tables for predictions and alerts.

### Application Development

- Develop backend services for data retrieval and prediction.
- Integrate the trained machine learning model.
- Display patient information and predictions.
- Generate and manage alerts.
- Build a user-friendly frontend interface.

---

# 4. Dataset Description

## 4.1 Data Source

The project uses the **TOLIFE COPD Dataset, Version 1.0**.

The dataset contains information collected from COPD participants, including physiological sensor measurements, clinical assessments, and recorded exacerbation events.

The original dataset is maintained separately from the GitHub repository because it contains sensitive patient-level information.

## 4.2 Dataset Overview

The following figures were recorded during the project's dataset exploration and database preparation stages.

| Description | Count |
|---|---:|
| Total participants | 74 |
| Participants from Germany | 34 |
| Participants from Spain | 40 |
| Recorded exacerbation events | 39 |
| Moderate exacerbation events | 29 |
| Severe exacerbation events | 10 |
| Unique patients with moderate events | 23 |
| Unique patients with severe events | 9 |

The 39 exacerbation events represent recorded events, not 39 independent patients.

This distinction is important when preparing training and testing datasets.

## 4.3 Clinical Assessment Data

The project processes clinical assessment information associated with participant visits.

The assessment data contains information collected at different timepoints.

The recorded participant distribution across visits was:

| Visit | Participants |
|---|---:|
| T1 | 74 |
| T2 | 65 |
| T3 | 49 |
| T4 | 24 |
| T5 | 12 |

Participant mapping was validated using the available participant identifiers and kit identifiers.

The validation included checks for:

- Unmatched participant records.
- Country mismatches.
- Duplicate participant-visit records.
- Missing kit identifiers.
- Missing timepoints.
- Missing visit dates.

## 4.4 Physiological Sensor Data

The project works with eight sensor streams:

| Sensor | Identifier |
|---|---|
| BRI | BRI |
| EI | EI |
| MI | MI |
| PEI | PEI |
| PRVI | PRVI |
| SHRI | SHRI |
| SII | SII |
| SQI | SQI |

These streams provide physiological or sensor-derived measurements used during the feature engineering process.

Their precise definitions, units, and interpretations should be taken from the original TOLIFE dataset documentation.

The project also validates sensor availability and signal-quality-related information where applicable.

## 4.5 Exacerbation Event Data

The exacerbation records contain information about recorded events, including their timestamps and severity.

The event records are used to construct target labels for the supervised machine learning task.

The event data must be correctly aligned with prediction timestamps to ensure that the model learns from information available before the event rather than information recorded afterward.

---

# 5. Technology Stack

The project uses the following technologies across its different development stages.

| Component | Technology |
|---|---|
| Programming Language | Python |
| Data Processing | Pandas, NumPy |
| Data Storage | CSV, Parquet |
| Data Visualization | Matplotlib |
| Machine Learning | Scikit-learn |
| Database | PostgreSQL |
| Database Platform | Supabase |
| Database Queries | SQL |
| Notebook Environment | Jupyter Notebook / JupyterLab |
| Environment Management | Conda |
| Version Control | Git |
| Code Hosting | GitHub |
| Backend | Python |
| Frontend | Web technologies |

Additional frameworks and libraries may be introduced as backend, frontend, and ML development progresses.

---

# 6. Project Architecture

ExacerbAlert is designed as a multi-component application.

The system separates data storage, machine learning, backend processing, and frontend presentation.

## 6.1 High-Level Architecture

```text
              TOLIFE COPD DATASET
                       |
                       v
             DATA PREPROCESSING
                       |
                       v
              FEATURE ENGINEERING
                       |
                       v
            EXACERBATION LABELING
                       |
                       v
             MODEL DATASET PREPARATION
                       |
                       v
                ML DEVELOPMENT
                       |
                       v
               TRAINED ML MODEL
                       |
                       |
                       v
+-------------------------------------------+
|              SUPABASE DATABASE            |
|                                           |
|  patients                                 |
|  sensor_measurements                      |
|  clinical_assessments                     |
|  exacerbations                            |
|  predictions                              |
|  alerts                                   |
+-------------------------------------------+
                       |
                       v
                PYTHON BACKEND
                       |
                       v
             ML PREDICTION PIPELINE
                       |
                       v
               PREDICTION RESULTS
                       |
                       v
                 ALERT SYSTEM
                       |
                       v
                   FRONTEND
```

The diagram represents the intended application architecture. The final runtime flow and integration details will be established during backend and ML development.

## 6.2 Component Responsibilities

**Data preprocessing:** Converts the original dataset into structured, cleaned, and validated data.

**Feature engineering:** Extracts useful variables from historical physiological measurements.

**Label generation:** Associates prediction observations with future exacerbation events.

**Machine learning:** Learns patterns from the prepared dataset and generates predictions.

**Supabase:** Stores structured patient, clinical, sensor, exacerbation, prediction, and alert information.

**Backend:** Connects the database, ML pipeline, and frontend.

**Frontend:** Presents patient information, prediction results, and alerts.

---

# 7. Repository Structure

The main development work is organized into Jupyter notebooks and supporting project files.

A simplified representation of the repository is:

```text
ExacerbAlert/
│
├── notebooks/
│   │
│   ├── 01_dataset_exploration.ipynb
│   ├── 02_data_standardization.ipynb
│   ├── 03_data_cleaning.ipynb
│   ├── 04_feature_engineering.ipynb
│   ├── 05_database_import.ipynb
│   ├── 06_exacerbation_label_creation.ipynb
│   └── 07_model_dataset_preparation.ipynb
│
├── database/
│   └── SQL scripts and database documentation
│
├── data/
│   └── Raw and processed datasets
│
├── environment.yml
├── .gitignore
└── README.md
```

This is a conceptual overview of the main project components. Check the actual repository for the complete file and directory structure.

## 7.1 Generated Data Directories

The preprocessing workflow generates local data files, including Parquet datasets.

The processed data is organized into feature and label outputs.

A simplified representation:

```text
notebooks/
└── data/
    └── processed/
        ├── features/
        │   └── *.parquet
        │
        └── labels/
            └── *.parquet
```

These files are used during machine learning development.

**Important:** Generated patient-level datasets are excluded from GitHub. Cloning the repository does not automatically download the raw or preprocessed patient-level data.

Authorized access to the datasets must be arranged separately.

---

# 8. Data Preprocessing and Feature Engineering

Data preprocessing is one of the foundational stages of ExacerbAlert.

The original dataset contains information from multiple participants, sensor streams, clinical assessments, and exacerbation records.

Before machine learning can be performed, these records must be cleaned, standardized, validated, and transformed into a consistent format.

The preprocessing workflow is organized into Jupyter notebooks.

## 8.1 Notebook 01 — Dataset Exploration

Purpose:

- Understand the original dataset structure.
- Inspect participant folders and source files.
- Explore available sensor measurements.
- Examine clinical assessment information.
- Inspect exacerbation records.
- Identify missing values and inconsistencies.

This stage establishes an understanding of the available data before applying transformations.

## 8.2 Notebook 02 — Data Standardization

Purpose:

- Standardize source data into a consistent structure.
- Organize participant-related records.
- Normalize relevant data representations.
- Prepare the data for subsequent cleaning and processing.

The goal is to make the different source records easier to process consistently.

## 8.3 Notebook 03 — Data Cleaning

Purpose:

- Identify missing and invalid values.
- Inspect sensor measurement quality.
- Validate timestamps.
- Check participant mappings.
- Inspect duplicate records.
- Apply appropriate cleaning operations.

Cleaning decisions should preserve valid observations and avoid introducing artificial patterns into the dataset.

## 8.4 Notebook 04 — Feature Engineering

Feature engineering transforms cleaned sensor measurements into variables that can be used by machine learning algorithms.

The notebook generates engineered features from the available sensor streams.

The workflow includes:

- Statistical feature generation.
- Temporal feature calculations.
- Measurement comparisons.
- Percentage-change calculations.
- Feature dictionary creation.
- Feature validation.

### Percentage Change Calculation

The percentage-change formula used in the project is:

\[
\text{Percentage Change}
=
\frac{\text{Latest}-\text{Previous}}
{\text{Previous}}\times 100
\]

When the previous value is zero, the percentage change is treated as undefined (`NaN`) rather than producing an invalid result.

The denominator is the signed previous value, not its absolute value.

A feature dictionary is maintained to document the engineered features and their calculation logic.

## 8.5 Notebook 05 — Database Import

This notebook is associated with importing the structured project data into Supabase PostgreSQL.

Its responsibilities include:

- Preparing structured records.
- Establishing database connections.
- Importing patient information.
- Importing sensor measurements.
- Importing clinical assessments.
- Importing exacerbation events.
- Validating imported records.

The database-import workflow is separate from the core ML dataset preparation workflow.

## 8.6 Preprocessing Outputs

The preprocessing stage produces structured feature and label datasets in Parquet format.

Parquet is used because it supports efficient storage and reading of structured tabular data.

These files form the input to the machine learning development stage.

---

# 9. Exacerbation Label Generation

## Notebook 06 — Exacerbation Label Creation

The objective of this notebook is to generate target labels for the seven-day exacerbation prediction task.

The prediction question is:

**Given the information available at a particular prediction timestamp, will the patient experience an exacerbation within the following seven days?**

This is formulated as a binary classification problem.

### Target Variable

| Label | Meaning |
|---|---|
| 1 | Exacerbation occurs within the next seven days |
| 0 | No exacerbation occurs within the next seven days |

Conceptually:

```text
Prediction timestamp
        |
        v
Patient's available historical information
        |
        v
Look ahead over the next seven days
        |
        v
Check recorded exacerbation events
        |
        v
Assign the target label
```

The actual notebook implementation defines the event-window boundaries and the treatment of missing or overlapping events.

These rules must be preserved and understood before training.

### Important Considerations

The label-generation process must account for:

- Correct event timestamp alignment.
- Prediction timestamps.
- The seven-day prediction horizon.
- Multiple events.
- Overlapping prediction windows.
- Missing event information.
- Observations after an exacerbation.
- Potential information leakage.

The target label must represent future events relative to the prediction timestamp.

Information from the future must not be included among the model's input features.

---

# 10. Model Dataset Preparation

## Notebook 07 — Model Dataset Preparation

This notebook prepares the engineered features and labels for machine learning.

It represents the transition from data engineering to ML development.

Its responsibilities include:

- Preparing the model feature matrix.
- Preparing the target variable.
- Organizing patient identifiers and timestamps.
- Identifying feature columns.
- Handling missing values.
- Preparing numerical and categorical features where applicable.
- Establishing preprocessing workflows.
- Preparing fold-specific transformations.

### Fold-Specific Preprocessing

An important part of the existing work is the use of fold-specific preprocessing.

This is intended to prevent information from validation or test data from influencing the preprocessing fitted on training data.

Operations such as:

- Imputation.
- Scaling.
- Encoding.
- Feature selection.

Must be fitted using training data only.

The fitted transformations should then be applied to the corresponding validation or test data.

### Current Status

The model dataset preparation workflow has been developed and validated for the current stage.

The final ML model has not yet been trained or selected.

The prepared training matrices and preprocessing pipelines were created in memory and have not yet been established as final production model artifacts.

---

# 11. Database Design

ExacerbAlert uses **Supabase PostgreSQL** as its relational database.

Supabase provides the PostgreSQL database infrastructure used to store structured application data.

The current database contains six primary tables.

## 11.1 Database Tables

| Table | Description |
|---|---|
| `patients` | Stores patient information |
| `sensor_measurements` | Stores physiological sensor measurements |
| `clinical_assessments` | Stores clinical assessment records |
| `exacerbations` | Stores recorded exacerbation events |
| `predictions` | Stores machine learning prediction results |
| `alerts` | Stores alerts generated from prediction results |

## 11.2 Patients

The `patients` table stores information used to identify and organize patient records.

It provides the patient-level relationship used by other tables.

## 11.3 Sensor Measurements

The `sensor_measurements` table stores physiological sensor measurements associated with patients.

These records provide the historical measurements used by the data processing and prediction workflows.

## 11.4 Clinical Assessments

The `clinical_assessments` table stores clinical assessment information associated with patient visits.

Clinical information can provide additional context for understanding patient status.

## 11.5 Exacerbations

The `exacerbations` table stores recorded exacerbation events.

These records are important for historical analysis and generation of the seven-day prediction target.

## 11.6 Predictions

The `predictions` table is intended to store results generated by the trained ML model.

It is currently empty and will be populated once prediction functionality is integrated.

## 11.7 Alerts

The `alerts` table is intended to store alerts generated from prediction results.

It is currently empty and will be populated when the backend alert workflow is implemented.

## 11.8 Current Database Validation

The following records were verified during the database-import stage:

| Data | Records |
|---|---:|
| Patients | 74 |
| Sensor measurements | 91,794 |
| Clinical assessments | 224 |
| Exacerbation events | 39 |
| Predictions | 0 |
| Alerts | 0 |

The predictions and alerts tables are intentionally empty at the current development stage.

The database already contains the foundational patient and historical data required for subsequent application development.

The locally generated feature and label Parquet files are currently maintained separately for ML development. They do not need to be imported into Supabase simply to train the model.

---

# 12. Machine Learning Development

Machine learning is the next major stage of the project.

The goal is to develop a model capable of predicting the likelihood of an upcoming COPD exacerbation within a seven-day horizon.

## 12.1 Problem Type

The initial task is:

**Supervised Binary Classification**

Input:

- Historical physiological measurements.
- Engineered sensor features.
- Other eligible information available at prediction time.

Output:

- `1`: Exacerbation within the next seven days.
- `0`: No exacerbation within the next seven days.

## 12.2 Candidate Algorithms

The initial model comparison is expected to include the following algorithms.

### Logistic Regression

A baseline classification model.

Advantages:

- Simple and interpretable.
- Suitable for binary classification.
- Useful as a benchmark.
- Provides a reference for more complex models.

### Random Forest

An ensemble tree-based algorithm.

Advantages:

- Can capture nonlinear patterns.
- Can model feature interactions.
- Does not require the same scaling requirements as many linear models.
- Provides feature-importance information.

### Gradient Boosting

An ensemble learning approach that builds models sequentially to improve predictive performance.

It can capture nonlinear relationships but must be evaluated carefully to avoid overfitting.

The final model will be selected based on evaluation results rather than algorithm complexity.

## 12.3 Evaluation Metrics

Accuracy alone is insufficient for this problem because the positive and negative classes may be imbalanced.

The model should be evaluated using:

| Metric | Purpose |
|---|---|
| Precision | Measures how many predicted positive cases are actually positive |
| Recall / Sensitivity | Measures how many actual positive cases are detected |
| Specificity | Measures how many actual negative cases are correctly identified |
| F1-score | Combines precision and recall |
| ROC-AUC | Measures ranking performance across classification thresholds |
| PR-AUC | Evaluates performance with particular attention to the positive class |
| Confusion Matrix | Shows true positives, true negatives, false positives, and false negatives |
| Brier Score | Measures the accuracy of predicted probabilities |

Threshold selection should balance the ability to detect exacerbations against the number of false alerts.

## 12.4 Preventing Data Leakage

The dataset contains repeated observations from the same participants.

Therefore, random row-level train/test splitting can produce misleading results.

The same patient's observations could appear in both training and testing data.

This may allow the model to learn patient-specific patterns rather than generalizable patterns.

The evaluation strategy should therefore respect patient identity.

Group-aware validation methods, such as `StratifiedGroupKFold` where feasible, should be investigated.

Additional checks should include:

- Patient overlap between training and testing sets.
- Features calculated using future information.
- Target-derived predictor columns.
- Duplicate observations.
- Incorrect event timestamp alignment.
- Preprocessing fitted on the complete dataset.
- Information from post-exacerbation measurements.

All preprocessing must be fitted within the training folds.

## 12.5 Model Interpretability

The project should investigate methods to understand which features influence predictions.

Possible approaches include:

- Logistic Regression coefficients.
- Permutation feature importance.
- Tree-based feature importance.
- SHAP, where appropriate.

Feature importance must not be interpreted as proof of causation or clinical significance.

## 12.6 Final ML Deliverables

The ML development stage should produce:

- Reproducible training code.
- Model comparison results.
- Evaluation reports.
- Selected model.
- Saved preprocessing and prediction pipeline.
- Feature schema documentation.
- Model metadata.
- Prediction function for backend integration.

No final algorithm or performance score is established at this stage.

---

# 13. Backend Development

The backend is responsible for connecting the database, machine learning pipeline, and frontend.

Its expected responsibilities include:

- Establishing database connectivity.
- Retrieving patient information.
- Retrieving relevant sensor measurements.
- Preparing the data required for model inference.
- Loading the trained ML model.
- Generating predictions.
- Storing prediction results.
- Creating and managing alerts.
- Providing APIs for frontend communication.

The backend must use the same feature definitions and preprocessing logic as the model training pipeline.

The final API contracts should be established collaboratively between the backend and ML developers.

---

# 14. Frontend Development

The frontend provides the user-facing interface of ExacerbAlert.

Its expected responsibilities include:

- Displaying patient information.
- Presenting relevant physiological measurements.
- Showing prediction results.
- Displaying generated alerts.
- Providing an understandable view of patient information.
- Communicating with backend APIs.

The frontend should retrieve application data through the backend rather than directly accessing the database.

The final interface and visualization requirements will be established during frontend development.

---

# 15. Development Environment Setup

The project uses Python and Conda for environment management.

The repository includes an `environment.yml` file containing the project environment configuration.

## 15.1 Prerequisites

Install:

- Git
- Miniforge or Anaconda
- Python environment support
- JupyterLab

For macOS users, Miniforge is a suitable Conda distribution.

Installation instructions:

https://github.com/conda-forge/miniforge

Check the Mac architecture:

```bash
uname -m
```

Possible outputs:

- `arm64` — Apple Silicon.
- `x86_64` — Intel Mac.

## 15.2 Clone the Repository

```bash
git clone https://github.com/Chirag-hub07/Tech_seva.git
```

Navigate into the repository:

```bash
cd Tech_seva
```

Switch to the main branch:

```bash
git checkout main
```

Pull the latest changes:

```bash
git pull origin main
```

## 15.3 Create the Conda Environment

Inspect the environment file:

```bash
cat environment.yml
```

Create the environment:

```bash
conda env create -f environment.yml
```

Activate the environment using the name specified in the YAML file:

```bash
conda activate exacerbalert
```

If the YAML file contains a machine-specific Windows `prefix`, remove or adjust that local setting before creating the environment on macOS.

Do not arbitrarily change package versions without documenting the reason.

## 15.4 Verify the Environment

```bash
python --version
```

Check the major project dependencies:

```bash
python -c "import pandas, numpy, sklearn, matplotlib, pyarrow; print('Environment OK')"
```

## 15.5 Launch JupyterLab

```bash
jupyter lab
```

Select the correct Python environment/kernel before executing the notebooks.

---

# 16. Running the Project

The main data preparation workflow follows this order:

1. `01_dataset_exploration.ipynb`
2. `02_data_standardization.ipynb`
3. `03_data_cleaning.ipynb`
4. `04_feature_engineering.ipynb`
5. `06_exacerbation_label_creation.ipynb`
6. `07_model_dataset_preparation.ipynb`

Notebook 05 is the separate database-import workflow.

Before running the notebooks:

- Obtain authorized access to the original TOLIFE dataset.
- Place the raw data in the expected directory structure.
- Activate the correct Python environment.
- Verify the notebook input paths.
- Verify that the required dependencies are installed.

## Important: First-Time Setup

Cloning the repository does not automatically download the raw dataset or locally generated Parquet files.

The `.gitignore` configuration excludes sensitive and generated data.

Therefore, a new developer must obtain the authorized dataset separately.

The notebook execution order and expected intermediate files should be checked before running the entire workflow.

If a notebook fails, inspect the traceback and resolve the underlying issue rather than skipping validation or changing preprocessing logic without justification.

---

# 17. Data Management and Security

ExacerbAlert works with health-related patient information.

Data privacy and responsible handling are essential.

The following practices must be followed:

- Never commit raw patient-level data to GitHub.
- Never commit generated patient-level Parquet or CSV files.
- Never commit database passwords or API keys.
- Keep `.env` files outside version control.
- Share patient-level datasets only with authorized team members.
- Use approved access-controlled storage for sensitive files.
- Do not upload sensitive patient information to unapproved external services.
- Preserve the original dataset and its documentation.
- Follow the original dataset's access, licensing, and usage requirements.

The repository's `.gitignore` excludes generated datasets and temporary notebook files.

---

# 18. Team Contributions

ExacerbAlert is being developed collaboratively, with responsibilities distributed across data preprocessing, database development, machine learning, backend development, and frontend development.

| Team Member | Assigned Responsibility |
|---|---|
| **Kartik Sharma** | Data Preprocessing and Database Development |
| **Chirag Virdi** | Data Preprocessing |
| **R. Srikar** | Machine Learning Development |
| **Ayesh Srivastava** | Backend Development |
| **Ayush Kumar** | Frontend Development |

## Individual Contributions

### Kartik Sharma — Data Preprocessing and Database

Responsible for contributing to the data preprocessing workflow and database development.

Key responsibilities and contributions:

- Dataset exploration and understanding.
- Data cleaning and preparation contributions.
- Feature engineering contributions.
- Feature validation.
- Development and maintenance of the Supabase PostgreSQL database.
- Database schema design.
- Importing structured patient information.
- Importing physiological sensor measurements.
- Importing clinical assessment records.
- Importing exacerbation event records.
- Validating database records and participant mappings.

### Chirag Virdi — Data Preprocessing

Responsible for contributing to the data preprocessing and preparation workflow.

Key responsibilities and contributions:

- Dataset exploration and preparation.
- Data standardization.
- Data cleaning contributions.
- Preparation and organization of structured data.
- Supporting the generation of datasets required for subsequent development stages.

### R. Srikar — Machine Learning

Responsible for the machine learning development stage.

Key responsibilities:

- Understanding the prepared feature and label datasets.
- Developing supervised classification models.
- Establishing appropriate patient-aware validation strategies.
- Training and comparing candidate algorithms.
- Evaluating model performance.
- Investigating feature importance and model interpretability.
- Selecting and saving the final prediction pipeline.
- Preparing the model for backend integration.

### Ayesh Srivastava — Backend Development

Responsible for backend development and application integration.

Key responsibilities:

- Developing backend services.
- Implementing API endpoints.
- Connecting the backend with Supabase PostgreSQL.
- Retrieving patient and sensor information.
- Integrating the trained ML prediction pipeline.
- Storing prediction results.
- Implementing alert-related backend functionality.
- Connecting backend services with the frontend.

### Ayush Kumar — Frontend Development

Responsible for frontend development and user interface implementation.

Key responsibilities:

- Developing the application interface.
- Designing patient information views.
- Displaying relevant physiological measurements.
- Presenting prediction results.
- Displaying alerts.
- Integrating frontend components with backend APIs.
- Improving application usability and presentation.

---

# 19. Current Development Status

The following table summarizes the project's current development stage.

| Component | Status |
|---|---|
| Dataset exploration | Completed |
| Data standardization | Completed |
| Data cleaning | Completed for current preprocessing stage |
| Feature engineering | Completed for current preprocessing stage |
| Seven-day label generation | Completed for current preprocessing stage |
| Model dataset preparation | Completed for current preprocessing stage |
| Supabase database schema | Completed |
| Core database data import | Completed |
| Database validation | Completed |
| ML model development | Pending / In progress |
| Model comparison and evaluation | Pending |
| Final model selection | Pending |
| Backend implementation | In progress |
| Frontend implementation | In progress |
| ML and backend integration | Pending |
| Predictions table population | Pending |
| Alerts table population | Pending |
| End-to-end integration testing | Pending |

---

# 20. Future Scope

The remaining development work focuses on completing the machine learning pipeline and integrating it into the application.

Planned improvements include:

### Machine Learning

- Train and compare multiple classification algorithms.
- Improve feature selection and model generalization.
- Evaluate model performance using patient-aware validation.
- Investigate probability calibration.
- Determine an appropriate prediction threshold.
- Evaluate event-level detection performance.
- Save the final model and preprocessing pipeline.

### Backend

- Implement model inference endpoints.
- Integrate the final prediction pipeline.
- Store prediction results.
- Implement alert generation.
- Improve API validation and error handling.

### Frontend

- Develop patient dashboards.
- Display sensor measurement trends.
- Present prediction probabilities.
- Display alerts and their associated information.
- Improve visualization and user experience.

### System Integration

- Connect the frontend, backend, database, and ML model.
- Validate the complete prediction workflow.
- Test data consistency across components.
- Perform end-to-end application testing.
- Document system limitations and deployment requirements.

### Research and Evaluation

- Investigate model generalization.
- Examine false-positive and false-negative predictions.
- Evaluate the impact of class imbalance.
- Investigate model interpretability.
- Document the limitations of the available dataset.

---

# 21. Repository Information

**GitHub Repository:**

https://github.com/Chirag-hub07/Tech_seva

**Primary Branch:** `main`

The repository contains the project's source code, preprocessing notebooks, environment configuration, and documentation.

Raw patient-level data and generated processed datasets are maintained separately and are not included in the GitHub repository.

---

# Project Summary

ExacerbAlert aims to develop a COPD exacerbation early-warning system by combining physiological sensor measurements, clinical information, data preprocessing, feature engineering, and supervised machine learning.

The project has established its foundational data engineering and database components.

The current focus is completing the ML prediction pipeline, developing backend and frontend functionality, and integrating all components into a unified application.

The project is being developed collaboratively:

- **Kartik Sharma:** Data Preprocessing and Database
- **Chirag Virdi:** Data Preprocessing
- **R. Srikar:** Machine Learning
- **Ayesh Srivastava:** Backend
- **Ayush Kumar:** Frontend

The ultimate goal is to develop a reproducible, responsibly evaluated, and integrated early-warning prototype that can estimate the likelihood of a COPD exacerbation within a seven-day prediction horizon.
