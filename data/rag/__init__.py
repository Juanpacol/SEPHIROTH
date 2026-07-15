"""
RAG (Retrieval-Augmented Generation) pipeline for medical evidence.

Keyword-scored retrieval over an in-memory corpus seeded with clinical
guideline excerpts. Designed so the vector-store backend (pgvector +
LlamaIndex) can replace `retrieve()` internals without changing callers —
every result always carries a citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

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


@dataclass
class Document:
    """Medical document with mandatory citation metadata."""

    id: str
    content: str
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        org = self.metadata.get("organization", "")
        year = self.metadata.get("year", "")
        title = self.metadata.get("title", self.source)
        parts = [p for p in [title, org, str(year) if year else ""] if p]
        return ", ".join(parts)


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
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Glycemic Targets & Pharmacologic Approaches",
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
        metadata={"organization": "ACC/AHA", "year": 2023, "title": "High Blood Pressure Management"},
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
        metadata={"organization": "AHA/ACC/HFSA", "year": 2022, "title": "Management of Heart Failure"},
    ),
    Document(
        id="gold-2024-copd",
        content=(
            "For COPD patients with frequent exacerbations, LABA+LAMA combination "
            "therapy is preferred. Inhaled corticosteroids are added for patients "
            "with blood eosinophils >=300 cells/uL or continued exacerbations."
        ),
        source="GOLD COPD Report",
        metadata={"organization": "GOLD", "year": 2024, "title": "COPD Diagnosis, Management and Prevention"},
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
            "organization": "ATS/IDSA",
            "year": 2023,
            "title": "Treatment of Community-Acquired Pneumonia",
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
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Chronic Kidney Disease in Diabetes",
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
        metadata={"organization": "USPSTF", "year": 2021, "title": "Screening for Colorectal Cancer"},
    ),
    Document(
        id="uspstf-2024-breast",
        content=(
            "The USPSTF recommends biennial screening mammography for women aged "
            "40 to 74 years. Evidence is insufficient to assess the balance of "
            "benefits and harms of screening in women 75 years and older."
        ),
        source="USPSTF Breast Cancer Screening Recommendation",
        metadata={"organization": "USPSTF", "year": 2024, "title": "Screening for Breast Cancer"},
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
        metadata={"organization": "KDIGO", "year": 2024, "title": "Evaluation and Management of CKD"},
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
        metadata={"organization": "ACC/AHA", "year": 2018, "title": "Management of Blood Cholesterol"},
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
        metadata={"organization": "GINA", "year": 2024, "title": "Global Strategy for Asthma Management"},
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
            "organization": "AHA/ASA",
            "year": 2021,
            "title": "Early Management of Acute Ischemic Stroke",
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
        metadata={"organization": "IDSA", "year": 2019, "title": "Treatment of Uncomplicated Cystitis"},
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
            "organization": "Surviving Sepsis Campaign",
            "year": 2021,
            "title": "Management of Sepsis and Septic Shock",
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
            "organization": "ACC/AHA/HRS",
            "year": 2024,
            "title": "Anticoagulation in Atrial Fibrillation",
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
        metadata={"organization": "ACR", "year": 2020, "title": "Management of Gout"},
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
        metadata={"organization": "WHO", "year": 2022, "title": "Treatment of Drug-Susceptible Tuberculosis"},
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
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Obesity Management in Type 2 Diabetes",
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
        metadata={"organization": "ACOG", "year": 2020, "title": "Gestational Hypertension and Preeclampsia"},
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
            "organization": "AAP",
            "year": 2013,
            "title": "Diagnosis and Management of Acute Otitis Media",
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
            "organization": "American Diabetes Association",
            "year": 2024,
            "title": "Hypertension Management in Diabetes",
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
            "organization": "ACC/AHA",
            "year": 2019,
            "title": "Primary Prevention of Cardiovascular Disease",
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
        metadata={"organization": "NICE", "year": 2022, "title": "Management of Depression in Adults"},
    ),
]


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class RAGPipeline:
    """Retrieval pipeline over medical documents. Every hit carries a citation."""

    def __init__(self, seed: bool = True):
        self.documents: List[Document] = list(SEED_GUIDELINES) if seed else []

    def add_document(self, doc: Document) -> None:
        self.documents.append(doc)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Score documents by weighted keyword overlap and return the top_k
        as dicts with content, source, citation, and score."""
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

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
                "score": round(score, 4),
                "metadata": doc.metadata,
            }
            for score, doc in scored[:top_k]
        ]


class MedicalKnowledgeBase:
    """Named collections of medical knowledge sources."""

    def __init__(self):
        self.pipeline = RAGPipeline()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.pipeline.retrieve(query, top_k=top_k)


__all__ = ["RAGPipeline", "Document", "MedicalKnowledgeBase", "SEED_GUIDELINES"]
