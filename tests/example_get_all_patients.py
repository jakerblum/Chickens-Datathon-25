#!/usr/bin/env python3
"""
Example: How to get all patients from a MIMICDataset instance.
"""

import sys
sys.path.insert(0, 'utils')

from Dataset import MIMICDataset

# Initialize with a small subset (e.g., 10 patients)
print("Initializing dataset with 10 patients...")
dataset = MIMICDataset(max_patients=10)

# Method 1: Using the new get_all_patients() convenience method (SIMPLEST)
print("\nMethod 1: Using get_all_patients() convenience method (RECOMMENDED)")
print("="*70)

all_patients = dataset.get_all_patients()
print(f"Retrieved {len(all_patients)} patient records")
for patient in all_patients:
    print(f"  - Patient {patient.subject_id}: {len(patient.admissions)} admissions")


# Method 2: Get all subject IDs, then retrieve each patient
print("\n\nMethod 2: Using get_all_subject_ids() and get_patient()")
print("="*70)

subject_ids = dataset.get_all_subject_ids()
print(f"Found {len(subject_ids)} patients in dataset")

# Get all patients as a list
all_patients_v2 = []
for subject_id in subject_ids:
    patient = dataset.get_patient(subject_id)
    if patient:
        all_patients_v2.append(patient)

print(f"Retrieved {len(all_patients_v2)} patient records")


# Method 3: List comprehension (more Pythonic)
print("\n\nMethod 3: Using list comprehension")
print("="*70)

all_patients_v3 = [
    dataset.get_patient(sid) 
    for sid in dataset.get_all_subject_ids()
    if dataset.get_patient(sid) is not None
]

print(f"Retrieved {len(all_patients_v3)} patient records using list comprehension")


# Method 4: Check dataset length first
print("\n\nMethod 4: Check dataset size")
print("="*70)

print(f"Dataset contains {len(dataset)} patients")
print(f"Number of subject IDs available: {len(dataset.get_all_subject_ids())}")


# Example: Process all patients
print("\n\nExample: Process all patients")
print("="*70)

all_patients = dataset.get_all_patients()
print(f"Processing {len(all_patients)} patients...")

total_admissions = sum(len(p.admissions) for p in all_patients)
print(f"Total admissions across all patients: {total_admissions}")

for patient in all_patients:
    print(f"\nPatient {patient.subject_id}:")
    print(f"  - Gender: {patient.demographics.get('gender')}")
    print(f"  - Age: {patient.demographics.get('anchor_age')}")
    print(f"  - Admissions: {len(patient.admissions)}")
    for i, adm in enumerate(patient.admissions, 1):
        print(f"    Admission {i}: {adm.admission_info.get('admission_type')} ({len(adm.diagnoses)} diagnoses)")
