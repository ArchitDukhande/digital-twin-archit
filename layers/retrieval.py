"""
Layer 4: Retrieval (reading the right memories)
Hierarchical retrieval: semantic memory routes to weeks, then pulls raw chunks.
"""
from typing import List, Dict, Any
import numpy as np
from openai import OpenAI


class Retrieval:
    def __init__(self, raw_memory, semantic_memory, client: OpenAI, embed_model: str, top_k: int = 6):
        self.raw_memory = raw_memory
        self.semantic_memory = semantic_memory
        self.client = client
        self.embed_model = embed_model
        self.top_k = top_k

    def _embed_query(self, query: str) -> List[float]:
        """Get embedding for query."""
        try:
            resp = self.client.embeddings.create(model=self.embed_model, input=[query])
            return resp.data[0].embedding
        except Exception:
            return []

    def _embed_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """Get embeddings for chunks (batch)."""
        texts = [c["text"] for c in chunks]
        if not texts:
            return {}
        
        try:
            resp = self.client.embeddings.create(model=self.embed_model, input=texts)
            embeddings = {chunks[i]["id"]: resp.data[i].embedding for i in range(len(chunks))}
            return embeddings
        except Exception:
            return {}

    def retrieve(self, query: str, date_range=None, max_context_chars: int = 3000) -> Dict[str, Any]:
        """
        Hierarchical retrieval:
        1. Use semantic memory to find relevant weeks
        2. Pull raw chunks from those weeks
        3. Score and rank by relevance
        4. Return top-k chunks within context limit
        """
        # Embed query
        q_emb = self._embed_query(query)
        if not q_emb:
            return {"chunks": [], "metadata": {"error": "embedding failed"}}

        # Step 1: Find relevant weeks via semantic memory
        relevant_weeks = self.semantic_memory.find_relevant_weeks(q_emb, top_k=3)
        candidate_chunk_ids = self.semantic_memory.get_chunk_ids_for_weeks(relevant_weeks)

        # Step 2: Get raw chunks
        candidate_chunks = []
        for chunk_id in candidate_chunk_ids:
            chunk = self.raw_memory.get_chunk_by_id(chunk_id)
            if chunk:
                candidate_chunks.append(chunk)

        # Also add chunks from date range if specified
        if date_range:
            start, end = date_range
            time_chunks = self.raw_memory.get_chunks_by_time_range(start, end)
            # Merge with candidates (deduplicate by ID)
            existing_ids = {c["id"] for c in candidate_chunks}
            for tc in time_chunks:
                if tc["id"] not in existing_ids:
                    candidate_chunks.append(tc)

        # If no semantic routing worked, fall back to all chunks
        if not candidate_chunks:
            candidate_chunks = self.raw_memory.get_all_chunks()

        # Always include identity.md for personal info questions
        # Keywords that suggest the question is about personal/profile information
        personal_keywords = ['you', 'your', 'archit', 'location', 'city', 'stay', 'live', 'where', 
                           'email', 'contact', 'phone', 'role', 'team', 'work', 'timezone']
        query_lower = query.lower()
        is_personal_query = any(keyword in query_lower for keyword in personal_keywords)
        if is_personal_query:
            all_chunks = self.raw_memory.get_all_chunks()
            identity_chunks = [c for c in all_chunks if 'identity.md' in c['file']]
            existing_ids = {c["id"] for c in candidate_chunks}
            for ic in identity_chunks:
                if ic["id"] not in existing_ids:
                    candidate_chunks.append(ic)
                    existing_ids.add(ic["id"])

        # Step 3: Score chunks
        chunk_embeddings = self._embed_chunks(candidate_chunks)
        q_emb_np = np.array(q_emb, dtype=float)

        scores = []
        for chunk in candidate_chunks:
            if chunk["id"] not in chunk_embeddings:
                scores.append((0.0, chunk))
                continue

            c_emb_np = np.array(chunk_embeddings[chunk["id"]], dtype=float)
            sim = np.dot(q_emb_np, c_emb_np) / (np.linalg.norm(q_emb_np) * np.linalg.norm(c_emb_np) + 1e-9)
            
            # Boost for different contexts
            boost = 0.0
            
            # Boost identity profile for personal queries
            if is_personal_query and 'identity.md' in chunk['file']:
                boost += 0.5
            
            # Boost if in date range
            if date_range and chunk.get("timestamp"):
                start, end = date_range
                if start <= chunk["timestamp"] <= end:
                    boost += 0.3

            scores.append((sim + boost, chunk))

        # Sort by score
        scores.sort(key=lambda x: x[0], reverse=True)

        # Step 4: Select top-k within context limit
        selected = []
        total_chars = 0
        for score, chunk in scores:
            if len(selected) >= self.top_k:
                break
            if total_chars + len(chunk["text"]) > max_context_chars:
                break
            selected.append({
                "chunk": chunk,
                "score": score,
            })
            total_chars += len(chunk["text"])

        return {
            "chunks": selected,
            "metadata": {
                "total_candidates": len(candidate_chunks),
                "selected_count": len(selected),
                "total_chars": total_chars,
                "relevant_weeks": [w.get("week") for w in relevant_weeks],
            }
        }
