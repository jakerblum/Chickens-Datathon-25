# Chickens-Datathon-25
**Team:** Jake, Rohin, and Conor

## Overview

This repository transforms raw MIMIC-IV hospital data into patient-friendly, interactive HTML summaries with AI-generated explanations, medication visualizations, and educational content. The system is designed to help patients understand their hospital visit, lab results, and medications through clear language and visual aids.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Data Pipeline](#data-pipeline)
- [Key Features](#key-features)
- [Installation & Setup](#installation--setup)
- [Usage](#usage)
- [File Structure](#file-structure)
- [How It Works](#how-it-works)
- [Output Examples](#output-examples)
- [Extending the System](#extending-the-system)

---

## System Architecture

```
MIMIC-IV Raw Data → JSON Conversion → AI Enrichment → HTML Generation
      ↓                    ↓                ↓               ↓
  Dataset.py        patient_json.py   Perplexity API   Interactive
  (Loader)          (Converter)       (Summarizer)     Web Page
```

---

## Data Pipeline

### 1. **Loading Patient Data** (`utils/Dataset.py`)

The `MIMICDataset` class loads compressed MIMIC-IV CSV files and builds an in-memory index:

**Input Files:**
- `patients.csv.gz` - Demographics
- `admissions.csv.gz` - Admission records
- `diagnoses_icd.csv.gz` - ICD diagnosis codes
- `procedures_icd.csv.gz` - Procedures performed
- `prescriptions.csv.gz` - Medications
- `labevents.csv.gz` - Laboratory test results
- Lookup tables for diagnosis/procedure names

**Process:**
```python
from utils.Dataset import MIMICDataset

# Load MIMIC-IV data
dataset = MIMICDataset(
    mimic_hosp_dir="path/to/mimic-iv/hosp",
    mimic_icu_dir="path/to/mimic-iv/icu"
)

# Get patient record
patient = dataset.get_patient(subject_id=12345)
```

**Key Features:**
- Lazy loading for memory efficiency
- Indexed lookups for fast access
- Filtering by admission type or diagnosis
- Chunked reading for large tables

---

### 2. **Converting to JSON** (`utils/patient_json.py`)

Transforms MIMIC data into structured JSON format:

```python
from utils.patient_json import patient_to_json

# Convert admission to JSON
json_data = patient_to_json(
    hadm_id=22595853,
    dataset=dataset,
    save=True,
    filename="data/patient_22595853.json"
)
```

**Output Structure:**
```json
{
  "hadm_id": 22595853,
  "timeline": [
    {
      "timestamp": "2180-05-06T22:23:00",
      "category": "Admission|Diagnosis|Procedure|Lab Tests|Medication|Discharge",
      "title": "Event title",
      "details": "HTML formatted details",
      "count": 1,
      "items": ["List of specific items"]
    }
  ],
  "lab_results": [
    {
      "timestamp": "2180-05-07T00:10:00",
      "category": "Hematology|Chemistry|Blood Gas|etc",
      "test_name": "Glucose",
      "value": 120.5,
      "status": "normal|abnormal",
      "unit": "mg/dL",
      "reference_range": "70-100",
      "itemid": 50931
    }
  ],
  "discharge_medications": [
    {
      "drug": "Aspirin",
      "dose": "325",
      "dose_unit": "mg",
      "route": "PO",
      "frequency": "1.0 doses per 24 hours",
      "start_time": "2180-05-07T01:00:00",
      "stop_time": "2180-05-08T12:00:00",
      "is_ongoing": false
    }
  ]
}
```

---

### 3. **Medication Database** (`Medications/Medications.json`)

Contains visual information for common medications:

```json
{
  "medications": [
    {
      "full_name": "Aspirin",
      "generic_name": "Aspirin",
      "brand_names": ["Aspirin", "Bayer"],
      "aliases": ["Acetylsalicylic acid"],
      "physical_description": "White, round tablet with 'ASPIRIN' imprint",
      "image_path": "Medications/Drug_Images/Aspirin.jpg"
    }
  ]
}
```

**Currently Supported Medications:**
- Acetaminophen (Tylenol)
- Aspirin
- Atorvastatin (Lipitor)
- Docusate Sodium (Colace)
- Emtricitabine-Tenofovir (Truvada)
- Furosemide (Lasix)
- Omeprazole (Prilosec)
- Potassium Chloride

**Image Directories:**
- `Medications/Drug_Images/` - Pill/tablet photographs
- `Medications/Timing_Images/` - Visual timing guides (future use)

---

## Key Features

### Main Script: `summarize_to_page.py`

Generates complete patient summaries with all medications and lab results.

**Key Functions:**

1. **`enrich_patient_data_with_visuals(data)`**
   - Matches patient medications to the medication database
   - Adds pill images and physical descriptions
   - Handles missing medications gracefully

2. **`create_gantt_timeline_from_json(timeline_list, hadm_id)`**
   - Creates interactive Plotly timeline visualization
   - Color-codes events by category
   - Shows temporal relationships between events

3. **`generate_medication_faqs(medications)`**
   - Generates patient-specific questions for each medication
   - Questions include:
     - Why was I prescribed this?
     - What are the side effects?
     - Can I stop taking it?
     - How long should I take it?
     - Food/drug interactions?
     - Proper dosing instructions

4. **`summarize_data(data, detail_level, show_citations)`**
   - Calls Perplexity AI API for intelligent summarization
   - Uses trusted medical sources (Mayo Clinic, Cleveland Clinic, NIH, etc.)
   - Returns structured JSON with:
     - Visit summary
     - Lab result explanations
     - Medication purposes
     - Medication FAQs
     - General frequently asked questions

5. **`generate_html_page(...)`**
   - Creates responsive, interactive HTML output
   - Embeds timeline visualization
   - Displays medication cards with images
   - Includes expandable FAQ sections
   - Shows references and citations

### Filtered Script: `summarize_to_page_filtered.py`

Identical to the main script but includes filtering capabilities:
- Filter lab results by category (Hematology, Chemistry, etc.)
- Filter medications by route (e.g., only oral medications)
- More streamlined output for specific use cases

**Use this when:**
- You want to focus on specific lab categories
- You need simplified medication lists
- You're targeting specific patient education scenarios

---

## Installation & Setup

### Prerequisites

```bash
# Python 3.8+
pip install pandas plotly perplexity-python
```

### Environment Setup

1. **Get Perplexity API Key:**
   - Sign up at https://www.perplexity.ai/
   - Generate API key from dashboard
   - Set environment variable:
     ```bash
     export PERPLEXITY_API_KEY="your-api-key-here"
     ```
     Or add to scripts directly (see line 11 in summarize_to_page.py)

2. **Download MIMIC-IV Data:**
   - Request access at https://physionet.org/content/mimiciv/
   - Download and extract to a local directory
   - Note the paths to `hosp/` and `icu/` directories

3. **Prepare Medication Images:**
   - Add medication images to `Medications/Drug_Images/`
   - Update `Medications/Medications.json` with new entries
   - Follow naming convention: `DrugName.jpg`

---

## Usage

### Basic Workflow

#### Step 1: Load and Convert MIMIC Data

```python
from utils.Dataset import MIMICDataset
from utils.patient_json import patient_to_json

# Load dataset
dataset = MIMICDataset(
    mimic_hosp_dir="/path/to/mimiciv/hosp",
    mimic_icu_dir="/path/to/mimiciv/icu"
)

# Convert to JSON
patient_to_json(
    hadm_id=22595853,
    dataset=dataset,
    save=True,
    filename="data/patient_22595853.json"
)
```

#### Step 2: Generate HTML Summary

```bash
# Basic usage
python summarize_to_page.py \
    --input_data data/patient_22595853.json \
    --output patient_summary_22595853.html

# With all options
python summarize_to_page.py \
    --input_data data/patient_test.json \
    --detail_level 2 \
    --output generated_htmls/patient_summary_test.html \
    --show_citations
```

**Command-Line Arguments:**

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--input_data` | string | Required | Path to patient JSON file |
| `--output` | string | `patient_summary_{hadm_id}.html` | Output HTML filename |
| `--detail_level` | int | `2` | Reading level: 1=Basic, 2=Enhanced, 3=Advanced |
| `--show_citations` | flag | False | Include source citations in output |

**Detail Levels:**

- **Level 1 (Basic)**: 5th-grade reading level
  - Simple language
  - Fewer technical terms
  - Shorter explanations
  - Best for general audience

- **Level 2 (Enhanced)**: High school reading level
  - Moderate terminology
  - Balanced detail
  - Practical focus
  - Best for most patients

- **Level 3 (Advanced)**: College reading level
  - Technical terminology
  - Detailed explanations
  - Medical/scientific context
  - Best for healthcare students or professionals

#### Step 3: View Output

Open the generated HTML file in any web browser. The page includes:

- **Header Section**: Patient admission ID and visit dates
- **Interactive Timeline**: Plotly chart showing all events
- **Visit Summary**: AI-generated overview
- **Lab Results**:
  - Visual bar charts comparing values to normal ranges
  - Patient-friendly explanations
  - Abnormal value highlighting
- **Medications**:
  - Card layout with images
  - Dosage and administration info
  - Physical descriptions
  - Medication-specific FAQs
- **General FAQs**: Common questions about the visit
- **References**: First 10 citations to medical sources (if enabled)

---

### Using the Filtered Version

```bash
python summarize_to_page_filtered.py \
    --input_data data/stroke_patient_1.json \
    --detail_level 1 \
    --output generated_htmls/filtered_level_1/stroke_patient_1.html
```

The filtered version provides the same features but with additional data filtering options built into the code.

---

## File Structure

```
Chickens-Datathon-25/
│
├── utils/
│   ├── Dataset.py                      # MIMIC-IV data loader
│   ├── patient_json.py                 # JSON conversion functions
│   ├── patient_extractors.py           # Data extraction utilities
│   ├── example_question_generator.py   # Question template system
│   ├── show_patients.py                # Patient data viewer
│   └── perplexity_question_templates.json  # Question templates
│
├── data/
│   ├── patient_test.json               # Sample patient data
│   ├── angina_patient_*.json           # Angina case examples
│   ├── stroke_patient_*.json           # Stroke case examples
│   ├── asthma_pulm_patient_*.json      # Respiratory case examples
│   ├── syncope_patient_*.json          # Syncope case examples
│   └── abdominal_patient_*.json        # Abdominal case examples
│
├── Medications/
│   ├── Medications.json                # Medication database
│   ├── Drug_Images/                    # Pill/tablet photographs
│   └── Timing_Images/                  # Timing visual aids
│
├── generated_htmls/
│   ├── filtered_level_1/               # Basic detail outputs
│   ├── filtered_level_2/               # Enhanced detail outputs
│   └── filtered_level_3/               # Advanced detail outputs
│
├── charts/                             # Visualization outputs
│
├── summarize.py                        # Simple summarization script
├── summarize_to_page.py                # Main HTML generator
├── summarize_to_page_filtered.py       # Filtered version
├── add_detailed_stats.py               # Statistics enhancement
│
├── *.ipynb                             # Jupyter notebooks
├── README.md                           # This file
└── USAGE_EXAMPLES.md                   # Additional examples
```

---

## How It Works

### Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: LOAD MIMIC-IV DATA                                      │
│                                                                  │
│ MIMIC-IV CSV Files (patients, admissions, diagnoses, labs, etc.)│
│         ↓                                                        │
│ Dataset.py loads and indexes data                               │
│         ↓                                                        │
│ PatientRecord objects with complete medical history             │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: CONVERT TO JSON                                         │
│                                                                  │
│ patient_json.py extracts:                                       │
│   - Timeline events (admission, diagnosis, procedures, etc.)    │
│   - Lab results (with values and reference ranges)              │
│   - Discharge medications (with dosing info)                    │
│         ↓                                                        │
│ Structured JSON file saved to data/ directory                   │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: ENRICH WITH VISUALS                                     │
│                                                                  │
│ summarize_to_page.py:                                           │
│   1. Loads patient JSON                                         │
│   2. Matches medications to Medications.json                    │
│   3. Adds pill images and physical descriptions                 │
│         ↓                                                        │
│ Enriched patient data with visual information                   │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: GENERATE QUESTIONS                                      │
│                                                                  │
│ QuestionGenerator creates medication-specific FAQs:             │
│   - Why prescribed?                                             │
│   - Side effects?                                               │
│   - Duration?                                                   │
│   - Interactions?                                               │
│   - How to take?                                                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: AI SUMMARIZATION                                        │
│                                                                  │
│ Perplexity API called with:                                     │
│   - Patient data                                   │
│   - Generated questions                                         │
│   - Detail level preference                                     │
│   - Trusted medical sources (Mayo, Cleveland Clinic, NIH)       │
│         ↓                                                        │
│ Returns structured JSON with:                                   │
│   - Visit summary                                               │
│   - Lab explanations                                            │
│   - Medication purposes                                         │
│   - FAQ answers                                                 │
│   - Citations                                                   │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: CREATE VISUALIZATIONS                                   │
│                                                                  │
│ create_gantt_timeline_from_json():                              │
│   - Builds interactive Plotly timeline                          │
│   - Color-codes by event type                                   │
│   - Shows temporal relationships                                │
│   - Exports as HTML div                                         │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: GENERATE HTML PAGE                                      │
│                                                                  │
│ generate_html_page():                                           │
│   - Creates responsive HTML template                            │
│   - Embeds timeline visualization                               │
│   - Builds medication cards with images                         │
│   - Adds lab result charts                                      │
│   - Includes FAQ sections                                       │
│   - Adds citations and references                               │
│   - Injects JavaScript for interactivity                        │
│         ↓                                                        │
│ FINAL OUTPUT: Interactive HTML file                             │
└─────────────────────────────────────────────────────────────────┘
```

### How Medication Images Are Pulled In

1. **Patient JSON contains**: `"drug": "Aspirin"`

2. **Normalization** (`normalize_drug_name`):
   - Converts to lowercase: `"aspirin"`
   - Removes special characters
   - Extracts brand name from parentheses if present

3. **Matching** (`find_medication_visual_info`):
   - Searches `Medications.json` for:
     - Exact generic name match
     - Brand name match
     - Alias match
   - Returns medication entry with image path

4. **Enrichment** (`enrich_patient_data_with_visuals`):
   - Adds `physical_description` field
   - Adds `image_path` field
   - Handles missing medications gracefully

5. **HTML Generation**:
   - Reads image file from disk
   - Encodes as base64
   - Embeds directly in HTML (no external dependencies)
   - Displays in medication card

**Example Flow:**
```
Patient JSON: "Aspirin"
     ↓
Normalize: "aspirin"
     ↓
Match in Medications.json:
{
  "generic_name": "Aspirin",
  "image_path": "Medications/Drug_Images/Aspirin.jpg"
}
     ↓
Enrich patient data with image path
     ↓
Generate HTML:
<img src="data:image/jpeg;base64,/9j/4AAQ..." />
```

---

## Output Examples

### Generated HTML Features

**1. Header Section**
- Gradient background
- Admission ID
- Visit dates

**2. Interactive Timeline**
- Horizontal Gantt-style chart
- Color-coded events:
  - Blue: Admission/Discharge
  - Purple: Diagnoses
  - Orange: Procedures
  - Red: Lab Tests
  - Green: Medications
- Hover tooltips with details
- Zoom and pan controls

**3. Lab Results Display**
- Visual bar charts showing:
  - Patient value
  - Normal range
  - Abnormal highlighting
- Status badges (Normal/Abnormal)
- Patient-friendly explanations
- Test categories (Hematology, Chemistry, etc.)

**4. Medication Cards**
- Pill image (if available)
- Generic and brand names
- Dosage information
- Route and frequency
- Physical description
- Expandable FAQ section per medication

**5. FAQ Section**
- Collapsible questions
- AI-generated answers
- Common concerns addressed

**6. References**
- Source citations (if enabled)
- Links to original medical sources

---

## Extending the System

### Adding New Medications

1. **Obtain pill image** (high-quality photo)

2. **Save to** `Medications/Drug_Images/MedicationName.jpg`

3. **Update** `Medications/Medications.json`:
```json
{
  "full_name": "New Medication Name",
  "generic_name": "Generic Name",
  "brand_names": ["Brand1", "Brand2"],
  "aliases": ["Alias1", "Alias2"],
  "physical_description": "Describe the pill appearance",
  "image_path": "Medications/Drug_Images/MedicationName.jpg"
}
```

4. **Run script** - medication will automatically be matched and displayed

### Adding Question Templates

Edit `utils/perplexity_question_templates.json`:

```json
{
  "id": "custom_question_id",
  "template": "Your question with {placeholders}?",
  "required_fields": ["field_name"],
  "category": "medications|diagnoses|procedures|general"
}
```

### Customizing Detail Levels

Modify the system prompt in `summarize_data()` function:

```python
# Line ~250 in summarize_to_page.py
detail_instructions = {
    1: "Explain at 5th grade level...",
    2: "Explain at high school level...",
    3: "Explain at college level..."
}
```

### Adding New Data Sources

Extend `patient_json.py` to include additional MIMIC-IV tables:

```python
def prepare_custom_data_list(data_df):
    """Convert custom data to list format"""
    custom_list = []
    for idx, row in data_df.iterrows():
        custom_list.append({
            'field1': row['column1'],
            'field2': row['column2']
        })
    return custom_list
```

---

## Technical Details

### Dependencies

- **pandas**: Data manipulation and analysis
- **plotly**: Interactive visualizations
- **perplexity-python**: AI-powered summarization
- **argparse**: Command-line interface
- **json**: Data serialization
- **re**: Regular expressions for text processing
- **datetime**: Timestamp handling
- **base64**: Image encoding for HTML

### External APIs

**Perplexity AI API**
- Model: `sonar`
- Domain filtering for medical accuracy
- Trusted sources:
  - my.clevelandclinic.org
  - mayoclinic.org
  - medlineplus.gov
  - webmd.com
  - pubmed.ncbi.nlm.nih.gov
  - nih.gov
  - drugs.com

### Data Source

**MIMIC-IV (Medical Information Mart for Intensive Care)**
- Version 3.1
- De-identified electronic health records
- Access requires PhysioNet credentialing
- https://physionet.org/content/mimiciv/

---

## Troubleshooting

### Common Issues

**1. "Perplexity API key not found"**
```bash
# Set environment variable
export PERPLEXITY_API_KEY="your-key-here"
```

**2. "Medication image not found"**
- Check that image exists in `Medications/Drug_Images/`
- Verify filename matches exactly in `Medications.json`
- Ensure image path is relative to project root

**3. "Empty timeline/No data"**
- Verify HADM_ID exists in dataset
- Check that JSON file has all required fields
- Ensure data was properly converted from MIMIC-IV

**4. "Module not found"**
```bash
pip install pandas plotly perplexity-python
```

---

## Contributors

**Team Chickens-Datathon-25**
- Jake
- Rohin
- Conor

---

## License

This project uses MIMIC-IV data, which requires PhysioNet credentialing and adherence to data use agreements.

---

## Acknowledgments

- **MIMIC-IV**: Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023). MIMIC-IV (version 3.1). PhysioNet.
- **Perplexity AI**: For intelligent medical information summarization
- **Plotly**: For interactive visualization capabilities
