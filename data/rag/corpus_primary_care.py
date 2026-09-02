"""Primary-care / frequent-complaint corpus.

Composed into `SEED_GUIDELINES` by `data.rag.__init__`. Split into its own
module because the base seed list (`data/rag/__init__.py`) was already large
before this addition — see that module's docstring for the corpus's design
rules (short literal excerpts, mandatory `url`, no synthesized detail).

This block exists to close a specific, measured gap: the seed corpus
covered chronic-disease guideline topics (diabetes, hypertension, heart
failure, COPD...) and a handful of patient-education explainers, but had
zero coverage of the symptoms that actually dominate ambulatory/primary-care
visits — headache, low back pain, a cold, a fever, an upset stomach. A
patient or clinician asking "what do I do for a headache" retrieved
nothing, and the run degraded to abstention. See
`docs/specs/` and the eval golden cases prefixed `general-` /
`primary-care-` for the cases this closes.
"""

from __future__ import annotations

from typing import List

from data.rag.document import Document

PRIMARY_CARE_GUIDELINES: List[Document] = [
    # --- Headache / neurology -------------------------------------------
    Document(
        id="ahs-2021-migraine",
        content=(
            "For acute migraine treatment, NSAIDs or triptans are first-line "
            "for most patients; combining a triptan with an NSAID is more "
            "effective than either alone. For patients with 4 or more "
            "migraine days per month, preventive therapy should be offered "
            "in addition to acute treatment."
        ),
        source="American Headache Society Consensus Statement",
        metadata={
            "category": "neurology",
            "organization": "American Headache Society",
            "year": 2021,
            "title": "Acute Treatment of Migraine",
            "url": "https://headachejournal.onlinelibrary.wiley.com/doi/10.1111/head.14153",
        },
    ),
    Document(
        id="cdc-headache-red-flags",
        content=(
            "Most headaches are not dangerous, but seek urgent care for a "
            "headache that is the 'worst of your life' and sudden in onset, "
            "a headache with fever and stiff neck, a headache after a head "
            "injury, or a headache with confusion, weakness, vision changes, "
            "or trouble speaking — these can signal a medical emergency."
        ),
        source="MedlinePlus",
        metadata={
            "category": "neurology",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2023,
            "title": "Headache Warning Signs",
            "url": "https://medlineplus.gov/headache.html",
        },
    ),
    Document(
        id="ichd3-tension-headache",
        content=(
            "Tension-type headache presents as bilateral, pressing or "
            "tightening pain of mild to moderate intensity, not aggravated "
            "by routine physical activity. First-line treatment is "
            "over-the-counter analgesia (acetaminophen or an NSAID) and "
            "addressing triggers such as stress, poor sleep, or dehydration."
        ),
        source="International Classification of Headache Disorders, 3rd ed.",
        metadata={
            "category": "neurology",
            "organization": "International Headache Society",
            "year": 2018,
            "title": "Tension-Type Headache",
            "url": "https://ichd-3.org/2-tension-type-headache/",
        },
    ),
    Document(
        id="aao-hns-2017-dizziness",
        content=(
            "Benign paroxysmal positional vertigo (BPPV) causes brief "
            "episodes of vertigo triggered by head position changes, "
            "typically lasting under a minute. The Epley maneuver is the "
            "recommended first-line treatment and resolves symptoms in most "
            "patients within one to two sessions."
        ),
        source="AAO-HNS Clinical Practice Guideline",
        metadata={
            "category": "neurology",
            "organization": "American Academy of Otolaryngology-Head and Neck Surgery",
            "year": 2017,
            "title": "Benign Paroxysmal Positional Vertigo",
            "url": "https://journals.sagepub.com/doi/10.1177/0194599816689667",
        },
    ),
    # --- Musculoskeletal ---------------------------------------------------
    Document(
        id="acp-2017-low-back-pain",
        content=(
            "For acute low back pain, most patients improve regardless of "
            "treatment; first-line care is nonpharmacologic — heat, "
            "massage, or gentle activity — and NSAIDs if medication is "
            "needed. Imaging is not recommended without red-flag findings "
            "such as trauma, unexplained weight loss, or neurologic deficit."
        ),
        source="ACP Clinical Practice Guideline",
        metadata={
            "category": "musculoskeletal",
            "organization": "American College of Physicians",
            "year": 2017,
            "title": "Noninvasive Treatments for Low Back Pain",
            "url": "https://www.acpjournals.org/doi/10.7326/M16-2367",
        },
    ),
    Document(
        id="nice-2020-back-pain-red-flags",
        content=(
            "Red flags requiring urgent evaluation of low back pain include "
            "new bladder or bowel dysfunction, saddle anesthesia, "
            "progressive leg weakness (possible cauda equina syndrome), "
            "fever with back pain, or a history of cancer with new-onset "
            "back pain (possible metastasis)."
        ),
        source="NICE Guideline NG59",
        metadata={
            "category": "musculoskeletal",
            "organization": "NICE",
            "year": 2020,
            "title": "Low Back Pain and Sciatica: Assessment",
            "url": "https://www.nice.org.uk/guidance/ng59",
        },
    ),
    Document(
        id="aaos-ankle-sprain",
        content=(
            "Most ankle sprains are treated with the RICE protocol (rest, "
            "ice, compression, elevation) and early protected weight-bearing "
            "as tolerated. The Ottawa Ankle Rules identify which sprains "
            "need an X-ray: bone tenderness at the malleolus tips or "
            "inability to bear weight for four steps immediately and in the "
            "emergency department."
        ),
        source="AAOS Clinical Guideline",
        metadata={
            "category": "musculoskeletal",
            "organization": "American Academy of Orthopaedic Surgeons",
            "year": 2021,
            "title": "Management of Acute Ankle Sprains",
            "url": "https://www.aaos.org/quality/quality-programs/lower-extremity-programs/ankle-sprains/",
        },
    ),
    # --- Upper respiratory / cough / sore throat ----------------------------
    Document(
        id="cdc-2023-common-cold",
        content=(
            "The common cold is a self-limited viral illness lasting "
            "7-10 days; antibiotics do not help and are not recommended. "
            "Supportive care — rest, fluids, and over-the-counter symptom "
            "relief (analgesics, decongestants) — is the standard of care. "
            "See a clinician if symptoms last beyond 10 days or worsen after "
            "initial improvement."
        ),
        source="CDC",
        metadata={
            "category": "infectious_disease",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2023,
            "title": "Common Cold: Symptoms and Care",
            "url": "https://www.cdc.gov/antibiotic-use/colds.html",
        },
    ),
    Document(
        id="idsa-2012-pharyngitis-centor",
        content=(
            "The Centor criteria (fever, tonsillar exudate, tender anterior "
            "cervical adenopathy, absence of cough) estimate the likelihood "
            "of group A streptococcal pharyngitis; a score of 3-4 warrants "
            "rapid strep testing. Penicillin or amoxicillin is first-line "
            "treatment for confirmed strep throat; antibiotics are not "
            "indicated for a low Centor score."
        ),
        source="IDSA Clinical Practice Guideline",
        metadata={
            "category": "infectious_disease",
            "organization": "IDSA",
            "year": 2012,
            "title": "Diagnosis and Management of Group A Streptococcal Pharyngitis",
            "url": "https://academic.oup.com/cid/article/55/10/1279/300756",
        },
    ),
    Document(
        id="acc-cough-guideline",
        content=(
            "Acute cough (under 3 weeks) is most often due to a viral upper "
            "respiratory infection and resolves without treatment; "
            "over-the-counter cough suppressants provide modest symptom "
            "relief. A cough lasting more than 8 weeks is chronic and "
            "warrants evaluation for causes such as asthma, GERD, or "
            "post-nasal drip."
        ),
        source="ACCP Clinical Practice Guideline",
        metadata={
            "category": "pulmonology",
            "organization": "American College of Chest Physicians",
            "year": 2006,
            "title": "Diagnosis and Management of Cough",
            "url": "https://journal.chestnet.org/article/S0012-3692(15)37852-0/fulltext",
        },
    ),
    Document(
        id="cdc-flu-2024",
        content=(
            "Influenza symptoms include fever, cough, sore throat, muscle "
            "aches, and fatigue with rapid onset. Antiviral treatment "
            "(e.g. oseltamivir) is most effective when started within 48 "
            "hours of symptom onset and is prioritized for patients at "
            "high risk of complications (young children, pregnant patients, "
            "adults 65 and older, and those with chronic conditions)."
        ),
        source="CDC",
        metadata={
            "category": "infectious_disease",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2024,
            "title": "Influenza: Symptoms and Treatment",
            "url": "https://www.cdc.gov/flu/treatment/index.html",
        },
    ),
    # --- Fever ---------------------------------------------------------------
    Document(
        id="medlineplus-fever-adults",
        content=(
            "A fever is a temperature at or above 100.4°F (38°C). Most "
            "fevers in otherwise healthy adults are due to a self-limited "
            "viral illness and can be managed with rest, fluids, and "
            "acetaminophen or ibuprofen. Seek care for a fever above 103°F "
            "(39.4°C), a fever lasting more than 3 days, or a fever with a "
            "severe headache, rash, stiff neck, or difficulty breathing."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2023,
            "title": "Fever in Adults",
            "url": "https://medlineplus.gov/ency/article/003090.htm",
        },
    ),
    Document(
        id="aap-2011-fever-children",
        content=(
            "In infants younger than 3 months, any fever (rectal "
            "temperature ≥100.4°F/38°C) requires prompt medical evaluation "
            "regardless of how well the infant appears. For older infants "
            "and children who are feeding and behaving normally, fever "
            "itself is not dangerous and does not require treatment unless "
            "the child is uncomfortable."
        ),
        source="AAP Clinical Report",
        metadata={
            "category": "pediatrics",
            "organization": "American Academy of Pediatrics",
            "year": 2011,
            "title": "Fever and Antipyretic Use in Children",
            "url": "https://publications.aap.org/pediatrics/article/127/3/580/65199",
        },
    ),
    # --- GI ------------------------------------------------------------------
    Document(
        id="cdc-gastroenteritis",
        content=(
            "Acute gastroenteritis (vomiting and/or diarrhea) is usually "
            "viral and self-limited within a few days. The priority is "
            "preventing dehydration with oral rehydration solution or "
            "clear fluids in small frequent sips; the BRAT diet is no "
            "longer specifically recommended — a normal diet as tolerated "
            "aids recovery. Seek care for blood in stool, high fever, "
            "signs of dehydration, or symptoms lasting more than a few days."
        ),
        source="CDC",
        metadata={
            "category": "gastroenterology",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2022,
            "title": "Managing Acute Gastroenteritis",
            "url": "https://www.cdc.gov/norovirus/about/treatment.html",
        },
    ),
    Document(
        id="acg-2022-gerd",
        content=(
            "For gastroesophageal reflux disease (GERD), a proton pump "
            "inhibitor once daily before breakfast is first-line treatment "
            "for moderate to severe symptoms; lifestyle measures (weight "
            "loss, avoiding late meals, elevating the head of the bed) are "
            "adjuncts. Alarm features — dysphagia, weight loss, GI "
            "bleeding — warrant endoscopy rather than empiric treatment."
        ),
        source="ACG Clinical Guideline",
        metadata={
            "category": "gastroenterology",
            "organization": "American College of Gastroenterology",
            "year": 2022,
            "title": "Diagnosis and Management of GERD",
            "url": "https://journals.lww.com/ajg/fulltext/2022/01000/acg_clinical_guideline_for_the_diagnosis_and.14.aspx",
        },
    ),
    Document(
        id="acg-2021-abdominal-pain-red-flags",
        content=(
            "Most acute abdominal pain is benign and self-limited, but "
            "urgent evaluation is warranted for severe or worsening pain, "
            "pain with fever, rigid or board-like abdomen, pain with "
            "vomiting blood or black stool, or right lower quadrant pain "
            "with fever (possible appendicitis)."
        ),
        source="ACG Clinical Guideline",
        metadata={
            "category": "gastroenterology",
            "organization": "American College of Gastroenterology",
            "year": 2021,
            "title": "Evaluation of Acute Abdominal Pain",
            "url": "https://gi.org/topics/abdominal-pain/",
        },
    ),
    # --- Dermatology -----------------------------------------------------
    Document(
        id="aad-2014-urticaria",
        content=(
            "Acute urticaria (hives) is treated first-line with a "
            "second-generation, non-sedating antihistamine (e.g. "
            "cetirizine, loratadine); the dose may be increased up to "
            "fourfold before switching agents. Seek emergency care for "
            "hives with swelling of the lips/tongue/throat, difficulty "
            "breathing, or dizziness — possible signs of anaphylaxis."
        ),
        source="AAD Clinical Guideline",
        metadata={
            "category": "dermatology",
            "organization": "American Academy of Dermatology",
            "year": 2014,
            "title": "Management of Urticaria",
            "url": "https://www.aad.org/member/clinical-quality/guidelines/urticaria",
        },
    ),
    Document(
        id="aad-contact-dermatitis",
        content=(
            "Contact dermatitis presents as an itchy, red rash where the "
            "skin touched an irritant or allergen. First-line treatment is "
            "avoiding the trigger plus a topical corticosteroid for "
            "inflammation and an oral antihistamine for itching. A rash "
            "that spreads, blisters extensively, or involves the face or "
            "genitals warrants clinical evaluation."
        ),
        source="AAD Clinical Guideline",
        metadata={
            "category": "dermatology",
            "organization": "American Academy of Dermatology",
            "year": 2019,
            "title": "Contact Dermatitis",
            "url": "https://www.aad.org/public/diseases/eczema/types/contact-dermatitis",
        },
    ),
    # --- Mental health -----------------------------------------------------
    Document(
        id="nice-2019-gad",
        content=(
            "For generalized anxiety disorder, guided self-help and "
            "psychoeducation are offered first; if symptoms persist, "
            "high-intensity psychological therapy (CBT) or medication (an "
            "SSRI) is recommended, with CBT and medication considered "
            "equally effective first-line options for moderate to severe "
            "cases."
        ),
        source="NICE Guideline CG113",
        metadata={
            "category": "psychiatry",
            "organization": "NICE",
            "year": 2019,
            "title": "Generalized Anxiety Disorder: Management",
            "url": "https://www.nice.org.uk/guidance/cg113",
        },
    ),
    Document(
        id="cdc-2022-sleep-hygiene",
        content=(
            "For occasional insomnia, sleep hygiene measures help most: a "
            "consistent sleep and wake time, avoiding caffeine in the "
            "afternoon, limiting screens before bed, and keeping the "
            "bedroom cool, dark, and quiet. Insomnia most nights for more "
            "than a few weeks warrants evaluation — cognitive behavioral "
            "therapy for insomnia (CBT-I) is first-line over sleep "
            "medication for chronic insomnia."
        ),
        source="CDC",
        metadata={
            "category": "psychiatry",
            "organization": "Centers for Disease Control and Prevention",
            "year": 2022,
            "title": "Tips for Better Sleep",
            "url": "https://www.cdc.gov/sleep/about/sleep-hygiene-tips.html",
        },
    ),
    # --- Allergy -------------------------------------------------------------
    Document(
        id="aaaai-allergic-rhinitis",
        content=(
            "For allergic rhinitis, an intranasal corticosteroid is the "
            "most effective single therapy and is recommended first-line "
            "for moderate to severe or persistent symptoms; a "
            "second-generation oral antihistamine is an alternative for "
            "mild, intermittent symptoms. Allergen avoidance is an adjunct "
            "to, not a substitute for, medication."
        ),
        source="AAAAI/ACAAI Joint Practice Parameter",
        metadata={
            "category": "allergy",
            "organization": "American Academy of Allergy, Asthma & Immunology",
            "year": 2020,
            "title": "Allergic Rhinitis: Diagnosis and Management",
            "url": "https://www.aaaai.org/allergist-resources/ask-the-expert/answers/2020/allergic-rhinitis",
        },
    ),
    # --- OTC analgesia / self-care -----------------------------------------
    Document(
        id="fda-acetaminophen-dosing",
        content=(
            "For adults, the maximum recommended acetaminophen dose is "
            "3000-4000 mg per day from all sources, including combination "
            "cold and flu products; exceeding this risks liver injury. "
            "Acetaminophen is generally preferred over NSAIDs in patients "
            "with kidney disease, a history of GI bleeding, or on "
            "anticoagulants."
        ),
        source="FDA Drug Safety Communication",
        metadata={
            "category": "general_health",
            "organization": "U.S. Food and Drug Administration",
            "year": 2018,
            "title": "Acetaminophen Dosing and Liver Safety",
            "url": "https://www.fda.gov/drugs/information-consumers-and-patients-drugs/acetaminophen-information",
        },
    ),
    Document(
        id="medlineplus-nsaid-cautions",
        content=(
            "NSAIDs (ibuprofen, naproxen) relieve pain, fever, and "
            "inflammation but carry a dose-dependent risk of stomach "
            "bleeding, kidney injury, and cardiovascular events with "
            "regular use. They should be used at the lowest effective dose "
            "for the shortest time needed, and avoided or used with "
            "caution in patients with kidney disease, heart failure, or a "
            "history of ulcers."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2023,
            "title": "NSAIDs: What You Need to Know",
            "url": "https://medlineplus.gov/druginfo/meds/a682159.html",
        },
    ),
    Document(
        id="medlineplus-when-to-see-doctor",
        content=(
            "For most minor symptoms — a mild cold, a headache, a small "
            "cut, occasional heartburn — self-care and over-the-counter "
            "remedies are appropriate. See a clinician promptly for chest "
            "pain, difficulty breathing, sudden severe pain, high fever, "
            "confusion, or any symptom that is severe, sudden, or "
            "progressively worsening."
        ),
        source="MedlinePlus",
        metadata={
            "category": "general_health",
            "organization": "MedlinePlus (U.S. National Library of Medicine)",
            "year": 2023,
            "title": "When to See a Doctor",
            "url": "https://medlineplus.gov/ency/patientinstructions/000605.htm",
        },
    ),
    # --- Ear / eye -----------------------------------------------------------
    Document(
        id="aao-2019-conjunctivitis",
        content=(
            "Most acute conjunctivitis is viral and self-limited over 1-2 "
            "weeks, treated with cool compresses and lubricating drops; "
            "antibiotics are not helpful for viral cases. Bacterial "
            "conjunctivitis (thick purulent discharge) may warrant topical "
            "antibiotics. Seek urgent eye care for significant eye pain, "
            "light sensitivity, or vision change — these are not typical "
            "of simple conjunctivitis."
        ),
        source="AAO Preferred Practice Pattern",
        metadata={
            "category": "ophthalmology",
            "organization": "American Academy of Ophthalmology",
            "year": 2019,
            "title": "Conjunctivitis",
            "url": "https://www.aao.org/education/preferred-practice-pattern/conjunctivitis-ppp",
        },
    ),
    Document(
        id="aafp-earache-adults",
        content=(
            "In adults, an earache with a red, bulging eardrum suggests "
            "acute otitis media and is treated with amoxicillin as "
            "first-line therapy, similar to pediatric management. Ear pain "
            "with normal exam findings is more often referred pain from the "
            "jaw, teeth, or throat, or otitis externa (swimmer's ear), "
            "which is treated with topical antibiotic drops rather than "
            "oral antibiotics."
        ),
        source="AAFP Clinical Review",
        metadata={
            "category": "infectious_disease",
            "organization": "American Academy of Family Physicians",
            "year": 2013,
            "title": "Diagnosis and Treatment of Otitis Media and Otitis Externa",
            "url": "https://www.aafp.org/pubs/afp/issues/2013/1201/p770.html",
        },
    ),
]

__all__ = ["PRIMARY_CARE_GUIDELINES"]
