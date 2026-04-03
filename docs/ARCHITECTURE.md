# Digital Twin MVP - Architecture Documentation

> A grounded, evidence-based personal assistant that answers questions using only your data.
> Built with Streamlit, OpenAI, and a 7-layer keyword-based retrieval pipeline.

---

## System Overview

```
User Question
     │
     ▼
┌─────────────┐
│   app.py    │  Layer 8: Streamlit UI (live status updates)
└─────────────┘
     │
     ▼
┌─────────────┐
│  twin.py    │  Orchestrator (LLM mode classification + step callbacks)
└─────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────┐
│                    7 Processing Layers              │
│                                                     │
│  L1: Raw Memory ──► L2: Keyword Memory              │
│         │                    │                      │
│         └────────┬───────────┘                      │
│                  ▼                                  │
│         L3: Query Understanding (+ LLM rewrite)     │
│                  │                                  │
│                  ▼                                  │
│         L4: Retrieval (two-level keyword routing)   │
│                  │                                  │
│                  ▼                                  │
│         L5: Evidence Extraction                     │
│                  │                                  │
│                  ▼                                  │
│         L6: Verifier Gate (entailment + anti-hall.) │
│                  │                                  │
│                  ▼                                  │
│         L7: Style Layer                             │
└─────────────────────────────────────────────────────┘
     │
     ▼
  Response with Citations
```

---

## File-by-File Breakdown

---

## 1. app.py (Streamlit UI)

### What It Does
The user-facing chat interface with **live status updates**. Displays an avatar, chat history, and debug info. Sends questions to `twin.py` with a `step_callback` so each layer's progress renders in real time inside the assistant bubble. Status lines disappear once the final answer arrives.

### Execution Timing
- **Startup**: `load_twin()` initializes the DigitalTwin (cached with `@st.cache_resource` to avoid re-init on every interaction).
- **Per-query**: Each chat input triggers `twin.answer(prompt, debug=True, step_callback=on_step)`.

### Key Functions

| Block | Purpose |
|-------|---------|
| `main()` | Entry point. Sets page config, loads twin, renders UI. |
| `load_twin()` | Cached initialization of DigitalTwin. Prevents cold start on every rerun. |
| Sidebar | Example questions and "Clear Chat" button. |
| `on_step(step, data)` | Callback that appends live status lines (keywords, mode, weeks, evidence count) to a growing log inside an `st.empty()` placeholder. |
| Chat input handler | Sends question to twin, displays answer, confidence badge, citations, and debug JSON in collapsible expanders. |
| `st.session_state.messages` | Stores chat history (including citations and debug) for display persistence across reruns. |

### Live Status Steps

| Step | What is shown |
|------|---------------|
| `query_parsed` | Keywords, rewritten query, date range |
| `mode` | SUMMARY_MODE or FACT_MODE |
| `retrieved` | Relevant weeks, candidate → selected chunk count |
| `evidence` | Number of supporting quotes |
| `answer_ready` | Confidence level |

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| `@st.cache_resource` for twin | Avoid re-indexing all chunks on every interaction | Fast per-query response | First load is slow (~5-10s depending on data size) |
| Live `st.empty()` status log | Visual feedback while pipeline runs | User sees progress layer by layer | Slight complexity |
| Confidence badge colors | Visual feedback: green=high, blue=medium, yellow=low | Quick trust signal | Subjective threshold definitions |
| Debug always collected | Debug JSON in collapsible expander per message | Always available for inspection | Minor overhead |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Twin init fails (missing API key, bad data) | `st.error()` and `st.stop()` |
| Query fails | `try/except` wraps `twin.answer()`, shows error in chat |
| Missing avatar image | Falls back to emoji "🤖" |

### Performance Notes
- **Streamlit cold start**: First load triggers full twin initialization (keyword extraction, embeddings). This is the main performance bottleneck. Subsequent queries are fast because `@st.cache_resource` preserves the twin.
- Rerunning the app (e.g., code change) clears the cache, causing another cold start.

### Improvements

**MVP-safe:**
- Add loading spinner during twin initialization
- Show estimated wait time on first load

**Production:**
- Pre-compute embeddings at build time
- Use Redis or persistent vector store to avoid startup embedding
- Add session timeout and memory limits

