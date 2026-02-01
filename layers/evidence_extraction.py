"""
Layer 5: Evidence Extraction
Identifies exact supporting snippets from retrieved chunks.
Provides receipts with chunk IDs and timestamps.
"""
from typing import List, Dict, Any
from openai import OpenAI
import json


class EvidenceExtraction:
    def __init__(self, client: OpenAI, gen_model: str):
        self.client = client
        self.gen_model = gen_model

    def extract(self, question: str, retrieved_chunks: List[Dict[str, Any]], answer_mode: str = "FACT_MODE") -> Dict[str, Any]:
        """
        Extract supporting evidence from retrieved chunks.
        Returns evidence snippets with citations.
        """
        if not retrieved_chunks:
            return {
                "evidence": [],
                "has_evidence": False,
            }

        # Build context from chunks
        context_parts = []
        for i, item in enumerate(retrieved_chunks):
            chunk = item["chunk"]
            context_parts.append(f"[CHUNK {i}] (ID: {chunk['id']}, File: {chunk['file']})\n{chunk['text']}")

        context = "\n\n---\n\n".join(context_parts)

        # Ask AI to extract supporting evidence - request up to 6 items
        extraction_prompt = (
            f"Given the question and context below, identify EXACT sentences or phrases from the context "
            f"that support an answer to the question. Extract up to 6 relevant evidence items. "
            f"Output ONLY valid JSON in this format:\n"
            f'{{"evidence":[{{"chunk_index":0,"quote":"exact text from chunk"}}]}}\n\n'
            f"If no evidence exists, output: {{\"evidence\":[]}}\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{context}\n\n"
            f"Output JSON only:"
        )

        try:
            resp = self.client.responses.create(
                model=self.gen_model,
                input=extraction_prompt,
                temperature=0.0,
            )
            extraction_text = getattr(resp, "output_text", '{"evidence":[]}')
        except Exception:
            extraction_text = '{"evidence":[]}'

        # Parse JSON strictly - no fallback
        evidence_items = []
        raw_extraction = extraction_text
        
        # Set minimum quote length based on mode
        min_quote_length = 5 if answer_mode == "SUMMARY_MODE" else 8
        
        try:
            data = json.loads(extraction_text.strip())
            for item in data.get("evidence", []):
                chunk_idx = item.get("chunk_index")
                quote = item.get("quote", "").strip()
                
                # Validate chunk index
                if chunk_idx is None or chunk_idx < 0 or chunk_idx >= len(retrieved_chunks):
                    continue
                
                # Validate quote length (flexible in summary mode)
                if len(quote) < min_quote_length:
                    continue
                
                # Validate quote appears verbatim in chunk (with whitespace normalization)
                chunk = retrieved_chunks[chunk_idx]["chunk"]
                chunk_text_normalized = ' '.join(chunk["text"].split())
                quote_normalized = ' '.join(quote.split())
                
                if quote_normalized not in chunk_text_normalized:
                    continue
                
                # Valid evidence
                evidence_items.append({
                    "quote": quote,
                    "chunk_id": chunk["id"],
                    "file": chunk["file"],
                    "timestamp": chunk.get("timestamp"),
                })
        except (json.JSONDecodeError, KeyError, TypeError):
            # JSON parsing failed - treat as no evidence
            pass

        return {
            "evidence": evidence_items,
            "has_evidence": len(evidence_items) > 0,
            "raw_extraction": raw_extraction,
        }
