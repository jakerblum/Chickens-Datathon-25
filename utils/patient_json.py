
import pandas as pd
from typing import Dict, List, Any
import json


def patient_to_json(hadm_id, dataset, as_json_string=False, save=False, filename=None):
    """
    Create a complete JSON representation of a patient admission including
    timeline, lab results, and discharge medications.
    
    Args:
        hadm_id: Hospital admission ID
        dataset: MIMICDataset instance
        as_json_string: If True, returns JSON string. If False, returns dictionary.
        
    Returns:
        Dictionary (or JSON string) with three lists: timeline, lab_results, discharge_medications
        Each list contains dictionaries with structured information for programmatic use.
    """
    # Get timeline
    timeline_df = dataset.get_admission_timeline(hadm_id)
    timeline_list = prepare_timeline_list(timeline_df)
    
    # Timeline timestamps are already converted to ISO format in prepare_timeline_list
    # This is just a safety check for any remaining Timestamp objects
    if isinstance(timeline_list, list):
        for event in timeline_list:
            if isinstance(event, dict) and 'timestamp' in event:
                if isinstance(event['timestamp'], pd.Timestamp):
                    event['timestamp'] = event['timestamp'].isoformat()
    
    # Get lab results
    lab_results_summary = dataset.get_lab_results_summary(hadm_id, include_normal=True)
    lab_results_list = prepare_lab_results_list(lab_results_summary)
    
    # Get discharge medications
    discharge_meds_df = dataset.get_discharge_medications(hadm_id)
    discharge_meds_list = prepare_discharge_medications_list(discharge_meds_df)
    
    result = {
        'hadm_id': hadm_id,
        'timeline': timeline_list,
        'lab_results': lab_results_list,
        'discharge_medications': discharge_meds_list
    }
    if save:
        with open(filename, "w") as f:
            json.dump(result, f)

    if as_json_string:
        return json.dumps(result, indent=2, default=str)
    return result


def prepare_timeline_list(timeline_df):
    """
    Consolidate timeline events into patient-friendly categories.
    Optimized for performance with better memory handling.
    """
    # Early return if empty
    if timeline_df.empty:
        return []
    
    # Ensure timestamp is datetime (avoid repeated conversions in groupby)
    if not pd.api.types.is_datetime64_any_dtype(timeline_df['timestamp']):
        timeline_df['timestamp'] = pd.to_datetime(timeline_df['timestamp'])
    
    events = []
    
    # Group by event type and timestamp - use sort=False for speed
    grouped = timeline_df.groupby(['timestamp', 'event_type'], sort=False)
    
    for (timestamp, event_type), group in grouped:
        # Get descriptions once
        descriptions = group['description'].tolist()
        count = len(descriptions)
        
        # Map event types to categories (avoid multiple if-elif checks)
        if event_type == 'Admission':
            events.append({
                'timestamp': timestamp.isoformat() if pd.notna(timestamp) else None,
                'category': 'Admission',
                'title': 'Admitted to Hospital',
                'details': descriptions[0],
                'count': 1,
                'items': descriptions
            })
        
        elif event_type == 'Diagnosis':
            events.append({
                'timestamp': timestamp.isoformat() if pd.notna(timestamp) else None,
                'category': 'Diagnosis',
                'title': f'Diagnoses ({count})',
                'details': '<br>'.join([f"• {d}" for d in descriptions]),
                'count': count,
                'items': descriptions
            })
        
        elif event_type == 'Procedure':
            events.append({
                'timestamp': timestamp.isoformat() if pd.notna(timestamp) else None,
                'category': 'Procedure',
                'title': f'Procedures ({count})',
                'details': '<br>'.join([f"• {p}" for p in descriptions]),
                'count': count,
                'items': descriptions
            })
        
        elif event_type == 'Lab Result':
            # Limit display to first 10, but keep all in items
            details = '<br>'.join([f"• {lab}" for lab in descriptions[:10]])
            if count > 10:
                details += f"<br>• ... and {count - 10} more"
            
            events.append({
                'timestamp': timestamp.isoformat() if pd.notna(timestamp) else None,
                'category': 'Lab Tests',
                'title': f'Lab Tests ({count})',
                'details': details,
                'count': count,
                'items': descriptions
            })
        
        elif event_type == 'Medication':
            # Limit display to first 10, but keep all in items
            details = '<br>'.join([f"• {med}" for med in descriptions[:10]])
            if count > 10:
                details += f"<br>• ... and {count - 10} more"
            
            events.append({
                'timestamp': timestamp.isoformat() if pd.notna(timestamp) else None,
                'category': 'Medication',
                'title': f'Medications ({count})',
                'details': details,
                'count': count,
                'items': descriptions
            })
        
        elif event_type == 'Discharge':
            events.append({
                'timestamp': timestamp.isoformat() if pd.notna(timestamp) else None,
                'category': 'Discharge',
                'title': 'Discharged from Hospital',
                'details': descriptions[0],
                'count': 1,
                'items': descriptions
            })
    
    # Convert to list once at the end
    return events