---

## 2. twin.py (Orchestrator)

### What It Does
The central coordinator. Initializes all 7 layers at startup, then routes each question through the pipeline: parse → classify mode (LLM) → retrieve → extract → verify → style. Emits `step_callback` events after each major layer so the UI can render live progress.

### Execution Timing
- **Startup**: Initializes all layers (RawMemory, KeywordMemory, QueryUnderstanding, Retrieval, EvidenceExtraction, VerifierGate, StyleLayer). Heavy work here.
- **Per-query**: `answer()` method runs the full pipeline.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Loads env vars, creates OpenAI client, initializes all 7 layers sequentially |
| `answer()` | Main entry point. Routes question through all layers. Calls `step_callback` after each layer. Returns dict with answer, confidence, citations, debug. |
| `_classify_mode_llm()` | LLM call with keyword hints to classify question as SUMMARY_MODE or FACT_MODE |
| `_determine_answer_mode()` | Always delegates to `_classify_mode_llm()` — no hardcoded rules |
| Greeting/help detection | Short-circuits pipeline for "hi", "help", etc. No memory lookup needed. |

### Pipeline Flow in `answer()`

```python
1. UI intent check (greetings, help) → short-circuit return
2. Layer 3: query_understanding.parse(question) → date_range, topics, keywords, rewritten_query
3. step_callback("query_parsed", ...)
4. Determine answer_mode via LLM classification (always LLM, with keyword hints)
5. step_callback("mode", ...)
6. Layer 4: retrieval.retrieve(question, date_range, keywords, rewritten_query) → chunks
7. step_callback("retrieved", ...)
8. Layer 5: evidence_extraction.extract(question, chunks, answer_mode) → evidence
9. step_callback("evidence", ...)
10. Layer 6: verifier_gate.generate_answer(question, evidence, chunks, mode) → answer
11. Layer 7: style_layer.apply_style(answer_result) → final answer
12. step_callback("answer_ready", ...)
13. Attach debug info if requested
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| LLM-based mode classification | More flexible than rules; handles edge cases | Adapts to any phrasing | Extra LLM call per query |
| Keyword hints in classify prompt | Guide the LLM without hardcoding rules | Best of both worlds | Hints may bias the model |
| Default to FACT_MODE on failure | Stricter mode is safer | Avoids over-summarizing | May refuse valid summary queries |
| Sequential layer init | Simple, predictable | Easy to debug | Slower startup (but only once) |
| `step_callback` after each layer | Decouples pipeline from UI | UI can render live progress | Slight overhead per callback |
| Greeting short-circuit | Avoid wasting API calls on "hi" | Cost savings | Hardcoded list may miss variations |

### Mode Classification Logic
```python
def _classify_mode_llm(self, question: str) -> str:
    # Keyword hints provided to LLM (not hardcoded rules):
    #   summary_keywords: "summarize", "overview", "what happened", "recap", ...
    #   fact_keywords: "how long", "how many", "why did", "who is", ...
    # LLM classifies based on overall intent, returns "summary" or "fact".
    # Fallback: FACT_MODE (stricter) on any failure.
