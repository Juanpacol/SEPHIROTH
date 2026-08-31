"""
RAG (Retrieval-Augmented Generation) pipeline for medical evidence.

Hybrid retrieval over an in-memory corpus seeded with clinical guideline
excerpts: keyword overlap (always available, zero dependencies) fused via
Reciprocal Rank Fusion with dense Gemini-embedding similarity (when an
embedding provider is configured). Every result always carries a citation,
and the output shape is identical regardless of which scoring path fired —
see `retrieve()`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from data.embeddings.base import EmbeddingProvider, EmbeddingUnavailable
from data.rag.corpus_primary_care import PRIMARY_CARE_GUIDELINES
from data.rag.document import Document
from data.vectors import InMemoryVectorStore, VectorStore

logger = logging.getLogger(__name__)

RRF_K = 60
# Dense embeddings are the more semantically precise signal when available;
# keyword overlap (unweighted by IDF) is a crude fallback prone to noise
# from generic shared words. Weighting dense 2x prevents keyword noise, or
# a near-exact RRF tie, from overriding a clear embedding-model win — see
# `_fuse()`.
KEYWORD_WEIGHT = 1.0
DENSE_WEIGHT = 2.0

STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "for",
    "in",
    "on",
    "to",
    "and",
    "or",
    "what",
    "which",
    "with",
    "how",
    "when",
    "should",
    "be",
    "my",
}


# Seed corpus: short excerpts from public clinical guidelines. Extend by
# calling RAGPipeline.add_document() or the /api/rag ingestion endpoint.
SEED_GUIDELINES: List[Document] = [
    Document(
        id="ada-2024-hba1c",
        content=(
            "An A1C goal for many nonpregnant adults with diabetes of <7% "
            "without significant hypoglycemia is appropriate. Metformin is the "
            "preferred initial pharmacologic agent for type 2 diabetes."
        ),
        source="ADA Standards of Care in Diabetes",
        metadata={
            "category": "endocrinology",
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Glycemic Targets & Pharmacologic Approaches",
            "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        },
    ),
    Document(
        id="acc-aha-2023-htn",
        content=(
            "A blood pressure target of <130/80 mmHg is recommended for most "
            "adults with hypertension. First-line agents include thiazide "
            "diuretics, ACE inhibitors, ARBs, and calcium channel blockers."
        ),
        source="ACC/AHA Hypertension Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "ACC/AHA",
            "year": 2023,
            "title": "High Blood Pressure Management",
            "url": "https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065",
        },
    ),
    Document(
        id="aha-2022-hf",
        content=(
            "In patients with heart failure with reduced ejection fraction "
            "(HFrEF), guideline-directed medical therapy includes ARNI/ACEi/ARB, "
            "beta-blockers, mineralocorticoid receptor antagonists, and SGLT2 "
            "inhibitors. SGLT2 inhibitors are recommended regardless of diabetes status."
        ),
        source="AHA/ACC/HFSA Heart Failure Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "AHA/ACC/HFSA",
            "year": 2022,
            "title": "Management of Heart Failure",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001063",
        },
    ),
    Document(
        id="gold-2024-copd",
        content=(
            "For COPD patients with frequent exacerbations, LABA+LAMA combination "
            "therapy is preferred. Inhaled corticosteroids are added for patients "
            "with blood eosinophils >=300 cells/uL or continued exacerbations."
        ),
        source="GOLD COPD Report",
        metadata={
            "category": "pulmonology",
            "organization": "GOLD",
            "year": 2024,
            "title": "COPD Diagnosis, Management and Prevention",
            "url": "https://goldcopd.org/2024-gold-report/",
        },
    ),
    Document(
        id="idsa-2023-cap",
        content=(
            "For outpatient community-acquired pneumonia in healthy adults, "
            "amoxicillin or doxycycline is recommended. For inpatients, "
            "beta-lactam plus macrolide combination therapy is standard."
        ),
        source="ATS/IDSA Community-Acquired Pneumonia Guideline",
        metadata={
            "category": "infectious_disease",
            "organization": "ATS/IDSA",
            "year": 2023,
            "title": "Treatment of Community-Acquired Pneumonia",
            "url": "https://doi.org/10.1164/rccm.201908-1581ST",
        },
    ),
    Document(
        id="ada-2024-ckd",
        content=(
            "In patients with type 2 diabetes and chronic kidney disease, an "
            "SGLT2 inhibitor is recommended for those with eGFR >=20 mL/min/1.73m2 "
            "to reduce CKD progression and cardiovascular risk. ACE inhibitors or "
            "ARBs are first-line for patients with albuminuria and hypertension."
        ),
        source="ADA Standards of Care in Diabetes",
        metadata={
            "category": "nephrology",
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Chronic Kidney Disease in Diabetes",
            "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        },
    ),
    Document(
        id="uspstf-2021-colorectal",
        content=(
            "The USPSTF recommends screening for colorectal cancer in all adults "
            "aged 45 to 75 years. Screening options include colonoscopy every 10 "
            "years, annual FIT testing, or stool DNA-FIT every 1-3 years."
        ),
        source="USPSTF Colorectal Cancer Screening Recommendation",
        metadata={
            "category": "screening",
            "organization": "USPSTF",
            "year": 2021,
            "title": "Screening for Colorectal Cancer",
            "url": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/colorectal-cancer-screening",
        },
    ),
    Document(
        id="uspstf-2024-breast",
        content=(
            "The USPSTF recommends biennial screening mammography for women aged "
            "40 to 74 years. Evidence is insufficient to assess the balance of "
            "benefits and harms of screening in women 75 years and older."
        ),
        source="USPSTF Breast Cancer Screening Recommendation",
        metadata={
            "category": "screening",
            "organization": "USPSTF",
            "year": 2024,
            "title": "Screening for Breast Cancer",
            "url": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/breast-cancer-screening",
        },
    ),
    Document(
        id="kdigo-2024-ckd",
        content=(
            "CKD staging is based on eGFR and albuminuria categories. SGLT2 "
            "inhibitors and ACE inhibitors or ARBs are recommended to slow "
            "progression in patients with albuminuric CKD, regardless of "
            "diabetes status."
        ),
        source="KDIGO Clinical Practice Guideline for CKD",
        metadata={
            "category": "nephrology",
            "organization": "KDIGO",
            "year": 2024,
            "title": "Evaluation and Management of CKD",
            "url": "https://kdigo.org/guidelines/ckd-evaluation-and-management/",
        },
    ),
    Document(
        id="acc-aha-2018-lipids",
        content=(
            "High-intensity statin therapy is recommended for patients with "
            "clinical atherosclerotic cardiovascular disease and for primary "
            "prevention in adults 40-75 years with LDL-C >=190 mg/dL or diabetes "
            "with additional risk factors."
        ),
        source="ACC/AHA Multi-Society Cholesterol Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "ACC/AHA",
            "year": 2018,
            "title": "Management of Blood Cholesterol",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000625",
        },
    ),
    Document(
        id="gina-2024-asthma",
        content=(
            "For adults and adolescents with asthma, as-needed low-dose "
            "ICS-formoterol is preferred as reliever therapy over short-acting "
            "beta-agonist alone, even at the mildest step of treatment, to "
            "reduce exacerbation risk."
        ),
        source="Global Initiative for Asthma Report",
        metadata={
            "category": "pulmonology",
            "organization": "GINA",
            "year": 2024,
            "title": "Global Strategy for Asthma Management",
            "url": "https://ginasthma.org/2026-gina-strategy-report/",
        },
    ),
    Document(
        id="aha-asa-2021-stroke",
        content=(
            "Intravenous alteplase is recommended within 4.5 hours of symptom "
            "onset for eligible patients with acute ischemic stroke. Mechanical "
            "thrombectomy is recommended for large-vessel occlusion within 24 "
            "hours in selected patients."
        ),
        source="AHA/ASA Acute Ischemic Stroke Guideline",
        metadata={
            "category": "neurology",
            "organization": "AHA/ASA",
            "year": 2021,
            "title": "Early Management of Acute Ischemic Stroke",
            "url": "https://www.ahajournals.org/doi/10.1161/STR.0000000000000211",
        },
    ),
    Document(
        id="idsa-2019-uti",
        content=(
            "Nitrofurantoin for 5 days or trimethoprim-sulfamethoxazole for 3 "
            "days are first-line agents for uncomplicated cystitis in women. "
            "Fluoroquinolones are reserved for cases where first-line agents "
            "are not suitable."
        ),
        source="IDSA Uncomplicated UTI Guideline",
        metadata={
            "category": "infectious_disease",
            "organization": "IDSA",
            "year": 2019,
            "title": "Treatment of Uncomplicated Cystitis",
            "url": "https://www.idsociety.org/practice-guideline/uncomplicated-cystitis-and-pyelonephritis-uti/",
        },
    ),
    Document(
        id="sscm-2021-sepsis",
        content=(
            "For patients with sepsis or septic shock, broad-spectrum "
            "antibiotics should be administered within 1 hour of recognition, "
            "along with 30 mL/kg of intravenous crystalloid fluid for "
            "hypotension or elevated lactate."
        ),
        source="Surviving Sepsis Campaign Guidelines",
        metadata={
            "category": "critical_care",
            "organization": "Surviving Sepsis Campaign",
            "year": 2021,
            "title": "Management of Sepsis and Septic Shock",
            "url": "https://www.sccm.org/SurvivingSepsisCampaign/Guidelines",
        },
    ),
    Document(
        id="accp-2024-afib",
        content=(
            "Oral anticoagulation is recommended for patients with atrial "
            "fibrillation and a CHA2DS2-VASc score of 2 or more in men or 3 or "
            "more in women. Direct oral anticoagulants are preferred over "
            "warfarin in most eligible patients."
        ),
        source="ACC/AHA/ACCP/HRS Atrial Fibrillation Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "ACC/AHA/HRS",
            "year": 2024,
            "title": "Anticoagulation in Atrial Fibrillation",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001193",
        },
    ),
    Document(
        id="acr-2020-gout",
        content=(
            "Urate-lowering therapy is recommended for patients with recurrent "
            "gout flares, tophi, or radiographic damage, with allopurinol as "
            "the preferred first-line agent, titrated to a serum urate target "
            "below 6 mg/dL."
        ),
        source="ACR Guideline for Management of Gout",
        metadata={
            "category": "rheumatology",
            "organization": "ACR",
            "year": 2020,
            "title": "Management of Gout",
            "url": "https://rheumatology.org/gout-guideline",
        },
    ),
    Document(
        id="who-2022-tb",
        content=(
            "The standard regimen for drug-susceptible pulmonary tuberculosis "
            "is a 6-month course of isoniazid, rifampicin, pyrazinamide, and "
            "ethambutol for 2 months, followed by isoniazid and rifampicin for "
            "4 months."
        ),
        source="WHO Consolidated Guidelines on Tuberculosis",
        metadata={
            "category": "infectious_disease",
            "organization": "WHO",
            "year": 2022,
            "title": "Treatment of Drug-Susceptible Tuberculosis",
            "url": "https://www.who.int/publications/i/item/9789240048126",
        },
    ),
    Document(
        id="ada-2024-obesity",
        content=(
            "GLP-1 receptor agonists and dual GIP/GLP-1 agonists are "
            "recommended for weight management in patients with type 2 "
            "diabetes and obesity, in addition to lifestyle intervention, "
            "given their combined glycemic and weight benefits."
        ),
        source="ADA Standards of Care in Diabetes",
        metadata={
            "category": "endocrinology",
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Obesity Management in Type 2 Diabetes",
            "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        },
    ),
    Document(
        id="acog-2020-preeclampsia",
        content=(
            "Low-dose aspirin starting at 12-28 weeks of gestation is "
            "recommended for patients at high risk of preeclampsia. Magnesium "
            "sulfate is recommended for seizure prophylaxis in patients with "
            "severe features of preeclampsia."
        ),
        source="ACOG Practice Bulletin on Preeclampsia",
        metadata={
            "category": "obstetrics",
            "organization": "ACOG",
            "year": 2020,
            "title": "Gestational Hypertension and Preeclampsia",
            "url": "https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2020/06/gestational-hypertension-and-preeclampsia",
        },
    ),
    Document(
        id="aap-2013-otitis",
        content=(
            "Amoxicillin is the first-line antibiotic for acute otitis media "
            "in children without recent beta-lactam exposure. Watchful waiting "
            "may be offered for children 6 months to 12 years with unilateral "
            "mild symptoms."
        ),
        source="AAP Clinical Practice Guideline on Acute Otitis Media",
        metadata={
            "category": "pediatrics",
            "organization": "AAP",
            "year": 2013,
            "title": "Diagnosis and Management of Acute Otitis Media",
            "url": "https://publications.aap.org/pediatrics/article/131/3/e964/30912",
        },
    ),
    Document(
        id="ada-2024-hypertension-dm",
        content=(
            "A blood pressure target of <130/80 mmHg is recommended for most "
            "adults with diabetes and hypertension. ACE inhibitors or ARBs are "
            "preferred first-line agents, particularly in the presence of "
            "albuminuria."
        ),
        source="ADA Standards of Care in Diabetes",
        metadata={
            "category": "endocrinology",
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Hypertension Management in Diabetes",
            "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        },
    ),
    Document(
        id="acc-aha-2019-primary-prevention",
        content=(
            "Aspirin for primary prevention of cardiovascular disease is not "
            "routinely recommended due to bleeding risk, except in select "
            "high-risk adults 40-70 years after a risk-benefit discussion with "
            "their clinician."
        ),
        source="ACC/AHA Primary Prevention of Cardiovascular Disease Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "ACC/AHA",
            "year": 2019,
            "title": "Primary Prevention of Cardiovascular Disease",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000678",
        },
    ),
    Document(
        id="nice-2022-depression",
        content=(
            "For moderate to severe depression, a combination of "
            "antidepressant medication and high-intensity psychological "
            "therapy such as cognitive behavioral therapy is recommended over "
            "either treatment alone."
        ),
        source="NICE Guideline on Depression in Adults",
        metadata={
            "category": "psychiatry",
            "organization": "NICE",
            "year": 2022,
            "title": "Management of Depression in Adults",
            "url": "https://www.nice.org.uk/guidance/ng222",
        },
    ),
    # --- Strengthening existing categories (cardiovascular, endocrinology,
    # infectious_disease, pulmonology, nephrology, rheumatology,
    # psychiatry) with adjacent, frequently-asked topics those categories
    # didn't cover yet. ---
    Document(
        id="acc-aha-2025-acs",
        content=(
            "For ST-elevation myocardial infarction (STEMI), primary "
            "percutaneous coronary intervention within 90 minutes of first "
            "medical contact is preferred over fibrinolysis. Dual antiplatelet "
            "therapy (aspirin plus a P2Y12 inhibitor) is recommended for all "
            "acute coronary syndrome patients regardless of reperfusion strategy."
        ),
        source="ACC/AHA Acute Coronary Syndrome Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "ACC/AHA",
            "year": 2025,
            "title": "Management of Acute Coronary Syndromes",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001168",
        },
    ),
    Document(
        id="acc-aha-2023-vte",
        content=(
            "For acute deep vein thrombosis or pulmonary embolism without "
            "cancer, direct oral anticoagulants are preferred over warfarin as "
            "first-line therapy. Anticoagulation duration is at least 3 months, "
            "extended indefinitely for unprovoked events with low bleeding risk."
        ),
        source="ACCP Antithrombotic Therapy for VTE Guideline",
        metadata={
            "category": "cardiovascular",
            "organization": "ACCP",
            "year": 2021,
            "title": "Antithrombotic Therapy for VTE Disease",
            "url": "https://journal.chestnet.org/article/S0012-3692(21)01506-3/fulltext",
        },
    ),
    Document(
        id="ata-2014-hypothyroidism",
        content=(
            "Levothyroxine is the first-line treatment for primary "
            "hypothyroidism, dosed to normalize TSH (typical target 0.4-4.0 "
            "mIU/L, adjusted for age). Levothyroxine should be taken on an "
            "empty stomach, separated from calcium or iron supplements by at "
            "least 4 hours to avoid reduced absorption."
        ),
        source="ATA Guidelines for Hypothyroidism",
        metadata={
            "category": "endocrinology",
            "organization": "American Thyroid Association",
            "year": 2014,
            "title": "Guidelines for the Treatment of Hypothyroidism",
            "url": "https://www.thyroid.org/hypothyroidism/",
        },
    ),
    Document(
        id="ada-2024-microvascular-screening",
        content=(
            "Adults with type 2 diabetes should have an annual dilated eye "
            "exam for retinopathy, an annual urine albumin-to-creatinine ratio "
            "for nephropathy, and an annual comprehensive foot exam with "
            "monofilament testing for peripheral neuropathy, starting at "
            "diagnosis."
        ),
        source="ADA Standards of Care in Diabetes",
        metadata={
            "category": "endocrinology",
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Microvascular Complications Screening in Diabetes",
            "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        },
    ),
    Document(
        id="idsa-2014-cellulitis",
        content=(
            "For non-purulent cellulitis, empiric therapy should cover "
            "streptococci with an agent such as cephalexin or dicloxacillin. "
            "Purulent cellulitis or abscess should be covered for MRSA with "
            "trimethoprim-sulfamethoxazole, doxycycline, or clindamycin, plus "
            "incision and drainage of any abscess."
        ),
        source="IDSA Skin and Soft Tissue Infection Guideline",
        metadata={
            "category": "infectious_disease",
            "organization": "IDSA",
            "year": 2014,
            "title": "Diagnosis and Management of Skin and Soft Tissue Infections",
            "url": "https://academic.oup.com/cid/article/59/2/e10/2895845",
        },
    ),
    Document(
        id="gold-2024-copd-exacerbation",
        content=(
            "Acute COPD exacerbations are treated with short-acting "
            "bronchodilators, a short course of oral corticosteroids "
            "(prednisone 40mg for 5 days), and antibiotics if increased "
            "sputum purulence is present alongside increased dyspnea or "
            "sputum volume."
        ),
        source="GOLD COPD Report",
        metadata={
            "category": "pulmonology",
            "organization": "GOLD",
            "year": 2024,
            "title": "Management of COPD Exacerbations",
            "url": "https://goldcopd.org/2024-gold-report/",
        },
    ),
    Document(
        id="kdigo-2012-aki",
        content=(
            "Acute kidney injury is staged by the rise in serum creatinine or "
            "decline in urine output: Stage 1 is a 1.5-1.9x creatinine rise or "
            "<0.5 mL/kg/h urine output for 6-12h. Management is supportive — "
            "optimize volume status, avoid nephrotoxins, and adjust "
            "renally-cleared drug doses; dialysis is reserved for refractory "
            "fluid overload, hyperkalemia, or acidosis."
        ),
        source="KDIGO Clinical Practice Guideline for Acute Kidney Injury",
        metadata={
            "category": "nephrology",
            "organization": "KDIGO",
            "year": 2012,
            "title": "Diagnosis and Management of Acute Kidney Injury",
            "url": "https://kdigo.org/guidelines/acute-kidney-injury/",
        },
    ),
    # --- General health knowledge: patient-education-level explanations,
    # not treatment guidance — a distinct category (`general_health`) from
    # the clinician-facing guideline excerpts above, sourced from public
    # patient-education bodies (MedlinePlus, CDC, WHO, AHA patient
    # materials). Serves both a clinician wanting a plain-language check
    # and the patient portal, which has had no knowledge source at all
    # until now. ---
    Document(
        id="medlineplus-blood-pressure",
        content=(
            "Blood pressure measures the force of blood against artery walls, "
            "given as two numbers: systolic (pressure while the heart beats) "
            "over diastolic (pressure between beats). A normal reading is "
            "below 120/80 mmHg. High blood pressure often has no symptoms, "
            "which is why regular checks matter even when feeling fine."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2024,
            "title": "Understanding Blood Pressure Readings",
            "url": "https://medlineplus.gov/highbloodpressure.html",
        },
    ),
    Document(
        id="medlineplus-a1c",
        content=(
            "The A1C (or HbA1c) test shows average blood sugar levels over "
            "the past 2-3 months. An A1C below 5.7% is normal, 5.7-6.4% "
            "indicates prediabetes, and 6.5% or higher indicates diabetes. "
            "Unlike a daily finger-stick, A1C reflects a longer-term trend "
            "rather than a single moment."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2024,
            "title": "The A1C Test and Diabetes",
            "url": "https://medlineplus.gov/a1c.html",
        },
    ),
    Document(
        id="medlineplus-cholesterol",
        content=(
            "Cholesterol travels in the blood in two main forms: LDL ('bad' "
            "cholesterol), which builds up in artery walls, and HDL ('good' "
            "cholesterol), which helps remove it. A cholesterol panel also "
            "reports triglycerides, another blood fat linked to heart disease "
            "risk when elevated."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2024,
            "title": "Cholesterol Levels: What They Mean",
            "url": "https://medlineplus.gov/cholesterollevelswhattheymean.html",
        },
    ),
    Document(
        id="cdc-hydration",
        content=(
            "There is no single daily water target that fits everyone — needs "
            "vary with body size, activity, climate, and health conditions. "
            "Thirst and pale-yellow urine are practical everyday indicators of "
            "adequate hydration; dark urine, dizziness, or infrequent "
            "urination can signal a need to drink more."
        ),
        source="CDC",
        metadata={
            "category": "general_health",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2022,
            "title": "Water and Healthier Drinks",
            "url": "https://www.cdc.gov/nutrition/data-statistics/plain-water-the-healthier-choice.html",
        },
    ),
    Document(
        id="medlineplus-heart-rate",
        content=(
            "A normal resting heart rate for most adults is 60-100 beats per "
            "minute, measured after sitting quietly. Well-conditioned "
            "athletes may have a lower resting rate, sometimes 40-60 bpm. A "
            "rate consistently outside 60-100 at rest, especially with "
            "symptoms like dizziness or chest discomfort, warrants medical "
            "evaluation."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2023,
            "title": "Understanding Your Heart Rate",
            "url": "https://medlineplus.gov/ency/article/003399.htm",
        },
    ),
    Document(
        id="cdc-sleep",
        content=(
            "Most adults need at least 7 hours of sleep per night for optimal "
            "health. Consistently getting less than 7 hours is linked to "
            "higher risk of obesity, diabetes, high blood pressure, heart "
            "disease, and depression. Sleep needs are higher for teens "
            "(8-10 hours) and school-age children (9-12 hours)."
        ),
        source="CDC",
        metadata={
            "category": "general_health",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2022,
            "title": "How Much Sleep Do I Need?",
            "url": "https://www.cdc.gov/sleep/about/index.html",
        },
    ),
    Document(
        id="cdc-stroke-warning-signs",
        content=(
            "The F.A.S.T. warning signs of stroke are: Face drooping on one "
            "side, Arm weakness or drift when raised, Speech that is slurred "
            "or strange, and Time to call emergency services immediately if "
            "any of these signs appear, even if they resolve. Fast treatment "
            "significantly improves outcomes."
        ),
        source="CDC",
        metadata={
            "category": "general_health",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2023,
            "title": "Stroke Signs and Symptoms (F.A.S.T.)",
            "url": "https://www.cdc.gov/stroke/signs-symptoms/index.html",
        },
    ),
] + PRIMARY_CARE_GUIDELINES


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class RAGPipeline:
    """Retrieval pipeline over medical documents. Every hit carries a citation.

    Fully functional with zero configuration — `RAGPipeline()` alone must
    keep working with no network or DB, since it's constructed at module
    scope by `intelligence/mcp/rag_server.py` and by the eval harness's
    `compute_retrieval_metrics`. Passing an `embedding_provider` upgrades
    retrieval to hybrid (dense + keyword); passing none keeps today's exact
    keyword-only behavior.
    """

    def __init__(
        self,
        seed: bool = True,
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_store: Optional[VectorStore] = None,
        min_similarity: float = 0.70,
    ):
        self.documents: List[Document] = list(SEED_GUIDELINES) if seed else []
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store or InMemoryVectorStore()
        self._min_similarity = min_similarity
        if seed and embedding_provider is not None:
            self._index_documents(self.documents)

    def _index_documents(self, docs: List[Document]) -> None:
        """Index documents one at a time so a single cache miss (a doc added
        without rebuilding the embeddings artifact) degrades only that one
        document to keyword-only, instead of silently emptying the entire
        vector store — the whole-corpus batch call used to raise on the
        first miss and `_index_documents` swallowed it with a bare `return`,
        leaving every other document unindexed too."""
        skipped = 0
        for doc in docs:
            try:
                vector = self._embedding_provider.embed_documents([doc.content])[0]
            except EmbeddingUnavailable:
                skipped += 1
                continue
            self._vector_store.upsert(doc.id, vector, {})
        if skipped:
            logger.warning(
                "RAGPipeline: %d/%d document(s) have no cached embedding and were "
                "left keyword-only for this session — rebuild the embeddings artifact.",
                skipped,
                len(docs),
            )

    def add_document(self, doc: Document) -> None:
        self.documents.append(doc)
        if self._embedding_provider is not None:
            self._index_documents([doc])

    def _retrieve_keyword(self, query_tokens: set) -> List[Dict[str, Any]]:
        """Today's original scoring: weighted keyword overlap."""
        scored = []
        for doc in self.documents:
            doc_tokens = _tokenize(doc.content)
            if not doc_tokens:
                continue
            overlap = sum(1 for t in doc_tokens if t in query_tokens)
            score = overlap / len(doc_tokens) ** 0.5
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "id": doc.id,
                "content": doc.content,
                "source": doc.source,
                "citation": doc.citation,
                "url": doc.metadata.get("url"),
                "score": round(score, 4),
                "metadata": doc.metadata,
            }
            for score, doc in scored
        ]

    def _fuse(
        self, keyword_hits: List[Dict[str, Any]], dense_hits: List[Any], top_k: int
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion, weighted toward the dense signal.

        Keyword scoring here isn't IDF-weighted (`score = overlap /
        sqrt(len(doc))`), so short documents sharing only generic words
        with the query (e.g. "patient", "class") can rank artificially
        high — real corpus behavior confirmed empirically while building
        the matching-quality test suite (see tests/test_embeddings_
        matching.py::test_compound_query_surfaces_all_relevant_documents
        and ::test_bp_target_specific_query_does_not_default_to_ckd_
        document). An equal-weight RRF let that keyword noise, or a
        near-exact RRF tie, outrank a real embedding-model win. Dense gets
        2x weight so it can only be overridden by a *clear* keyword
        signal, not by noise or a coin-flip tie.
        """
        by_id = {doc.id: doc for doc in self.documents}
        rrf_scores: Dict[str, float] = {}
        for rank, hit in enumerate(keyword_hits):
            rrf_scores[hit["id"]] = rrf_scores.get(hit["id"], 0.0) + KEYWORD_WEIGHT / (RRF_K + rank + 1)
        for rank, scored_doc in enumerate(dense_hits):
            rrf_scores[scored_doc.id] = rrf_scores.get(scored_doc.id, 0.0) + DENSE_WEIGHT / (RRF_K + rank + 1)

        ordered_ids = sorted(rrf_scores.keys(), key=lambda doc_id: rrf_scores[doc_id], reverse=True)
        results = []
        for doc_id in ordered_ids[:top_k]:
            doc = by_id.get(doc_id)
            if doc is None:
                continue
            results.append(
                {
                    "id": doc.id,
                    "content": doc.content,
                    "source": doc.source,
                    "citation": doc.citation,
                    "url": doc.metadata.get("url"),
                    "score": round(rrf_scores[doc_id], 4),
                    "metadata": doc.metadata,
                }
            )
        return results

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Return the top_k documents as dicts with content, source,
        citation, and score. Hybrid when an embedding provider is
        configured and available; keyword-only otherwise — the output
        shape never changes. Reranked for diversity and content-budgeted
        (`src/sephiroth/context/`) before returning."""
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        keyword_hits = self._retrieve_keyword(query_tokens)
        if self._embedding_provider is None:
            return self._finalize(keyword_hits, top_k)

        try:
            query_vector = self._embedding_provider.embed_query(query)
        except EmbeddingUnavailable:
            return self._finalize(keyword_hits, top_k)  # full fallback — never raises to the caller

        dense_hits = self._vector_store.search(query_vector, top_k=top_k * 2, min_score=self._min_similarity)
        return self._finalize(self._fuse(keyword_hits, dense_hits, top_k), top_k)

    def _finalize(self, hits: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        from core.config import settings
        from sephiroth.context import mmr_rerank, truncate

        reranked = mmr_rerank(hits, top_k=top_k)
        for hit in reranked:
            if hit.get("content"):
                hit["content"] = truncate(hit["content"], settings.max_context_chars)
        return reranked


class MedicalKnowledgeBase:
    """Named collections of medical knowledge sources."""

    def __init__(self):
        self.pipeline = RAGPipeline()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.pipeline.retrieve(query, top_k=top_k)


__all__ = ["RAGPipeline", "Document", "MedicalKnowledgeBase", "SEED_GUIDELINES"]
