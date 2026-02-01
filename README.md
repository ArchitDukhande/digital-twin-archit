# Digital Twin MVP - Layered Architecture

A trustworthy AI digital twin that answers questions based on your real work data (Slack, emails, docs) while refusing to hallucinate.

## Architecture

The system uses **8 clean layers** that mirror human reasoning:

### Layer 1: Raw Memory (Ground Truth)
- **Purpose:** Preserve truth exactly as written
- **Module:** `layers/raw_memory.py`
- **What it does:**
  - Loads all .md files from `data/`
  - Parses Slack messages with timestamps
  - Chunks documents into logical sections
  - Tags everything with IDs, file paths, line numbers
- **Rule:** Never interprets. This is the source of truth.

### Layer 2: Semantic Memory (Human-like Remembering)
- **Purpose:** Speed up recall by creating summaries
- **Module:** `layers/semantic_memory.py`
- **What it does:**
  - Groups raw chunks by week
  - AI-generates concise summaries for each week
  - Embeds summaries for routing
  - Caches to `.cache/semantic_summaries.json`
- **Rule:** Only for routing retrieval, never for direct answers

### Layer 3: Query Understanding (Intent + Time)
- **Purpose:** Translate vague human language into constraints
- **Module:** `layers/query_understanding.py`
- **What it does:**
  - Parses "late Dec" → Dec 20-31
  - Handles Q1/Q2/Q3/Q4 patterns
  - Extracts key topics/keywords
  - Assumes 2025 for missing years in this MVP
- **Rule:** Makes queries work even when they're vague

### Layer 4: Retrieval (Reading the Right Memories)
- **Purpose:** Hierarchical retrieval - semantic first, then raw
- **Module:** `layers/retrieval.py`
- **What it does:**
  1. Uses semantic memory to find relevant weeks
  2. Pulls raw chunks from those weeks
  3. Scores by embedding similarity + date boost
  4. Returns top-k within context limit
- **Rule:** Gathering context only, not answering yet

### Layer 5: Evidence Extraction
- **Purpose:** Prove every claim with exact quotes
- **Module:** `layers/evidence_extraction.py`
- **What it does:**
  - AI identifies exact supporting snippets
  - Attaches chunk IDs and timestamps
  - Creates "receipts" for auditing
- **Rule:** If no supporting snippets, no answer allowed

### Layer 6: Verifier / Refusal Gate (Anti-Hallucination)
- **Purpose:** Enforce honesty - the most important layer
- **Module:** `layers/verifier_gate.py`
- **What it does:**
  - Checks if evidence supports the answer
  - Generates answer only from evidence
  - Refuses with "I do not see it" when uncertain
  - Assigns confidence scores
- **Rule:** No evidence = no answer. This prevents hallucinations.

### Layer 7: Style Layer
- **Purpose:** Sound like "Archit" while staying grounded
- **Module:** `layers/style_layer.py`
- **What it does:**
  - Uses `data/identity.md` for style guidance
  - Rephrases to match voice (concise, direct, Slack-style)
  - Never overrides facts
- **Rule:** Style is phrasing. Evidence determines content.

### Layer 8: UI (Streamlit)
- **Purpose:** Make it usable and demoable
- **Module:** `app.py`
- **What it does:**
  - Chat interface
  - Shows answer with confidence badge
  - Displays citations with timestamps
  - Optional debug panel showing chunks and reasoning
- **Rule:** Makes evaluation easy for reviewers

## Key Features

✅ **Smart reading of messy data** - Works with informal, unlabeled, chronological messages  
✅ **Hierarchical retrieval** - Semantic memory routes to the right time/topic  
✅ **Evidence-based answers** - Every claim has receipts (citations with chunk IDs)  
✅ **Refusal when uncertain** - Says "I do not see it" instead of hallucinating  
✅ **Date-aware** - Understands "late Dec", "Q3", "around Christmas"  
✅ **Grounded in truth** - Raw memory is immutable source of truth  

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   Create `.env` file:
   ```
   OPENAI_API_KEY=your_key_here
   TWIN_EMBED_MODEL=text-embedding-3-small
   TWIN_GEN_MODEL=gpt-4o-mini
   TWIN_TOP_K=6
   TWIN_MAX_CONTEXT_CHARS=3000
   ```

3. **Add your data:**
   Place `.md` files in `data/`:
   - `data/identity.md` - style guide
   - `data/dummy_slack.md` - chat logs
   - `data/dummy_mails/*.md` - emails

## Usage

### CLI (Quick Testing)
```bash
# Basic question
python main.py "What was I working on in late December?"

# With debug info
python main.py --debug "What happened in Q4?"
```

### Streamlit UI (Full Experience)
```bash
streamlit run app.py
```

Then open http://localhost:8501

## Example Outputs

**Question:** "What was I working on in late December?"

**Answer:** "I was focused on cold start optimization and scaling infrastructure for the inference pipeline."

**Confidence:** HIGH

**Citations:**
1. "worked on reducing cold start latency from 2s to 800ms" - `dummy_slack.md` - Dec 22, 2025
2. "discussed scaling approach with CTO" - `dummy_slack.md` - Dec 28, 2025

---

**Question:** "What's my favorite food?"

**Answer:** "I do not see it"

**Confidence:** NONE

**Reasoning:** No supporting evidence found in the data.

## How It Prevents Hallucinations

1. **Raw Memory is immutable** - No rewriting or summarizing source data
2. **Evidence Extraction** - Every answer must cite exact snippets
3. **Verifier Gate** - Refuses when evidence is weak or missing
4. **Grounded generation** - Model only sees retrieved context, not training data
5. **Clear refusal phrase** - "I do not see it" instead of making stuff up

## Project Structure

```
digitaltwin/
├── layers/
│   ├── __init__.py
│   ├── raw_memory.py          # Layer 1
│   ├── semantic_memory.py     # Layer 2
│   ├── query_understanding.py # Layer 3
│   ├── retrieval.py           # Layer 4
│   ├── evidence_extraction.py # Layer 5
│   ├── verifier_gate.py       # Layer 6
│   └── style_layer.py         # Layer 7
├── data/
│   ├── identity.md
│   ├── dummy_slack.md
│   └── dummy_mails/
├── .cache/
│   ├── embeddings.json        # (generated)
│   └── semantic_summaries.json # (generated)
├── twin.py                    # Orchestrator
├── app.py                     # Layer 8: UI
├── main.py                    # CLI
├── requirements.txt
└── README.md
```

## Why This Architecture Works

- **Testable:** Each layer can be tested independently
- **Transparent:** Debug mode shows exactly what each layer did
- **Robust:** Works with messy, unstructured data
- **Trustworthy:** Refuses instead of hallucinating
- **Extensible:** Easy to add new layers or swap components

## Production Considerations

For a real deployment:
- Add authentication for the UI
- Implement rate limiting
- Store embeddings in a vector DB (Pinecone, Weaviate)
- Add logging and monitoring
- Implement user feedback loop for continuous improvement
- Add more sophisticated date/time parsing
- Support more file formats (JSON, CSV, PDFs)

## License

MIT
