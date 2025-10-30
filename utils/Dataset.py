"""
Author(s):
    Jacob Blum (jblum7@uic.edu)
    Rohin Manohar (rmanohar@usc.edu)
    Conor Moore (moorecon@ohsu.edu)

Licensed under the MIT License. Copyright MDplus and the author(s) 2023.
"""
import os
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ICUStayRecord:
    """Represents a single ICU stay with all related data."""
    stay_id: int
    stay_info: Dict  # From icustays.csv
    vital_signs: Optional[pd.DataFrame] = None  # From chartevents.csv
    medications: Optional[pd.DataFrame] = None  # From inputevents.csv
    outputs: Optional[pd.DataFrame] = None  # From outputevents.csv
    procedures: Optional[pd.DataFrame] = None  # From procedureevents.csv


@dataclass
class AdmissionRecord:
    """Represents a single hospital admission with all related data."""
    hadm_id: int
    admission_info: Dict  # From admissions.csv
    diagnoses: List[Dict] = field(default_factory=list)  # From diagnoses_icd.csv
    procedures: List[Dict] = field(default_factory=list)  # From procedures_icd.csv
    medications: Optional[pd.DataFrame] = None  # From prescriptions.csv
    lab_results: Optional[pd.DataFrame] = None  # From labevents.csv
    microbiology: Optional[pd.DataFrame] = None  # From microbiologyevents.csv
    icu_stays: List[ICUStayRecord] = field(default_factory=list)  # Related ICU stays


@dataclass
class PatientRecord:
    """Represents a complete patient record with all admissions and data."""
    subject_id: int
    demographics: Dict  # From patients.csv
    admissions: List[AdmissionRecord] = field(default_factory=list)
    
    def __repr__(self):
        num_admissions = len(self.admissions)
        num_icu_stays = sum(len(adm.icu_stays) for adm in self.admissions)
        return (f"PatientRecord(subject_id={self.subject_id}, "
                f"gender={self.demographics.get('gender', 'N/A')}, "
                f"age={self.demographics.get('anchor_age', 'N/A')}, "
                f"admissions={num_admissions}, icu_stays={num_icu_stays})")


