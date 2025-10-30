# MIMIC-IV Dataset Extraction Usage Examples

This document provides examples for using the patient data extraction utilities.

## Overview

The `MIMICDataset` class now includes several methods to extract specific aspects of patient records:

1. **`get_admission_timeline(hadm_id)`** - Chronological timeline of admission events
2. **`get_lab_results_summary(hadm_id, include_normal=False)`** - Organized lab results (positive/negative/abnormal)
3. **`get_discharge_medications(hadm_id)`** - Medications at discharge
4. **`get_patients_by_chief_concern(concern, max_patients=10)`** - Find patients by diagnosis/chief concern

## Examples

### 1. Get Admission Timeline

```python
from utils.Dataset import MIMICDataset

dataset = MIMICDataset(max_patients=5)
patient = dataset.get_patient(10000032)
hadm_id = patient.admissions[0].hadm_id

timeline = dataset.get_admission_timeline(hadm_id)
print(timeline[['timestamp', 'event_type', 'description']])
```

Returns a DataFrame with:
- `timestamp`: When the event occurred
- `event_type`: Type (Admission, Diagnosis, Procedure, Medication, Lab Result, Discharge)
- `description`: Human-readable description
- `details`: Full details as string

### 2. Get Lab Results Summary

```python
lab_summary = dataset.get_lab_results_summary(hadm_id, include_normal=False)

# Positive/abnormal results
print(lab_summary['positive'][['charttime', 'label', 'valuenum', 'flag']])

# Negative results
print(lab_summary['negative'][['charttime', 'label', 'valuenum', 'flag']])

# All flagged results
print(lab_summary['flagged'])

# All lab results
print(lab_summary['all'])
```

Returns a dictionary with DataFrames:
- `positive`: Lab results with HIGH/ABNORMAL/POSITIVE flags
- `negative`: Lab results with LOW/NEGATIVE/NORMAL flags
- `flagged`: All results with any flag
- `all`: All lab results sorted by time

### 3. Get Discharge Medications

```python
discharge_meds = dataset.get_discharge_medications(hadm_id)
print(discharge_meds[['drug', 'dose_val_rx', 'dose_unit_rx', 'route', 'starttime', 'stoptime']])
```

Returns a DataFrame of medications that:
- Have no stop time (ongoing)
- Stop after discharge time
- Continue after discharge

### 4. Get Patients by Chief Concern

```python
# Search by description (case-insensitive, partial match)
angina_patients = dataset.get_patients_by_chief_concern("angina", max_patients=10)

# Search by exact ICD code
cad_patients = dataset.get_patients_by_chief_concern("41401", max_patients=10, search_description=False)

for patient in angina_patients:
    print(f"Patient {patient.subject_id}: {len(patient.admissions)} admissions")
```

Searches diagnosis descriptions and ICD codes to find matching patients.

## Notes

- **Physician Notes**: MIMIC-IV notes are in a separate module that requires additional access. The current dataset does not include notes in the core hospital/ICU modules.

- **Date Shifting**: All dates are shifted for de-identification. Use the `anchor_year_group` field physician demographics to understand the actual time period.

- **Performance**: For large datasets, use filtering (max_patients, admission_type_filter, diagnosis_filter) to speed up loading.

