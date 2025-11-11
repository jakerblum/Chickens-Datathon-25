"""
Example script showing how to generate patient-specific questions
from the template JSON file for Perplexity API calls.
"""

import json
import pandas as pd
from typing import List, Dict, Any


class QuestionGenerator:
    """Generate patient-specific questions from templates."""

    def __init__(self, template_file: str = 'perplexity_question_templates.json'):
        """Load question templates from JSON file."""
        with open(template_file, 'r') as f:
            self.data = json.load(f)
        self.templates = self.data['question_templates']

    def generate_question(self, category: str, template_id: str, **kwargs) -> str:
        """
        Generate a specific question by filling in template fields.

        Args:
            category: Question category (e.g., 'medications', 'diagnoses')
            template_id: Specific template ID (e.g., 'med_side_effects')
            **kwargs: Field values to substitute (e.g., medication_name='Furosemide')

        Returns:
            Formatted question string

        Example:
            >>> qg = QuestionGenerator()
            >>> qg.generate_question('medications', 'med_side_effects',
            ...                      medication_name='Furosemide')
            'What are the side effects of Furosemide I should watch for?'
        """
        # Find the template
        templates = self.templates[category]['templates']
        template_obj = next((t for t in templates if t['id'] == template_id), None)

        if not template_obj:
            raise ValueError(f"Template {template_id} not found in category {category}")

        # Check required fields
        missing = [f for f in template_obj['required_fields'] if f not in kwargs]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Fill in the template
        question = template_obj['template'].format(**kwargs)
        return question

    def get_all_templates(self, category: str = None) -> List[Dict]:
        """Get all templates, optionally filtered by category."""
        if category:
            return self.templates[category]['templates']

        all_templates = []
        for cat, data in self.templates.items():
            for template in data['templates']:
                template_copy = template.copy()
                template_copy['category'] = cat
                all_templates.append(template_copy)
        return all_templates


def generate_medication_questions(medications_df: pd.DataFrame,
                                  generator: QuestionGenerator) -> List[Dict[str, str]]:
    """
    Generate questions for all medications in a patient's prescription list.

    Args:
        medications_df: DataFrame from prescriptions.csv with columns:
                       ['drug', 'dose_val_rx', 'dose_unit_rx', 'route', 'form_rx', etc.]
        generator: QuestionGenerator instance

    Returns:
        List of dicts with 'question' and 'context' keys
    """
    questions = []

    for _, med in medications_df.iterrows():
        med_name = med['drug']

        # Question 1: Why was I prescribed this?
        q1 = generator.generate_question(
            'medications', 'med_why_prescribed',
            medication_name=med_name
        )
        questions.append({'question': q1, 'context': f"Medication: {med_name}"})

        # Question 2: Side effects
        q2 = generator.generate_question(
            'medications', 'med_side_effects',
            medication_name=med_name
        )
        questions.append({'question': q2, 'context': f"Medication: {med_name}"})

        # Question 3: How to take (if dosing info available)
        if pd.notna(med['dose_val_rx']) and pd.notna(med['route']):
            q3 = generator.generate_question(
                'medications', 'med_how_to_take',
                medication_name=med_name,
                dose_val=med['dose_val_rx'],
                dose_unit=med['dose_unit_rx'],
                route=med['route']
            )
            questions.append({'question': q3, 'context': f"Medication: {med_name}"})

    return questions


def generate_diagnosis_questions(diagnoses: List[Dict],
                                 generator: QuestionGenerator) -> List[Dict[str, str]]:
    """
    Generate questions for patient diagnoses.

    Args:
        diagnoses: List of diagnosis dicts with 'long_title' and 'seq_num'
        generator: QuestionGenerator instance

    Returns:
        List of dicts with 'question' and 'context' keys
    """
    questions = []

    # Prioritize primary diagnoses (seq_num = 1)
    primary_dx = [d for d in diagnoses if d.get('seq_num') == 1]
    other_dx = [d for d in diagnoses if d.get('seq_num') != 1]

    # Process primary diagnoses first
    for dx in primary_dx[:3]:  # Top 3 primary diagnoses
        dx_name = dx['long_title']

        # What is this condition?
        q1 = generator.generate_question(
            'diagnoses', 'dx_what_is',
            diagnosis_name=dx_name
        )
        questions.append({'question': q1, 'context': f"Primary diagnosis: {dx_name}"})

        # How is it treated?
        q2 = generator.generate_question(
            'diagnoses', 'dx_treatment',
            diagnosis_name=dx_name
        )
        questions.append({'question': q2, 'context': f"Primary diagnosis: {dx_name}"})

        # Symptoms to watch for
        q3 = generator.generate_question(
            'diagnoses', 'dx_symptoms_watch',
            diagnosis_name=dx_name
        )
        questions.append({'question': q3, 'context': f"Primary diagnosis: {dx_name}"})

    return questions


