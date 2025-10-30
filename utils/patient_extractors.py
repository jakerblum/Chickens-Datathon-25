"""
Patient data extraction utilities for MIMIC-IV dataset.

This module provides convenient methods for extracting specific aspects of patient records
for chart summarization, including timelines, lab results, and medications.
"""

import pandas as pd
from typing import Dict, List, Optional
from .Dataset import AdmissionRecord, PatientRecord


def get_admission_timeline(
    admission: AdmissionRecord,
    d_icd_diagnoses: pd.DataFrame,
    d_icd_procedures: pd.DataFrame,
    d_labitems: pd.DataFrame
) -> pd.DataFrame:
    """
    Get chronological timeline of key events during an admission.
    
    Args:
        admission: AdmissionRecord object
        d_icd_diagnoses: DataFrame with ICD diagnosis descriptions
        d_icd_procedures: DataFrame with ICD procedure descriptions
        d_labitems: DataFrame with lab item descriptions
        
    Returns:
        DataFrame with chronological events (admission, diagnoses, procedures, medications, lab results, etc.)
    """
    events = []
    try:
        adm_time = pd.to_datetime(admission.admission_info.get('admittime'))
    except:
        adm_time = pd.Timestamp.now()
    
    # Admission event
    events.append({
        'timestamp': adm_time,
        'event_type': 'Admission',
        'description': f"Admitted via {admission.admission_info.get('admission_location', 'Unknown')}",
        'details': str(admission.admission_info)
    })
    
    # Diagnoses (use seq_num or assume ordered by time)
    for diag in sorted(admission.diagnoses, key=lambda x: x.get('seq_num', 999)):
        icd_code = str(diag.get('icd_code', ''))
        icd_version = diag.get('icd_version', 9)
        # Get description
        desc_match = d_icd_diagnoses[
            (d_icd_diagnoses['icd_code'].astype(str) == icd_code) &
            (d_icd_diagnoses['icd_version'] == icd_version)
        ]
        desc = desc_match['long_title'].iloc[0] if not desc_match.empty else f"ICD-{icd_version}: {icd_code}"
        
        events.append({
            'timestamp': adm_time,  # Diagnoses are typically assigned at admission
            'event_type': 'Diagnosis',
            'description': desc,
            'details': str(diag)
        })
    
    # Procedures
    for proc in sorted(admission.procedures, key=lambda x: x.get('seq_num', 999)):
        icd_code = str(proc.get('icd_code', ''))
        icd_version = proc.get('icd_version', 9)
        chartdate = proc.get('chartdate', admission.admission_info.get('admittime'))
        
        # Get description
        desc_match = d_icd_procedures[
            (d_icd_procedures['icd_code'].astype(str) == icd_code) &
            (d_icd_procedures['icd_version'] == icd_version)
        ]
        desc = desc_match['long_title'].iloc[0] if not desc_match.empty else f"ICD-{icd_version}: {icd_code}"
        
        try:
            proc_time = pd.to_datetime(chartdate)
        except:
            proc_time = adm_time
        
        events.append({
            'timestamp': proc_time,
            'event_type': 'Procedure',
            'description': desc,
            'details': str(proc)
        })
    
    # Medications (prescriptions)
    if admission.medications is not None and not admission.medications.empty:
        for _, med in admission.medications.iterrows():
            try:
                start_time = pd.to_datetime(med.get('starttime', adm_time))
            except:
                start_time = adm_time
            
            events.append({
                'timestamp': start_time,
                'event_type': 'Medication',
                'description': f"{med.get('drug', 'Unknown drug')} - {med.get('dose_val_rx', '')} {med.get('dose_unit_rx', '')}",
                'details': str(med.to_dict())
            })
    
    # Lab results - key abnormal values
    if admission.lab_results is not None and not admission.lab_results.empty:
        # Get flagged results
        flagged_labs = admission.lab_results[
            (admission.lab_results['flag'].notna()) &
            (admission.lab_results['flag'] != '')
        ]
        
        for _, lab in flagged_labs.iterrows():
            try:
                lab_time = pd.to_datetime(lab.get('charttime', adm_time))
            except:
                lab_time = adm_time
            
            # Get lab item description
            itemid = lab.get('itemid')
            if pd.notna(itemid):
                item_match = d_labitems[d_labitems['itemid'] == itemid]
                item_label = item_match['label'].iloc[0] if not item_match.empty else f"Item {itemid}"
            else:
                item_label = "Unknown Lab"
            
            value = lab.get('valuenum', lab.get('value', 'N/A'))
            flag = lab.get('flag', '')
            
            events.append({
                'timestamp': lab_time,
                'event_type': 'Lab Result',
                'description': f"{item_label}: {value} ({flag})",
                'details': str(lab.to_dict())
            })
    
    # Discharge event
    try:
        disch_time = pd.to_datetime(admission.admission_info.get('dischtime'))
        events.append({
            'timestamp': disch_time,
            'event_type': 'Discharge',
            'description': f"Discharged to {admission.admission_info.get('discharge_location', 'Unknown')}",
            'details': str(admission.admission_info)
        })
    except:
        pass
    
    # Create DataFrame and sort by timestamp
    timeline_df = pd.DataFrame(events)
    if not timeline_df.empty:
        timeline_df = timeline_df.sort_values('timestamp').reset_index(drop=True)
    
    return timeline_df