```

### Failure Modes

| Failure | Handling |
|---------|----------|
| Missing OPENAI_API_KEY | `RuntimeError` at init |
| Layer init fails | Exception propagates up |
| Mode classification LLM fails | Defaults to FACT_MODE |
| Any layer fails mid-query | Returns refusal or error |

### Improvements

**MVP-safe:**
- Add timing logs for each layer (measure bottlenecks)
- Cache query embeddings within a session

**Production:**
- Async layer execution where possible
- Circuit breaker for OpenAI failures
- Rate limiting

---

## 3. layers/raw_memory.py

### What It Does
Loads all `.md` files from the data directory and parses them into chunks. Preserves exact text as ground truth for citations. Never interprets or summarizes.

### Execution Timing
- **Startup only**: `_load_all()` runs once during init. Walks the data directory recursively.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Sets data_dir, calls `_load_all()` |
| `_load_all()` | Recursively finds `.md` files, routes to appropriate parser (slack → email → document) |
| `_parse_slack_messages()` | Parses chat logs with timestamps into individual message chunks |
| `_parse_email()` | Parses email files into single chunks with timestamp, sender, recipient, subject metadata |
| `_looks_like_email()` | Detects email files by `From:/To:/Subject:` header patterns |
| `_parse_document()` | Parses regular docs into ~1000 char chunks |
| `_parse_timestamp_from_line()` | Regex extraction for ISO dates and "Dec 22, 2025" formats |
| `get_chunk_by_id()` | O(n) lookup by chunk ID |
| `get_chunks_by_time_range()` | Filters chunks by timestamp |
| `get_all_chunks()` | Returns full list |

### Chunk Schema
```python
{
    "id": "dummy_slack:msg:5",      # unique identifier
    "file": "data/dummy_slack.md",  # source file path
    "text": "actual message text",  # raw content (never modified)
    "timestamp": datetime or None,  # parsed timestamp
    "start_line": 10,               # for debugging/citation
    "end_line": 15,
    "type": "slack_message" | "email" | "document" | "profile",
    # Email-only fields:
    "sender": "CTO" or None,
    "recipient": "Archit" or None,
    "subject": "Access and credentials" or None,
}
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Special handling for `identity.md` | Keep profile as single chunk for better retrieval | Always retrieves full identity | May be too large for context |
| ~1000 char chunk limit | Balance between context and precision | Good retrieval granularity | May split mid-sentence |
| Slack detection by filename | Simple heuristic | No config needed | May miss unconventional names |
| Email detection by folder + headers | Matches `*mail*` dirs or `From:/To:/Subject:` patterns | Works for any email format | Needs ≥2 headers to match |
| Emails kept as single chunk | Emails are short and self-contained | Full context preserved, proper timestamps | No splitting for long emails |

### Failure Modes

| Failure | Handling |
|---------|----------|
| File read fails (encoding, permission) | `try/except`, continues to next file |
| No timestamp found | Chunk gets `timestamp: None` |
| Empty file | Produces no chunks (silent skip) |

### Security Notes
- Raw memory stores everything as-is, including sensitive data
- Filtering happens downstream in verifier_gate.py

### Improvements

**MVP-safe:**
- Add chunk count logging at startup
- Warn if no chunks loaded

**Production:**
- Use a proper chunking library (LangChain, LlamaIndex)
- Add overlap between chunks to avoid context loss
- Index chunk IDs in a dict for O(1) lookup

---

## 4. layers/keyword_memory.py

### What It Does
Replaces the old Semantic Memory layer. Extracts keywords from every chunk using LLM, builds per-chunk keyword embeddings, and aggregates keywords per week. Week-level embeddings are used **only for routing** (narrowing the candidate pool); per-message keyword embeddings drive the actual ranking in the Retrieval layer.

No LLM summaries are generated — only keyword lists. This is cheaper and faster than the old approach of generating weekly summaries.

### Execution Timing
- **Startup**: Loads cached keyword index from `.cache/keyword_index.json` or builds from scratch (LLM calls for keyword extraction + embedding calls).

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Sets up paths, calls `_load_or_build()` |
| `_load_or_build()` | Loads from cache or builds index |
| `_build_index()` | Iterates all chunks, extracts keywords, embeds keyword strings, groups by week |
| `_extract_keywords()` | LLM extracts 5-8 keywords/phrases from chunk text. Returns JSON array. |
| `_fallback_keywords()` | Top-8 non-stopword words by frequency (used when LLM fails) |
| `_embed()` | Embeds a keyword string. Returns None on failure. |
| `_save_index()` | Persists index to JSON cache |
| `find_relevant_weeks()` | Cosine similarity between query embedding and week keyword embeddings → top-k weeks |
| `get_chunk_ids_for_weeks()` | Returns all chunk IDs from selected weeks |
| `score_chunks_by_keywords()` | Cosine similarity between query embedding and per-chunk keyword embeddings. Returns sorted `(score, chunk_id)` list. |

