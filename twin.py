"""
Digital Twin - Orchestrator
Connects all 7 layers into a cohesive system.
"""
import os
import re
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

from layers.raw_memory import RawMemory
from layers.semantic_memory import SemanticMemory
from layers.query_understanding import QueryUnderstanding
from layers.retrieval import Retrieval
from layers.evidence_extraction import EvidenceExtraction
from layers.verifier_gate import VerifierGate
from layers.style_layer import StyleLayer


class DigitalTwin:
    def __init__(self, data_dir: str = "data"):
        load_dotenv()

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing. Set it in your environment or .env file.")

        self.embed_model = os.getenv("TWIN_EMBED_MODEL", "text-embedding-3-small")
        self.gen_model = os.getenv("TWIN_GEN_MODEL", "gpt-4o-mini")
        self.top_k = int(os.getenv("TWIN_TOP_K", "6"))
        self.max_context_chars = int(os.getenv("TWIN_MAX_CONTEXT_CHARS", "3000"))

        self.client = OpenAI(api_key=api_key)

        # Initialize all layers
        print("Initializing Layer 1: Raw Memory...")
        self.raw_memory = RawMemory(data_dir)

        print("Initializing Layer 2: Semantic Memory...")
        self.semantic_memory = SemanticMemory(
            self.raw_memory,
            self.client,
            self.embed_model,
            self.gen_model
        )

        print("Initializing Layer 3: Query Understanding...")
        self.query_understanding = QueryUnderstanding(default_year=2025)

        print("Initializing Layer 4: Retrieval...")
        self.retrieval = Retrieval(
            self.raw_memory,
            self.semantic_memory,
            self.client,
            self.embed_model,
            self.top_k
        )

        print("Initializing Layer 5: Evidence Extraction...")
        self.evidence_extraction = EvidenceExtraction(self.client, self.gen_model)

        print("Initializing Layer 6: Verifier Gate...")
        self.verifier_gate = VerifierGate(self.client, self.gen_model)

        print("Initializing Layer 7: Style Layer...")
        self.style_layer = StyleLayer(self.client, self.gen_model)

        print("✓ Digital Twin initialized successfully")

    def _classify_mode_llm(self, question: str) -> str:
        """
        Use LLM to classify question as SUMMARY_MODE or FACT_MODE.
        Provides keyword hints to guide classification.
        
        Returns: "SUMMARY_MODE" or "FACT_MODE"
        """
        # Keyword hints for LLM reference (not hardcoded rules)
        summary_keywords = [
            "summarize", "summary", "overview", "what happened", 
            "what was i working on", "what did i do", "recap", "journey",
            "highlights", "main activities", "key events"
        ]
        
        fact_keywords = [
            "how long", "how many", "why did", "when did", 
            "who is", "where is", "what is my", "specific", 
            "exactly", "credential", "email", "password"
        ]
        
        classify_prompt = (
            "Classify this question as 'summary' or 'fact'.\n\n"
            "SUMMARY: Broad questions about what happened, activities over time, main themes.\n"
            f"Common summary keywords: {', '.join(summary_keywords)}\n\n"
            "FACT: Specific questions with a concrete answer.\n"
            f"Common fact keywords: {', '.join(fact_keywords)}\n\n"
            "Use these keywords as hints, but classify based on the overall intent.\n"
            "Return ONLY one word: summary OR fact\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )
        
        try:
            resp = self.client.chat.completions.create(
                model=self.gen_model,
                messages=[{"role": "user", "content": classify_prompt}],
                temperature=0.0,
                max_tokens=10,
            )
            result = resp.choices[0].message.content.strip().lower()
            
            # Parse response
            if "summary" in result:
                return "SUMMARY_MODE"
            elif "fact" in result:
                return "FACT_MODE"
            else:
                # Default to FACT_MODE (stricter) if unclear
                return "FACT_MODE"
        except Exception:
            # On failure, default to FACT_MODE (stricter)
            return "FACT_MODE"

    def _determine_answer_mode(self, question: str, date_range) -> str:
        """
        Determine answer mode using LLM classification with keyword hints.
        
        The LLM always decides, but we provide keyword hints for guidance.
        No hardcoded rules - LLM interprets intent.
        
        Returns: "SUMMARY_MODE" or "FACT_MODE"
        """
        # Always use LLM to classify - it has keyword hints for reference
        return self._classify_mode_llm(question)

    def answer(self, question: str, debug: bool = False) -> Dict[str, Any]:
        """
        Process a question through all layers and return grounded answer.
        
        Returns:
            {
                "answer": str,
                "confidence": str,
                "citations": list,
                "reasoning": str,
                "debug": dict (if debug=True)
            }
        """

        # --- UI-level intents (greetings / help) ---
        q = question.strip().lower()
        q = re.sub(r"[^\w\s]", " ", q)
        q = " ".join(q.split())   

        greetings = {"hi", "hello", "hey"}
        help_intents = {
            "help",
            "what can you do",
            "how do you work",
            "examples",
            "example questions"
        }

        if q in greetings:
            return {
                "answer": (
                    "Hi. You can ask me about my work, decisions, and messages. "
                    "For example: What happened in late December around inference?"
                ),
                "confidence": "none",
                "reasoning": "Greeting handled as a UI intent without using memory.",
                "citations": [],
            }

        if q in help_intents:
            return {
                "answer": (
                    "I answer questions about my work using only the data you provided. "
                    "If I cannot find evidence, I will refuse. "
                    "Try asking: What was I working on in Q4 2025?"
                ),
                "confidence": "none",
                "reasoning": "Help intent handled as a UI intent without using memory.",
                "citations": [],
            }


        # Layer 3: Parse query
        parsed_query = self.query_understanding.parse(question)
        date_range = parsed_query.get("date_range")

        # Determine answer mode using HYBRID approach (rules + LLM)
        answer_mode = self._determine_answer_mode(question, date_range)

        # Layer 4: Retrieve relevant chunks (ALWAYS use date_range)
        retrieval_result = self.retrieval.retrieve(
            question,
            date_range=date_range,
            max_context_chars=self.max_context_chars
        )

        retrieved_chunks = retrieval_result["chunks"]

        # Layer 5: Extract evidence
        evidence = self.evidence_extraction.extract(question, retrieved_chunks, answer_mode)

        # Layer 6: Generate answer with verification
        answer_result = self.verifier_gate.generate_answer(
            question,
            evidence,
            retrieved_chunks,
            answer_mode
        )

        # Layer 7: Apply style
        final_result = self.style_layer.apply_style(answer_result)

        # Add debug info if requested
        if debug:
            final_result["debug"] = {
                "answer_mode": answer_mode,  # SUMMARY_MODE or FACT_MODE
                "parsed_query": parsed_query,
                "retrieval_metadata": retrieval_result["metadata"],
                "retrieved_chunks": [
                    {
                        "id": item["chunk"]["id"],
                        "file": item["chunk"]["file"],
                        "score": item["score"],
                        "text_preview": item["chunk"]["text"][:200] + "...",
                    }
                    for item in retrieved_chunks
                ],
                "evidence": evidence,
            }

        return final_result
