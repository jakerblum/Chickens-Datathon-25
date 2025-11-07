import argparse
import json
import os
import re
from perplexity import Perplexity
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

os.environ["PERPLEXITY_API_KEY"] = "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"

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
        # Check generic name match
        med_generic_normalized = med['generic_name'].lower().replace(' ', '').replace('-', '')
        if generic in med_generic_normalized or med_generic_normalized in generic:
            return med

        # Check brand name match
        if brand:
            for brand_name in med.get('brand_names', []):
                if brand.lower() in brand_name.lower() or brand_name.lower() in brand.lower():
                    return med

        # Check aliases
        for alias in med.get('aliases', []):
            alias_normalized = alias.lower().replace(' ', '').replace('-', '')
            if generic in alias_normalized or alias_normalized in generic:
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

def summarize_data(data, detail_level):
    # Enrich patient data with visual medication information
    data = enrich_patient_data_with_visuals(data)

    client = Perplexity()
    with open("utils/perplexity_question_templates.json", "r") as f:
        question_templates = json.load(f)

    system_prompt = f"""
    You are a professional patient advocate that is tasked with interpreting patient chart data from a provider's perspective and translating it into an easy-to-digest format for a patient.
    You are given a JSON object containing the patient's data. You are to summarize the data in a way that is easy to understand for a patient. Only provide information that you can verify from your search results, and clearly state if certain details are not available.

    Please return your response in a JSON object with the following keys:
    - visit_summary: A summary and interpretation of the patient's visit. The visit is included in input data as a timeline of events under the 'timeline' key.
    - lab_results_summary: A list of ALL test results (both abnormal and normal) from the patient's lab results, alongside what each lab test measures and what the result signifies.
                           Include EVERY lab result provided in the 'lab_results' data, not just pertinent ones. Be sure not to make any diagnoses or draw any conclusions from the lab results, just say theoretically what the result signals and why it might be important to the patient. Reference ranges are provided.
                           Input data includes a 'lab_results' key which contains a list of lab results, reference ranges, and flags.
    - medication_summary: A list of all of the pertinent medications the patient is taking, alongside what the medication is for and what the dosage is. Please be sure to give a human-readable description of what the medication is for and how it works.
                          Input data includes a 'discharge_medications' key which contains a list of medications the patient is taking, alongside what the medication is for and what the dosage is.
                          If 'enriched_medications' is available with physical_description and image_path fields, include this visual information in the medication summary for accessibility.
    - frequently_asked_questions: Please provide a list of frequently asked questions and answers according to the following specification and the patient's data. {question_templates}
                                  When answering "How should I take [medication]?" questions, if enriched_medications contains physical_description, include it in the answer for pill identification (e.g., "This medication is a blue oval tablet with 'GILEAD' and '701' imprinted on one side").
                                  If an image_path is available, also include it in the response.

    """

    detail_prompt = f"Responses should follow either 'basic mode' (1), 'enhanced mode' (2), or 'learner mode' (3) with increasing detail and complexity. Imagine basic mode to be 5th grade competency and learner mode to be someone taking a college level course. For 'basic mode' (1), use a largelanguage model to simplify the language of the response."
    data_prompt = f"Please summarize the following data: {data}. The data is a JSON object containing the patient's data. Please use detail of level {detail_level}."

    response = client.chat.completions.create(
        model="sonar",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": detail_prompt},
            {"role": "user", "content": data_prompt}
        ],
        search_domain_filter = ["my.clevelandclinic.org", "mayoclinic.org", "medlineplus.gov", "webmd.com", "pubmed.ncbi.nlm.nih.gov", "nih.gov", "drugs.com"]
    )
    return response.choices[0].message.content

def generate_html_page(data, summary_json, detail_level, output_path):
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
                <h2>Lab Results <span class="badge">{len(summary.get('lab_results_summary', []))} Tests</span></h2>
                <div class="grid">
