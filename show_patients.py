#!/usr/bin/env python3
"""
Display patient records from MIMIC-IV dataset.

This script loads and displays patient records from the MIMIC-IV dataset with
hierarchical organization (patient -> admissions -> ICU stays). You can filter
by admission type, diagnosis codes, and limit the number of patients.

Usage:
    python show_patients.py [max_patients] [admission_type_filter] [diagnosis_filter]

Arguments:
    max_patients (int, optional):
        Maximum number of patients to load and display. Default: 1
        Example: python show_patients.py 5
    
    admission_type_filter (str, optional):
        Filter patients by admission type. Must match one of the valid types exactly.
        Default: None (loads all admission types)
        Example: python show_patients.py 5 EMERGENCY
    
    diagnosis_filter (str, optional):
        Filter patients by ICD diagnosis code(s). Can be:
        - A single ICD code (e.g., "41401" for coronary artery disease)
        - A regex pattern (e.g., "^414" for all codes starting with 414)
        - Multiple codes as comma-separated string (not yet implemented in command line)
        Default: None (loads all diagnoses)
        Example: python show_patients.py 5 EMERGENCY "41401"

Available Admission Types:
    The following admission types are available in MIMIC-IV:
    
    - EW EMER.                      (Emergency Department admission)
    - EU OBSERVATION                (Emergency Unit observation)
    - OBSERVATION ADMIT             (Observation admission)
    - URGENT                        (Urgent admission)
    - SURGICAL SAME DAY ADMISSION   (Same-day surgical admission)
    - DIRECT OBSERVATION            (Direct observation)
    - DIRECT EMER.                  (Direct emergency)
    - ELECTIVE                      (Elective admission)
    - AMBULATORY OBSERVATION        (Ambulatory observation)

Examples:
    # Show 1 patient record (default)
    python show_patients.py
    
    # Show 5 patient records
    python show_patients.py 5
    
    # Show 10 emergency patients only
    python show_patients.py 10 "EW EMER."
    
    # Show 5 elective patients with a specific diagnosis
    python show_patients.py 5 ELECTIVE "41401"
    
    # Show urgent patients matching a diagnosis pattern
    python show_patients.py 10 URGENT "^414"

Notes:
    - Large datasets may take several minutes to load
    - ICU time-series data is only loaded for small datasets (≤10 admissions)
    - The script has a 5-minute timeout to prevent hanging
    - Diagnosis filter supports regex patterns for flexible matching
    
Date Shifting (De-identification):
    MIMIC-IV shifts all dates forward by a random offset (typically ~165-265 years) for each
    patient to preserve privacy while maintaining relative timing. For example, a date showing
    as "2180-05-06" corresponds to an actual date in the anchor_year_group period (e.g., 
    "2014 - 2016"). All dates for a given patient are shifted by the same offset, so time
    differences and sequences are preserved. The anchor_year_group field shows the actual
    time period when the patient was admitted.
"""

import sys
sys.path.insert(0, 'utils')

from Dataset import MIMICDataset