def generate_lab_questions(labs_df: pd.DataFrame,
                          generator: QuestionGenerator) -> List[Dict[str, str]]:
    """
    Generate questions for abnormal lab results.

    Args:
        labs_df: DataFrame with lab results including 'label', 'valuenum',
                'valueuom', 'flag' columns
        generator: QuestionGenerator instance

    Returns:
        List of dicts with 'question' and 'context' keys
    """
    questions = []

    # Filter to abnormal results
    abnormal_labs = labs_df[labs_df['flag'].notna() &
                           (labs_df['flag'] != '') &
                           (labs_df['valuenum'].notna())]

    for _, lab in abnormal_labs.iterrows():
        lab_name = lab['label']
        value = lab['valuenum']
        unit = lab['valueuom'] if pd.notna(lab['valueuom']) else ''
        flag = lab['flag']

        # Why is this abnormal?
        q1 = generator.generate_question(
            'lab_results', 'lab_abnormal_why',
            lab_name=lab_name,
            abnormal_flag=flag,
            value=value,
            unit=unit
        )
        questions.append({'question': q1, 'context': f"Lab: {lab_name} = {value} {unit} ({flag})"})

        # What can I do to improve it?
        q2 = generator.generate_question(
            'lab_results', 'lab_improve',
            lab_name=lab_name
        )
        questions.append({'question': q2, 'context': f"Lab: {lab_name}"})

    return questions


def generate_procedure_questions(procedures: List[Dict],
                                 generator: QuestionGenerator) -> List[Dict[str, str]]:
    """
    Generate questions about procedures.

    Args:
        procedures: List of procedure dicts with 'long_title'
        generator: QuestionGenerator instance

    Returns:
        List of dicts with 'question' and 'context' keys
    """
    questions = []

    for proc in procedures[:5]:  # Top 5 procedures
        proc_name = proc['long_title']

        # Why did I need this?
        q1 = generator.generate_question(
            'procedures', 'proc_why_needed',
            procedure_name=proc_name
        )
        questions.append({'question': q1, 'context': f"Procedure: {proc_name}"})

        # Recovery time
        q2 = generator.generate_question(
            'procedures', 'proc_recovery',
            procedure_name=proc_name
        )
        questions.append({'question': q2, 'context': f"Procedure: {proc_name}"})

    return questions


def generate_multi_factor_questions(patient_data: Dict[str, Any],
                                    generator: QuestionGenerator) -> List[Dict[str, str]]:
    """
    Generate complex questions combining multiple data points.

    Args:
        patient_data: Dict containing:
            - 'medications': List of medication dicts
            - 'diagnoses': List of diagnosis dicts
            - 'labs': DataFrame of lab results
        generator: QuestionGenerator instance

    Returns:
        List of dicts with 'question' and 'context' keys
    """
    questions = []

    meds = patient_data.get('medications', [])
    diagnoses = patient_data.get('diagnoses', [])
    labs = patient_data.get('labs', pd.DataFrame())

    # Medication + Diagnosis combinations
    if meds and diagnoses:
        for med in meds[:3]:
            for dx in diagnoses[:2]:
                q = generator.generate_question(
                    'multi_factor', 'multi_dx_med_match',
                    medication_name=med.get('drug', 'unknown'),
                    diagnosis_name=dx.get('long_title', 'unknown')
                )
                questions.append({
                    'question': q,
                    'context': f"Med-Dx relationship"
                })

    # Medication + Lab combinations
    if meds and not labs.empty:
        abnormal_labs = labs[labs['flag'].notna()]
        for med in meds[:2]:
            for _, lab in abnormal_labs.head(2).iterrows():
                q = generator.generate_question(
                    'multi_factor', 'multi_med_lab_effect',
                    medication_name=med.get('drug', 'unknown'),
                    lab_name=lab['label'],
                    abnormal_flag=lab['flag']
                )
                questions.append({
                    'question': q,
                    'context': f"Med-Lab relationship"
                })

    return questions


def example_usage():
    """Example showing how to use the question generator with patient data."""

    # Initialize generator
    generator = QuestionGenerator('perplexity_question_templates.json')

    # Example 1: Generate a single question
    question = generator.generate_question(
        category='medications',
        template_id='med_side_effects',
        medication_name='Metoprolol'
    )
    print(f"Single question: {question}\n")

    # Example 2: Generate questions from a medications DataFrame
    # (This would come from your patient data loading)
    medications_df = pd.DataFrame([
        {'drug': 'Furosemide', 'dose_val_rx': 40, 'dose_unit_rx': 'mg', 'route': 'PO'},
        {'drug': 'Spironolactone', 'dose_val_rx': 25, 'dose_unit_rx': 'mg', 'route': 'PO'},
    ])

    med_questions = generate_medication_questions(medications_df, generator)
    print("Medication questions:")
    for q in med_questions[:3]:
        print(f"  - {q['question']}")
    print()

    # Example 3: Generate questions for diagnoses
    diagnoses = [
        {'long_title': 'Congestive heart failure', 'seq_num': 1},
        {'long_title': 'Hypertension', 'seq_num': 2},
    ]

    dx_questions = generate_diagnosis_questions(diagnoses, generator)
    print("Diagnosis questions:")
    for q in dx_questions[:3]:
        print(f"  - {q['question']}")
    print()

    # Example 4: Format for Perplexity API
    all_questions = med_questions + dx_questions

    # Create the format for Perplexity API
    perplexity_payload = [
        {
            "role": "user",
            "content": q['question']
        }
        for q in all_questions
    ]

    print("Perplexity API payload structure:")
    print(json.dumps(perplexity_payload[:2], indent=2))


if __name__ == '__main__':
    example_usage()
