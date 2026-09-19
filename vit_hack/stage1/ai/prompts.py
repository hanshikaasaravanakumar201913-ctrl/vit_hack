"""ATLAS Clinical Study Intelligence — Prompts and Clinical Guardrails.

Encapsulates system instructions, grounding contracts, clinical explanation
standards, general knowledge definitions, and out-of-scope policies for the AI conversational layer.
"""

SYSTEM_PROMPT_ATLAS = """You are ATLAS, an expert AI Clinical Study Intelligence Assistant for clinical trials.
You assist clinical researchers, medical monitors, biostatisticians, and data managers in analyzing clinical trial data (STUDY-042).

Your factual knowledge of the study is STRICTLY grounded in retrieved CDISC SDTM study records (DM, AE, LB, VS, EX, CM, DS, MH, EG) and protocol rules provided in context.

CRITICAL CLINICAL BOUNDARIES & INTEGRITY RULES:
1. NEVER INVENT CLINICAL FACTS: Do not invent subject IDs, visit names, laboratory values, adverse event terms, medications, or record sequences.
2. CITATION DISCIPLINE: Every study-specific factual statement must be backed by the retrieved RecordRef citations. Do not make up citations.
3. CLEAR CLINICAL SEPARATION: Always distinguish clearly between:
   - Observed Record (e.g., "ALT was recorded as 3.995 µkat/L at Week 8")
   - Protocol Rule (e.g., "Protocol Section 6.2 defines Hy's law threshold as ALT > 3× ULN and Total Bilirubin > 2× ULN within 14 days")
   - Derived Calculation (e.g., "Converted: 3.995 µkat/L × 60 = 239.7 U/L, which equals 5.3× the ULN of 45 U/L")
   - Clinical Interpretation (e.g., "Meets biochemical criteria for potential drug-induced liver injury")
   - Uncertainty (e.g., "The available data cut does not include viral hepatitis serology")
4. MEDICAL MONITOR OVERSIGHT: Frame safety evaluations as objective clinical findings for medical monitor review. The human medical monitor retains final decision-making authority.
5. OUT-OF-SCOPE INQUIRIES: If a user asks about non-study topics (sports, games, politics, coding, general trivia), politely explain your specific role as the STUDY-042 clinical intelligence assistant and decline to answer questions outside clinical study analysis.
"""

FEW_SHOT_CLINICAL_STYLE = """
Example Response Style:

Subject 042-S07-001 was enrolled at Site S07 in the Active Drug Arm (DRUG, 10 mg).

Clinical Safety Finding:
The available laboratory records indicate a potential Hy's law liver safety finding recorded at the Week 8 visit:
• ALT: 3.995 µkat/L (converted to 239.7 U/L; 5.3× ULN where local ULN is 0.75 µkat/L / 45 U/L)
• Total Bilirubin: 5.38 mg/dL (4.5× ULN where local ULN is 1.2 mg/dL)
• Both tests were collected concurrently on 2024-05-14.

Protocol Evaluation:
Under STUDY-042 Protocol Section 6.2, these values meet the biochemical criteria for potential Hy's Law (ALT > 3× ULN with concurrent Total Bilirubin > 2× ULN within 14 days without baseline elevation).

Supporting Evidence:
• LB / 042-S07-001 / seq 25 (ALT: 3.995 µkat/L)
• LB / 042-S07-001 / seq 27 (Bilirubin: 5.38 mg/dL)
"""

OUT_OF_SCOPE_MESSAGE = (
    "I can chat about general topics too, but ATLAS specializes strictly in STUDY-042 clinical study intelligence and protocol safety analytics. "
    "My evidence engine evaluates randomized subjects, laboratory biomarkers, adverse events, dosing compliance, concomitant medications, and protocol rules. "
    "If you're here for STUDY-042, I can assist with subject longitudinal profiles, safety surveillance, protocol amendments, or evidence citations."
)

CLARIFICATION_NO_SUBJECT_MESSAGE = (
    "Could you please specify which subject you are referring to? Please provide a subject identifier "
    "(such as 042-S07-001 or 042-S05-003) or select a subject from the Study Graph or Patient 360 view."
)

CANDY_DIETARY_RESPONSE = (
    "😄 If you mean literally, I don't have a candy policy for you personally! "
    "But if you're asking whether candy, sugar, or dietary intake is restricted for participants in STUDY-042, "
    "I can check the protocol and available study records for that.\n\n"
    "Under STUDY-042 protocol for Type 2 Diabetes, subjects are maintained on standardized lifestyle and dietary counseling, "
    "with glycemic control monitored longitudinally via fasting plasma glucose and HbA1c assessments.\n\n"
    "Want me to check the study protocol for specific dietary restrictions or glycemic monitoring rules?"
)

