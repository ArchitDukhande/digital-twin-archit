"""
Layer 1: Raw Memory (ground truth)
Preserves raw data exactly as it was written. Never interprets.
This is the source of truth for citations and evidence.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date


class RawMemory:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.raw_chunks: List[Dict[str, Any]] = []
        self._load_all()

    def _load_all(self) -> None:
        """Load all .md files and preserve them as raw chunks with metadata."""
        for md_path in sorted(self.data_dir.rglob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8")
            except Exception:
                continue

            # Parse based on file type
            if "slack" in md_path.name.lower() or "chat" in md_path.name.lower():
                chunks = self._parse_slack_messages(text, str(md_path))
            else:
                chunks = self._parse_document(text, str(md_path))

            self.raw_chunks.extend(chunks)

    def _parse_timestamp_from_line(self, line: str) -> Optional[datetime]:
        """Extract datetime from various formats."""
        # ISO-like timestamps
        m = re.search(r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2})", line)
        if m:
            try:
                return datetime.fromisoformat(m.group(1).replace(" ", "T"))
            except Exception:
                pass

        # Month name patterns like Dec 22, 2025 14:05
        m2 = re.search(r"([A-Za-z]+\s+\d{1,2},\s*\d{4})(?:\s+(\d{1,2}:\d{2}))?", line)
        if m2:
            date_part = m2.group(1)
            time_part = m2.group(2) or "00:00"
            for fmt in ["%B %d, %Y %H:%M", "%b %d, %Y %H:%M"]:
                try:
                    return datetime.strptime(f"{date_part} {time_part}", fmt)
                except Exception:
                    continue
        return None

    def _parse_slack_messages(self, text: str, file_path: str) -> List[Dict[str, Any]]:
        """Parse slack/chat messages into individual chunks with timestamps."""
        lines = text.splitlines()
        messages = []
        current = {"ts": None, "text": "", "start_line": 0}
        line_num = 0

        for line in lines:
            line_num += 1
            ts = self._parse_timestamp_from_line(line)
            if ts is not None:
                # Save previous message
                if current["text"].strip():
                    messages.append({
                        "id": f"{Path(file_path).stem}:msg:{len(messages)}",
                        "file": file_path,
                        "text": current["text"].strip(),
                        "timestamp": current["ts"],
                        "start_line": current["start_line"],
                        "end_line": line_num - 1,
                        "type": "slack_message",
                    })
                # Start new message
                current = {"ts": ts, "text": line, "start_line": line_num}
            else:
                # Continuation
                if current["text"]:
                    current["text"] += "\n" + line
                else:
                    current = {"ts": None, "text": line, "start_line": line_num}

        # Final message
        if current["text"].strip():
            messages.append({
                "id": f"{Path(file_path).stem}:msg:{len(messages)}",
                "file": file_path,
                "text": current["text"].strip(),
                "timestamp": current["ts"],
                "start_line": current["start_line"],
                "end_line": line_num,
                "type": "slack_message",
            })

        return messages

    def _parse_document(self, text: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse regular documents into logical chunks.
        Special case: identity.md is kept as a single chunk.
        """
        # Special handling for identity.md - keep it whole
        if Path(file_path).name == "identity.md":
            return [{
                "id": "identity:profile",
                "file": file_path,
                "text": text.strip(),
                "timestamp": None,
                "start_line": 1,
                "end_line": text.count("\n") + 1,
                "type": "profile",
            }]

        # Simple chunking by paragraphs or sections
        chunks = []
        paragraphs = text.split("\n\n")
        current_chunk = ""
        chunk_start = 1
        line_count = 1

        for para in paragraphs:
            if not para.strip():
                continue

            # Cap at ~1000 chars per chunk
            if len(current_chunk) + len(para) > 1000 and current_chunk:
                chunks.append({
                    "id": f"{Path(file_path).stem}:chunk:{len(chunks)}",
                    "file": file_path,
                    "text": current_chunk.strip(),
                    "timestamp": None,
                    "start_line": chunk_start,
                    "end_line": line_count,
                    "type": "document",
                })
                current_chunk = para
                chunk_start = line_count + 1
            else:
                current_chunk += "\n\n" + para if current_chunk else para

            line_count += para.count("\n") + 2

        # Final chunk
        if current_chunk.strip():
            chunks.append({
                "id": f"{Path(file_path).stem}:chunk:{len(chunks)}",
                "file": file_path,
                "text": current_chunk.strip(),
                "timestamp": None,
                "start_line": chunk_start,
                "end_line": line_count,
                "type": "document",
            })

        return chunks

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific chunk by ID."""
        for chunk in self.raw_chunks:
            if chunk["id"] == chunk_id:
                return chunk
        return None

    def get_chunks_by_time_range(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """Get all chunks within a time range."""
        results = []
        for chunk in self.raw_chunks:
            if chunk["timestamp"] and start <= chunk["timestamp"] <= end:
                results.append(chunk)
        return results

    def get_all_chunks(self) -> List[Dict[str, Any]]:
        """Return all raw chunks."""
        return self.raw_chunks