### Index Schema
```python
# Cached to .cache/keyword_index.json
{
    "chunk_keywords": {
        "dummy_slack:msg:5": {
            "keywords": ["inference", "latency", "cold start", ...],
            "embedding": [0.012, -0.034, ...]  # 1536-dim
        },
        ...
    },
    "weeks": {
        "2025-W51": {
            "keywords": ["inference", "latency", "cold start", "deployment", ...],  # union of chunk keywords
            "embedding": [0.008, -0.021, ...],  # embedding of joined keywords
            "chunk_ids": ["dummy_slack:msg:5", "dummy_slack:msg:6", ...]
        },
        ...
    }
}
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Keywords instead of summaries | No LLM summarization needed — cheaper, faster, no info loss | Lower cost, no hallucinated summaries | Less context than a full summary |
| LLM keyword extraction | Better than regex for technical terms and entities | High quality keywords | LLM cost per chunk at startup |
| Fallback to frequency-based | Robustness when LLM fails | Always produces keywords | Lower quality |
| Per-chunk + per-week embeddings | Two-level ranking: coarse week routing + fine message scoring | Efficient retrieval | More embeddings to store |
| JSON file cache | Simple, no external DB | Easy to inspect/debug | Not scalable to very large data |
| Week key format `%Y-W%U` | Groups chunks by calendar week | Natural temporal grouping | Timezone-unaware |

### Failure Modes

| Failure | Handling |
|---------|----------|
| LLM keyword extraction fails | Falls back to `_fallback_keywords()` (frequency-based) |
| Embedding fails | `embedding: None`, chunk/week gets score 0 in retrieval |
| Cache file corrupted | Rebuilds index from scratch |
| No chunks with timestamps | `weeks` dict is empty, retrieval falls back to all chunks |

### Improvements

**MVP-safe:**
- Log when rebuilding index vs loading from cache
- Add cache invalidation when data files change

**Production:**
- Use vector DB (Pinecone, Qdrant, Chroma)
- Incremental updates instead of full rebuild
- Batch LLM keyword extraction calls

---

## 5. layers/query_understanding.py

### What It Does
Parses natural language time expressions into concrete date ranges AND uses LLM to rewrite the query into optimized search keywords. Handles "late December", "Q4 2025", "around Christmas", etc.

### Execution Timing
- **Per-query**: `parse()` runs on each question. Date parsing is pure Python (no LLM). `rewrite_for_search()` makes one LLM call.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Sets default_year, builds month_map, holidays dict. Stores client + gen_model for LLM rewrite. |
| `parse_date_range()` | Regex-based time parser. Returns `(start_datetime, end_datetime)` or None. |
| `extract_topics()` | Simple keyword extraction (filters stopwords) — used as fallback. |
| `rewrite_for_search()` | **LLM call**: rewrites query into `{"keywords": [...], "rewritten": "..."}`. Only extracts/normalises terms present in the question — never adds external facts. Falls back to `extract_topics()`. |
| `parse()` | Returns structured dict with query, date_range, topics, **keywords**, **rewritten_query**. |

### Return Schema
```python
{
    "query": "What happened in late December around inference?",
    "date_range": (datetime(2025, 12, 20), datetime(2025, 12, 31, 23, 59, 59)),
    "topics": ["december", "inference"],
    "keywords": ["inference", "late december", "activity"],        # LLM-extracted
    "rewritten_query": "inference activities late December 2025"   # LLM-rewritten
}
```

### Supported Date Patterns

| Pattern | Example | Result |
|---------|---------|--------|
| Quarter | "Q4 2025" | Oct 1 - Dec 31, 2025 |
| Early/mid/late month | "late December" | Dec 20 - Dec 31 |
| Full month | "December 2025" | Dec 1 - Dec 31 |
| Holidays | "around Christmas" | Dec 24 - Dec 26 |

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Regex-based date parsing | Fast, deterministic, no API cost | Zero latency for dates | Limited flexibility |
| LLM-based query rewrite | Better search keywords than regex extraction | Handles synonyms, normalization | One LLM call per query |
| Strict "no hallucination" rewrite prompt | Keywords must come from the question itself | Prevents fabricated context | May miss useful expansions |
| Default year 2025 | Matches data context | No year ambiguity | Hardcoded assumption |
| 3-day holiday window | Capture "around Christmas" intent | Natural language friendly | May be too narrow/wide |
| Graceful fallback to `extract_topics()` | Robustness when LLM unavailable | Always returns keywords | Lower quality |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Unrecognized date format | Returns `None` (no date filtering) |
| LLM rewrite fails | Falls back to `extract_topics()` for keywords, original query for rewritten |
| No client provided | Skips LLM rewrite entirely, uses fallback |

### Improvements

**MVP-safe:**
- Add "last week", "yesterday", "this month" support
- Handle "2 weeks ago" relative dates

**Production:**
- Use dateparser library for robust parsing
- LLM fallback for ambiguous date queries
- Support multiple date ranges in one query

---

## 6. layers/retrieval.py

### What It Does
Two-level keyword-based retrieval. Level 1 (week routing): embed query keywords → cosine similarity vs week keyword embeddings → top-3 weeks. Level 2 (message ranking): combined score of keyword similarity (0.6) and full-text similarity (0.4), plus date-range and identity boosts. Returns top-k chunks within a context budget.

### Execution Timing
- **Per-query**: Multiple embedding API calls (query keywords, query text, batch chunk text embeddings).

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Stores references to raw_memory, keyword_memory, client, embed_model, top_k |
| `_embed()` | Single embedding call for a text string |
| `_score_full_text()` | Batch-embed chunk texts and compute cosine similarity against query |
| `retrieve()` | Main method. Two-level keyword-based retrieval. Takes `keywords` and `rewritten_query` from QueryUnderstanding. |

### Retrieval Pipeline
```
1. Build keyword_str from parsed keywords (or fall back to raw query)
2. Build search_text from rewritten_query (or fall back to raw query)
3. Embed keyword_str → q_kw_emb (for week routing + keyword scoring)
4. Embed search_text → q_full_emb (for full-text reranking)
5. Level 1: keyword_memory.find_relevant_weeks(q_kw_emb, top_k=3) → week routing
6. Collect candidate chunk IDs from those weeks
7. Add chunks from explicit date range (if parsed)
8. Fallback: if no candidates, use all chunks
9. Inject identity.md chunks for personal queries (detected by keyword set)
10. Level 2: keyword_memory.score_chunks_by_keywords(candidates, q_kw_emb) → keyword scores
11. _score_full_text(candidates, q_full_emb) → full-text scores
12. Combined: score = 0.6 × keyword_sim + 0.4 × full_text_sim
13. Apply boosts: date range (+0.2), identity.md (+0.4)
14. Sort by score, select top-k within max_context_chars
```

### Scoring Formula
```python
score = 0.6 * keyword_cosine_sim + 0.4 * full_text_cosine_sim