HOSPITALIZATION_CLARIFICATION_RESPONSE = (
    "Do you mean currently hospitalized subjects in STUDY-042, or subjects who have ever had a hospitalization recorded as a serious adverse event (AESHOSP = 'Y')?\n\n"
    "### Clinical Context in STUDY-042:\n"
    "• Inpatient hospitalization is tracked under CDISC SDTM variable `AESHOSP` in the Adverse Events (AE) domain.\n"
    "• Across our cohort of 241 subjects, participants such as **042-S01-003** (Chest Pain) and **042-S05-003** (Hepatotoxicity) had inpatient hospitalizations recorded, qualifying their events as Serious Adverse Events (SAEs).\n"
    "• If you are inquiring about active inpatient stays at the current data cut, all acute hospitalizations had resolved prior to the cut date.\n\n"
    "Would you like me to summarize all subjects with serious adverse events requiring hospitalization, or focus on a specific investigational site?"
)

MORTALITY_RESPONSE = (
    "In **STUDY-042**, disposition (DS) and adverse event (AE) records across all 241 enrolled subjects indicate **zero reported deaths (0 fatal cases)** in the available study cuts (through Cut 12).\n\n"
    "### Disposition & Safety Finding Summary:\n"
    "• **Total Enrolled Cohort:** 241 subjects across 12 investigational sites.\n"
    "• **Mortality Records (DS/AE):** 0 deaths reported (`DSDECOD` and `DSTERM` have zero fatal disposition events; `AEOUT` has zero fatal outcomes).\n"
    "• **Study Discontinuations:** All subjects who discontinued early (such as participants withdrawing due to elevated transaminases or adverse events) were non-fatal.\n"
    "• **Serious Adverse Events (SAEs):** Inpatient hospitalizations were reported (e.g. chest pain, transaminase elevations), but all subjects survived without fatal outcomes.\n\n"
    "I can inspect specific discontinuation records (DS domain) or adverse event reports (AE domain) for any subject if you would like to investigate further."
)

PLACEBO_DOSE_STUDY042_RESPONSE = (
    "In **STUDY-042**, participants randomized to the **PLACEBO** arm received **0 mg** of active investigational product daily.\n\n"
    "To maintain strict double-blind trial conditions, the placebo was administered as visually identical oral capsules matching "
    "the appearance, size, and packaging of the active 10 mg and 20 mg investigational tablets."
)

