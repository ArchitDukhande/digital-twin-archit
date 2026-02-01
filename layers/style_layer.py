"""
Layer 7: Style Layer (sound like you)
Uses identity.md to guide tone while preserving evidence-based content.
"""
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI


class StyleLayer:
    def __init__(self, client: OpenAI, gen_model: str, identity_file: str = "data/identity.md"):
        self.client = client
        self.gen_model = gen_model
        self.identity_guide = ""
        
        # Load identity.md for style guidance
        try:
            self.identity_guide = Path(identity_file).read_text(encoding="utf-8")
        except Exception:
            self.identity_guide = "You are Archit, a concise and direct communicator."

    def apply_style(self, answer_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply Archit's voice to the answer while preserving factual content.
        Only rephrase if answer is substantive (not a refusal).
        """
        answer = answer_result.get("answer", "")
        answer_lower = answer.lower()
        
        # Don't restyle refusals (both "don't see" and "do not see")
        if "do not see" in answer_lower or "don't see" in answer_lower:
            return answer_result
        
        # Don't restyle quote-only fallback answers
        if answer.startswith("From my data:"):
            return answer_result
        
        # Don't restyle very short answers
        if len(answer) < 10:
            return answer_result

        # Extract Sources line to preserve it
        sources_line = ""
        answer_body = answer
        if "Sources:" in answer:
            parts = answer.rsplit("Sources:", 1)
            answer_body = parts[0].strip()
            sources_line = "Sources:" + parts[1]

        # Style rules emphasizing first-person
        style_summary = (
            "Style rules:\n"
            "- Use 'I' for individual actions and observations.\n"
            "- Use 'we' only when the evidence clearly shows a shared decision or agreement.\n"
            "- Keep it concise, direct, work-focused.\n"
            "- No buzzwords, no hype, no em dash.\n"
            "- Preserve all facts, numbers, and technical details exactly.\n"
            "- Do not add any information not in the original.\n"
        )

        restyle_prompt = (
            f"{style_summary}\n\n"
            "Rewrite the answer below in Archit's voice.\n"
            "Preserve all factual meaning and numbers exactly.\n\n"
            f"Original answer:\n{answer_body}\n\n"
            "Rewritten answer:"
        )

        try:
            resp = self.client.responses.create(
                model=self.gen_model,
                input=restyle_prompt,
                temperature=0.0,
                max_output_tokens=120,
            )
            styled_answer = getattr(resp, "output_text", answer_body)
        except Exception:
            styled_answer = answer_body

        styled_answer = styled_answer.strip()
        if not styled_answer:
            styled_answer = answer_body
        
        # Re-attach Sources line
        if sources_line:
            styled_answer = styled_answer + "\n\n" + sources_line

        # Update answer in result
        answer_result["answer"] = styled_answer
        return answer_result
