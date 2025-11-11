import argparse
import json
import os
import re
from perplexity import Perplexity
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils.example_question_generator import QuestionGenerator

os.environ["PERPLEXITY_API_KEY"] = "REDACTED_FOR_PRIVACY"

def normalize_drug_name(drug_name):
    """Extract and normalize drug name from patient data"""
    drug_name = drug_name.lower()
    # Extract brand name if in parentheses
    brand_match = re.search(r'\(([^)]+)\)', drug_name)
    brand = brand_match.group(1) if brand_match else None
    # Remove parentheses and extract base name
    generic = re.sub(r'\([^)]*\)', '', drug_name).strip()
    generic = re.sub(r'[^a-z0-9-]', '', generic)
    return generic, brand

def find_medication_visual_info(patient_drug_name, medications_db):
    """Match patient drug to medication database for visual information"""
    generic, brand = normalize_drug_name(patient_drug_name)

    for med in medications_db.get('medications', []):
        # Check generic name match - require EXACT match to avoid false positives
        # (e.g., "Sodium Chloride" shouldn't match "Potassium Chloride")
        med_generic_normalized = med['generic_name'].lower().replace(' ', '').replace('-', '')
        if generic == med_generic_normalized:
            return med

        # Check brand name match
        if brand:
            for brand_name in med.get('brand_names', []):
                brand_normalized = brand_name.lower().replace(' ', '').replace('-', '')
                if brand.replace(' ', '').replace('-', '') == brand_normalized:
                    return med

        # Check aliases
        for alias in med.get('aliases', []):
            alias_normalized = alias.lower().replace(' ', '').replace('-', '')
            if generic == alias_normalized:
                return med

    return None

def enrich_patient_data_with_visuals(data):
    """Add visual medication information to patient data"""
    try:
        with open("Medications/Medications.json", "r") as f:
            meds_db = json.load(f)

        enriched_meds = []
        for med in data.get('discharge_medications', []):
            drug_name = med.get('drug', '')
            visual_info = find_medication_visual_info(drug_name, meds_db)

            enriched_med = med.copy()
            if visual_info:
                enriched_med['physical_description'] = visual_info.get('physical_description')
                enriched_med['image_path'] = visual_info.get('image_path')

            enriched_meds.append(enriched_med)

        # Add enriched medications to data
        data['enriched_medications'] = enriched_meds
    except FileNotFoundError:
        # If medications database doesn't exist, continue without enrichment
        pass

    return data

def create_gantt_timeline_from_json(timeline_list, hadm_id=None):
    """
    Create a single-row horizontal timeline with non-overlapping bars and arrows.
    Returns the HTML div string for embedding.
    """
    if not timeline_list:
        return "<p>No timeline data available</p>"

    # Convert to DataFrame
    timeline_df = pd.DataFrame(timeline_list)
    timeline_df['timestamp'] = pd.to_datetime(timeline_df['timestamp'])

    # Color scheme
    color_map = {
        'Admission': '#2E86AB',
        'Diagnosis': '#A23B72',
        'Procedure': '#F18F01',
        'Lab Tests': '#C73E1D',
        'Medication': '#6A994E',
        'Discharge': '#2E86AB'
    }

    # Filter out events after discharge
    discharge_events = timeline_df[timeline_df['category'] == 'Discharge']
    if not discharge_events.empty:
        discharge_time = discharge_events['timestamp'].iloc[0]
        events_filtered = timeline_df[timeline_df['timestamp'] <= discharge_time].copy()
    else:
        events_filtered = timeline_df.copy()

    # Sort events by timestamp
    events_sorted = events_filtered.sort_values(['timestamp']).reset_index(drop=True)

    # Prepare data for timeline
    gantt_data = []

    for idx, row in events_sorted.iterrows():
        start_pos = idx
        end_pos = idx + 0.9

        gantt_data.append({
            'Task': 'Hospital Stay',
            'Start': start_pos,
            'Finish': end_pos,
            'Description': row['title'],
            'Details': row['details'],
            'Category': row['category'],
            'Count': row['count'],
            'Timestamp': row['timestamp'].strftime('%Y-%m-%d %H:%M')
        })

    gantt_df = pd.DataFrame(gantt_data)

    # Create figure
    fig = go.Figure()

    # Track which categories we've shown in legend
    legend_shown = set()

    # Add bars
    for idx, row in gantt_df.iterrows():
        category = row['Category']
        show_in_legend = category not in legend_shown
        if show_in_legend:
            legend_shown.add(category)

        fig.add_trace(go.Bar(
            x=[row['Finish'] - row['Start']],
            y=['Hospital Stay'],
            base=row['Start'],
            orientation='h',
            marker=dict(
                color=color_map.get(category, '#999999'),
                line=dict(color='white', width=2)
            ),
            name=category,
            text=row['Description'],
            textposition='inside',
            textfont=dict(size=11, color='white', family='Arial Black'),
            insidetextanchor='middle',
            hovertemplate=(
                f"<b>{row['Description']}</b><br><br>"
                f"{row['Details']}<br><br>"
                f"<i>{row['Timestamp']}</i>"
                "<extra></extra>"
            ),
            showlegend=bool(show_in_legend)
        ))

        # Add arrow between bars (except after last bar)
        if idx < len(gantt_df) - 1:
            arrow_start_x = row['Finish']
            arrow_end_x = gantt_df.iloc[idx + 1]['Start']

            fig.add_annotation(
                x=arrow_end_x,
                y='Hospital Stay',
                ax=arrow_start_x,
                ay='Hospital Stay',
                xref='x',
                yref='y',
                axref='x',
                ayref='y',
                showarrow=True,
                arrowhead=2,
                arrowsize=1.5,
                arrowwidth=2,
                arrowcolor='gray'
            )

    # Update layout
    title_text = 'Patient Hospital Stay Timeline'
    if hadm_id:
        title_text += f' - Admission {hadm_id}'

    fig.update_layout(
        title=title_text,
        height=250,
        xaxis=dict(
            title='Event Sequence',
            showticklabels=False,
            showgrid=False,
            zeroline=False
        ),
        yaxis=dict(
            title='',
            showticklabels=False,
            showgrid=False
        ),
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='center',
            x=0.5
        ),
        hovermode='closest',
        plot_bgcolor='white',
        barmode='overlay',
        bargap=0
    )

    # Return as HTML div
    return fig.to_html(include_plotlyjs='cdn', div_id='timeline-chart')

