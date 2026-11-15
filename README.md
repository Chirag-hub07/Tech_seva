# Tech_seva

## ExacerbAlert – COPD Context-Aware Healthcare System

ExacerbAlert is a healthcare research project focused on monitoring longitudinal COPD patient data, identifying changes in health indicators, and developing an early-warning system for potential exacerbations.

### Project Status

- Dataset exploration and initial data-quality auditing completed.
- Data preprocessing and standardization in progress.
- Machine learning pipeline and application development planned.

### Dataset

The project uses the TOLIFE Clinical Health Indices Dataset V1.0.

Dataset: https://zenodo.org/records/16642439

Raw healthcare data is excluded from GitHub.

### Environment Setup

```bash
conda env create -f environment.yml
conda activate exacerbalert
```

Launch JupyterLab:

```bash
jupyter lab
```

### Current Notebook

`notebooks/01_dataset_exploration.ipynb`

Contains dataset inventory, exploratory analysis, and initial data-quality audits.