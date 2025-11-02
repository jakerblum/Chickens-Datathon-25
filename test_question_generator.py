"""
Test script to generate a question for a discharge medication
"""
import sys
import pandas as pd
from utils.Dataset import MIMICDataset
from example_question_generator import QuestionGenerator

# Initialize dataset - load just a few patients to test quickly
print("Loading patient data...")
dataset = MIMICDataset(
    data_dir="physionet.org/files/mimiciv/3.1",
    max_patients=10  # Just load 10 patients to test quickly
)

# Get all patients
patients = dataset.get_all_patients()
print(f"\nLoaded {len(patients)} patients")

# Find a patient with discharge medications and calculate duration
best_patient = None
best_hadm_id = None
best_medication = None
longest_duration = pd.Timedelta(0)

for patient in patients:
    for admission in patient.admissions:
        hadm_id = admission.hadm_id

        # Get discharge medications
        discharge_meds = dataset.get_discharge_medications(hadm_id)

        if discharge_meds is not None and not discharge_meds.empty:
            # Calculate duration for each medication
            discharge_meds['duration'] = pd.to_datetime(discharge_meds['stoptime']) - pd.to_datetime(discharge_meds['starttime'])

            # Find the medication with longest duration
            for _, med in discharge_meds.iterrows():
                if med['duration'] > longest_duration:
                    longest_duration = med['duration']
                    best_medication = med
                    best_hadm_id = hadm_id
                    best_patient = patient

if best_medication is not None:
    print("\n" + "="*80)
    print("FOUND DISCHARGE MEDICATION WITH LONGEST DURATION")
    print("="*80)
    print(f"\nPatient ID: {best_patient.subject_id}")
    print(f"Admission ID: {best_hadm_id}")
    print(f"\nMedication: {best_medication['drug']}")
    print(f"Dose: {best_medication['dose_val_rx']} {best_medication['dose_unit_rx']}")
    print(f"Route: {best_medication['route']}")
    print(f"Duration: {longest_duration}")
    print(f"Start: {best_medication['starttime']}")
    print(f"Stop: {best_medication['stoptime']}")

    # Generate question using the template
    print("\n" + "="*80)
    print("GENERATING QUESTION FOR PERPLEXITY API")
    print("="*80)

    generator = QuestionGenerator('perplexity_question_templates.json')

    # Generate the side effects question
    question = generator.generate_question(
        category='medications',
        template_id='med_side_effects',
        medication_name=best_medication['drug']
    )

    print(f"\nGenerated Question:")
    print(f"  {question}")

    # Also generate a "how to take" question with dosing info
    print("\nAlso generating 'how to take' question with dosing info:")
    how_to_take = generator.generate_question(
        category='medications',
        template_id='med_how_to_take',
        medication_name=best_medication['drug'],
        dose_val=best_medication['dose_val_rx'],
        dose_unit=best_medication['dose_unit_rx'],
        route=best_medication['route']
    )
    print(f"  {how_to_take}")

    # Show what this would look like for Perplexity API
    print("\n" + "="*80)
    print("PERPLEXITY API PAYLOAD FORMAT")
    print("="*80)

    import json
    perplexity_payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    }

    print(json.dumps(perplexity_payload, indent=2))

else:
    print("\nNo discharge medications found in the sample patients.")
    print("Try increasing max_patients parameter.")