def get_lab_results_summary(
    admission: AdmissionRecord,
    d_labitems: pd.DataFrame,
    include_normal: bool = False
) -> Dict[str, pd.DataFrame]:
    """
    Get organized lab results with positive/negative/abnormal interpretations.
    
    Args:
        admission: AdmissionRecord object
        d_labitems: DataFrame with lab item descriptions
        include_normal: If True, includes normal results. If False, only abnormal/flagged results.
        
    Returns:
        Dictionary with keys:
        - 'positive': Lab results with positive/abnormal flags (e.g., 'HIGH', 'ABNORMAL', 'POSITIVE')
        - 'negative': Lab results with negative/normal flags (e.g., 'NEGATIVE', 'NORMAL', 'LOW')
        - 'flagged': Lab results with any flag (organized by flag type)
        - 'all': All lab results sorted by time
    """
    if not admission or admission.lab_results is None or admission.lab_results.empty:
        return {
            'positive': pd.DataFrame(),
            'negative': pd.DataFrame(),
            'flagged': pd.DataFrame(),
            'all': pd.DataFrame()
        }
    
    labs = admission.lab_results.copy()
    
    # Add lab item descriptions
    labs = labs.merge(
        d_labitems[['itemid', 'label', 'category']],
        on='itemid',
        how='left'
    )
    
    # Sort by time
    labs['charttime'] = pd.to_datetime(labs['charttime'], errors='coerce')
    labs = labs.sort_values('charttime').reset_index(drop=True)
    
    # Categorize by flags
    positive_flags = ['HIGH', 'H', 'ABNORMAL', 'ABN', 'POSITIVE', 'POS', '>', 'CRITICAL']
    negative_flags = ['LOW', 'L', 'NEGATIVE', 'NEG', 'NORMAL', 'NORM', '<', 'N', 'NAN']
    
    labs['flag_str'] = labs['flag'].astype(str).str.upper()
    labs['is_positive'] = labs['flag_str'].isin(positive_flags) | \
                          labs['flag_str'].str.contains('^H', regex=True, na=False) | \
                          labs['flag_str'].str.contains('^>', regex=True, na=False)
    
    labs['is_negative'] = labs['flag_str'].isin(negative_flags) | \
                          labs['flag_str'].str.contains('^L', regex=True, na=False) | \
                          labs['flag_str'].str.contains('^<', regex=True, na=False)
    
    results = {}
    
    if include_normal:
        results['positive'] = labs[labs['is_positive']].copy()
        results['negative'] = labs[labs['is_negative']].copy()
    else:
        results['positive'] = labs[labs['is_positive']].copy() if labs['is_positive'].any() else pd.DataFrame()
        results['negative'] = labs[labs['is_negative']].copy() if labs['is_negative'].any() else pd.DataFrame()
    
    results['flagged'] = labs[labs['flag'].notna() & (labs['flag'].astype(str) != '')].copy()
    results['all'] = labs.copy()
    
    return results


def get_discharge_medications(admission: AdmissionRecord) -> pd.DataFrame:
    """
    Get medications that the patient is prescribed at discharge or will continue after discharge.
    
    Args:
        admission: AdmissionRecord object
        
    Returns:
        DataFrame with discharge medications (medications with stoptime after discharge time or no stoptime)
    """
    if not admission or admission.medications is None or admission.medications.empty:
        return pd.DataFrame()
    
    meds = admission.medications.copy()
    
    # Get discharge time
    try:
        discharge_time = pd.to_datetime(admission.admission_info.get('dischtime'), errors='coerce')
    except:
        discharge_time = None
    
    # Convert stop times
    meds['starttime'] = pd.to_datetime(meds['starttime'], errors='coerce')
    meds['stoptime'] = pd.to_datetime(meds['stoptime'], errors='coerce')
    
    # Medications that continue after discharge or have no stop time
    # (assuming medications without stop time are ongoing)
    if discharge_time is not None:
        discharge_meds = meds[
            (meds['stoptime'].isna()) |  # No stop time
            (meds['stoptime'] >= discharge_time) |  # Stop after discharge
            ((meds['stoptime'].isna()) & (meds['starttime'].notna()))  # Started but no stop
        ].copy()
    else:
        # If no discharge time, assume medications without stop time are discharge meds
        discharge_meds = meds[meds['stoptime'].isna()].copy()
    
    # Sort by drug name and start time
    if not discharge_meds.empty:
        discharge_meds = discharge_meds.sort_values(['drug', 'starttime']).reset_index(drop=True)
    
    return discharge_meds

