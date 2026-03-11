# Digital Twin MVP - Architecture Documentation

> A grounded, evidence-based personal assistant that answers questions using only your data.
> Built with Streamlit, OpenAI, and a 7-layer retrieval pipeline.

---

## System Overview

```
User Question
     │
     ▼
┌─────────────┐
│   app.py    │  Layer 8: Streamlit UI
└─────────────┘
     │
     ▼
┌─────────────┐
│  twin.py    │  Orchestrator (connects all layers)
└─────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────┐
│                    7 Processing Layers              │
│                                                     │
│  L1: Raw Memory ──► L2: Semantic Memory             │
│         │                    │                      │
│         └────────┬───────────┘                      │
│                  ▼                                  │
│         L3: Query Understanding                     │
│                  │                                  │
│                  ▼                                  │
│         L4: Retrieval                               │
│                  │                                  │
│                  ▼                                  │
│         L5: Evidence Extraction                     │
│                  │                                  │
│                  ▼                                  │
│         L6: Verifier Gate (anti-hallucination)      │
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
The user-facing chat interface. Displays an avatar, chat history, and optional debug panel. Sends questions to `twin.py` and renders answers with citations and confidence badges.

### Execution Timing
- **Startup**: `load_twin()` initializes the DigitalTwin (cached with `@st.cache_resource` to avoid re-init on every interaction).
- **Per-query**: Each chat input triggers `twin.answer(prompt, debug=show_debug)`.

### Key Functions

| Block | Purpose |
|-------|---------|
| `main()` | Entry point. Sets page config, loads twin, renders UI. |
| `load_twin()` | Cached initialization of DigitalTwin. Prevents cold start on every rerun. |
| Sidebar controls | Toggles for "Show Debug Info" and "Show Citations". Example questions for guidance. |
| Chat input handler | Sends question to twin, displays answer, confidence badge, citations, and debug JSON. |
| `st.session_state.messages` | Stores chat history for display persistence across reruns. |

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| `@st.cache_resource` for twin | Avoid re-embedding all chunks on every interaction | Fast per-query response | First load is slow (~5-10s depending on data size) |
| Confidence badge colors | Visual feedback: green=high, blue=medium, yellow=low | Quick trust signal | Subjective threshold definitions |
| Optional debug panel | Allows inspection of retrieval and evidence without cluttering UI | Great for debugging/demo | Adds complexity to response object |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Twin init fails (missing API key, bad data) | `st.error()` and `st.stop()` |
| Query fails | `try/except` wraps `twin.answer()`, shows error in chat |
| Missing avatar image | Falls back to emoji "🤖" |

### Performance Notes
- **Streamlit cold start**: First load triggers full twin initialization (embedding generation, semantic summaries). This is the main performance bottleneck. Subsequent queries are fast because `@st.cache_resource` preserves the twin.
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
The central coordinator. Initializes all 7 layers at startup, then routes each question through the pipeline: parse → retrieve → extract → verify → style.

### Execution Timing
- **Startup**: Initializes all layers (RawMemory, SemanticMemory, etc.). Heavy work here.
- **Per-query**: `answer()` method runs the full pipeline.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Loads env vars, creates OpenAI client, initializes all 7 layers sequentially |
| `answer()` | Main entry point. Routes question through all layers. Returns dict with answer, confidence, citations, debug. |
| Greeting/help detection | Short-circuits pipeline for "hi", "help", etc. No memory lookup needed. |
| Mode detection | Determines SUMMARY_MODE vs FACT_MODE based on heuristics |

### Pipeline Flow in `answer()`

```python
1. UI intent check (greetings, help) → short-circuit return
2. Layer 3: query_understanding.parse(question) → date_range, topics
3. Determine answer_mode (SUMMARY_MODE if date range or "what happened")
4. Layer 4: retrieval.retrieve(question, date_range) → chunks
5. Layer 5: evidence_extraction.extract(question, chunks) → evidence
6. Layer 6: verifier_gate.generate_answer(question, evidence, chunks, mode) → answer
7. Layer 7: style_layer.apply_style(answer_result) → final answer
8. Attach debug info if requested
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Heuristic mode detection | Fast, no LLM call needed | Zero latency for mode routing | May misclassify edge cases |
| Sequential layer init | Simple, predictable | Easy to debug | Slower startup (but only once) |
| Greeting short-circuit | Avoid wasting API calls on "hi" | Cost savings | Hardcoded list may miss variations |

