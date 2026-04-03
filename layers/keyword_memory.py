"""
Layer 2: Keyword Memory
Every message is indexed with extracted keywords.
Weeks aggregate those keywords for coarse routing only — no LLM summaries.

Index structure (cached to .cache/keyword_index.json):
  chunk_keywords : { chunk_id -> {keywords: [...], embedding: [...]} }
  weeks          : { week_key -> {keywords: [...], embedding: [...], chunk_ids: [...]} }

Week-level embeddings are used only for routing (not scoring).
Per-message keyword embeddings drive the actual ranking.
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import OpenAI
import numpy as np


class KeywordMemory:
    def __init__(self, raw_memory, client: OpenAI, embed_model: str, gen_model: str):
        self.raw_memory = raw_memory
        self.client = client
        self.embed_model = embed_model
        self.gen_model = gen_model

        self.cache_path = Path(".cache")
        self.cache_path.mkdir(exist_ok=True)
        self.index_file = self.cache_path / "keyword_index.json"

        # week_key -> {keywords, embedding, chunk_ids}
        self.weeks: Dict[str, Dict[str, Any]] = {}
        # chunk_id -> {keywords, embedding}
        self.chunk_keywords: Dict[str, Dict[str, Any]] = {}

        self._load_or_build()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_or_build(self) -> None:
        """Load cached index or build from scratch."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.weeks = data.get("weeks", {})
                self.chunk_keywords = data.get("chunk_keywords", {})
                print(f"  Keyword index loaded: {len(self.chunk_keywords)} chunks, {len(self.weeks)} weeks")
                return
            except Exception:
                pass

        print("  Building keyword index (first run)...")
        self._build_index()
        self._save_index()
        print(f"  Keyword index built: {len(self.chunk_keywords)} chunks, {len(self.weeks)} weeks")

    def _save_index(self) -> None:
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(
                {"weeks": self.weeks, "chunk_keywords": self.chunk_keywords},
                f, indent=2, ensure_ascii=False,
            )

    # ── Keyword extraction ────────────────────────────────────────────────────

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract 5-8 specific keywords from text using LLM.
        Only concrete terms that appear in the text — never invented.
        Falls back to frequency-based extraction on any failure.
        """
        prompt = (
            "Extract 5 to 8 specific keywords or key phrases from the text below.\n"
            "Rules:\n"
            "- Return ONLY a JSON array of strings, nothing else.\n"
            "- Focus on nouns, technical terms, and named entities present in the text.\n"
            "- Do NOT invent terms absent from the text.\n"
            "- Lowercase all keywords.\n\n"
            f"Text:\n{text[:800]}\n\n"
            "JSON array:"
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.gen_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            content = resp.choices[0].message.content.strip()
            arr_match = re.search(r'\[.*?\]', content, re.DOTALL)
            if arr_match:
                keywords = json.loads(arr_match.group(0))
                return [str(k).lower().strip() for k in keywords if isinstance(k, str) and k.strip()]
        except Exception:
            pass
        return self._fallback_keywords(text)

    def _fallback_keywords(self, text: str) -> List[str]:
        """Top-8 non-stopword words by frequency."""
        stop_words = {
            "the", "a", "an", "is", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "shall", "can",
            "i", "we", "you", "he", "she", "it", "they",
            "my", "our", "your", "his", "her", "its", "their",
            "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "up", "about", "into",
            "this", "that", "so", "then", "if", "not", "just",
        }
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        freq: Dict[str, int] = {}
        for w in words:
            if w not in stop_words:
                freq[w] = freq.get(w, 0) + 1
        return [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:8]]

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[List[float]]:
        """Embed a keyword string. Returns None on failure."""
        if not text.strip():
            return None
        try:
            resp = self.client.embeddings.create(model=self.embed_model, input=[text])
            return resp.data[0].embedding
        except Exception:
            return None

    # ── Index build ───────────────────────────────────────────────────────────

    def _build_index(self) -> None:
        """
        Build keyword index for every chunk, then aggregate per week.
        Each chunk gets keywords + a keyword embedding.
        Each week gets the union of its chunks' keywords + a week-level embedding.
        """
        weekly_chunks: Dict[str, List[str]] = {}  # week_key -> [chunk_id, ...]

        for chunk in self.raw_memory.get_all_chunks():
            chunk_id = chunk["id"]
            keywords = self._extract_keywords(chunk["text"])
            keyword_str = " ".join(keywords)
            embedding = self._embed(keyword_str)

            self.chunk_keywords[chunk_id] = {
                "keywords": keywords,
                "embedding": embedding,
            }

            if chunk.get("timestamp"):
                week_key = chunk["timestamp"].strftime("%Y-W%U")
                weekly_chunks.setdefault(week_key, []).append(chunk_id)

        # Aggregate keywords per week (deduped, preserving insertion order)
        for week_key, chunk_ids in weekly_chunks.items():
            seen: set = set()
            week_keywords: List[str] = []
            for cid in chunk_ids:
                for kw in self.chunk_keywords.get(cid, {}).get("keywords", []):
                    if kw not in seen:
                        seen.add(kw)
                        week_keywords.append(kw)

            week_str = " ".join(week_keywords)
            self.weeks[week_key] = {
                "keywords": week_keywords,
                "embedding": self._embed(week_str),
                "chunk_ids": chunk_ids,
            }

    # ── Public routing API ────────────────────────────────────────────────────

    def find_relevant_weeks(
        self, query_embedding: List[float], top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Return top-k weeks ranked by cosine similarity between
        the query embedding and the week keyword embedding.
        Weeks are routing only — they narrow the candidate pool.
        """
        if not self.weeks:
            return []

        q_emb = np.array(query_embedding, dtype=float)
        scores = []
        for week_key, week_data in self.weeks.items():
            emb = week_data.get("embedding")
            if emb:
                w_emb = np.array(emb, dtype=float)
                sim = float(
                    np.dot(q_emb, w_emb)
                    / (np.linalg.norm(q_emb) * np.linalg.norm(w_emb) + 1e-9)
                )
            else:
                sim = 0.0
            scores.append((sim, week_key))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [
            {"week": wk, "chunk_ids": self.weeks[wk]["chunk_ids"]}
            for _, wk in scores[:top_k]
        ]

    def get_chunk_ids_for_weeks(self, weeks: List[Dict[str, Any]]) -> List[str]:
        """Get all chunk IDs from selected weeks."""
        chunk_ids: List[str] = []
        for week in weeks:
            chunk_ids.extend(week.get("chunk_ids", []))
        return chunk_ids

    def score_chunks_by_keywords(
        self, chunk_ids: List[str], query_embedding: List[float]
    ) -> List[tuple]:
        """
        Score chunks by cosine similarity of their keyword embedding to the query.
        Returns list of (score, chunk_id) sorted descending.
        Used by Retrieval for Level-2 per-message ranking.
        """
        q_emb = np.array(query_embedding, dtype=float)
        scores = []
        for cid in chunk_ids:
            ck = self.chunk_keywords.get(cid, {})
            emb = ck.get("embedding")
            if emb:
                c_emb = np.array(emb, dtype=float)
                sim = float(
                    np.dot(q_emb, c_emb)
                    / (np.linalg.norm(q_emb) * np.linalg.norm(c_emb) + 1e-9)
                )
            else:
                sim = 0.0
            scores.append((sim, cid))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores
