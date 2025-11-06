import argparse
import json
import os
from perplexity import Perplexity

os.environ["PERPLEXITY_API_KEY"] = 

def summarize_data(data, detail_level):
    client = Perplexity()
    with open("utils/perplexity_question_templates.json", "r") as f:
        question_templates = json.load(f)

    system_prompt = f"""
    You are a professional patient advocate that is tasked with interpreting patient chart data from a provider's perspective and translating it into an easy-to-digest format for a patient.
    You are given a JSON object containing the patient's data. You are to summarize the data in a way that is easy to understand for a patient. Only provide information that you can verify from your search results, and clearly state if certain details are not available. 

    Please return your response in a JSON object with the following keys:
    - visit_summary: A summary and interpretation of the patient's visit. The visit is included in input data as a timeline of events under the 'timeline' key.
    - lab_results_summary: A list of all of the pertinent positive and negative test results according to the patient's chief complaint and visit timeline, alongside what the lab test measures and what the result signifies.
                           Be sure not to make any diagnoses or draw any conclusions from the lab results, just say theoretically what the result signals and why it might be important to the patient. Reference ranges are provided.
                           Input data includes a 'lab_results' key which contains a list of lab results, reference ranges, and flags.
    - medication_summary: A list of all of the pertinent medications the patient is taking, alongside what the medication is for and what the dosage is. Please be sure to give a human-readable description of what the medication is for and how it works.
                          Input data includes a 'discharge_medications' key which contains a list of medications the patient is taking, alongside what the medication is for and what the dosage is.
    - frequently_asked_questions: Please provide a list of frequently asked questions and answers according to the following specification and the patient's data. {question_templates}

    """

    detail_prompt = f"Responses should follow either 'basic mode' (1), 'enhanced mode' (2), or 'learner mode' (3) with increasing detail and complexity. Imagine basic mode to be 8th grade competency and learner mode to be someone taking a college level course."
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_data", type=str, required=True)
    parser.add_argument("--detail_level", type=int, required=True, choices=[1, 2, 3])
    args = parser.parse_args()

    with open(args.input_data, "r") as f:
        data = json.load(f)

    print(summarize_data(data, args.detail_level))