### Mode Detection Logic
```python
is_summary_mode = (
    date_range is not None or               # "Q4 2025" → summary
    question.startswith("what happened") or # "what happened last week" → summary
    "what was i working on" in question or  # explicit summary request
    "what was i doing" in question
)
```

This is fast but imperfect. Alternative: LLM-based classification (removed as dead code).

### Failure Modes

| Failure | Handling |
|---------|----------|
| Missing OPENAI_API_KEY | `RuntimeError` at init |
| Layer init fails | Exception propagates up |
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
| `_load_all()` | Recursively finds `.md` files, routes to appropriate parser |
| `_parse_slack_messages()` | Parses chat logs with timestamps into individual message chunks |
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
    "type": "slack_message" | "document" | "profile"
}
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Special handling for `identity.md` | Keep profile as single chunk for better retrieval | Always retrieves full identity | May be too large for context |
| ~1000 char chunk limit | Balance between context and precision | Good retrieval granularity | May split mid-sentence |
| Slack detection by filename | Simple heuristic | No config needed | May miss unconventional names |

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

## 4. layers/semantic_memory.py

### What It Does
Generates weekly summaries of raw chunks and embeds them. Acts as a "routing layer" to quickly narrow down which time periods are relevant before doing expensive chunk-level retrieval.

### Execution Timing
- **Startup**: Loads cached summaries from `.cache/semantic_summaries.json` or generates new ones (expensive: multiple LLM calls + embeddings).

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Sets up paths, calls `_load_or_generate()` |
| `_load_or_generate()` | Loads from cache or generates summaries |
| `_generate_weekly_summaries()` | Groups chunks by ISO week, calls LLM to summarize, embeds summaries |
| `_save_summaries()` | Persists to JSON cache |
| `find_relevant_weeks()` | Cosine similarity between query embedding and week embeddings |
| `get_chunk_ids_for_weeks()` | Returns chunk IDs from selected weeks |

### Summary Schema
```python
{
    "week": "2025-W51",
    "summary": "AI-generated summary of the week's activities",
    "chunk_ids": ["dummy_slack:msg:0", "dummy_slack:msg:1", ...],
    "start_date": "2025-12-20T10:00:00",
    "end_date": "2025-12-26T18:00:00",
    "embedding": [0.012, -0.034, ...]  # 1536-dim for text-embedding-3-small
}
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Weekly granularity | Balances summary quality and count | Few summaries to search | May miss daily patterns |
| JSON file cache | Simple, no external DB | Easy to inspect/debug | Not scalable to large data |
| Limit to 20 chunks per week | Avoid hitting token limits | Predictable cost | May lose info in busy weeks |
| 3000 char limit on summary input | Stay within context window | Reliable | Truncates long weeks |

### Failure Modes

| Failure | Handling |
|---------|----------|
| LLM call fails | Summary becomes "Summary generation failed" |
| Embedding fails | `embedding: None`, week gets score 0 in retrieval |
| Cache file corrupted | Regenerates summaries |

### Improvements

**MVP-safe:**
- Log when regenerating summaries vs loading from cache
- Add cache invalidation when data changes

**Production:**
- Use vector DB (Pinecone, Qdrant, Chroma)
- Dynamic granularity (daily for recent, weekly for old)
- Incremental updates instead of full regeneration

---

## 5. layers/query_understanding.py

### What It Does
Parses natural language time expressions into concrete date ranges. Handles "late December", "Q4 2025", "around Christmas", etc. Also extracts topic keywords.

### Execution Timing
- **Per-query**: `parse()` runs on each question. Pure Python, no LLM calls.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Sets default_year, builds month_map and holidays dict |
| `parse_date_range()` | Main parser. Returns `(start_datetime, end_datetime)` or None |
| `extract_topics()` | Simple keyword extraction (filters stopwords) |
| `parse()` | Returns structured dict with query, date_range, topics |

### Supported Patterns

| Pattern | Example | Result |
|---------|---------|--------|
| Quarter | "Q4 2025" | Oct 1 - Dec 31, 2025 |
| Early/mid/late month | "late December" | Dec 20 - Dec 31 |
| Full month | "December 2025" | Dec 1 - Dec 31 |
| Holidays | "around Christmas" | Dec 24 - Dec 26 |

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Regex-based parsing | Fast, deterministic, no API cost | Zero latency | Limited flexibility |
| Default year 2025 | Matches data context | No year ambiguity | Hardcoded assumption |
| 3-day holiday window | Capture "around Christmas" intent | Natural language friendly | May be too narrow/wide |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Unrecognized date format | Returns `None` (no date filtering) |
| Typos in month names | Falls through, returns `None` |

### Improvements

**MVP-safe:**
- Add "last week", "yesterday", "this month" support
- Handle "2 weeks ago" relative dates

**Production:**
- Use dateparser library for robust parsing
- LLM fallback for ambiguous queries
- Support multiple date ranges in one query

---

## 6. layers/retrieval.py

### What It Does
Hierarchical retrieval: uses semantic memory to find relevant weeks, pulls raw chunks from those weeks, scores by embedding similarity, and returns top-k within context limit.

### Execution Timing
- **Per-query**: Main retrieval logic runs here. Multiple embedding API calls.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Stores references to raw_memory, semantic_memory, client |
| `_embed_query()` | Single embedding call for the question |
| `_embed_chunks()` | Batch embedding for candidate chunks |
| `retrieve()` | Main method. Implements hierarchical retrieval. |

### Retrieval Pipeline
```
1. Embed query
2. Find top-3 relevant weeks via semantic memory (cosine similarity)
3. Get chunk IDs from those weeks
4. Add chunks from explicit date range (if parsed)
5. Fallback: if no candidates, use all chunks
6. Inject identity.md for personal queries ("where do you work")
7. Embed all candidate chunks (batch)
8. Score = cosine_similarity + boost (date match, identity boost)
9. Sort by score, select top-k within max_context_chars
```

### Scoring Boosts
```python
# Identity boost for personal queries
if is_personal_query and 'identity.md' in chunk['file']:
    boost += 0.5