class MIMICDataset:
    """
    A comprehensive dataset loader for MIMIC-IV that organizes patient data
    hierarchically for easy extraction and analysis.
    """
    
    def __init__(
        self, 
        data_dir: Union[Path, str] = "physionet.org/files/mimiciv/3.1",
        max_patients: Optional[int] = None,
        admission_type_filter: Optional[Union[str, List[str]]] = None,
        diagnosis_filter: Optional[Union[str, List[str]]] = None,
        eager_load: bool = True
    ):
        """
        Initialize the MIMIC dataset loader.
        
        Args:
            data_dir: Path to the MIMIC-IV data directory (should contain hosp/ and icu/ subdirectories)
            max_patients: Maximum number of patients to load. If None, loads all patients.
            admission_type_filter: Filter by admission type(s). Can be a string or list of strings.
                                  Common types: 'EMERGENCY', 'ELECTIVE', 'URGENT', 'NEWBORN', 'EW EMER.'
            diagnosis_filter: Filter by ICD diagnosis code(s). Can be a string, list of strings, or regex pattern.
                             Only loads patients with at least one matching diagnosis.
            eager_load: If True, loads all data upfront. If False, loads data on-demand (slower queries, less memory).
        """
        self.data_dir = Path(data_dir)
        self.hosp_dir = self.data_dir / "hosp"
        self.icu_dir = self.data_dir / "icu"
        
        # Filter parameters
        self.max_patients = max_patients
        self.admission_type_filter = admission_type_filter
        self.diagnosis_filter = diagnosis_filter
        self.eager_load = eager_load
        
        # Filter sets (computed during loading)
        self._filtered_subject_ids = None
        self._filtered_hadm_ids = None
        
        # DataFrames for core tables
        self.patients_df = None
        self.admissions_df = None
        self.icustays_df = None
        self.diagnoses_df = None
        self.procedures_df = None
        self.prescriptions_df = None
        self.labevents_df = None
        self.microbiology_df = None
        self.chartevents_df = None
        self.inputevents_df = None
        self.outputevents_df = None
        self.procedureevents_df = None
        
        # Dictionary tables for lookups
        self.d_icd_diagnoses = None  # ICD diagnosis descriptions
        self.d_labitems = None  # Lab item descriptions
        self.d_icd_procedures = None  # ICD procedure descriptions
        
        # Indexed views for fast lookup
        self._admissions_by_subject = None
        self._icustays_by_hadm = None
        self._diagnoses_by_hadm = None
        self._procedures_by_hadm = None
        self._prescriptions_by_hadm = None
        self._labevents_by_hadm = None
        self._microbiology_by_hadm = None
        self._chartevents_by_stay = None
        self._inputevents_by_stay = None
        self._outputevents_by_stay = None
        self._procedureevents_by_stay = None
        
        self._load_data()
    
    def _apply_admission_filters(self):
        """Apply admission type and diagnosis filters to the admissions dataframe."""
        # Filter by admission type
        if self.admission_type_filter is not None:
            if isinstance(self.admission_type_filter, str):
                filter_types = [self.admission_type_filter]
            else:
                filter_types = list(self.admission_type_filter)
            
            self.admissions_df = self.admissions_df[
                self.admissions_df['admission_type'].isin(filter_types)
            ]
            print(f"  - Filtered by admission type: {filter_types}")
        
        # Filter by diagnosis codes
        if self.diagnosis_filter is not None:
            # Load diagnoses in chunks to find matching hadm_ids (more memory efficient)
            print("  - Loading diagnoses for filtering (chunked)...")
            matching_hadm_ids = set()
            
            # Try to load just first chunk to see if we can match quickly
            chunk_size = 100000
            for chunk in pd.read_csv(self.hosp_dir / "diagnoses_icd.csv.gz", compression='gzip', chunksize=chunk_size):
                # Prepare diagnosis filter
                if isinstance(self.diagnosis_filter, str):
                    # Could be regex pattern or single code
                    try:
                        # Try as regex pattern
                        import re
                        pattern = re.compile(self.diagnosis_filter)
                        chunk_matches = chunk[chunk['icd_code'].astype(str).str.contains(pattern, na=False)]
                    except:
                        # Treat as literal code
                        chunk_matches = chunk[chunk['icd_code'].astype(str) == self.diagnosis_filter]
                else:
                    # List of codes
                    filter_codes = [str(code) for code in self.diagnosis_filter]
                    chunk_matches = chunk[chunk['icd_code'].astype(str).isin(filter_codes)]
                
                if not chunk_matches.empty:
                    matching_hadm_ids.update(chunk_matches['hadm_id'].dropna().unique())
            
            # Filter admissions
            if matching_hadm_ids:
                self.admissions_df = self.admissions_df[
                    self.admissions_df['hadm_id'].isin(matching_hadm_ids)
                ]
                print(f"  - Filtered by diagnosis codes, found {len(matching_hadm_ids)} matching admissions")
            else:
                # No matches found
                self.admissions_df = self.admissions_df.iloc[0:0]  # Empty dataframe
                print(f"  - No admissions found matching diagnosis filter")
    
    def _load_data(self):
        """Load all data tables from CSV files with optional filtering."""
        print("Loading MIMIC-IV data tables...")
        
        # Core patient and admission data
        print("  - Loading patients...")
        self.patients_df = pd.read_csv(self.hosp_dir / "patients.csv.gz", compression='gzip')
        
        print("  - Loading admissions...")
        self.admissions_df = pd.read_csv(self.hosp_dir / "admissions.csv.gz", compression='gzip')
        
        # Apply filters to admissions first
        self._apply_admission_filters()
        
        # Limit patients if requested
        if self.max_patients is not None:
            unique_subjects = sorted(self.admissions_df['subject_id'].unique())[:self.max_patients]
            self.admissions_df = self.admissions_df[self.admissions_df['subject_id'].isin(unique_subjects)]
            print(f"  - Limited to {len(unique_subjects)} patients")
        
        # Update filtered IDs
        self._filtered_subject_ids = set(self.admissions_df['subject_id'].unique())
        self._filtered_hadm_ids = set(self.admissions_df['hadm_id'].unique())
        
        print(f"  - Filtered to {len(self._filtered_subject_ids)} patients, {len(self._filtered_hadm_ids)} admissions")
        
        # Filter patients table
        self.patients_df = self.patients_df[self.patients_df['subject_id'].isin(self._filtered_subject_ids)]
        
        print("  - Loading ICU stays...")
        self.icustays_df = pd.read_csv(self.icu_dir / "icustays.csv.gz", compression='gzip')
        # Filter ICU stays to only those matching our admissions
        self.icustays_df = self.icustays_df[self.icustays_df['hadm_id'].isin(self._filtered_hadm_ids)]
        
        # Load dictionary tables for lookups
        print("  - Loading diagnosis dictionary...")
        self.d_icd_diagnoses = pd.read_csv(self.hosp_dir / "d_icd_diagnoses.csv.gz", compression='gzip')
        
        print("  - Loading lab items dictionary...")
        self.d_labitems = pd.read_csv(self.hosp_dir / "d_labitems.csv.gz", compression='gzip')
        
        print("  - Loading procedure dictionary...")
        self.d_icd_procedures = pd.read_csv(self.hosp_dir / "d_icd_procedures.csv.gz", compression='gzip')
        
        # Clinical data
        print("  - Loading diagnoses...")
        self.diagnoses_df = pd.read_csv(self.hosp_dir / "diagnoses_icd.csv.gz", compression='gzip')
        if self._filtered_hadm_ids:
            self.diagnoses_df = self.diagnoses_df[self.diagnoses_df['hadm_id'].isin(self._filtered_hadm_ids)]
        
        print("  - Loading procedures...")
        self.procedures_df = pd.read_csv(self.hosp_dir / "procedures_icd.csv.gz", compression='gzip')
        if self._filtered_hadm_ids:
            self.procedures_df = self.procedures_df[self.procedures_df['hadm_id'].isin(self._filtered_hadm_ids)]
        
        print("  - Loading prescriptions...")
        if self._filtered_hadm_ids:
            # Only load prescriptions for filtered admissions
            chunk_list = []
            chunk_size = 100000
            for chunk in pd.read_csv(self.hosp_dir / "prescriptions.csv.gz", compression='gzip', low_memory=False, chunksize=chunk_size):
                chunk_filtered = chunk[chunk['hadm_id'].isin(self._filtered_hadm_ids)]
                if not chunk_filtered.empty:
                    chunk_list.append(chunk_filtered)
            if chunk_list:
                self.prescriptions_df = pd.concat(chunk_list, ignore_index=True)
            else:
                self.prescriptions_df = pd.DataFrame()
        else:
            self.prescriptions_df = pd.DataFrame()
        
        print("  - Loading lab events (filtering by hadm_id)...")
        # Load in chunks for memory efficiency
        if self._filtered_hadm_ids:
            chunk_list = []
            chunk_size = 100000
            for chunk in pd.read_csv(self.hosp_dir / "labevents.csv.gz", compression='gzip', low_memory=False, chunksize=chunk_size):
                chunk_filtered = chunk[chunk['hadm_id'].isin(self._filtered_hadm_ids)]
                if not chunk_filtered.empty:
                    chunk_list.append(chunk_filtered)
                # Stop early if we have enough data for a small subset
                if len(self._filtered_hadm_ids) <= 10 and len(chunk_list) > 0:
                    break
            if chunk_list:
                self.labevents_df = pd.concat(chunk_list, ignore_index=True)
            else:
                self.labevents_df = pd.DataFrame()
        else:
            self.labevents_df = pd.DataFrame()
        
        print("  - Loading microbiology events...")
        self.microbiology_df = pd.read_csv(self.hosp_dir / "microbiologyevents.csv.gz", compression='gzip')
        if self._filtered_hadm_ids:
            self.microbiology_df = self.microbiology_df[self.microbiology_df['hadm_id'].isin(self._filtered_hadm_ids)]
        
        # ICU time-series data (these are large, so we'll load them on-demand)
        # Set to None initially - will be loaded when needed
        print("  - ICU time-series data will be loaded on-demand...")
        self.chartevents_df = None
        self.inputevents_df = None
        self.outputevents_df = None
        self.procedureevents_df = None
        
        print("Indexing data for fast lookups...")
        self._build_indexes()
        
        print("Data loading complete!")
    
    def _build_indexes(self):
        """Build indexes for fast lookups by subject_id, hadm_id, and stay_id."""
        # Group admissions by subject_id
        self._admissions_by_subject = defaultdict(list)
        for _, row in self.admissions_df.iterrows():
            self._admissions_by_subject[row['subject_id']].append(row.to_dict())
        
        # Group ICU stays by hadm_id
        self._icustays_by_hadm = defaultdict(list)
        for _, row in self.icustays_df.iterrows():
            self._icustays_by_hadm[row['hadm_id']].append(row.to_dict())
        
        # Group diagnoses by hadm_id
        self._diagnoses_by_hadm = defaultdict(list)
        for _, row in self.diagnoses_df.iterrows():
            if pd.notna(row['hadm_id']):
                self._diagnoses_by_hadm[row['hadm_id']].append(row.to_dict())
        
        # Group procedures by hadm_id
        self._procedures_by_hadm = defaultdict(list)
        for _, row in self.procedures_df.iterrows():
            if pd.notna(row['hadm_id']):
                self._procedures_by_hadm[row['hadm_id']].append(row.to_dict())
        
        # Group prescriptions by hadm_id (store as DataFrame for easier querying)
        # Use groupby for efficiency with large datasets
        print("  - Indexing prescriptions...")
        self._prescriptions_by_hadm = {
            hadm_id: group for hadm_id, group in self.prescriptions_df.groupby('hadm_id')
        }
        
        # Group lab events by hadm_id
        print("  - Indexing lab events...")
        # Only index hadm_ids that exist in admissions (many lab events have NaN hadm_id)
        valid_hadm_ids = set(self.admissions_df['hadm_id'].unique())
        labevents_with_hadm = self.labevents_df[self.labevents_df['hadm_id'].isin(valid_hadm_ids)]
        self._labevents_by_hadm = {
            hadm_id: group for hadm_id, group in labevents_with_hadm.groupby('hadm_id')
        }
        
        # Group microbiology by hadm_id
        print("  - Indexing microbiology events...")
        self._microbiology_by_hadm = {
            hadm_id: group for hadm_id, group in self.microbiology_df.groupby('hadm_id')
        }
        
        # Group ICU time-series data by stay_id
        # Note: These tables are very large, so we'll index on-demand when needed
        # For now, we'll just prepare the DataFrames and index only when queried
        print("  - Preparing ICU time-series data (indexed on-demand)...")
        self._chartevents_by_stay = {}
        self._inputevents_by_stay = {}
        self._outputevents_by_stay = {}
        self._procedureevents_by_stay = {}
        # These will be populated on-demand in _get_icu_stay_data method
    
    def _load_icu_tables_if_needed(self):
        """Load ICU time-series tables on-demand if not already loaded."""
        # Skip loading if we have a large dataset to avoid timeout
        if len(self._filtered_hadm_ids) > 100:
            print("  - Skipping ICU time-series data (too many admissions for on-demand loading)")
            return
            
        if self.chartevents_df is None:
            print("  - Loading ICU chart events (on-demand)...")
            try:
                self.chartevents_df = pd.read_csv(self.icu_dir / "chartevents.csv.gz", compression='gzip', nrows=1000000)  # Limit rows
            except Exception as e:
                print(f"  - Warning: Could not load chart events: {e}")
                self.chartevents_df = pd.DataFrame()
        if self.inputevents_df is None:
            print("  - Loading ICU input events (on-demand)...")
            try:
                self.inputevents_df = pd.read_csv(self.icu_dir / "inputevents.csv.gz", compression='gzip', nrows=500000)  # Limit rows
            except Exception as e:
                print(f"  - Warning: Could not load input events: {e}")
                self.inputevents_df = pd.DataFrame()
        if self.outputevents_df is None:
            print("  - Loading ICU output events (on-demand)...")
            try:
                self.outputevents_df = pd.read_csv(self.icu_dir / "outputevents.csv.gz", compression='gzip', nrows=500000)  # Limit rows
            except Exception as e:
                print(f"  - Warning: Could not load output events: {e}")
                self.outputevents_df = pd.DataFrame()
        if self.procedureevents_df is None:
            print("  - Loading ICU procedure events (on-demand)...")
            try:
                self.procedureevents_df = pd.read_csv(self.icu_dir / "procedureevents.csv.gz", compression='gzip', nrows=100000)  # Limit rows
            except Exception as e:
                print(f"  - Warning: Could not load procedure events: {e}")
                self.procedureevents_df = pd.DataFrame()
    
    def _get_icu_stay_data(self, stay_id: int) -> Dict[str, Optional[pd.DataFrame]]:
        """
        Get ICU time-series data for a specific stay_id (on-demand indexing).
        
        Args:
            stay_id: The ICU stay's stay_id
            
        Returns:
            Dictionary with keys: vital_signs, medications, outputs, procedures
        """
        # Check if already indexed
        if stay_id in self._chartevents_by_stay:
            return {
                'vital_signs': self._chartevents_by_stay.get(stay_id),
                'medications': self._inputevents_by_stay.get(stay_id),
                'outputs': self._outputevents_by_stay.get(stay_id),
                'procedures': self._procedureevents_by_stay.get(stay_id)
            }
        
        # Load ICU tables if needed (only for small datasets)
        if self._filtered_hadm_ids and len(self._filtered_hadm_ids) <= 10:
            self._load_icu_tables_if_needed()
        else:
            # For larger datasets, return empty data
            return {
                'vital_signs': None,
                'medications': None,
                'outputs': None,
                'procedures': None
            }
        
        # Index on-demand
        if self.chartevents_df is not None and not self.chartevents_df.empty:
            mask_chart = self.chartevents_df['stay_id'] == stay_id
            if mask_chart.any():
                self._chartevents_by_stay[stay_id] = self.chartevents_df[mask_chart].copy()
        
        if self.inputevents_df is not None and not self.inputevents_df.empty:
            mask_input = self.inputevents_df['stay_id'] == stay_id
            if mask_input.any():
                self._inputevents_by_stay[stay_id] = self.inputevents_df[mask_input].copy()
        
        if self.outputevents_df is not None and not self.outputevents_df.empty:
            mask_output = self.outputevents_df['stay_id'] == stay_id
            if mask_output.any():
                self._outputevents_by_stay[stay_id] = self.outputevents_df[mask_output].copy()
        
        if self.procedureevents_df is not None and not self.procedureevents_df.empty:
            mask_proc = self.procedureevents_df['stay_id'] == stay_id
            if mask_proc.any():
                self._procedureevents_by_stay[stay_id] = self.procedureevents_df[mask_proc].copy()
        
        return {
            'vital_signs': self._chartevents_by_stay.get(stay_id),
            'medications': self._inputevents_by_stay.get(stay_id),
            'outputs': self._outputevents_by_stay.get(stay_id),
            'procedures': self._procedureevents_by_stay.get(stay_id)
        }
    
    def get_patient(self, subject_id: int) -> Optional[PatientRecord]:
        """
        Get a complete patient record by subject_id.
        
        Args:
            subject_id: The patient's subject_id
            
        Returns:
            PatientRecord with all admissions and related data, or None if not found
        """
        # Get patient demographics
        patient_row = self.patients_df[self.patients_df['subject_id'] == subject_id]
        if patient_row.empty:
            return None
        
        demographics = patient_row.iloc[0].to_dict()
        
        # Get all admissions for this patient
        admissions_data = self._admissions_by_subject.get(subject_id, [])
        admissions = []
        
        for adm_data in admissions_data:
            hadm_id = adm_data['hadm_id']
            
            # Get diagnoses
            diagnoses = self._diagnoses_by_hadm.get(hadm_id, [])
            
            # Get procedures
            procedures = self._procedures_by_hadm.get(hadm_id, [])
            
            # Get medications
            medications = self._prescriptions_by_hadm.get(hadm_id)
            
            # Get lab results
            lab_results = self._labevents_by_hadm.get(hadm_id)
            
            # Get microbiology
            microbiology = self._microbiology_by_hadm.get(hadm_id)
            
            # Get ICU stays for this admission
            icu_stays_data = self._icustays_by_hadm.get(hadm_id, [])
            icu_stays = []
            
            for stay_data in icu_stays_data:
                stay_id = stay_data['stay_id']
                
                # Get ICU time-series data (on-demand indexing)
                icu_data = self._get_icu_stay_data(stay_id)
                
                icu_stay = ICUStayRecord(
                    stay_id=stay_id,
                    stay_info=stay_data,
                    vital_signs=icu_data['vital_signs'],
                    medications=icu_data['medications'],
                    outputs=icu_data['outputs'],
                    procedures=icu_data['procedures']
                )
                icu_stays.append(icu_stay)
            
            admission = AdmissionRecord(
                hadm_id=hadm_id,
                admission_info=adm_data,
                diagnoses=diagnoses,
                procedures=procedures,
                medications=medications,
                lab_results=lab_results,
                microbiology=microbiology,
                icu_stays=icu_stays
            )
            admissions.append(admission)
        
        return PatientRecord(
            subject_id=subject_id,
            demographics=demographics,
            admissions=admissions
        )
    
    def get_admission(self, hadm_id: int) -> Optional[AdmissionRecord]:
        """
        Get a single admission record by hadm_id.
        
        Args:
            hadm_id: The admission's hadm_id
            
        Returns:
            AdmissionRecord with all related data, or None if not found
        """
        adm_row = self.admissions_df[self.admissions_df['hadm_id'] == hadm_id]
        if adm_row.empty:
            return None
        
        admission_info = adm_row.iloc[0].to_dict()
        subject_id = admission_info['subject_id']
        
        # Get all related data (same logic as in get_patient)
        diagnoses = self._diagnoses_by_hadm.get(hadm_id, [])
        procedures = self._procedures_by_hadm.get(hadm_id, [])
        medications = self._prescriptions_by_hadm.get(hadm_id)
        lab_results = self._labevents_by_hadm.get(hadm_id)
        microbiology = self._microbiology_by_hadm.get(hadm_id)
        
        # Get ICU stays
        icu_stays_data = self._icustays_by_hadm.get(hadm_id, [])
        icu_stays = []
        
        for stay_data in icu_stays_data:
            stay_id = stay_data['stay_id']
            
            # Get ICU time-series data (on-demand indexing)
            icu_data = self._get_icu_stay_data(stay_id)
            
            icu_stay = ICUStayRecord(
                stay_id=stay_id,
                stay_info=stay_data,
                vital_signs=icu_data['vital_signs'],
                medications=icu_data['medications'],
                outputs=icu_data['outputs'],
                procedures=icu_data['procedures']
            )
            icu_stays.append(icu_stay)
        
        return AdmissionRecord(
            hadm_id=hadm_id,
            admission_info=admission_info,
            diagnoses=diagnoses,
            procedures=procedures,
            medications=medications,
            lab_results=lab_results,
            microbiology=microbiology,
            icu_stays=icu_stays
        )
    
    def get_all_subject_ids(self) -> List[int]:
        """Get a list of all subject_ids in the dataset."""
        return sorted(self.patients_df['subject_id'].unique().tolist())
    
    def get_all_patients(self) -> List[PatientRecord]:
        """
        Get all patient records in the dataset.
        
        Returns:
            List of PatientRecord objects for all patients in the dataset.
        """
        patients = []
        for subject_id in self.get_all_subject_ids():
            patient = self.get_patient(subject_id)
            if patient:
                patients.append(patient)
        return patients
    
    def get_patients_by_chief_concern(
        self, 
        concern: str, 
        max_patients: int = 10,
        search_description: bool = True
    ) -> List[PatientRecord]:
        """
        Get patients by chief concern (diagnosis).
        
        Args:
            concern: Search term - can be ICD code or description (e.g., "angina", "41401")
            max_patients: Maximum number of patients to return
            search_description: If True, searches in diagnosis descriptions. If False, only matches exact ICD codes.
            
        Returns:
            List of PatientRecord objects matching the concern
        """
        # First, find matching ICD codes
        matching_codes = set()
        
        if search_description:
            # Search in diagnosis descriptions (case-insensitive, partial match)
            concern_lower = concern.lower()
            matches = self.d_icd_diagnoses[
                self.d_icd_diagnoses['long_title'].str.lower().str.contains(concern_lower, na=False)
            ]
            matching_codes.update(matches['icd_code'].astype(str).unique())
        
        # Also try exact ICD code match
        exact_match = self.d_icd_diagnoses[self.d_icd_diagnoses['icd_code'].astype(str) == concern]
        if not exact_match.empty:
            matching_codes.update(exact_match['icd_code'].astype(str).unique())
        
        if not matching_codes:
            return []
        
        # Find admissions with matching diagnoses
        matching_admissions = self.diagnoses_df[
            self.diagnoses_df['icd_code'].astype(str).isin(matching_codes)
        ]
        
        # Get unique subject_ids
        matching_subject_ids = sorted(matching_admissions['subject_id'].unique())[:max_patients]
        
        # Return PatientRecord objects
        patients = []
        for subject_id in matching_subject_ids:
            patient = self.get_patient(subject_id)
            if patient:
                patients.append(patient)
        
        return patients
    
    def get_admission_timeline(self, hadm_id: int) -> pd.DataFrame:
        """
        Get chronological timeline of key events during an admission.
        Uses the patient_extractors module.
        """
        from .patient_extractors import get_admission_timeline
        admission = self.get_admission(hadm_id)
        if not admission:
            return pd.DataFrame()
        return get_admission_timeline(admission, self.d_icd_diagnoses, self.d_icd_procedures, self.d_labitems)
    
    def get_lab_results_summary(
        self, 
        hadm_id: int,
        include_normal: bool = False
    ) -> Dict[str, pd.DataFrame]:
        """
        Get organized lab results with positive/negative/abnormal interpretations.
        Uses the patient_extractors module.
        """
        from .patient_extractors import get_lab_results_summary
        admission = self.get_admission(hadm_id)
        if not admission:
            return {
                'positive': pd.DataFrame(),
                'negative': pd.DataFrame(),
                'flagged': pd.DataFrame(),
                'all': pd.DataFrame()
            }
        return get_lab_results_summary(admission, self.d_labitems, include_normal)
    
    def get_discharge_medications(self, hadm_id: int) -> pd.DataFrame:
        """
        Get medications that the patient is prescribed at discharge or will continue after discharge.
        Uses the patient_extractors module.
        """
        from .patient_extractors import get_discharge_medications
        admission = self.get_admission(hadm_id)
        if not admission:
            return pd.DataFrame()
        return get_discharge_medications(admission)
    
    def __len__(self) -> int:
        """Return the number of patients in the dataset."""
        return len(self.patients_df)