def prepare_lab_results_list(lab_results_summary: Dict[str, pd.DataFrame]):
    """
    Convert lab results summary dictionary into a list of structured lab result entries.
    Includes ALL lab results from all categories (positive, negative, flagged, all).
    
    Args:
        lab_results_summary: Dictionary from get_lab_results_summary with keys:
            'positive', 'negative', 'flagged', 'all'
            
    Returns:
        List of dictionaries with lab result information
    """
    lab_results = []
    
    # Get all lab results (use 'all' if available, otherwise combine all categories)
    if not lab_results_summary['all'].empty:
        all_labs = lab_results_summary['all'].copy()
    else:
        # Combine all categories
        all_labs = pd.concat([
            lab_results_summary.get('positive', pd.DataFrame()),
            lab_results_summary.get('negative', pd.DataFrame()),
            lab_results_summary.get('flagged', pd.DataFrame())
        ]).drop_duplicates().reset_index(drop=True)
    
    if all_labs.empty:
        return []
    
    # Ensure charttime is datetime
    if not pd.api.types.is_datetime64_any_dtype(all_labs['charttime']):
        all_labs['charttime'] = pd.to_datetime(all_labs['charttime'], errors='coerce')
    
    # Sort by time
    all_labs = all_labs.sort_values('charttime').reset_index(drop=True)
    
    # Process each lab result
    for _, lab in all_labs.iterrows():
        charttime = lab.get('charttime')
        label = lab.get('label', 'Unknown Lab')
        category = lab.get('category', 'Unknown Category')
        
        # Get value (prefer numeric, fall back to text)
        value = lab.get('valuenum', None)
        if pd.isna(value):
            value = lab.get('value', None)
        
        flag = str(lab.get('flag_str', None))
        valueuom = lab.get('valueuom', None)
        ref_range_lower = lab.get('ref_range_lower', None)
        ref_range_upper = lab.get('ref_range_upper', None)
        comments = lab.get('comments', '')
        
        # Determine status
        if flag == "ABNORMAL":
            status = 'abnormal'
        elif flag == "NAN" or flag == "" or flag == "None":
            status = 'normal'
        
        lab_results.append({
            'timestamp': charttime.isoformat() if pd.notna(charttime) else None,
            'category': category,
            'test_name': label,
            'value': value,
            'status': status,
            'unit': valueuom if pd.notna(valueuom) else None,
            'reference_range': f"{ref_range_lower}-{ref_range_upper}" if (ref_range_lower or ref_range_upper) else None,
            'comments': comments,
            'itemid': int(lab.get('itemid')) if pd.notna(lab.get('itemid')) else None
        })
    
    return lab_results


def prepare_discharge_medications_list(discharge_meds_df: pd.DataFrame):
    """
    Convert discharge medications DataFrame into a list of structured medication entries.
    Includes ALL discharge medications.
    
    Args:
        discharge_meds_df: DataFrame from get_discharge_medications
        
    Returns:
        List of dictionaries with medication information
    """
    medications = []
    
    if discharge_meds_df.empty:
        return medications
    
    # Ensure starttime is datetime
    if not pd.api.types.is_datetime64_any_dtype(discharge_meds_df['starttime']):
        discharge_meds_df['starttime'] = pd.to_datetime(discharge_meds_df['starttime'], errors='coerce')
    if 'stoptime' in discharge_meds_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(discharge_meds_df['stoptime']):
            discharge_meds_df['stoptime'] = pd.to_datetime(discharge_meds_df['stoptime'], errors='coerce')
    
    # Sort by drug name and start time
    discharge_meds_df = discharge_meds_df.sort_values(['drug', 'starttime']).reset_index(drop=True)
    
    # Process each medication
    for _, med in discharge_meds_df.iterrows():
        drug = med.get('drug', 'Unknown Medication')
        dose_val = med.get('dose_val_rx', None)
        dose_unit = med.get('dose_unit_rx', None)
        route = med.get('route', None)
        starttime = med.get('starttime')
        stoptime = med.get('stoptime')
        form_rx = med.get('form_rx', None)
        doses_per_24hrs = med.get('doses_per_24_hrs', None) 
        
        medications.append({
            'drug': drug,
            'dose': dose_val,
            'dose_unit': dose_unit,
            'route': route,
            'form': form_rx,
            'frequency': f"{doses_per_24hrs} doses per 24 hours" if doses_per_24hrs and pd.notna(doses_per_24hrs) else None,
            'start_time': starttime.isoformat() if pd.notna(starttime) else None,
            'stop_time': stoptime.isoformat() if pd.notna(stoptime) else None,
            'is_ongoing': pd.isna(stoptime) or (pd.notna(starttime) and pd.isna(stoptime))
        })
    
    return medications