def main():
    import sys
    
    # Default: load first 5 patients
    max_patients = 5
    admission_filter = None
    diagnosis_filter = None
    
    # Parse command line arguments for filtering
    if len(sys.argv) > 1:
        max_patients = int(sys.argv[1])
    if len(sys.argv) > 2:
        admission_filter = sys.argv[2]
    if len(sys.argv) > 3:
        diagnosis_filter = sys.argv[3]
    
    print("Initializing MIMIC dataset...")
    if max_patients or admission_filter or diagnosis_filter:
        print(f"  - Max patients: {max_patients}")
        print(f"  - Admission type filter: {admission_filter}")
        print(f"  - Diagnosis filter: {diagnosis_filter}")
    
    dataset = MIMICDataset(
        max_patients=max_patients if max_patients else None,
        admission_type_filter=admission_filter,
        diagnosis_filter=diagnosis_filter
    )
    
    print("\n" + "="*80)
    print("First 5 Patient Records:")
    print("="*80 + "\n")
    
    subject_ids = dataset.get_all_subject_ids()[:5]
    
    for i, subject_id in enumerate(subject_ids, 1):
        print(f"\n{i}. Patient Record")
        print("-" * 80)
        patient = dataset.get_patient(subject_id)
        if patient:
            print(patient)
            print(f"  Demographics:")
            print(f"    - Gender: {patient.demographics.get('gender', 'N/A')}")
            print(f"    - Age: {patient.demographics.get('anchor_age', 'N/A')}")
            print(f"    - Year Group: {patient.demographics.get('anchor_year_group', 'N/A')}")
            print(f"    - Date of Death: {patient.demographics.get('dod', 'N/A')}")
            print(f"  Number of admissions: {len(patient.admissions)}")
            
            for j, adm in enumerate(patient.admissions, 1):
                print(f"\n  Admission {j} (hadm_id={adm.hadm_id}):")
                print(f"    - Type: {adm.admission_info.get('admission_type', 'N/A')}")
                print(f"    - Admission Time: {adm.admission_info.get('admittime', 'N/A')} (shifted)")
                print(f"    - Discharge Time: {adm.admission_info.get('dischtime', 'N/A')} (shifted)")
                print(f"    - Location: {adm.admission_info.get('admission_location', 'N/A')} -> {adm.admission_info.get('discharge_location', 'N/A')}")
                print(f"    - Insurance: {adm.admission_info.get('insurance', 'N/A')}")
                print(f"    - Race: {adm.admission_info.get('race', 'N/A')}")
                print(f"    - Diagnoses: {len(adm.diagnoses)} ICD codes")
                if adm.diagnoses:
                    print(f"      Sample: {', '.join([d.get('icd_code', '') for d in adm.diagnoses[:3]])}")
                print(f"    - Procedures: {len(adm.procedures)} ICD procedure codes")
                if adm.procedures:
                    print(f"      Sample: {', '.join([p.get('icd_code', '') for p in adm.procedures[:3]])}")
                print(f"    - Medications: {len(adm.medications) if adm.medications is not None else 0} prescriptions")
                print(f"    - Lab results: {len(adm.lab_results) if adm.lab_results is not None else 0} lab events")
                print(f"    - Microbiology: {len(adm.microbiology) if adm.microbiology is not None else 0} events")
                print(f"    - ICU stays: {len(adm.icu_stays)}")
                
                for k, stay in enumerate(adm.icu_stays, 1):
                    print(f"\n      ICU Stay {k} (stay_id={stay.stay_id}):")
                    print(f"        - Unit: {stay.stay_info.get('first_careunit', 'N/A')}")
                    print(f"        - Admission: {stay.stay_info.get('intime', 'N/A')} (shifted)")
                    print(f"        - Discharge: {stay.stay_info.get('outtime', 'N/A')} (shifted)")
                    print(f"        - Length of Stay: {stay.stay_info.get('los', 'N/A')} days")
                    print(f"        - Vital signs: {len(stay.vital_signs) if stay.vital_signs is not None else 0} measurements")
                    print(f"        - Medications: {len(stay.medications) if stay.medications is not None else 0} input events")
                    print(f"        - Outputs: {len(stay.outputs) if stay.outputs is not None else 0} output events")
                    print(f"        - Procedures: {len(stay.procedures) if stay.procedures is not None else 0} procedure events")

