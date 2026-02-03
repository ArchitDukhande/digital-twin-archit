"""
Layer 6: Verifier / Refusal Gate (anti-hallucination)
Enforces honesty. No evidence = no answer.
This is the main defense against hallucinations.
"""
import re
import json
from typing import Dict, Any, List
from openai import OpenAI


class VerifierGate:
    def __init__(self, client: OpenAI, gen_model: str):
        self.client = client
        self.gen_model = gen_model
        
        # Sensitive patterns to block (specific patterns only)
        self.sensitive_patterns = [
            r'sk-[A-Za-z0-9]{20,}',  # OpenAI keys
            r'AKIA[0-9A-Z]{16}',  # AWS access keys
            r'password[:\s]*[^\s]+',  # Password fields
            r'api[_-]?key[:\s]*[^\s]+',  # API key fields
            r'secret[:\s]*[^\s]+',  # Secret fields
            r'token[:\s]*[^\s]+',  # Token fields
        ]
    
    def _contains_sensitive_info(self, text: str, source_file: str = "") -> bool:
        """
        Check if text contains sensitive information.
        Contact info from identity.md is allowed since it's the user's public profile.
        """
        if not text:
            return False
        
        # Allow all content from identity.md - it's the user's intended public profile
        if 'identity.md' in source_file:
            return False
            
        text_lower = text.lower()
        for pattern in self.sensitive_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        # Additional keyword checks - expanded to catch variations
        sensitive_keywords = [
            'password', 'passwd', 'pwd',
            'api_key', 'api key', 'apikey',
            'secret', 'token', 
            'credential', 'credentials', 'creds', 'cred',
            'aws access', 'aws secret', 'aws key',
            'account id', 'account number',
            'private key', 'ssh key'
        ]
        return any(keyword in text_lower for keyword in sensitive_keywords)

    def _entailment_state(self, question: str, evidence_quotes: List[str]) -> str:
        """
        Check if evidence semantically supports answering the question.
        Returns "yes", "no", or "unknown".
        
        "yes" = evidence supports the question
        "no" = evidence explicitly does NOT support the question  
        "unknown" = cannot determine (parsing failed, uncertain)
        """
        if not evidence_quotes:
            return "no"
        
        evidence_text = "\n".join([f"- {q}" for q in evidence_quotes])
        
        entailment_prompt = (
            f"Does the evidence below semantically support answering this question? "
            f"Return ONLY JSON: {{\"state\": \"yes\", \"reason\": \"...\"}} or {{\"state\": \"no\", \"reason\": \"...\"}} "
            f"or {{\"state\": \"unknown\", \"reason\": \"...\"}}.\\n\\n"
            f"Question: {question}\\n\\n"
            f"Evidence:\\n{evidence_text}\\n\\n"
            f"IMPORTANT: Return 'no' if the evidence is about something different than what the question asks. "
            f"For example, if the question asks about 'customer complaints' but evidence only mentions "
            f"'internal errors' or 'invoke failures', return 'no'. "
            f"Return 'unknown' only if you genuinely cannot determine.\\n\\n"
            f"JSON:"
        )

        
        try:
            resp = self.client.chat.completions.create(
                model=self.gen_model,
                messages=[{"role": "user", "content": entailment_prompt}],
                temperature=0.0,
                max_tokens=150,
            )
            entailment_text = resp.choices[0].message.content.strip()
        except Exception:
            # LLM call failed - return unknown (fail open)
            return "unknown"
        
        # Parse JSON response with improved multiline handling
        try:
            # Try to extract JSON with DOTALL for multiline responses
            json_match = re.search(r'\{[^{}]*"state"\s*:\s*"(yes|no|unknown)"[^{}]*\}', entailment_text, re.DOTALL | re.IGNORECASE)
            if not json_match:
                # Fallback: try simpler pattern
                json_match = re.search(r'\{.+?\}', entailment_text, re.DOTALL)
            
            if not json_match:
                return "unknown"
            
            json_text = json_match.group(0)
            data = json.loads(json_text)
            state = data.get("state", "unknown").lower()
            
            if state in ["yes", "no", "unknown"]:
                return state
            else:
                return "unknown"
                
        except Exception:
            # Parsing failed - return unknown (fail open)
            return "unknown"


    def generate_answer(self, question: str, evidence: Dict[str, Any], retrieved_chunks: list, answer_mode: str = "FACT_MODE") -> Dict[str, Any]:
        """
        Generate answer only if evidence supports it.
        Behavior depends on answer_mode and entailment state.
        """
        # CRITICAL: Block questions asking for sensitive information
        if self._contains_sensitive_info(question):
            return {
                "answer": "I cannot share sensitive information like credentials, passwords, or API keys.",
                "confidence": "none",
                "reasoning": "Question blocked due to requesting sensitive information.",
                "citations": [],
            }
        
        if not evidence.get("has_evidence") or len(evidence.get("evidence", [])) == 0:
            return {
                "answer": "I do not see this in your data.",
                "confidence": "none",
                "reasoning": "No supporting evidence found in the data.",
                "citations": [],
            }

        if answer_mode == "SUMMARY_MODE":
            # Summary mode: allow 1+ chunks, no strict entailment check
            # Asking "what happened", not verifying specific claims
            unique_chunks = set(ev["chunk_id"] for ev in evidence["evidence"])
            if len(unique_chunks) == 0:
                return {
                    "answer": "I do not see this in your data.",
                    "confidence": "none",
                    "reasoning": "No evidence found for summary.",
                    "citations": [],
                }
            # Proceed to answer generation (no entailment check needed for summaries)
            entailment = "yes"  # Set for downstream logic
            summary_confidence_boost = "high" if len(unique_chunks) >= 2 else "medium"
        else:
            # FACT_MODE: Run strict entailment check
            evidence_quotes = [ev["quote"] for ev in evidence["evidence"]]
            entailment = self._entailment_state(question, evidence_quotes)
            
            if entailment == "no":
                # Evidence explicitly does NOT support the question
                return {
                    "answer": "I do not see this in your data.",
                    "confidence": "none",
                    "reasoning": "Evidence does not support the question.",
                    "citations": [],
                }
            
            if entailment == "unknown":
                # Entailment unclear - use QUOTE-ONLY fallback (no paraphrasing)
                # Get up to 3 quotes from distinct chunks
                seen_chunks = set()
                quote_lines = []
                for ev in evidence["evidence"]:
                    if ev["chunk_id"] not in seen_chunks and len(quote_lines) < 3:
                        quote_lines.append(f"- {ev['quote']}")
                        seen_chunks.add(ev["chunk_id"])
                
                if quote_lines:
                    answer_text = "From my data:\n" + "\n".join(quote_lines)
                    # Build citations for quote-only answer
                    citations = []
                    for ev in evidence["evidence"]:
                        if ev["chunk_id"] in seen_chunks:
                            citations.append({
                                "text": ev["quote"],
                                "source": ev["file"],
                                "chunk_id": ev["chunk_id"],
                                "timestamp": ev.get("timestamp"),
                            })
                    return {
                        "answer": answer_text,
                        "confidence": "medium",
                        "reasoning": "Entailment unclear, returning quote-only answer.",
                        "citations": citations,
                    }
                else:
                    # No valid quotes - refuse
                    return {
                        "answer": "I do not see this in your data.",
                        "confidence": "none",
                        "reasoning": "Cannot verify if evidence supports the question.",
                        "citations": [],
                    }
            
            # entailment == "yes" - proceed normally
            summary_confidence_boost = None


        # Build evidence summary with chunk IDs
        evidence_summary = "\n".join([
            f"- {ev['quote']} (from {ev['chunk_id']})"
            for ev in evidence["evidence"]
        ])
        
        # Generate answer - adjust prompt based on mode
        if answer_mode == "SUMMARY_MODE":
            answer_prompt = (
                f"You are Archit answering questions about your work. "
                f"“Use ‘I’ for individual actions and observations. Use ‘we’ only when the evidence clearly shows a shared decision or agreement."
                f"Provide a brief summary based ONLY on the evidence below. "
                f"Each point must come from the evidence. Do NOT invent facts. Do NOT claim customer complaints unless explicitly mentioned. "
                f"Write short, clear, work-focused. No em dash. No tech jargon. "
                f"At the end, add: Sources: <chunk_ids>\n\n"
                f"Question: {question}\n\n"
                f"Evidence:\n{evidence_summary}\n\n"
                f"Answer:"
            )
        else:
            # FACT_MODE
            answer_prompt = (
                f"You are Archit answering a specific question. Use ONLY the evidence below. "
                f"“Use ‘I’ for individual actions and observations. Use ‘we’ only when the evidence clearly shows a shared decision or agreement."
                f"Do NOT invent facts. Do NOT infer beyond what is stated. "
                f"Write short, clear, work-focused. No em dash. No tech jargon. "
                f"At the end, add: Sources: <chunk_ids>\n\n"
                f"Question: {question}\n\n"
                f"Evidence:\n{evidence_summary}\n\n"
                f"Answer:"
            )


        try:
            resp = self.client.responses.create(
                model=self.gen_model,
                input=answer_prompt,
                temperature=0.0,
            )
            answer_text = getattr(resp, "output_text", "I do not see this in your data.")
        except Exception:
            answer_text = "I do not see this in your data."

        answer_text = answer_text.strip()
        if not answer_text or answer_text == "":
            answer_text = "I do not see this in your data."

        # CRITICAL: Check for sensitive information leakage
        # Get source files from evidence to allow identity.md content
        evidence_sources = [ev.get("file", "") for ev in evidence.get("evidence", [])]
        is_from_identity = any('identity.md' in src for src in evidence_sources)
        if not is_from_identity and self._contains_sensitive_info(answer_text):
            return {
                "answer": "I cannot share that because it contains sensitive information.",
                "confidence": "none",
                "reasoning": "Answer blocked due to sensitive information detection.",
                "citations": [],
            }

        # Check if answer is a refusal
        is_refusal = "do not see" in answer_text.lower()

        # Build citations - only include if quote is non-empty and meaningful
        citations = []
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        for ev in evidence["evidence"]:
            quote_text = ev.get("quote", "").strip()
            source_file = ev.get("file", "")
            
            # Filter out empty, placeholder, or very short quotes
            # Check: not empty, not placeholder, longer than 5 chars, not just underscores/dots
            is_valid = (
                quote_text 
                and len(quote_text) > 5
                and quote_text not in ("__", "___", "...", "----", "N/A", "n/a")
                and not quote_text.replace("_", "").replace(".", "").replace("-", "").strip() == ""
            )
            if is_valid:
                # Redact emails unless from identity.md
                if 'identity.md' not in source_file:
                    quote_text = re.sub(email_pattern, '[redacted]', quote_text)
                
                # Skip citations containing sensitive info (except from identity.md)
                if not self._contains_sensitive_info(quote_text, source_file):
                    citations.append({
                        "text": quote_text,
                        "source": source_file,
                        "chunk_id": ev["chunk_id"],
                        "timestamp": ev.get("timestamp"),
                    })

        # Assess confidence based on citations and mode
        if is_refusal:
            confidence = "none"
        elif 'summary_confidence_boost' in locals() and summary_confidence_boost:
            # SUMMARY_MODE: use boost based on unique chunks
            confidence = summary_confidence_boost
        elif len(citations) >= 2:
            confidence = "high"
        else:
            confidence = "medium"

        return {
            "answer": answer_text,
            "confidence": confidence,
            "reasoning": f"Based on {len(citations)} valid citation(s) from retrieved context.",
            "citations": citations,
        }
