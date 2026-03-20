"""Conversation state manager for multi-turn sessions."""

from __future__ import annotations

import uuid
from typing import Optional


class ConversationManager:
    """Manages conversation history per session.

    Each session maintains a list of ``{"role": ..., "content": ...}`` dicts
    compatible with the OpenAI chat format.  A system prompt is prepended
    automatically when retrieving messages.
    """

    def __init__(self, system_prompt: str, history_limit: int = 10) -> None:
        self.system_prompt = system_prompt
        self.history_limit = history_limit
        self.sessions: dict[str, list[dict]] = {}

    def _ensure_session(self, session_id: str) -> None:
        if session_id not in self.sessions:
            self.sessions[session_id] = []

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message and enforce the history limit."""
        self._ensure_session(session_id)
        self.sessions[session_id].append({"role": role, "content": content})
        # Keep only the most recent messages (pairs of user+assistant ideally).
        if len(self.sessions[session_id]) > self.history_limit:
            self.sessions[session_id] = self.sessions[session_id][
                -self.history_limit :
            ]

    def get_messages(self, session_id: str) -> list[dict]:
        """Return full message list including the system prompt."""
        self._ensure_session(session_id)
        return [
            {"role": "system", "content": self.system_prompt},
            *self.sessions[session_id],
        ]

    def get_history(self, session_id: str) -> list[dict]:
        """Return raw conversation history (without system prompt)."""
        self._ensure_session(session_id)
        return list(self.sessions[session_id])

    def clear(self, session_id: str) -> None:
        """Remove all history for a session."""
        self.sessions.pop(session_id, None)

    def new_session(self) -> str:
        """Create a new session and return its ID."""
        session_id = uuid.uuid4().hex[:12]
        self.sessions[session_id] = []
        return session_id