def main():
    """Example usage of the MIMICDataset."""
    # Example: Load first 5 patients with EMERGENCY admissions
    dataset = MIMICDataset(max_patients=5, admission_type_filter='EMERGENCY')
    
    # Get first 5 patients
    subject_ids = dataset.get_all_subject_ids()[:5]
    
    print("\n" + "="*80)
    print("First 5 Patient Records:")
    print("="*80 + "\n")
    
    for subject_id in subject_ids:
        patient = dataset.get_patient(subject_id)
        if patient:
            print(patient)
            print(f"  Demographics: {patient.demographics}")
            print(f"  Number of admissions: {len(patient.admissions)}")
            
            for i, adm in enumerate(patient.admissions, 1):
                print(f"    Admission {i} (hadm_id={adm.hadm_id}):")
                print(f"      Type: {adm.admission_info.get('admission_type', 'N/A')}")
                print(f"      Diagnoses: {len(adm.diagnoses)} ICD codes")
                print(f"      Procedures: {len(adm.procedures)} ICD procedure codes")
                print(f"      Medications: {len(adm.medications) if adm.medications is not None else 0} prescriptions")
                print(f"      Lab results: {len(adm.lab_results) if adm.lab_results is not None else 0} lab events")
                print(f"      ICU stays: {len(adm.icu_stays)}")
                
                for j, stay in enumerate(adm.icu_stays, 1):
                    print(f"        ICU Stay {j} (stay_id={stay.stay_id}):")
                    print(f"          Unit: {stay.stay_info.get('first_careunit', 'N/A')}")
                    print(f"          Vital signs: {len(stay.vital_signs) if stay.vital_signs is not None else 0} measurements")
                    print(f"          Medications: {len(stay.medications) if stay.medications is not None else 0} input events")
            
            print()


if __name__ == "__main__":
    main()