GENERAL_CLINICAL_CONCEPTS = {
    "placebo": {
        "title": "Placebo in Clinical Trials",
        "general": (
            "In clinical research, a **placebo** is a pharmacologically inactive substance (such as starch or saline) manufactured "
            "to look, taste, and be administered identically to the active investigational drug. It serves as a negative control to distinguish "
            "actual pharmacodynamic drug effects from psychological expectations (the placebo effect), observer bias, and natural disease progression."
        ),
        "study_context": (
            "In **STUDY-042**, the **PLACEBO** arm is one of the three randomized study arms (alongside Active Drug 10 mg and Active Drug 20 mg). "
            "Participants randomized to placebo receive 0 mg daily capsules matching the active investigational drug. For example, subject "
            "**042-S07-001** was randomized to the PLACEBO arm."
        ),
        "follow_ups": [
            "Tell me about subject 042-S07-001",
            "What was the placebo dose in STUDY-042?",
            "Which subjects meet potential Hy's law criteria?",
        ],
    },
    "hys_law": {
        "title": "Hy's Law (Drug-Induced Liver Injury)",
        "general": (
            "**Hy's Law** is a regulatory biomarker rule established by Dr. Hyman Zimmerman to predict severe drug-induced liver injury (DILI). "
            "A potential Hy's law case requires: (1) transaminase elevation (ALT or AST > 3× ULN), (2) concurrent hyperbilirubinemia (Total Bilirubin > 2× ULN) "
            "without initial findings of cholestasis (alkaline phosphatase elevation), and (3) no other pre-existing baseline disease explaining the injury. "
            "Cases meeting Hy's law carry an estimated 10% risk of acute liver failure and mortality."
        ),
        "study_context": (
            "In **STUDY-042**, liver safety is governed by Protocol Section 6.2. Two qualifying candidate subjects have been detected across the trial: "
            "**042-S07-001** (Site S07, ALT 5.3× ULN, Bilirubin > 2× ULN) and **042-S05-003** (Site S05, ALT 188 U/L, Bilirubin 2.9 mg/dL). Both cases "
            "require immediate medical monitor safety review."
        ),
        "follow_ups": [
            "Which subjects meet potential Hy's law criteria?",
            "Tell me about subject 042-S07-001",
            "Tell me about subject 042-S05-003",
        ],
    },
    "double_blind": {
        "title": "Double-Blind Study Design",
        "general": (
            "A **double-blind** study is an experimental design in which neither the participants nor the investigators, site staff, or assessing physicians "
            "know which treatment arm (active drug dose vs placebo) an individual subject has been randomized to receive. This eliminates conscious and "
            "unconscious bias in symptom reporting, efficacy assessment, and adverse event grading."
        ),
        "study_context": (
            "**STUDY-042** is a multi-center, randomized, double-blind trial evaluating investigational therapy in Type 2 Diabetes across 12 clinical sites. "
            "Blinding is maintained using matching capsule formulations across all 3 arms (10 mg, 20 mg, and Placebo)."
        ),
        "follow_ups": [
            "What was the placebo dose in STUDY-042?",
            "Which subjects at site S09 received a wrong dose?",
            "What are the inclusion criteria?",
        ],
    },
    "adverse_event": {
        "title": "Adverse Events (AE) and Serious Adverse Events (SAE)",
        "general": (
            "An **Adverse Event (AE)** is any untoward medical occurrence in a patient or clinical trial subject administered a medicinal product, "
            "whether or not considered causally related to the treatment. A **Serious Adverse Event (SAE)** is defined by regulatory guidelines (ICH GCP) "
            "as any event resulting in death, a life-threatening experience, inpatient hospitalization or prolongation of existing hospitalization, "
            "persistent or significant disability, or a congenital anomaly."
        ),
        "study_context": (
            "In **STUDY-042**, adverse events are recorded in the CDISC SDTM `AE` domain. Under Protocol Section 6.1, any event requiring inpatient "
            "hospitalization (`AESHOSP = 'Y'`) automatically triggers SAE escalation for prompt medical monitor audit."
        ),
        "follow_ups": [
            "Which subjects had serious adverse events?",
            "Tell me about subject 042-S01-003",
            "Tell me about subject 042-S07-001",
        ],
    },
    "cdisc_sdtm": {
        "title": "CDISC SDTM Standard",
        "general": (
            "The **Clinical Data Interchange Standards Consortium (CDISC) Study Data Tabulation Model (SDTM)** is the global standard format for "
            "structuring clinical trial data for submission to regulatory authorities (FDA, EMA, PMDA). It organizes clinical variables into standardized "
            "two-character domains (e.g. DM for Demographics, AE for Adverse Events, LB for Laboratory Tests, EX for Exposure)."
        ),
        "study_context": (
            "In **STUDY-042**, our knowledge graph is built directly upon verified CDISC SDTM datasets comprising 26,482 records across 241 subjects "
            "in 8 core domains (DM, AE, LB, VS, EX, CM, DS, MH). Every clinical conclusion in ATLAS is traceable to an immutable CDISC record citation."
        ),
        "follow_ups": [
            "Tell me about subject 042-S07-001",
            "Show me the actual records",
            "Which subjects meet potential Hy's law criteria?",
        ],
    },
    "hba1c": {
        "title": "Hemoglobin A1c (HbA1c)",
        "general": (
            "**Hemoglobin A1c (HbA1c)** is glycated hemoglobin that reflects the average blood glucose concentration over the preceding 2 to 3 months. "
            "It is the primary gold standard biomarker for diagnosing and managing Type 2 Diabetes Mellitus."
        ),
        "study_context": (
            "In **STUDY-042**, HbA1c reduction is the primary efficacy endpoint for the investigational drug. Per protocol inclusion criteria, subjects "
            "were required to have screening HbA1c between 7.0% and 10.5%."
        ),
        "follow_ups": [
            "What are the inclusion criteria?",
            "Tell me about subject 042-S07-001",
            "What changed in the latest protocol amendment?",
        ],
    },
    "transaminases": {
        "title": "Alanine Aminotransferase (ALT) and Aspartate Aminotransferase (AST)",
        "general": (
            "**ALT** and **AST** are intracellular enzymes predominantly synthesized in hepatocytes. When liver cell membranes are compromised, "
            "these enzymes leak into the serum, serving as sensitive indicators of hepatocellular necrosis or drug-induced liver injury."
        ),
        "study_context": (
            "In **STUDY-042**, the central laboratory normal upper limit (ULN) for ALT and AST is 56 U/L. However, Site S07 reports in SI units "
            "(µkat/L with ULN 0.93 µkat/L; converted × 60 to U/L). ATLAS normalizes these unit differences automatically."
        ),
        "follow_ups": [
            "Which subjects meet potential Hy's law criteria?",
            "Tell me about subject 042-S07-001",
            "Check whether the screening value was already elevated",
        ],
    },
    "sdv": {
        "title": "Source Data Verification (SDV)",
        "general": (
            "**Source Data Verification (SDV)** is a Good Clinical Practice (GCP) quality control procedure in which clinical trial monitors "
            "compare electronic Case Report Form (eCRF) entries against original hospital/clinic source documents (e.g. medical charts, lab printouts) "
            "to ensure data integrity, accuracy, and completeness."
        ),
        "study_context": (
            "In **STUDY-042**, our surveillance engine identified unnatural vital signs reporting at Site S11 (SYSBP variance near zero, stdev 0.71 mmHg). "
            "Under GCP guidelines, ATLAS recommends 100% targeted SDV and site re-training while preserving all raw records under active surveillance."
        ),
        "follow_ups": [
            "Which site has suspicious reporting behavior?",
            "Why was S11 flagged?",
            "What monitor escalations are still pending?",
        ],
    },
}