# Date range boost
if chunk.timestamp in date_range:
    score += 0.2

# Identity boost for personal queries
if is_personal and 'identity.md' in chunk.file:
    score += 0.4
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Two-level routing (week → message) | Narrows candidates cheaply before expensive scoring | Efficient | May miss chunks outside top weeks |
| 0.6 keyword + 0.4 full-text blend | Keywords catch specific terms; full-text catches context | Balanced precision | Weights are heuristic |
| Batch embedding for full-text | Fewer API calls | Cost efficient | All-or-nothing (one failure = no scores) |
| +0.2 date boost | Temporal relevance matters | Surfaces time-relevant chunks | May over-boost irrelevant content in range |
| +0.4 identity boost | Personal queries need profile info | Reliable for "who are you" questions | High boost may dominate |
| top_k=6 default | Balance context size and coverage | Usually enough | May miss relevant chunks |
| max_context_chars=3000 | Stay within LLM limits | Predictable | May truncate important info |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Query keyword embedding fails | Returns empty chunks with error metadata |
| Full-text batch embedding fails | Full-text scores are 0 (keyword-only ranking) |
| No candidates from week routing | Falls back to all chunks |

### Performance Notes
This layer makes multiple OpenAI API calls per query:
1. One for keyword embedding
2. One for full-text query embedding (skipped if same as keyword string)
3. One batch call for candidate chunk text embeddings

This is the main latency contributor per query.

### Improvements

