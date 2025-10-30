#!/usr/bin/env python3
"""
Test script for patient data extraction utilities.
Demonstrates the new extraction methods.
"""

import sys
sys.path.insert(0, 'utils')

from Dataset import MIMICDataset

def main():
    print("Loading MIMIC dataset (limited to 1 patient for testing)...")
    dataset = MIMICDataset(max_patients=1)
    
    # Get first patient
    patient = dataset.get_patient(dataset.get_all_subject_ids()[0])
    if not patient:
        print("No patient found!")
        return
    
    print(f"\nPatient: {patient.subject_id}")
    print(f"Admissions: {len(patient.admissions)}")
    
    # Test timeline extraction
    if patient.admissions:
        hadm_id = patient.admissions[0].hadm_id
        print(f"\n{'='*80}")
        print(f"1. ADMISSION TIMELINE (hadm_id={hadm_id})")
        print(f"{'='*80}")
        timeline = dataset.get_admission_timeline(hadm_id)
        if not timeline.empty:
            print(timeline[['timestamp', 'event_type', 'description']].head(20).to_string())
        else:
            print("No timeline data available")
        
        # Test lab results summary
        print(f"\n{'='*80}")
        print(f"2. LAB RESULTS SUMMARY (hadm_id={hadm_id})")
        print(f"{'='*80}")
        lab_summary = dataset.get_lab_results_summary(hadm_id, include_normal=False)
        print(f"\nPositive/Abnormal results: {len(lab_summary['positive'])}")
        if not lab_summary['positive'].empty:
            print(lab_summary['positive'][['charttime', 'label', 'valuenum', 'flag']].head(10).to_string())
        print(f"\nNegative results: {len(lab_summary['negative'])}")
        if not lab_summary['negative'].empty:
            print(lab_summary['negative'][['charttime', 'label', 'valuenum', 'flag']].head(5).to_string())
        print(f"\nAll flagged results: {len(lab_summary['flagged'])}")
        
        # Test discharge medications
        print(f"\n{'='*80}")
        print(f"3. DISCHARGE MEDICATIONS (hadm_id={hadm_id})")
        print(f"{'='*80}")
        discharge_meds = dataset.get_discharge_medications(hadm_id)
        if not discharge_meds.empty:
            print(discharge_meds[['drug', 'dose_val_rx', 'dose_unit_rx', 'route', 'starttime', 'stoptime']].to_string())
        else:
            print("No discharge medications found")
    
    # Test chief concern search
    print(f"\n{'='*80}")
    print("4. GET PATIENTS BY CHIEF CONCERN: 'angina'")
    print(f"{'='*80}")
    angina_patients = dataset.get_patients_by_chief_concern("angina", max_patients=3)
    print(f"Found {len(angina_patients)} patients with angina")
    for p in angina_patients:
        print(f"  - Patient {p.subject_id}: {len(p.admissions)} admissions")

if __name__ == "__main__":
    main()

