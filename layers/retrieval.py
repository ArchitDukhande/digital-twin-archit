"""
Layer 4: Retrieval — Two-level keyword-based routing

Level 1 (week routing):
  Embed query keywords → cosine similarity vs week keyword embeddings → top-3 weeks.
  Weeks narrow the candidate pool only; they do not score messages directly.

Level 2 (message ranking):
  Cosine similarity between query keyword embedding and per-message keyword embedding.
  Combined (0.6) with full-text cosine similarity (0.4) for precision.

Strict no-hallucination: ranking is purely similarity-based; the LLM
only touches evidence extraction and verification (later layers).
"""
from typing import List, Dict, Any, Optional
import numpy as np
from openai import OpenAI


class Retrieval:
    def __init__(self, raw_memory, keyword_memory, client: OpenAI, embed_model: str, top_k: int = 6):
        self.raw_memory = raw_memory
        self.keyword_memory = keyword_memory
        self.client = client
        self.embed_model = embed_model
        self.top_k = top_k

    def _embed(self, text: str) -> List[float]:
        """Embed a single text string."""
        if not text.strip():
            return []
        try:
            resp = self.client.embeddings.create(model=self.embed_model, input=[text])
            return resp.data[0].embedding
        except Exception:
            return []

    def _score_full_text(
        self, chunks: List[Dict[str, Any]], q_emb: List[float]
    ) -> Dict[str, float]:
        """
        Batch-embed chunk texts and compute cosine similarity against query.
        Returns {chunk_id: score}.
        """
        if not chunks or not q_emb:
            return {}
        texts = [c["text"] for c in chunks]
        try:
            resp = self.client.embeddings.create(model=self.embed_model, input=texts)
            q_np = np.array(q_emb, dtype=float)
            scores: Dict[str, float] = {}
            for i, chunk in enumerate(chunks):
                c_np = np.array(resp.data[i].embedding, dtype=float)
                sim = float(
                    np.dot(q_np, c_np) / (np.linalg.norm(q_np) * np.linalg.norm(c_np) + 1e-9)
                )
                scores[chunk["id"]] = sim
            return scores
        except Exception:
            return {}

    def retrieve(
        self,
        query: str,
        date_range=None,
        max_context_chars: int = 3000,
        keywords: Optional[List[str]] = None,
        rewritten_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Two-level keyword-based retrieval.

        1. Embed keyword string → week cosine similarity → top-3 weeks (routing).
        2. Collect candidate chunks from those weeks.
        3. Score each candidate: 0.6 × keyword_sim + 0.4 × full-text_sim.
        4. Apply date-range and identity boosts, sort, return top-k.
        """
        # Build the search strings
        keyword_str = " ".join(keywords) if keywords else query
        search_text = rewritten_query or query

        # Embed query keywords (for week routing + per-message keyword scoring)
        q_kw_emb = self._embed(keyword_str)
        # Embed full query text (for full-text reranking)
        q_full_emb = self._embed(search_text) if search_text != keyword_str else q_kw_emb

        if not q_kw_emb:
            return {"chunks": [], "metadata": {"error": "embedding failed"}}

        # ── Level 1: Week routing ─────────────────────────────────────────────
        relevant_weeks = self.keyword_memory.find_relevant_weeks(q_kw_emb, top_k=3)
        candidate_ids = self.keyword_memory.get_chunk_ids_for_weeks(relevant_weeks)

        # Gather candidate chunks (deduped)
        seen_ids: set = set()
        candidate_chunks: List[Dict[str, Any]] = []
        for cid in candidate_ids:
            chunk = self.raw_memory.get_chunk_by_id(cid)
            if chunk and cid not in seen_ids:
                candidate_chunks.append(chunk)
                seen_ids.add(cid)

        # Add date-range chunks if provided
        if date_range:
            start, end = date_range
            for tc in self.raw_memory.get_chunks_by_time_range(start, end):
                if tc["id"] not in seen_ids:
                    candidate_chunks.append(tc)
                    seen_ids.add(tc["id"])

        # Fallback: search all chunks if routing returned nothing
        if not candidate_chunks:
            candidate_chunks = self.raw_memory.get_all_chunks()
            seen_ids = {c["id"] for c in candidate_chunks}

        # Always include identity.md for personal-info queries
        personal_keywords = {
            "you", "your", "archit", "location", "city", "stay", "live",
            "where", "email", "contact", "phone", "role", "team", "work", "timezone",
        }
        combined_lower = (keyword_str + " " + search_text).lower()
        is_personal = bool(personal_keywords & set(combined_lower.split()))
        if is_personal:
            for ic in self.raw_memory.get_all_chunks():
                if "identity.md" in ic["file"] and ic["id"] not in seen_ids:
                    candidate_chunks.append(ic)
                    seen_ids.add(ic["id"])

        # ── Level 2: Per-message keyword scoring ─────────────────────────────
        kw_score_list = self.keyword_memory.score_chunks_by_keywords(
            [c["id"] for c in candidate_chunks], q_kw_emb
        )
        kw_scores: Dict[str, float] = dict(kw_score_list)

        # Full-text cosine similarity scores
        full_scores = self._score_full_text(candidate_chunks, q_full_emb)

        # ── Combined scoring & ranking ────────────────────────────────────────
        combined = []
        for chunk in candidate_chunks:
            cid = chunk["id"]
            kw_sim = kw_scores.get(cid, 0.0)
            ft_sim = full_scores.get(cid, 0.0)
            score = 0.6 * kw_sim + 0.4 * ft_sim

            # Boost chunks that fall inside the requested date range
            if date_range and chunk.get("timestamp"):
                s, e = date_range
                if s <= chunk["timestamp"] <= e:
                    score += 0.2

            # Boost identity.md for personal queries
            if is_personal and "identity.md" in chunk["file"]:
                score += 0.4

            combined.append((score, chunk))

        combined.sort(key=lambda x: x[0], reverse=True)

        # ── Select top-k within context budget ───────────────────────────────
        selected: List[Dict[str, Any]] = []
        total_chars = 0
        for score, chunk in combined:
            if len(selected) >= self.top_k:
                break
            if total_chars + len(chunk["text"]) > max_context_chars:
                break
            selected.append({"chunk": chunk, "score": score})
            total_chars += len(chunk["text"])

        return {
            "chunks": selected,
            "metadata": {
                "total_candidates": len(candidate_chunks),
                "selected_count": len(selected),
                "total_chars": total_chars,
                "relevant_weeks": [w.get("week") for w in relevant_weeks],
                "keyword_str": keyword_str,
                "rewritten_query": search_text,
            },
        }