**MVP-safe:**
- Cache chunk text embeddings (they don't change between queries)
- Log retrieval scores for debugging

**Production:**
- Pre-compute and persist chunk text embeddings at startup
- Use approximate nearest neighbor (ANN) for large datasets
- Add BM25 keyword search as a third scoring signal

---

## 7. layers/evidence_extraction.py

### What It Does
Given retrieved chunks and a question, asks the LLM to extract exact verbatim quotes that support the answer. Validates that quotes actually appear in chunks. Adjusts minimum quote length based on answer mode.

### Execution Timing
- **Per-query**: One LLM call to extract evidence.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Stores client and model name |
| `extract()` | Main method. Takes `answer_mode` parameter. Builds prompt, calls LLM, parses and validates JSON response. |

### Extraction Prompt
```
Given the question and context below, identify EXACT sentences or phrases 
from the context that support an answer. Extract up to 6 relevant evidence items.
Output ONLY valid JSON: {"evidence":[{"chunk_index":0,"quote":"exact text"}]}
```

### Validation Logic
```python
1. Parse JSON response
2. For each evidence item:
   - Validate chunk_index is in range
   - Validate quote length > min_quote_length
     • SUMMARY_MODE: min 5 chars (more flexible)
     • FACT_MODE: min 8 chars (stricter)
   - Validate quote appears verbatim in chunk (with whitespace normalization)
3. Only validated items are returned
```

### Return Schema
```python
{
    "evidence": [
        {
            "quote": "exact text from chunk",
            "chunk_id": "dummy_slack:msg:5",
            "file": "data/dummy_slack.md",
            "timestamp": datetime or None,
        },
        ...
    ],
    "has_evidence": True,
    "raw_extraction": "<raw LLM output>"  # for debugging
}
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Strict verbatim validation | Prevents hallucinated quotes | Trustworthy citations | May reject valid paraphrases |
| Whitespace normalization | LLM may alter spacing | More robust matching | Could match unintended text |
| Up to 6 evidence items | Balance coverage and noise | Good for summaries | May include weak evidence |
| Different min lengths by mode | Summaries need flexibility, facts need precision | Adapts to use case | Complexity |
| `raw_extraction` in response | Debugging aid | Trace LLM output | Minor overhead |

### Known Issue
Uses `client.responses.create()` (OpenAI Responses API) instead of `client.chat.completions.create()`. This requires the newer Responses API to be available.

### Failure Modes

| Failure | Handling |
|---------|----------|
| LLM returns invalid JSON | `json.JSONDecodeError` caught, returns no evidence |
| Quote not found in chunk | Item rejected (not included in output) |
| LLM fails | Returns `{"evidence": [], "has_evidence": false}` |

### Improvements

**MVP-safe:**
- Return partial matches with lower confidence
- Log rejected quotes for debugging

**Production:**
- Use structured output (function calling) for reliable JSON
- Fuzzy matching for near-verbatim quotes
- Confidence scores per evidence item

---

## 8. layers/verifier_gate.py

### What It Does
The anti-hallucination layer. Checks if evidence actually supports the question (entailment), blocks sensitive information, and generates the final answer only if verification passes. Behaviour changes based on SUMMARY_MODE vs FACT_MODE.

### Execution Timing
- **Per-query**: One or two LLM calls (entailment check in FACT_MODE + answer generation).

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Stores client, model, sensitive patterns (regex + keyword lists) |
| `_contains_sensitive_info()` | Regex + keyword check for credentials, API keys, etc. Allows `identity.md` content through. |
| `_entailment_state()` | LLM call to check if evidence supports the question. Returns "yes", "no", or "unknown". |
| `generate_answer()` | Main method. Verification logic + answer generation with mode-specific prompts. |

### Entailment States

| State | Meaning | Action |
|-------|---------|--------|
| "yes" | Evidence supports question | Generate full answer |
| "no" | Evidence does NOT support question | Refuse ("I do not see this") |
| "unknown" | Can't determine | Quote-only fallback (no paraphrasing) |

### Answer Generation Flow
```
1. Check question for sensitive keywords → block if found
2. Check if evidence exists → refuse if empty
3. If SUMMARY_MODE:
   - Skip entailment check
   - Require at least 1 unique chunk
   - Confidence: "high" if ≥2 chunks, "medium" otherwise
4. If FACT_MODE:
   - Run entailment check
   - "no" → refuse ("I do not see this in your data.")
   - "unknown" → quote-only fallback (up to 3 quotes from distinct chunks)
   - "yes" → generate answer
5. Build answer prompt (different for summary vs fact)
   - Both enforce: "Use 'I', no em dash, no jargon, no invented facts"
   - Summary: "Provide a brief summary"
   - Fact: "Do NOT infer beyond what is stated"
6. Call LLM to generate answer
7. Check answer for sensitive leakage → block if found
   - Exception: identity.md content is allowed
8. Build citations (filter invalid, redact emails for non-identity sources)
9. Compute confidence:
   - Summary: based on unique chunk count
   - Fact: based on citation count (≥2 = high, else medium)
   - Refusal: "none"
```

### Quote-Only Fallback
When entailment is unclear, instead of risking hallucination:
```
From my data:
- "exact quote 1"
- "exact quote 2"
```
This preserves trust by showing raw evidence without interpretation. Limited to 3 quotes from distinct chunks.

### Sensitive Information Blocking

**Regex patterns blocked:**
- `sk-*` (OpenAI keys)
- `AKIA*` (AWS access keys)
- `password:`, `api_key:`, `secret:`, `token:` fields

**Keyword checks:**
- password, passwd, pwd, api_key, secret, token, credential, creds, aws access, aws secret, private key, ssh key, account id, account number

**Exception:** Content from `identity.md` is allowed (user's intended public profile).

**Defense in depth:** Sensitive check runs on (1) the question, (2) the generated answer, and (3) each citation.

### Citation Building
- Filters out empty, placeholder, or very short quotes (< 5 chars)
- Filters out underscores-only, dots-only, dashes-only content
- Redacts email addresses from citations **unless** source is `identity.md`
- Skips citations containing sensitive info (except from `identity.md`)

### Known Issue
Uses `client.responses.create()` (OpenAI Responses API) for answer generation instead of `client.chat.completions.create()`. Entailment check correctly uses `client.chat.completions.create()`.

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Entailment check for facts | Prevent "retrieved but unrelated" answers | High precision | Extra LLM call, latency |
| Skip entailment for summaries | Summaries are exploratory, not claims | Faster summaries | May include tangential info |
| Quote-only fallback | Safe default when uncertain | Preserves trust | Less natural response |
| Block sensitive at input AND output | Defense in depth | Robust protection | May over-block |
| Allow identity.md content | User's public profile should be shareable | "Where do you work?" works | Must trust identity.md |
| Email redaction in citations | Privacy protection | Prevents leakage | May obscure useful info |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Entailment LLM fails | Returns "unknown" (fail open to quote-only) |
| Answer LLM fails | Returns refusal |
| JSON parsing fails in entailment | Returns "unknown" |

### Improvements

**MVP-safe:**
- Log blocked queries for audit
- Add more credential patterns (GCP, Azure)

**Production:**
- Use a dedicated PII detection service
- Configurable blocklists per deployment
- Audit logging for compliance

---

## 9. layers/style_layer.py

### What It Does
Applies Archit's voice to answers while preserving factual content. Uses identity.md as style guidance. Does not restyle refusals or quote-only answers.

### Execution Timing
- **Per-query**: One LLM call (skipped for refusals and quote-only answers).

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Loads identity.md for style reference |
| `apply_style()` | Main method. Decides whether to restyle, calls LLM if needed |

### Skip Conditions
```python
# Don't restyle these:
- Refusals ("do not see", "don't see")
- Quote-only fallback ("From my data:")
- Very short answers (< 10 chars)
```

### Style Rules (in prompt)
```
- Use 'I' for individual actions and observations
- Use 'we' only when evidence shows shared decision
- Keep it concise, direct, work-focused
- No buzzwords, no hype, no em dash
- Preserve all facts, numbers, and technical details exactly
- Do not add any information not in the original
```

### Known Issue
Uses `client.responses.create()` (OpenAI Responses API) with `max_output_tokens=120` instead of `client.chat.completions.create()`.

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Skip restyling refusals | Refusals should be clear, not styled | Consistent UX | None |
| Preserve "Sources:" line | Extracts and re-attaches after restyling | Traceability | Slight complexity |
| Low temperature (0.0) | Deterministic styling | Consistent voice | May be too rigid |
| Max 120 output tokens | Keep it concise | Matches personality | May truncate |

### Failure Modes

| Failure | Handling |
|---------|----------|
| LLM fails | Returns original answer unchanged |
| Empty response | Returns original answer |
| identity.md missing | Uses fallback: "You are Archit, a concise and direct communicator." |

### Improvements

**MVP-safe:**
- A/B test styled vs unstyled responses
- Add style strength parameter

**Production:**
- Fine-tune a small model on Archit's writing samples
- Learn style from examples rather than instructions

---

## Cross-Cutting Concerns

### Performance Hotspots

| Layer | Cause | Mitigation |
|-------|-------|------------|
| KeywordMemory init | LLM keyword extraction + embeddings for all chunks | Cache to `.cache/keyword_index.json` |
| QueryUnderstanding | LLM query rewrite | Falls back to simple extraction |
| Mode Classification | LLM call to classify SUMMARY/FACT | Defaults to FACT on failure |
| Retrieval | Keyword embed + full-text batch embed | Can cache chunk text embeddings |
| Evidence Extraction | LLM call | Single call, bounded output |
| Verifier | Entailment LLM call | Skip for summary mode |
| Style | Restyle LLM call | Skip for refusals/quote-only |

**Total LLM calls per query (worst case: FACT_MODE):**
1. Query rewrite (QueryUnderstanding)
2. Mode classification (twin.py)
3. Query keyword embedding (Retrieval)
4. Query full-text embedding (Retrieval)
5. Batch chunk text embeddings (Retrieval)
6. Evidence extraction
7. Entailment check (fact mode only)
8. Answer generation
9. Style rewriting

**Reduced for SUMMARY_MODE:** Skips entailment check (step 7).

### Error Handling Philosophy
- Layers fail gracefully and return neutral/empty results
- Downstream layers handle missing input
- LLM failures fall back to safe defaults (FACT_MODE, extract_topics, quote-only)
- Final fallback: "I do not see this in your data."

### Security Layers
1. **Raw Memory**: Stores everything (no filtering)
2. **Keyword Memory**: No security (passes through)
3. **Evidence Extraction**: No security (passes through)
4. **Verifier Gate**: Main filter (blocks sensitive input, output, citations; redacts emails)
5. **Style Layer**: No security (trusts verifier output)

---

## If I Had 1 More Day

**Priority 1: Pre-compute chunk text embeddings**
- Store full-text embeddings alongside keyword embeddings in keyword_memory
- Eliminates per-query batch embedding calls in retrieval
- Estimated impact: 2-3x faster queries

**Priority 2: Migrate to consistent API**
- `evidence_extraction.py`, `verifier_gate.py`, and `style_layer.py` use `client.responses.create()`
- Standardize on `client.chat.completions.create()` or confirm Responses API availability

**Priority 3: Structured output for evidence extraction**
- Use OpenAI function calling instead of free-form JSON
- More reliable parsing, fewer validation failures

**Priority 4: Incremental keyword index updates**
- Detect new/changed files and update only those chunks/weeks
- Avoid full rebuild on data changes

**Priority 5: Better date parsing**
- Use `dateparser` library
- Handle "2 weeks ago", "last Monday", etc.

**Priority 6: Observability**
- Add timing logs per layer
- Track which questions hit quote-only fallback
- Monitor entailment failure rate

---

## Summary Table

| Layer | File | LLM Calls | Main Risk | Key Defense |
|-------|------|-----------|-----------|-------------|
| 1 | raw_memory.py | 0 | Data corruption | Graceful file read |
| 2 | keyword_memory.py | N (startup) | Cache miss | Disk persistence + fallback keywords |
| 3 | query_understanding.py | 1 (rewrite) | LLM failure | Fallback to `extract_topics()` |
| 4 | retrieval.py | 2-3 | Empty results | Fallback to all chunks |
| 5 | evidence_extraction.py | 1 | Hallucinated quotes | Verbatim validation |
| 6 | verifier_gate.py | 1-2 | Hallucination | Entailment + quote-only fallback |
| 7 | style_layer.py | 0-1 | Fact distortion | Skip for refusals |
| 8 | app.py | 0 | Init failure | Error display |
| - | twin.py | 1 (mode) | Orchestration bug | Layer isolation + FACT default |

---

*Generated for panel interview preparation. Last updated: Apr 2026.*