# Date range boost
if date_range and chunk["timestamp"] in range:
    boost += 0.3
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Two-stage retrieval | Reduces embedding calls | Cheaper, faster | May miss chunks outside top weeks |
| Batch embedding | Fewer API calls | Cost efficient | All-or-nothing (one failure = no embeddings) |
| top_k=6 default | Balance context size and coverage | Usually enough | May miss relevant chunks |
| max_context_chars=3000 | Stay within LLM limits | Predictable | May truncate important info |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Query embedding fails | Returns empty chunks with error metadata |
| Chunk embedding fails | Those chunks get score 0 |
| No candidates found | Falls back to all chunks |

### Performance Hotspot
This layer makes multiple OpenAI API calls per query:
1. One for query embedding
2. One batch call for chunk embeddings (can be 10-50 chunks)

This is the main latency contributor per query.

### Improvements

**MVP-safe:**
- Cache chunk embeddings (they don't change)
- Log retrieval scores for debugging

**Production:**
- Pre-compute and persist chunk embeddings
- Use approximate nearest neighbor (ANN) for large datasets
- Hybrid retrieval: combine semantic + BM25 keyword search

---

## 7. layers/evidence_extraction.py

### What It Does
Given retrieved chunks and a question, asks the LLM to extract exact verbatim quotes that support the answer. Validates that quotes actually appear in chunks.

### Execution Timing
- **Per-query**: One LLM call to extract evidence.

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Stores client and model name |
| `extract()` | Main method. Builds prompt, calls LLM, parses and validates JSON response |

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
   - Validate quote length > min_quote_length (5 for summary, 8 for fact)
   - Validate quote appears verbatim in chunk (with whitespace normalization)
3. Only validated items are returned
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Strict verbatim validation | Prevents hallucinated quotes | Trustworthy citations | May reject valid paraphrases |
| Whitespace normalization | LLM may alter spacing | More robust matching | Could match unintended text |
| Up to 6 evidence items | Balance coverage and noise | Good for summaries | May include weak evidence |
| Different min lengths by mode | Summaries need flexibility | Adapts to use case | Complexity |

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
The anti-hallucination layer. Checks if evidence actually supports the question (entailment), blocks sensitive information, and generates the final answer only if verification passes.

### Execution Timing
- **Per-query**: One or two LLM calls (entailment check + answer generation).

### Key Functions

| Block | Purpose |
|-------|---------|
| `__init__()` | Stores client, model, sensitive patterns |
| `_contains_sensitive_info()` | Regex + keyword check for credentials, API keys, etc. |
| `_entailment_state()` | LLM call to check if evidence supports the question |
| `generate_answer()` | Main method. Verification logic + answer generation |

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
3. If SUMMARY_MODE: skip entailment, allow 1+ chunks
4. If FACT_MODE: run entailment check
   - "no" → refuse
   - "unknown" → quote-only fallback
   - "yes" → generate answer
5. Build answer prompt (different for summary vs fact)
6. Call LLM to generate answer
7. Check answer for sensitive leakage → block if found
8. Build citations (filter invalid, redact emails)
9. Compute confidence (high/medium/none)
```

### Quote-Only Fallback
When entailment is unclear, instead of risking hallucination:
```
From my data:
- "exact quote 1"
- "exact quote 2"
```
This preserves trust by showing raw evidence without interpretation.

### Sensitive Information Blocking

**Patterns blocked:**
- `sk-*` (OpenAI keys)
- `AKIA*` (AWS keys)
- Keywords: password, api_key, secret, token, credential, etc.

**Exception:** Content from `identity.md` is allowed (user's intended public profile).

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Entailment check for facts | Prevent "retrieved but unrelated" answers | High precision | Extra LLM call, latency |
| Skip entailment for summaries | Summaries are exploratory, not claims | Faster summaries | May include tangential info |
| Quote-only fallback | Safe default when uncertain | Preserves trust | Less natural response |
| Block sensitive at input AND output | Defense in depth | Robust protection | May over-block |

### Failure Modes

| Failure | Handling |
|---------|----------|
| Entailment LLM fails | Returns "unknown" (fail open to quote-only) |
| Answer LLM fails | Returns refusal |
| JSON parsing fails | Returns "unknown" |

### Security Notes
- Sensitive detection happens on: (1) question, (2) generated answer, (3) each citation
- Email addresses are redacted from citations (except identity.md)
- This is the primary security layer

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
- **Per-query**: One LLM call (skipped for refusals).

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
```

### Design Decisions

| Decision | Why | Pros | Cons |
|----------|-----|------|------|
| Skip restyling refusals | Refusals should be clear, not styled | Consistent UX | None |
| Preserve "Sources:" line | Keep citation reference | Traceability | Slight complexity |
| Low temperature (0.0) | Deterministic styling | Consistent voice | May be too rigid |
| Max 120 tokens | Keep it concise | Matches personality | May truncate |

### Failure Modes

| Failure | Handling |
|---------|----------|
| LLM fails | Returns original answer unchanged |
| Empty response | Returns original answer |
| identity.md missing | Uses fallback description |

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
| SemanticMemory init | Generates summaries + embeddings | Cache to disk |
| Retrieval | Batch embedding of chunks | Cache chunk embeddings |
| Verifier | Entailment LLM call | Skip for summary mode |
| Style | Restyle LLM call | Skip for refusals |

**Total LLM calls per query (worst case):**
1. Query embedding (retrieval)
2. Chunk embeddings (retrieval)
3. Evidence extraction
4. Entailment check (fact mode only)
5. Answer generation
6. Style rewriting

### Error Handling Philosophy
- Layers fail gracefully and return neutral/empty results
- Downstream layers handle missing input
- Final fallback: "I do not see this in your data."

### Security Layers
1. **Raw Memory**: Stores everything (no filtering)
2. **Evidence Extraction**: No security (passes through)
3. **Verifier Gate**: Main filter (blocks sensitive input, output, citations)
4. **Style Layer**: No security (trusts verifier output)

---

## If I Had 1 More Day

**Priority 1: Pre-compute chunk embeddings**
- Store embeddings alongside chunks in raw_memory
- Eliminates per-query embedding calls
- Estimated impact: 2-3x faster queries

**Priority 2: Add BM25 keyword search**
- Hybrid retrieval: semantic + keyword
- Catches exact matches that embeddings miss
- Especially useful for technical terms, names

**Priority 3: Structured output for evidence extraction**
- Use OpenAI function calling instead of free-form JSON
- More reliable parsing, fewer validation failures

**Priority 4: Incremental semantic memory updates**
- Detect new/changed files and update only those weeks
- Avoid full regeneration on data changes

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
| 2 | semantic_memory.py | N (startup) | Cache miss | Disk persistence |
| 3 | query_understanding.py | 0 | Parse failure | Returns None |
| 4 | retrieval.py | 2 | Empty results | Fallback to all chunks |
| 5 | evidence_extraction.py | 1 | Hallucinated quotes | Verbatim validation |
| 6 | verifier_gate.py | 1-2 | Hallucination | Entailment + fallback |
| 7 | style_layer.py | 0-1 | Fact distortion | Skip for refusals |
| 8 | app.py | 0 | Init failure | Error display |
| - | twin.py | 0 | Orchestration bug | Layer isolation |

---

*Generated for panel interview preparation. Last updated: Feb 2026.*