"""

    # Add lab results with reference ranges from original data
    for lab in summary.get('lab_results_summary', []):
        # Get test name from AI summary
        test_name = lab.get('test') or lab.get('test_name') or 'Unknown Test'

        # Get description/significance from AI summary (this is what we want from AI)
        significance = lab.get('significance') or lab.get('description') or lab.get('measures') or ''

        # Find matching lab result in original data - ALL values come from here
        ref_range = 'N/A'
        numeric_value = None
        range_min = None
        range_max = None
        lab_status = 'normal'  # Default to normal
        unit = ''
        measurement = 'N/A'  # Default if no match found
        found_in_original = False

        for orig_lab in data.get('lab_results', []):
            if orig_lab.get('test_name', '').lower() == test_name.lower():
                # ALL actual data values come from original patient data
                ref_range = orig_lab.get('reference_range', 'N/A')
                unit = orig_lab.get('unit', '')
                measurement = orig_lab.get('value', 'N/A')
                lab_status = orig_lab.get('status', 'normal').lower()
                found_in_original = True

                try:
                    numeric_value = float(orig_lab.get('value', 0))
                    # Parse reference range like "0.4-1.1" or "8.4-10.3"
                    if ref_range and ref_range != 'N/A' and '-' in str(ref_range):
                        range_parts = str(ref_range).split('-')
                        range_min = float(range_parts[0])
                        range_max = float(range_parts[1])
                except (ValueError, TypeError, IndexError):
                    pass
                break

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

        html_content += f"""
                    <div class="lab-result-card">
                        <h3>{test_name}</h3>
                        <div class="measurement">{measurement_with_units}</div>
                        <div class="result {result_class}">{lab_status.capitalize()}</div>
                        <div class="reference-range">Reference Range: {ref_range} {unit if unit else ''}</div>
                        {bar_html}
                        <p>{significance}</p>
                    </div>
"""

    html_content += """
                </div>
            </div>

            <!-- Medications Section -->
            <div class="section">
                <h2>Medications <span class="badge">{} Prescribed</span></h2>
""".format(len(summary.get('medication_summary', [])))

    # Add medications
    for med in summary.get('medication_summary', []):
        # Handle both possible field name formats
        med_name = med.get('name') or med.get('medication') or med.get('drug') or 'Unknown Medication'
        dose = med.get('dose') or med.get('dosage') or 'Dose not specified'
        purpose = med.get('purpose') or med.get('description') or ''

        html_content += f"""
                <div class="medication-card">
                    <h3>{med_name}</h3>
                    <div class="dose">{dose}</div>
                    <div class="purpose">{purpose}</div>
"""

        # Add visual information if available from enriched data
        enriched_meds = data.get('enriched_medications', [])
        for enriched in enriched_meds:
            # More flexible matching
            enriched_drug = enriched.get('drug', '').lower()
            search_name = med_name.lower()

            # Try matching by removing common prefixes and checking if either contains the other
            if (search_name in enriched_drug or enriched_drug in search_name or
                any(part in enriched_drug for part in search_name.split() if len(part) > 3)):

                if enriched.get('physical_description'):
                    html_content += f"""
                    <div class="pill-description">
                        <strong>Pill Appearance:</strong> {enriched.get('physical_description')}
                    </div>
"""
                if enriched.get('image_path'):
                    # Convert relative path to absolute or use as-is
                    import os
                    img_path = enriched.get('image_path')
                    # Convert backslashes to forward slashes for web compatibility
                    img_path = img_path.replace('\\', '/')

                    html_content += f"""
                    <div class="pill-image">
                        <img src="{img_path}" alt="{med_name} pill image" onerror="this.style.display='none'; this.parentElement.innerHTML='<p style=\\'color: #999; font-style: italic;\\'>Image not available</p>';">
                    </div>
"""
                break

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
        </div>

        <footer>
            <p>&copy; 2025 Patient Care Summary | Generated with AI-assisted medical interpretation</p>
            <p style="font-size: 0.9em; margin-top: 10px; opacity: 0.8;">This summary is for informational purposes only. Always consult with your healthcare provider.</p>
        </footer>
    </div>
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
    args = parser.parse_args()

    with open(args.input_data, "r") as f:
        data = json.load(f)

    # Generate summary from Perplexity
    print("Generating patient summary...")
    summary_json = summarize_data(data, args.detail_level)

    # Determine output path
    if args.output is None:
        hadm_id = data.get('hadm_id', 'unknown')
        output_path = f"patient_summary_{hadm_id}.html"
    else:
        output_path = args.output

    # Generate HTML page
    generate_html_page(data, summary_json, args.detail_level, output_path)
