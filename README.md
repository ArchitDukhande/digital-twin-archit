# Digital Twin of Archit at Sara

Live demo:  
https://archit-at-sara-twin.streamlit.app/

---

# Problem Statement

The goal of this project is to build a digital twin that can represent me in a real work context and answer questions as me, based only on data that exists. The focus is not on fluency or feature completeness, but on correctness, traceability, and safety.

This started as a **personal project inspired by a technical panel discussion about digital twins and knowledge preservation systems**. During that conversation, I became interested in a very strict question:

> Can a digital twin remember what I worked on, why decisions were made, and when things happened, using only real evidence and without hallucinating?

I decided to implement a working prototype to explore that question.

For this project, I modeled a digital twin of myself in my current role at Sara.

---

# Motivation and Framing

A key idea discussed during the panel was that people should have **control over what information their digital twin can access**, rather than the system assuming access to everything by default.

Based on that principle, I framed the system as if I were configuring a digital twin for myself inside a company environment.

I made the following decisions about what information the twin would have access to:

- Work communication such as **Slack messages and emails**, since they capture decisions and investigation context.
- **No personal documents or calendar data**, to maintain privacy boundaries.
- **Identity information** that a company would already have during onboarding, such as role, team, manager, and start date.

This keeps the project standalone, reproducible, and privacy safe.

---

# Design Philosophy

The system is designed around how humans remember information.

People rarely recall every message verbatim. Instead, they remember themes, time periods, important decisions, and failures. The exact details are retrieved later when needed.

Because of this, the digital twin is structured as explicit layers that mirror human memory and reasoning. The focus of the project is intentionally on **system design, grounding, and safety**, rather than UI polish.

---

# Data Sources and Assumptions

The twin is grounded in three types of data.

### Slack Messages
Informal, day to day communication capturing investigations, debugging steps, and technical context.

### Emails
Higher level communication such as onboarding and coordination messages.

### Identity Profile
Basic information a company would already have during onboarding, including role, team, manager, and start date.

To keep the project reproducible, the integrations are simulated. The system treats them as if they were real integrations. All data is dummy and sanitized. No real credentials or sensitive identifiers are included.

---

# Layered System Design

The system is implemented as a pipeline of layers, each with a single responsibility.

## Layer 1: Raw Memory

All source data is ingested as immutable chunks. Slack messages, emails, and documents are each parsed with dedicated logic that extracts timestamps and metadata. Nothing is interpreted or rewritten at this stage. This layer acts as the ground truth used for verification and citations.

---

## Layer 2: Keyword Memory

Keywords are extracted from every chunk using an LLM and aggregated per week. Week-level keyword embeddings are used only for routing to narrow the candidate pool. Per-chunk keyword embeddings drive the actual ranking in retrieval. No summaries are generated.

---

## Layer 3: Query Understanding

User questions are parsed to extract time signals such as “late December”, “Q4 2025”, or “during onboarding”. The query is also rewritten by an LLM into optimized search keywords, strictly derived from the question itself.

---

## Layer 4: Retrieval

Two-level keyword-based retrieval. Relevant weeks are selected first via keyword embedding similarity. Candidate chunks are then scored using a blend of keyword similarity and full-text embedding similarity, with boosts for date range matches and identity queries.

---

## Layer 5: Evidence Extraction

Exact supporting quotes are extracted verbatim from retrieved chunks and validated against the original text to guarantee traceability.

---

## Layer 6: Verifier and Refusal Gate

This layer enforces the system’s core safety guarantees.

- If no evidence exists, the system refuses to answer.
- If retrieved evidence does not actually support the question, the system refuses.
- If the relationship between evidence and question is unclear, the system returns the quotes instead of generating an answer.

---

## Layer 7: Style Layer

Answers are formatted to sound like me in a professional work context. This layer is restricted from adding new information or modifying the meaning of the evidence.

---

## Layer 8: User Interface

A Streamlit chat interface allows interaction with the twin. While the pipeline runs, live status lines show progress layer by layer. The final view includes:

- generated answers
- supporting citations
- confidence score
- collapsible debugging information

The UI is intentionally minimal because the focus of the project is system architecture.

---

# Anti-Hallucination Guarantee

The central invariant of this system is:

> **No evidence means no answer.**

This guarantee is enforced through:

- verbatim quote validation
- entailment checks for factual questions
- refusal when evidence does not support the query
- blocking sensitive requests such as credentials or passwords

The goal is to ensure the system never invents information.

---

# Evaluation and Testing

Testing focused on correctness and refusal behavior rather than wording quality.

End to end integration tests exercise the full pipeline from query understanding through retrieval, evidence extraction, verification, and response generation.

These tests confirm that:

- supported questions produce answers with citations
- unsupported questions are refused
- ambiguous questions return evidence rather than fabricated explanations

Verifier logic was also tested independently to ensure that related but non supporting evidence is rejected while directly supporting evidence allows answers.

Raw memory ingestion was validated to ensure:

- chunking preserves traceability
- timestamps are detected correctly
- chunk boundaries remain consistent with original sources

---

# Engineering Quality and Reproducibility

The project was designed to be reproducible and easy to inspect.

- clear module boundaries between layers
- deterministic data loading from local files
- no secrets committed to the repository
- Streamlit UI as the primary interactive interface
- optional devcontainer for local or Codespaces setup

---

# Possible Extensions

Future extensions would follow the same architecture.

New data sources could be added by converting them into the same raw memory chunk format used in the system today. The retrieval, evidence extraction, and verifier layers would remain unchanged so the system continues to enforce evidence based answers.

---

# Live Demo

You can interact with the digital twin here:

https://archit-at-sara-twin.streamlit.app/

---

# Closing Note

This project was originally built for a technical panel interview where I was asked to design a digital twin system. I later expanded it into a personal project to explore the idea more deeply and turn the design into a working prototype.