def generate_medication_faqs(medications, generator):
    """
    Generate FAQ questions for each PO medication using QuestionGenerator.

    Args:
        medications: List of medication dicts from discharge_medications
        generator: QuestionGenerator instance

    Returns:
        Dict mapping medication names to their FAQ questions
    """
    medication_faqs = {}

    for med in medications:
        route = med.get('route', '').upper()

        # Only generate FAQs for PO (oral) medications
        if route != 'PO':
            continue

        drug_name = med.get('drug', '')
        if not drug_name:
            continue

        # Generate list of questions for this medication
        questions = []

        # Question templates to use for each PO medication
        question_types = [
            ('med_why_prescribed', {}),
            ('med_side_effects', {}),
            ('med_can_stop', {}),
            ('med_duration', {}),
            ('med_food_interactions', {}),
        ]

        # Add dosing-specific questions if we have the data
        dose_val = med.get('dose_val_rx', '') or med.get('dose', '')
        dose_unit = med.get('dose_unit_rx', '') or med.get('dose_unit', '')

        if dose_val and dose_unit:
            question_types.append(('med_how_to_take', {
                'dose_val': dose_val,
                'dose_unit': dose_unit,
                'route': route
            }))
            question_types.append(('med_dose_change', {
                'dose_val': dose_val,
                'dose_unit': dose_unit
            }))

        # Generate each question
        for template_id, extra_params in question_types:
            try:
                question = generator.generate_question(
                    category='medications',
                    template_id=template_id,
                    medication_name=drug_name,
                    **extra_params
                )
                questions.append(question)
            except Exception as e:
                print(f"Warning: Could not generate question {template_id} for {drug_name}: {e}")
                continue

        # Check for drug interactions with other PO medications
        other_po_meds = [m.get('drug') for m in medications
                        if m.get('route', '').upper() == 'PO' and m.get('drug') != drug_name]

        if other_po_meds:
            # Generate interaction question with the first other PO medication
            try:
                interaction_q = generator.generate_question(
                    category='medications',
                    template_id='med_interactions',
                    medication_1=drug_name,
                    medication_2=other_po_meds[0]
                )
                questions.append(interaction_q)
            except Exception as e:
                print(f"Warning: Could not generate interaction question for {drug_name}: {e}")

        medication_faqs[drug_name] = questions

    return medication_faqs

def load_filtered_labs_list():
    """Load the list of labs to include from JSON file"""
    try:
        with open("filtered_labs_list.json", "r") as f:
            labs_config = json.load(f)
            return set(labs_config.get('included_labs', []))
    except FileNotFoundError:
        print("Warning: filtered_labs_list.json not found. Including all labs.")
        return None

def filter_lab_results(lab_results, included_labs):
    """Filter lab results to only include specified tests"""
    if included_labs is None:
        return lab_results

    filtered = []
    for lab in lab_results:
        test_name = lab.get('test_name', '')
        if test_name in included_labs:
            filtered.append(lab)

    print(f"Filtered labs: {len(filtered)}/{len(lab_results)} tests (keeping only specified labs)")
    return filtered