def main():
    # Check for help flag
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        print(__doc__)
        return
    
    # Default: load just 1 patient
    max_patients = 1
    admission_filter = None
    diagnosis_filter = None
    
    # Parse command line arguments for filtering
    if len(sys.argv) > 1:
        max_patients = int(sys.argv[1])
    if len(sys.argv) > 2:
        admission_filter = sys.argv[2]
    if len(sys.argv) > 3:
        diagnosis_filter = sys.argv[3]
    
    print("Initializing MIMIC dataset...")
    print(f"  - Max patients: {max_patients}")
    if admission_filter:
        print(f"  - Admission type filter: {admission_filter}")
    if diagnosis_filter:
        print(f"  - Diagnosis filter: {diagnosis_filter}")
    print()
    
    dataset = MIMICDataset(
        max_patients=max_patients if max_patients else None,
        admission_type_filter=admission_filter,
        diagnosis_filter=diagnosis_filter,
        eager_load=True  # Load all data upfront
    )
    
    print("\n" + "="*80)
    print(f"Patient Record(s):")
    print("="*80 + "\n")
    
    subject_ids = dataset.get_all_subject_ids()[:max_patients]
    
    for i, subject_id in enumerate(subject_ids, 1):
        print(f"\n{i}. Patient Record")
        print("-" * 80)
        patient = dataset.get_patient(subject_id)
        if patient:
            print(patient)
            print(f"\n  Demographics:")
            print(f"    - Gender: {patient.demographics.get('gender', 'N/A')}")
            print(f"    - Age: {patient.demographics.get('anchor_age', 'N/A')}")
            year_group = patient.demographics.get('anchor_year_group', 'N/A')
            anchor_year = patient.demographics.get('anchor_year', 'N/A')
            print(f"    - Actual Time Period: {year_group} (dates shifted by ~{int(anchor_year) - 2015 if isinstance(anchor_year, (int, float)) else '?'} years for de-identification)")
            print(f"    - Date of Death: {patient.demographics.get('dod', 'N/A')} (shifted)")
            print(f"\n  Number of admissions: {len(patient.admissions)}")
            
            for j, adm in enumerate(patient.admissions, 1):
                print(f"\n  Admission {j} (hadm_id={adm.hadm_id}):")
                print(f"    - Type: {adm.admission_info.get('admission_type', 'N/A')}")
                print(f"    - Admission Time: {adm.admission_info.get('admittime', 'N/A')} (shifted)")
                print(f"    - Discharge Time: {adm.admission_info.get('dischtime', 'N/A')} (shifted)")
                print(f"    - Location: {adm.admission_info.get('admission_location', 'N/A')} -> {adm.admission_info.get('discharge_location', 'N/A')}")
                print(f"    - Insurance: {adm.admission_info.get('insurance', 'N/A')}")
                print(f"    - Race: {adm.admission_info.get('race', 'N/A')}")
                print(f"    - Diagnoses: {len(adm.diagnoses)} ICD codes")
                if adm.diagnoses:
                    sample_codes = [d.get('icd_code', '') for d in adm.diagnoses[:5]]
                    print(f"      Sample codes: {', '.join(sample_codes)}")
                print(f"    - Procedures: {len(adm.procedures)} ICD procedure codes")
                if adm.procedures:
                    sample_codes = [p.get('icd_code', '') for p in adm.procedures[:5]]
                    print(f"      Sample codes: {', '.join(sample_codes)}")
                print(f"    - Medications: {len(adm.medications) if adm.medications is not None else 0} prescriptions")
                if adm.medications is not None and len(adm.medications) > 0:
                    sample_drugs = adm.medications['drug'].dropna().unique()[:3]
                    print(f"      Sample drugs: {', '.join(sample_drugs)}")
                print(f"    - Lab results: {len(adm.lab_results) if adm.lab_results is not None else 0} lab events")
                print(f"    - Microbiology: {len(adm.microbiology) if adm.microbiology is not None else 0} events")
                print(f"    - ICU stays: {len(adm.icu_stays)}")
                
                for k, stay in enumerate(adm.icu_stays, 1):
                    print(f"\n      ICU Stay {k} (stay_id={stay.stay_id}):")
                    print(f"        - Unit: {stay.stay_info.get('first_careunit', 'N/A')}")
                    print(f"        - Admission: {stay.stay_info.get('intime', 'N/A')} (shifted)")
                    print(f"        - Discharge: {stay.stay_info.get('outtime', 'N/A')} (shifted)")
                    print(f"        - Length of Stay: {stay.stay_info.get('los', 'N/A')} days")
                    print(f"        - Vital signs: {len(stay.vital_signs) if stay.vital_signs is not None else 0} measurements")
                    print(f"        - Medications: {len(stay.medications) if stay.medications is not None else 0} input events")
                    print(f"        - Outputs: {len(stay.outputs) if stay.outputs is not None else 0} output events")
                    print(f"        - Procedures: {len(stay.procedures) if stay.procedures is not None else 0} procedure events")
        else:
            print(f"  ERROR: Could not load patient {subject_id}")


if __name__ == "__main__":
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Dataset loading took too long!")
    
    # Set a 5 minute timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(300)  # 5 minutes
    
    try:
        main()
    except TimeoutError:
        print("\nERROR: Dataset loading timed out after 5 minutes.")
        print("Try filtering by admission type or diagnosis to reduce data size.")
        sys.exit(1)
    finally:
        signal.alarm(0)  # Cancel the alarm

