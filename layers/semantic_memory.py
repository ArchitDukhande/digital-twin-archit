"""
Layer 2: Semantic Memory (human-like remembering)
Generates weekly summaries and semantic clusters to speed up recall.
This layer is lossy on purpose - it routes retrieval to the right area.
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta
from openai import OpenAI
import numpy as np


class SemanticMemory:
    def __init__(self, raw_memory, client: OpenAI, embed_model: str, gen_model: str):
        self.raw_memory = raw_memory
        self.client = client
        self.embed_model = embed_model
        self.gen_model = gen_model
        self.cache_path = Path(".cache")
        self.cache_path.mkdir(exist_ok=True)
        self.summaries_file = self.cache_path / "semantic_summaries.json"
        self.summaries: List[Dict[str, Any]] = []
        self._load_or_generate()

    def _load_or_generate(self) -> None:
        """Load cached summaries or generate new ones."""
        if self.summaries_file.exists():
            try:
                with open(self.summaries_file, "r", encoding="utf-8") as f:
                    self.summaries = json.load(f)
                return
            except Exception:
                pass

        # Generate weekly summaries
        self._generate_weekly_summaries()
        self._save_summaries()

    def _save_summaries(self) -> None:
        """Persist summaries to disk."""
        with open(self.summaries_file, "w", encoding="utf-8") as f:
            json.dump(self.summaries, f, indent=2, ensure_ascii=False)

    def _generate_weekly_summaries(self) -> None:
        """Group raw chunks by week and generate AI summaries."""
        # Group chunks by week
        weekly_groups: Dict[str, List[Dict[str, Any]]] = {}

        for chunk in self.raw_memory.get_all_chunks():
            if chunk.get("timestamp"):
                # Get week key (ISO week)
                week_key = chunk["timestamp"].strftime("%Y-W%U")
                if week_key not in weekly_groups:
                    weekly_groups[week_key] = []
                weekly_groups[week_key].append(chunk)

        # Generate summary for each week
        for week_key, chunks in weekly_groups.items():
            if not chunks:
                continue

            # Concatenate texts
            combined = "\n\n---\n\n".join([c["text"] for c in chunks[:20]])  # limit to first 20
            
            # Ask AI to summarize
            summary_prompt = (
                f"Summarize the following week's messages and activities in 2-3 concise sentences. "
                f"Focus on topics, decisions, and key work mentioned. Do not invent details.\n\n{combined[:3000]}"
            )

            try:
                resp = self.client.responses.create(
                    model=self.gen_model,
                    input=summary_prompt,
                    temperature=0.3,
                )
                summary_text = getattr(resp, "output_text", "No summary available")
            except Exception:
                summary_text = "Summary generation failed"

            # Embed the summary for routing
            try:
                emb_resp = self.client.embeddings.create(
                    model=self.embed_model,
                    input=[summary_text]
                )
                embedding = emb_resp.data[0].embedding
            except Exception:
                embedding = None

            self.summaries.append({
                "week": week_key,
                "summary": summary_text,
                "chunk_ids": [c["id"] for c in chunks],
                "start_date": min(c["timestamp"] for c in chunks if c.get("timestamp")).isoformat() if any(c.get("timestamp") for c in chunks) else None,
                "end_date": max(c["timestamp"] for c in chunks if c.get("timestamp")).isoformat() if any(c.get("timestamp") for c in chunks) else None,
                "embedding": embedding,
            })

    def find_relevant_weeks(self, query_embedding: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        """Find most relevant weeks based on semantic similarity."""
        if not self.summaries:
            return []

        scores = []
        q_emb = np.array(query_embedding, dtype=float)

        for summary in self.summaries:
            if summary.get("embedding"):
                s_emb = np.array(summary["embedding"], dtype=float)
                sim = np.dot(q_emb, s_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(s_emb) + 1e-9)
                scores.append((sim, summary))
            else:
                scores.append((0.0, summary))

        # Sort by similarity
        scores.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scores[:top_k]]

    def get_chunk_ids_for_weeks(self, weeks: List[Dict[str, Any]]) -> List[str]:
        """Get all chunk IDs from selected weeks."""
        chunk_ids = []
        for week in weeks:
            chunk_ids.extend(week.get("chunk_ids", []))
        return chunk_ids