def summarize_data(data, detail_level):
    # Load filtered labs list
    included_labs = load_filtered_labs_list()

    # Filter lab results before processing
    if included_labs:
        data['lab_results'] = filter_lab_results(data.get('lab_results', []), included_labs)

    # Enrich patient data with visual medication information
    data = enrich_patient_data_with_visuals(data)

    client = Perplexity()
    with open("utils/perplexity_question_templates.json", "r") as f:
        question_templates = json.load(f)

    # Initialize QuestionGenerator
    generator = QuestionGenerator('utils/perplexity_question_templates.json')

    # Generate medication-specific FAQ questions for PO medications
    discharge_meds = data.get('discharge_medications', [])
    medication_faqs = generate_medication_faqs(discharge_meds, generator)

    print(f"Generated questions for {len(medication_faqs)} PO medications:")
    for med_name, questions in medication_faqs.items():
        print(f"  - {med_name}: {len(questions)} questions")

    # Create a simplified payload with only essential information
    # Remove large/unnecessary fields to reduce payload size
    simplified_data = {
        'hadm_id': data.get('hadm_id'),
        'timeline': data.get('timeline', [])[:10],  # Limit timeline to first 10 events
        'lab_results': data.get('lab_results', []),
        'discharge_medications': data.get('discharge_medications', []),
        'enriched_medications': data.get('enriched_medications', []),
        'medication_faqs': medication_faqs,
        'diagnoses': data.get('diagnoses', []),
        'procedures': data.get('procedures', [])
    }

    system_prompt = """
    You are a professional patient advocate.  You are given a JSON object containing the patient's data. Only provide information that you can verify from your search results, and clearly state if certain details are not available. Return ONLY valid JSON with these exact keys:

    {
      "visit_summary": "brief 2-3 sentence summary of visit",
      "lab_results_summary": [{"test_name": "...", "significance": "what this means", "abnormal_explanation": "why this is abnormal (if status is abnormal)"}],
      "medication_purposes": {
        "drug_name_1": "what it's for and how it works",
        "drug_name_2": "what it's for and how it works"
      },
      "medication_faqs": {
        "drug_name_1": [{"question": "exact question from input", "answer": "your researched answer"}],
        "drug_name_2": [{"question": "exact question from input", "answer": "your researched answer"}]
      },
      "frequently_asked_questions": [{"question": "...", "answer": "..."}]
    }



    CRITICAL RULES:
    1. lab_results_summary: You MUST return one entry for EVERY lab test found in the `lab_results` input data. The `test_name` in your JSON output must EXACTLY match the `test_name` from the input data.
       - The 'significance' should be a brief, 1-2 sentence patient-friendly explanation of what the test measures (e.g., "This test checks your kidney function" or "This measures sugar in your blood"), even if the result is normal.
       - The 'abnormal_explanation' field should ONLY be included if the lab status is "abnormal". When abnormal, explain WHY it might be abnormal based on the patient's medical information inside the JSON, referencing specific events. Example: "This can be elevated after the cardiac procedure you underwent".
       - If the lab is normal, do NOT include the 'abnormal_explanation' field at all.
    2. medication_purposes: For EACH drug in discharge_medications, provide a brief purpose/description
    3. medication_faqs: For drugs in medication_faqs input, answer those EXACT questions only
    4. Use exact drug names as keys (copy from discharge_medications.drug and medication_faqs keys)
    5. Each FAQ answer should be 2-4 sentences maximum
    6. frequently_asked_questions: Generate EXACTLY 7 general questions about diagnoses, procedures, and discharge
    7. DO NOT put medication questions in frequently_asked_questions
    8. IMPORTANT: All FAQ questions and answers MUST be written in FIRST/SECOND PERSON from the patient's perspective
       - Use "I", "you", "your", "my" (e.g., "Why should I...", "You should...", "Your condition...")
       - NEVER use third person like "the patient", "their", "they"
       - Write as if speaking directly to the patient
    """

    detail_prompt = f"Use detail level {detail_level}: 1=5th grade language, 2=high school, 3=college level."

    # Convert to JSON string and check size
    data_json_str = json.dumps(simplified_data, indent=2)
    print(f"\nPayload size: {len(data_json_str):,} characters")

    data_prompt = f"Please summarize this patient data:\n\n{data_json_str}"

    print(f"Sending request to Perplexity...")

    response = client.chat.completions.create(
        model="sonar",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": detail_prompt},
            {"role": "user", "content": data_prompt}
        ],
        search_domain_filter = ["my.clevelandclinic.org", "mayoclinic.org", "medlineplus.gov", "webmd.com", "pubmed.ncbi.nlm.nih.gov", "nih.gov", "drugs.com"],
        timeout=300.0  # 5 minutes timeout
    )

    # Extract citations from the response
    # Perplexity API returns citations in the response object
    citations = []

    # Save full response for debugging
    try:
        if hasattr(response, 'model_dump'):
            response_dict = response.model_dump()
            with open('perplexity_response_debug.json', 'w', encoding='utf-8') as f:
                json.dump(response_dict, f, indent=2, default=str)
            print(f"✓ Full response saved to perplexity_response_debug.json")
    except Exception as e:
        print(f"Could not save debug response: {e}")

    # Check various possible locations for citations in the response
    if hasattr(response, 'citations') and response.citations:
        citations = response.citations
        print(f"✓ Found {len(citations)} citations in response.citations")
    elif hasattr(response.choices[0].message, 'citations') and response.choices[0].message.citations:
        citations = response.choices[0].message.citations
        print(f"✓ Found {len(citations)} citations in message.citations")
    elif hasattr(response, 'model_extra') and response.model_extra and 'citations' in response.model_extra:
        citations = response.model_extra['citations']
        print(f"✓ Found {len(citations)} citations in model_extra")

    # If no citations found yet, try to access as dict
    if not citations:
        try:
            response_dict = response.model_dump() if hasattr(response, 'model_dump') else dict(response)
            citations = response_dict.get('citations', [])
            if citations:
                print(f"✓ Found {len(citations)} citations in response dict")
            else:
                print(f"⚠ No citations found in response")
                print(f"  Available keys: {list(response_dict.keys())}")
        except Exception as e:
            print(f"⚠ Could not extract citations: {e}")

    # Also extract search_results if available for richer citation display
    search_results = []
    try:
        response_dict = response.model_dump() if hasattr(response, 'model_dump') else dict(response)
        search_results = response_dict.get('search_results', [])
        if search_results:
            print(f"✓ Found {len(search_results)} detailed search results")
    except:
        pass

    # Return both content, citations, and search results
    return {
        'content': response.choices[0].message.content,
        'citations': citations,
        'search_results': search_results
    }

def generate_html_page(data, summary_json, detail_level, output_path, citations=None):
    """Generate interactive HTML page with all information"""

    # Parse summary JSON
    try:
        summary = json.loads(summary_json)
    except json.JSONDecodeError as e:
        print(f"\nERROR: Failed to parse JSON response from Perplexity.")
        print(f"JSON Error: {e}")
        print(f"\nFirst 500 characters of response:")
        print(summary_json[:500])
        print(f"\n... (showing error location) ...")
        # Show context around the error
        error_pos = e.pos if hasattr(e, 'pos') else 0
        start = max(0, error_pos - 100)
        end = min(len(summary_json), error_pos + 100)
        print(f"Context around error position {error_pos}:")
        print(summary_json[start:end])

        # If the response is wrapped in markdown code blocks
        import re
        json_match = re.search(r'```json\s*(\{.*\})\s*```', summary_json, re.DOTALL)
        if json_match:
            try:
                summary = json.loads(json_match.group(1))
            except json.JSONDecodeError as e2:
                print(f"\nERROR: Even after extracting from markdown, JSON is malformed.")
                print(f"JSON Error: {e2}")
                print(f"\nSaving raw response to 'perplexity_error_response.txt' for debugging...")
                with open('perplexity_error_response.txt', 'w', encoding='utf-8') as f:
                    f.write(summary_json)
                raise Exception("Perplexity returned malformed JSON. Check 'perplexity_error_response.txt' for the raw response.")
        else:
            print(f"\nWARNING: Could not parse JSON and no markdown code block found.")
            print(f"Saving raw response to 'perplexity_error_response.txt' for debugging...")
            with open('perplexity_error_response.txt', 'w', encoding='utf-8') as f:
                f.write(summary_json)
            summary = {
                "visit_summary": summary_json,
                "lab_results_summary": [],
                "medication_summary": [],
                "frequently_asked_questions": []
            }

    # Debug: Print summary structure
    print(f"\nDEBUG - Summary keys: {summary.keys()}")
    if summary.get('lab_results_summary'):
        print(f"DEBUG - First lab result keys: {summary['lab_results_summary'][0].keys() if summary['lab_results_summary'] else 'empty'}")
    if summary.get('medication_summary'):
        print(f"DEBUG - First medication keys: {summary['medication_summary'][0].keys() if summary['medication_summary'] else 'empty'}")

    # Generate timeline HTML
    timeline_html = create_gantt_timeline_from_json(data.get('timeline', []), data.get('hadm_id'))

    # Build HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Patient Summary - Admission {data.get('hadm_id', 'N/A')}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}

        header {{
            background: linear-gradient(135deg, #2E86AB 0%, #1a5276 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}

        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}

        .content {{
            padding: 40px;
        }}

        .section {{
            margin-bottom: 40px;
            padding: 30px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 5px solid #2E86AB;
        }}

        .section h2 {{
            color: #2E86AB;
            margin-bottom: 20px;
            font-size: 2em;
            border-bottom: 3px solid #2E86AB;
            padding-bottom: 10px;
        }}

        .timeline-section {{
            background: white;
            border: 2px solid #e0e0e0;
            padding: 20px;
            margin-bottom: 40px;
            border-radius: 10px;
        }}

        .summary-text {{
            font-size: 1.1em;
            line-height: 1.8;
            color: #555;
            background: white;
            padding: 20px;
            border-radius: 8px;
        }}

        .lab-result-card, .medication-card {{
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .lab-result-card:hover, .medication-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}

        .lab-result-card h3, .medication-card h3 {{
            color: #A23B72;
            margin-bottom: 10px;
            font-size: 1.3em;
        }}

        .lab-result-card .measurement {{
            font-size: 1.5em;
            font-weight: bold;
            color: #2E86AB;
            margin: 10px 0;
        }}

        .lab-result-card .result {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            margin-bottom: 10px;
        }}

        .result.normal {{
            background: #d4edda;
            color: #155724;
        }}

        .result.abnormal {{
            background: #f8d7da;
            color: #721c24;
        }}

        .reference-range {{
            font-size: 0.9em;
            color: #666;
            margin: 10px 0;
            font-weight: 500;
        }}

        .lab-bar-container {{
            margin: 15px 0;
            padding: 10px 0;
        }}

        .lab-bar-background {{
            position: relative;
            height: 30px;
            background: #f0f0f0;
            border-radius: 15px;
            overflow: visible;
            margin-bottom: 5px;
        }}

        .lab-bar-normal-range {{
            position: absolute;
            top: 0;
            height: 100%;
            background: linear-gradient(to right, #d4edda, #c3e6cb);
            border: 2px solid #28a745;
            border-radius: 15px;
        }}

        .lab-bar-normal-range .lab-bar-label-min,
        .lab-bar-normal-range .lab-bar-label-max {{
            font-weight: 600;
            color: #28a745;
            font-size: 0.85em;
        }}

        .lab-bar-marker {{
            position: absolute;
            top: -5px;
            width: 4px;
            height: 40px;
            transform: translateX(-2px);
            border-radius: 2px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            z-index: 10;
        }}

        .lab-bar-marker::after {{
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 12px;
            height: 12px;
            background: inherit;
            border-radius: 50%;
            border: 2px solid white;
        }}

        .lab-bar-value-label {{
            position: absolute;
            top: -30px;
            left: 50%;
            transform: translateX(-50%);
            color: white;
            padding: 4px 10px;
            border-radius: 5px;
            font-size: 0.8em;
            font-weight: bold;
            white-space: nowrap;
            pointer-events: none;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        }}

        .lab-bar-labels {{
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 0.85em;
            color: #666;
            margin-top: 30px;
            padding: 0 5px;
        }}

        .lab-bar-label-normal {{
            font-size: 0.8em;
            color: #28a745;
            font-weight: 600;
            text-align: center;
        }}

        .medication-card .dose {{
            font-size: 1.2em;
            color: #6A994E;
            font-weight: bold;
            margin: 10px 0;
        }}

        .medication-card .purpose {{
            color: #666;
            font-style: italic;
            margin-top: 10px;
        }}

        .medication-card .pill-description {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px;
            margin-top: 15px;
            border-radius: 5px;
        }}

        .medication-card .pill-image {{
            margin-top: 15px;
            text-align: center;
        }}

        .medication-card .pill-image img {{
            max-width: 300px;
            border-radius: 8px;
            border: 3px solid #ddd;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}

        .medication-faqs {{
            margin-top: 20px;
            border-top: 2px solid #e0e0e0;
            padding-top: 15px;
        }}

        .medication-faqs-header {{
            font-weight: bold;
            color: #6A994E;
            font-size: 1.1em;
            cursor: pointer;
            display: flex;
            align-items: center;
            padding: 10px;
            background: #f0f7ed;
            border-radius: 5px;
            margin-bottom: 10px;
            transition: background 0.2s;
        }}

        .medication-faqs-header:hover {{
            background: #e1f0d9;
        }}

        .medication-faqs-header::before {{
            content: '\u25BC';
            margin-right: 10px;
            font-size: 0.8em;
            transition: transform 0.3s;
        }}

        .medication-faqs-header.collapsed::before {{
            transform: rotate(-90deg);
        }}

        .medication-faqs-content {{
            max-height: 1000px;
            overflow: hidden;
            transition: max-height 0.3s ease-in-out, opacity 0.3s ease-in-out;
            opacity: 1;
        }}

        .medication-faqs-content.collapsed {{
            max-height: 0;
            opacity: 0;
        }}

        .medication-faq-item {{
            margin: 10px 0;
            padding: 15px;
            background: #fafafa;
            border-radius: 5px;
            border-left: 3px solid #6A994E;
        }}

        .medication-faq-item .question {{
            font-size: 1.05em;
            color: #2E86AB;
            font-weight: 600;
            margin-bottom: 8px;
        }}

        .medication-faq-item .question::before {{
            content: "Q: ";
            color: #A23B72;
            margin-right: 5px;
        }}

        .medication-faq-item .answer {{
            font-size: 0.95em;
            color: #555;
            line-height: 1.6;
        }}

        .medication-faq-item .answer::before {{
            content: "A: ";
            color: #6A994E;
            font-weight: bold;
            margin-right: 5px;
        }}

        .faq-section {{
            background: white;
        }}

        .faq-item {{
            margin-bottom: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #6A994E;
        }}

        .faq-item .question {{
            font-size: 1.3em;
            color: #2E86AB;
            font-weight: bold;
            margin-bottom: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
        }}

        .faq-item .question::before {{
            content: "Q: ";
            color: #A23B72;
            margin-right: 10px;
            font-size: 1.2em;
        }}

        .faq-item .answer {{
            font-size: 1.1em;
            color: #555;
            line-height: 1.8;
            margin-top: 10px;
        }}

        .faq-item .answer::before {{
            content: "A: ";
            color: #6A994E;
            font-weight: bold;
            margin-right: 5px;
        }}

        .badge {{
            display: inline-block;
            padding: 5px 12px;
            background: #2E86AB;
            color: white;
            border-radius: 20px;
            font-size: 0.9em;
            margin-left: 10px;
        }}

        .citations-list {{
            list-style-position: outside;
            padding-left: 25px;
            margin: 0;
        }}

        .citation-item {{
            margin-bottom: 15px;
            padding: 10px;
            background: white;
            border-radius: 5px;
            transition: background 0.2s;
        }}

        .citation-item:hover {{
            background: #f0f7ff;
        }}

        .citation-item a {{
            color: #2E86AB;
            text-decoration: none;
            font-size: 1em;
            line-height: 1.6;
            word-wrap: break-word;
        }}

        .citation-item a:hover {{
            text-decoration: underline;
            color: #1a5276;
        }}

        footer {{
            background: #2c3e50;
            color: white;
            text-align: center;
            padding: 20px;
            margin-top: 40px;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}

        @media (max-width: 768px) {{
            .content {{
                padding: 20px;
            }}

            header h1 {{
                font-size: 1.8em;
            }}

            .section {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Patient Hospital Stay Summary</h1>
            <p>Admission ID: {data.get('hadm_id', 'N/A')} | Detail Level: {detail_level}</p>
        </header>

        <div class="content">
            <!-- Timeline Section -->
            <div class="timeline-section">
                {timeline_html}
            </div>

            <!-- Visit Summary Section -->
            <div class="section">
                <h2>Visit Summary</h2>
                <div class="summary-text">
                    {summary.get('visit_summary', 'No summary available')}
                </div>
            </div>

            <!-- Lab Results Section -->
            <div class="section">
                <h2>Lab Results <span class="badge">{len([lab for lab in data.get('lab_results', []) if lab.get('value') and lab.get('value') != 'N/A'])} Tests</span></h2>
                <div class="grid">
"""

    # Add lab results - iterate through ORIGINAL data, get descriptions from AI summary
    # Create a lookup dict for AI descriptions and abnormal explanations
    ai_lab_descriptions = {}
    ai_lab_abnormal_explanations = {}
    for lab in summary.get('lab_results_summary', []):
        test_name = lab.get('test') or lab.get('test_name') or ''
        significance = lab.get('significance') or lab.get('description') or lab.get('measures') or ''
        abnormal_explanation = lab.get('abnormal_explanation', '')
        if test_name:
            ai_lab_descriptions[test_name.lower()] = significance
            if abnormal_explanation:
                ai_lab_abnormal_explanations[test_name.lower()] = abnormal_explanation

    # Sort lab results by timestamp (chronological order)
    # Using enumerate to preserve original order for ties
    lab_results_with_index = [(idx, lab) for idx, lab in enumerate(data.get('lab_results', []))]
    sorted_labs = sorted(lab_results_with_index, key=lambda x: (x[1].get('timestamp', ''), x[0]))

    # Now iterate through ALL original lab results in chronological order
    for idx, orig_lab in sorted_labs:
        # Get ALL values from original patient data
        test_name = orig_lab.get('test_name', 'Unknown Test')
        ref_range = orig_lab.get('reference_range', 'N/A')
        unit = orig_lab.get('unit', '')
        measurement = orig_lab.get('value', 'N/A')
        lab_status = orig_lab.get('status', 'normal').lower()
        timestamp = orig_lab.get('timestamp', '')

        # Format timestamp as human-readable
        formatted_timestamp = ''
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_timestamp = dt.strftime('%b %d, %Y at %I:%M %p')
            except:
                formatted_timestamp = timestamp

        # Skip labs with no numeric value (like text-only results)
        if measurement == 'N/A' or measurement is None or (isinstance(measurement, str) and not measurement.replace('.', '').replace('-', '').isdigit()):
            continue

        # Get description/significance from AI summary if available
        significance = ai_lab_descriptions.get(test_name.lower(), '')

        # Get abnormal explanation if this lab is abnormal
        abnormal_explanation = ''
        if lab_status == 'abnormal':
            abnormal_explanation = ai_lab_abnormal_explanations.get(test_name.lower(), '')

        # Try to parse numeric values for graph
        numeric_value = None
        range_min = None
        range_max = None

        try:
            numeric_value = float(measurement)
            # Parse reference range like "0.4-1.1" or "8.4-10.3"
            if ref_range and ref_range != 'N/A' and '-' in str(ref_range):
                range_parts = str(ref_range).split('-')
                range_min = float(range_parts[0])
                range_max = float(range_parts[1])
        except (ValueError, TypeError, IndexError):
            pass

        # Determine result class based on actual lab status flag
        result_class = 'abnormal' if lab_status == 'abnormal' else 'normal'

        # Format measurement with units (all from original data)
        if unit and unit.strip():
            measurement_with_units = f"{measurement} {unit}"
        else:
            measurement_with_units = str(measurement)

        # Generate visual bar graph if we have numeric data
        bar_html = ''
        if numeric_value is not None and range_min is not None and range_max is not None:
            # Calculate position as percentage
            range_span = range_max - range_min

            # Handle edge case where range_min equals range_max
            if range_span == 0:
                # Create a small artificial range around the single value
                range_span = max(abs(range_min) * 0.1, 1.0)  # 10% of value or 1.0, whichever is larger
                range_min = range_min - range_span / 2
                range_max = range_max + range_span / 2

            if range_span > 0:
                # Dynamically extend the visual range based on patient's value
                # Start with 20% padding on each side
                padding_factor = 0.2
                visual_min = range_min - (range_span * padding_factor)
                visual_max = range_max + (range_span * padding_factor)

                # If patient value is outside the padded range, extend to include it
                if numeric_value < visual_min:
                    # Value is too low - extend the lower bound
                    visual_min = numeric_value - (range_span * 0.1)
                elif numeric_value > visual_max:
                    # Value is too high - extend the upper bound
                    visual_max = numeric_value + (range_span * 0.1)

                visual_span = visual_max - visual_min

                # Safety check: ensure visual_span is positive
                if visual_span <= 0:
                    visual_span = range_span * 1.4  # Fallback to 140% of normal range
                    visual_min = range_min - (range_span * 0.2)
                    visual_max = range_max + (range_span * 0.2)

                # Calculate percentages for the green normal range
                normal_start_pct = ((range_min - visual_min) / visual_span) * 100
                normal_width_pct = (range_span / visual_span) * 100

                # Calculate patient value position
                value_pct = ((numeric_value - visual_min) / visual_span) * 100

                # Ensure value is within 0-100% (should always be true now)
                value_pct = max(0, min(100, value_pct))

                bar_color = '#28a745' if result_class == 'normal' else '#dc3545'
                label_bg_color = 'rgba(40, 167, 69, 0.9)' if result_class == 'normal' else 'rgba(220, 53, 69, 0.9)'

                # Add value label on the marker
                value_label = f"{numeric_value}"

                bar_html = f"""
                    <div class="lab-bar-container">
                        <div class="lab-bar-background">
                            <div class="lab-bar-normal-range" style="left: {normal_start_pct}%; width: {normal_width_pct}%;">
                                <span class="lab-bar-label-min" style="position: absolute; left: 0; bottom: -25px;">{range_min}</span>
                                <span class="lab-bar-label-max" style="position: absolute; right: 0; bottom: -25px;">{range_max}</span>
                            </div>
                            <div class="lab-bar-marker" style="left: {value_pct}%; background-color: {bar_color};" title="Your value: {value_label}">
                                <span class="lab-bar-value-label" style="background: {label_bg_color};">{value_label}</span>
                            </div>
                        </div>
                        <div class="lab-bar-labels">
                            <span class="lab-bar-label-normal">Normal Range</span>
                        </div>
                    </div>
                """

        # Build abnormal explanation HTML if exists
        abnormal_html = ''
        if abnormal_explanation:
            abnormal_html = f"""
                        <div style="background: #fff3cd; border-left: 4px solid #ff9800; padding: 12px; margin-top: 15px; border-radius: 5px;">
                            <div style="color: #856404; font-weight: bold; margin-bottom: 8px;">Why is this abnormal?</div>
                            <div style="color: #856404; line-height: 1.6;">{abnormal_explanation}</div>
                            <div style="color: #856404; font-style: italic; margin-top: 10px; font-size: 0.9em;">⚠️ Please consult your care provider for more information.</div>
                        </div>"""

        html_content += f"""
                    <div class="lab-result-card">
                        <h3>{test_name}</h3>
                        {f'<div style="color: #666; font-size: 0.9em; margin-bottom: 10px;"><strong>Test Date:</strong> {formatted_timestamp}</div>' if formatted_timestamp else ''}
                        <div class="measurement">{measurement_with_units}</div>
                        <div class="result {result_class}">{lab_status.capitalize()}</div>
                        <div class="reference-range">Reference Range: {ref_range} {unit if unit else ''}</div>
                        {bar_html}
                        <p>{significance}</p>
                        {abnormal_html}
                    </div>
"""

    html_content += """
                </div>
            </div>

            <!-- Medications Section -->
            <div class="section">
                <h2>Medications <span class="badge">{} Prescribed</span></h2>
""".format(len(data.get('discharge_medications', [])))

    # Add medications - use ORIGINAL data for name/dose, AI data for purpose/FAQs
    medication_purposes = summary.get('medication_purposes', {})
    medication_faqs_dict = summary.get('medication_faqs', {})

    for idx, med in enumerate(data.get('discharge_medications', [])):
        # Get name and dose from ORIGINAL patient data (no AI confounds)
        med_name = med.get('drug', 'Unknown Medication')
        dose_val = med.get('dose', '')
        dose_unit = med.get('dose_unit', '')
        route = med.get('route', '')
        frequency = med.get('frequency', '')

        # Format dose with units, route, and frequency
        if dose_val and dose_unit:
            dose = f"{dose_val} {dose_unit}"
            if route:
                dose += f" ({route})"
            # Add frequency if available
            if frequency:
                # Parse frequency to make it more readable
                # e.g., "1.0 doses per 24 hours" -> "every 24 hours"
                if 'doses per' in str(frequency):
                    freq_parts = str(frequency).split('doses per')
                    if len(freq_parts) == 2:
                        num_doses = freq_parts[0].strip()
                        time_period = freq_parts[1].strip()
                        dose += f" - {num_doses} time(s) per {time_period}"
                else:
                    dose += f" - {frequency}"
        else:
            dose = 'Dose not specified'

        # Get purpose from AI output (this is where AI adds value)
        purpose = medication_purposes.get(med_name, '')

        # Get FAQs from AI output (only for PO medications)
        med_faqs = medication_faqs_dict.get(med_name, [])

        html_content += f"""
                <div class="medication-card">
                    <h3>{med_name}</h3>
                    <div class="dose">{dose}</div>
                    <div class="purpose">{purpose}</div>
"""

        # Add visual information if available from enriched data
        enriched_meds = data.get('enriched_medications', [])
        for enriched in enriched_meds:
            # Normalize both names for exact matching (to avoid false positives like Sodium Chloride matching Potassium Chloride)
            enriched_drug = enriched.get('drug', '').lower().replace(' ', '').replace('-', '')
            search_name = med_name.lower().replace(' ', '').replace('-', '')

            # Use exact match or check if the full normalized names match
            # This prevents "sodiumchloride" from matching "potassiumchloride"
            if search_name == enriched_drug:

                if enriched.get('physical_description'):
                    html_content += f"""
                    <div class="pill-description">
                        <strong>Pill Appearance:</strong> {enriched.get('physical_description')}
                    </div>
"""
                if enriched.get('image_path'):
                    # Convert image to base64 for embedding
                    import os
                    import base64
                    img_path = enriched.get('image_path')

                    try:
                        # Read image and convert to base64
                        with open(img_path, 'rb') as img_file:
                            img_data = img_file.read()
                            img_base64 = base64.b64encode(img_data).decode('utf-8')

                        # Determine image MIME type from extension
                        ext = os.path.splitext(img_path)[1].lower()
                        mime_types = {
                            '.jpg': 'image/jpeg',
                            '.jpeg': 'image/jpeg',
                            '.png': 'image/png',
                            '.gif': 'image/gif',
                            '.webp': 'image/webp'
                        }
                        mime_type = mime_types.get(ext, 'image/jpeg')

                        # Create data URI
                        img_data_uri = f"data:{mime_type};base64,{img_base64}"

                        html_content += f"""
                    <div class="pill-image">
                        <img src="{img_data_uri}" alt="{med_name} pill image" style="max-width: 300px;">
                    </div>
"""
                    except Exception as e:
                        # If image can't be loaded, show error message
                        html_content += f"""
                    <div class="pill-image">
                        <p style='color: #999; font-style: italic;'>Image not available</p>
                    </div>
"""
                break

        # Add medication-specific FAQs (open by default for PDF conversion compatibility)
        if med_faqs:
            html_content += f"""
                    <div class="medication-faqs">
                        <div class="medication-faqs-header" onclick="toggleMedicationFAQ({idx})">
                            Frequently Asked Questions ({len(med_faqs)})
                        </div>
                        <div class="medication-faqs-content" id="med-faq-{idx}">
"""
            for faq in med_faqs:
                question = faq.get('question', '')
                answer = faq.get('answer', '')
                html_content += f"""
                            <div class="medication-faq-item">
                                <div class="question">{question}</div>
                                <div class="answer">{answer}</div>
                            </div>
"""
            html_content += """
                        </div>
                    </div>
"""

        html_content += """
                </div>
"""

    html_content += """
            </div>

            <!-- FAQ Section -->
            <div class="section faq-section">
                <h2>Frequently Asked Questions</h2>
"""

    # Add FAQs
    for faq in summary.get('frequently_asked_questions', []):
        html_content += f"""
                <div class="faq-item">
                    <div class="question">{faq.get('question', '')}</div>
                    <div class="answer">{faq.get('answer', '')}</div>
                </div>
"""

    html_content += """
            </div>
"""

    # Add citations section if citations are provided and available
    if citations and len(citations) > 0:
        html_content += """
            <!-- Citations Section -->
            <div class="section">
                <h2>References & Citations</h2>
                <p style="margin-bottom: 15px; color: #666;">The information in this summary was gathered from the following trusted medical sources:</p>
                <ol class="citations-list">
"""
        for idx, citation in enumerate(citations):
            # Handle both string citations and dictionary citations (search_results)
            if isinstance(citation, str):
                citation_url = citation
                citation_text = citation
                citation_snippet = None
            elif isinstance(citation, dict):
                citation_url = citation.get('url', citation.get('link', ''))
                citation_text = citation.get('title', citation_url)
                citation_snippet = citation.get('snippet')
            else:
                continue

            # Build citation HTML with optional snippet
            if citation_snippet:
                html_content += f"""
                    <li class="citation-item">
                        <a href="{citation_url}" target="_blank" rel="noopener noreferrer"><strong>{citation_text}</strong></a>
                        <div style="color: #666; font-size: 0.9em; margin-top: 5px; line-height: 1.4;">{citation_snippet}</div>
                    </li>
"""
            else:
                html_content += f"""
                    <li class="citation-item">
                        <a href="{citation_url}" target="_blank" rel="noopener noreferrer">{citation_text}</a>
                    </li>
"""
        html_content += """
                </ol>
            </div>
"""

    html_content += """
        </div>

        <footer>
            <p>&copy; 2025 Patient Care Summary | Generated with AI-assisted medical interpretation</p>
            <p style="font-size: 0.9em; margin-top: 10px; opacity: 0.8;">This summary is for informational purposes only. Always consult with your healthcare provider.</p>
        </footer>
    </div>

    <script>
        function toggleMedicationFAQ(idx) {
            const header = document.querySelectorAll('.medication-faqs-header')[idx];
            const content = document.getElementById('med-faq-' + idx);

            if (content.classList.contains('collapsed')) {
                content.classList.remove('collapsed');
                header.classList.remove('collapsed');
            } else {
                content.classList.add('collapsed');
                header.classList.add('collapsed');
            }
        }
    </script>
</body>
</html>
"""

    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✓ Interactive HTML page generated: {output_path}")

    # Also save the parsed summary JSON for debugging
    debug_json_path = output_path.replace('.html', '_debug.json')
    with open(debug_json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"✓ Debug JSON saved: {debug_json_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_data", type=str, required=True, help="Path to patient JSON file")
    parser.add_argument("--detail_level", type=int, required=True, choices=[1, 2, 3], help="Detail level (1=basic, 2=enhanced, 3=learner)")
    parser.add_argument("--output", type=str, default=None, help="Output HTML file path (default: patient_summary_<hadm_id>.html)")
    parser.add_argument("--show_citations", action="store_true", help="Display all citations at the bottom of the HTML page")
    args = parser.parse_args()

    with open(args.input_data, "r") as f:
        data = json.load(f)

    # Generate summary from Perplexity
    print("Generating patient summary...")
    response_data = summarize_data(data, args.detail_level)

    # Extract summary and citations
    summary_json = response_data['content']

    # Use search_results if available (has titles), otherwise fall back to citations (just URLs)
    citations = None
    if args.show_citations:
        search_results = response_data.get('search_results', [])
        if search_results:
            citations = search_results
            print(f"Using {len(citations)} detailed search results for citations")
        else:
            citations = response_data.get('citations', [])
            print(f"Using {len(citations)} URL citations")

    # Determine output path
    if args.output is None:
        hadm_id = data.get('hadm_id', 'unknown')
        output_path = f"patient_summary_{hadm_id}_filtered.html"
    else:
        output_path = args.output

    # Generate HTML page
    generate_html_page(data, summary_json, args.detail_level, output_path, citations)
