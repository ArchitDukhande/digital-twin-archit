"""
Layer 3: Query Understanding (intent + time)
Translates vague human language into concrete search constraints.
The LLM rewrites the query into search keywords — strictly from the
question itself, no hallucination of external facts.
"""
import re
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any


class QueryUnderstanding:
    def __init__(self, default_year: int = 2025, client=None, gen_model: str = "gpt-4o-mini"):
        self.default_year = default_year
        self.client = client
        self.gen_model = gen_model
        self.month_map = {m.lower(): i + 1 for i, m in enumerate((
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
        ))}
        # Holiday date mappings
        self.holidays = {
            "christmas": (12, 25),
            "new year": (1, 1),
            "thanksgiving": (11, 25),  # Approximate
        }

    def parse_date_range(self, query: str) -> Optional[Tuple[datetime, datetime]]:
        """Parse date/time constraints from query."""
        q = query.lower()

        # Holiday patterns (e.g., "Christmas", "around Christmas")
        for holiday, (month, day) in self.holidays.items():
            if holiday in q:
                # Use a 3-day window around the holiday
                year = self.default_year
                # Adjust year for New Year if we're in late December context
                if holiday == "new year" and "2026" in q:
                    year = 2026
                elif holiday == "christmas" and month == 12:
                    # Christmas 2025
                    year = 2025
                
                center = datetime(year, month, day)
                start = center - timedelta(days=1)
                end = center + timedelta(days=1, hours=23, minutes=59, seconds=59)
                return (start, end)

        # Early/mid/late month patterns
        m = re.search(r"(early|mid|late)\s+([a-z]+)\s*(\d{4})?", q)
        if m:
            when, mon, yr = m.groups()
            mon_l = mon.lower()
            if mon_l[:3] in [k[:3] for k in self.month_map.keys()]:
                # Find full month name
                full_month = next((k for k in self.month_map.keys() if k.startswith(mon_l[:3])), None)
                if full_month:
                    year = int(yr) if yr else self.default_year
                    mon_idx = self.month_map[full_month]
                    
                    if when == "early":
                        start = datetime(year, mon_idx, 1)
                        end = datetime(year, mon_idx, 10, 23, 59, 59)
                    elif when == "mid":
                        start = datetime(year, mon_idx, 10)
                        end = datetime(year, mon_idx, 20, 23, 59, 59)
                    else:  # late
                        start = datetime(year, mon_idx, 20)
                        # End of month
                        if mon_idx == 12:
                            end = datetime(year, 12, 31, 23, 59, 59)
                        else:
                            end = datetime(year, mon_idx + 1, 1) - timedelta(seconds=1)
                    
                    return (start, end)

        # Quarter patterns (Q1, Q2, Q3, Q4)
        m_q = re.search(r"q([1-4])\s*(\d{4})?", q)
        if m_q:
            quarter, yr = m_q.groups()
            year = int(yr) if yr else self.default_year
            q_num = int(quarter)
            start_month = (q_num - 1) * 3 + 1
            start = datetime(year, start_month, 1)
            end_month = start_month + 2
            if end_month == 12:
                end = datetime(year, 12, 31, 23, 59, 59)
            else:
                end = datetime(year, end_month + 1, 1) - timedelta(seconds=1)
            return (start, end)

        # Full month patterns (e.g., "December 2025")
        m2 = re.search(r"([a-z]+)\s+(\d{4})", q)
        if m2:
            mon, yr = m2.groups()
            mon_l = mon.lower()
            if mon_l[:3] in [k[:3] for k in self.month_map.keys()]:
                full_month = next((k for k in self.month_map.keys() if k.startswith(mon_l[:3])), None)
                if full_month:
                    year = int(yr)
                    mon_idx = self.month_map[full_month]
                    start = datetime(year, mon_idx, 1)
                    if mon_idx == 12:
                        end = datetime(year, 12, 31, 23, 59, 59)
                    else:
                        end = datetime(year, mon_idx + 1, 1) - timedelta(seconds=1)
                    return (start, end)

        return None

    def extract_topics(self, query: str) -> List[str]:
        """Extract key topics/keywords from query (simple fallback)."""
        stop_words = {"what", "when", "where", "who", "how", "why", "was", "were", "did", "do", "does",
                      "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "i", "you",
                      "my", "your", "late", "early", "mid"}
        words = re.findall(r'\b\w+\b', query.lower())
        topics = [w for w in words if w not in stop_words and len(w) > 2]
        return topics[:5]

    def rewrite_for_search(self, query: str) -> Dict[str, Any]:
        """
        Use LLM to rewrite the query into search keywords.
        Strict rule: only extract/normalise terms present in the query.
        Never add external facts or hallucinate context.
        Falls back to simple extraction when LLM is unavailable.
        """
        if not self.client:
            return {"keywords": self.extract_topics(query), "rewritten": query}

        prompt = (
            "Rewrite the question below into 3-8 search keywords.\n"
            "Rules:\n"
            "- Return ONLY JSON: {\"keywords\": [...], \"rewritten\": \"...\"}\n"
            "- Keywords must come from the question itself; do NOT add external facts.\n"
            "- Normalise: plurals → singular, common synonyms → canonical form.\n"
            "- rewritten: a concise version of the question for dense embedding.\n\n"
            f"Question: {query}\n\nJSON:"
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.gen_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
            )
            content = resp.choices[0].message.content.strip()
            json_match = re.search(r'\{.*?\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                keywords = [str(k).lower().strip() for k in data.get("keywords", []) if k]
                rewritten = str(data.get("rewritten", query)).strip() or query
                return {"keywords": keywords, "rewritten": rewritten}
        except Exception:
            pass
        return {"keywords": self.extract_topics(query), "rewritten": query}

    def parse(self, query: str) -> dict:
        """Parse query into structured intent including LLM-rewritten search keywords."""
        date_range = self.parse_date_range(query)
        topics = self.extract_topics(query)
        search_intent = self.rewrite_for_search(query)
        return {
            "query": query,
            "date_range": date_range,
            "topics": topics,
            "keywords": search_intent["keywords"],
            "rewritten_query": search_intent["rewritten"],
        }
