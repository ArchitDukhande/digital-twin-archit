# Digital Twin of Archit at Sara

Live demo: https://archit-at-sara-twin.streamlit.app/

---

## Problem statement

The goal of this project is to build a digital twin that can represent me in a real work context and answer questions as me, based only on data that exists. The focus is not on fluency or feature completeness, but on correctness, traceability, and safety.

For this take-home, I chose to model a **digital twin of myself in my current role at Sara**. The core problem I wanted to solve was intentionally strict:

> Can a digital twin remember what I worked on, why decisions were made, and when things happened, using only real evidence and without hallucinating?

This aligns closely with **Viven’s core focus on preserving knowledge with its original context**, and with the principle that **wrong information is more harmful than no information**.

---

## Motivation and framing

During my conversation with Jonathan, one idea stood out clearly:  
people should have **control over what information is shared**, and the system should not assume access to everything by default.

Based on that, I made the following framing decisions, reflecting how I would choose to configure a digital twin if I were working at Sara and had the option to decide what data to share:

- I would choose to share work communication such as Slack messages and emails, since they capture decisions and context.
- I would intentionally not share personal documents or calendar data.
- I would treat identity information as something the company already has during onboarding, such as role, team, manager, and start date.

This keeps the project standalone, reproducible, and privacy safe.

---

## Design philosophy

I designed the system around how humans remember.

People do not recall every message verbatim first. They remember themes, time periods, key decisions, and failures. Details are recalled later when needed.

Because of this, I structured the digital twin as explicit layers, each mirroring a part of human memory and reasoning. I intentionally spent more time on system design, grounding, and safety than on UI polish.

---

## Data sources and assumptions

The twin is grounded in three types of data:

- **Slack messages**  
  Informal, day to day communication that captures decisions and investigation context.

- **Emails**  
  Onboarding and higher level communication.

- **Identity profile**  
  Information Sara would already have during onboarding, such as role, team, manager, and start date.

These sources are simulated to keep the project reproducible. The system treats them as real integrations. All data is dummy and sanitized. No real credentials or sensitive identifiers are included.

---

## Layered system design

The system is built as a pipeline of layers, each with a single responsibility.

### Layer 1: Raw memory  
All source data is ingested as immutable chunks. Nothing is interpreted or rewritten. This is the ground truth used for citations and verification.

### Layer 2: Semantic memory  
Raw chunks are grouped by week and summarized. This layer is intentionally lossy and is used only to route retrieval.

### Layer 3: Query understanding  
User questions are parsed to extract intent and time ranges such as “late December” or “Q4 2025”.

### Layer 4: Retrieval  
Relevant weeks are selected first, then raw chunks are ranked using embeddings with time based boosts.

### Layer 5: Evidence extraction  
Exact supporting quotes are extracted verbatim from retrieved chunks and validated against the original text.

### Layer 6: Verifier and refusal gate  
This is the core safety layer.  
If there is no evidence, the system refuses to answer.  
If evidence exists but does not support the question, the system refuses.  
If entailment is unclear, the system returns quotes only.

### Layer 7: Style layer  
Answers are formatted to sound like me in a work context, without adding information or changing meaning.

### Layer 8: UI  
A simple Streamlit chat interface that shows answers, confidence, citations, and optional debug information.

---

## Anti hallucination guarantee

The central invariant of this system is:

> **No evidence means no answer.**

This is enforced through verbatim quote validation, entailment checks for factual questions, refusal on unsupported queries, and blocking of sensitive requests such as credentials or passwords.

---

## Evaluation and testing

I validated the system by testing behavior at multiple levels, with a focus on correctness and refusal rather than exact wording.

End to end integration tests exercise the full pipeline from query understanding through retrieval, evidence extraction, verification, and final response. These tests confirm that summary questions and fact based questions are answered only when supported by evidence, and that unsupported or ambiguous questions are refused.

I also tested the verifier logic in isolation to ensure that related but non supporting evidence is rejected, while directly supporting evidence allows an answer. This validates the system’s core anti hallucination behavior.

Finally, I inspected raw memory ingestion to confirm that source data is chunked correctly, timestamps are detected where expected, and chunk boundaries preserve traceability back to the original data.

---

## Engineering quality and reproducibility

- Clear module boundaries between layers  
- Deterministic data loading from local files  
- No secrets committed to the repository  
- Streamlit UI as the primary interactive experience  
- Optional devcontainer for local or Codespaces setup  

---

## How I would design extensions

Any extensions would follow the same structure and guarantees already in place.

New data sources would be added by converting them into the same raw memory chunk format used today. The retrieval, evidence extraction, and verifier layers would remain unchanged so the system continues to answer only when evidence exists and refuse otherwise.

---

## Live demo

You can interact with the digital twin here:  
https://archit-at-sara-twin.streamlit.app/

---

## Closing note

This project is intentionally scoped and opinionated. It prioritizes preserving knowledge with context, explainability, and refusal over fluency. That choice was deliberate and reflects how I understand Viven’s core mission.
