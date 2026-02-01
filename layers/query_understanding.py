"""
Layer 3: Query Understanding (intent + time)
Translates vague human language into concrete search constraints.
Handles phrases like "late Dec", "Q3", "around Christmas", etc.
"""
import re
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List


class QueryUnderstanding:
    def __init__(self, default_year: int = 2025):
        self.default_year = default_year
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
        """Extract key topics/keywords from query."""
        # Simple keyword extraction (can be enhanced with NLP)
        stop_words = {"what", "when", "where", "who", "how", "why", "was", "were", "did", "do", "does",
                      "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "i", "you",
                      "my", "your", "late", "early", "mid"}
        
        words = re.findall(r'\b\w+\b', query.lower())
        topics = [w for w in words if w not in stop_words and len(w) > 2]
        return topics[:5]  # top 5 keywords

    def parse(self, query: str) -> dict:
        """Parse query into structured intent."""
        return {
            "query": query,
            "date_range": self.parse_date_range(query),
            "topics": self.extract_topics(query),
        }
