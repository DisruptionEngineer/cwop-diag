"""
CWOP Engine — Context Window Orchestration for diagnostics.
Manages context slots, token budgets, and data flow between
OBD-II data, DTC lookups, and the LLM.
"""

import time
from dataclasses import dataclass, field


@dataclass
class ContextSlot:
    """A named slot in the context window with its own token budget."""
    name: str
    category: str  # "auto" or "demand"
    content: str = ""
    token_estimate: int = 0
    max_tokens: int = 500
    last_updated: float = 0.0
    source: str = ""

    @property
    def utilization(self) -> float:
        if self.max_tokens == 0:
            return 0
        return min(1.0, self.token_estimate / self.max_tokens)


class CWOPEngine:
    """
    Orchestrates context window content for the diagnostic LLM.

    Manages what data the LLM sees, how much budget each source gets,
    and assembles the full context for each inference call.
    """

    def __init__(self, total_budget: int = 1500):
        """
        Args:
            total_budget: Total token budget for context.
                          Pi 4 with 1.5B model: keep at 1500-2000.
                          With larger model or Mac mini: can go to 4000+.
        """
        self.total_budget = total_budget
        self.slots: dict[str, ContextSlot] = {}
        self._init_default_slots()

    def _init_default_slots(self):
        """Set up default context slots for automotive diagnostics."""
        defaults = [
            # Auto-loaded slots
            ("dtc_codes", "auto", 400, "DTC Database"),
            ("live_data", "auto", 300, "OBD-II Sensors"),
            ("llm_analysis", "auto", 600, "AI Analysis"),
            # On-demand slots
            ("freeze_frame", "demand", 200, "Freeze Frame"),
            ("repair_history", "demand", 300, "Repair History"),
            ("tsb_matches", "demand", 400, "TSB Lookup"),
        ]
        for name, cat, budget, source in defaults:
            self.slots[name] = ContextSlot(
                name=name, category=cat, max_tokens=budget, source=source
            )

    def update_slot(self, name: str, content: str):
        """Update a context slot with new content."""
        if name not in self.slots:
            self.slots[name] = ContextSlot(
                name=name, category="demand", max_tokens=500, source="manual"
            )
        slot = self.slots[name]
        slot.content = content
        slot.token_estimate = self._estimate_tokens(content)
        slot.last_updated = time.time()

    def get_budget_status(self) -> dict:
        """Get current budget allocation and utilization."""
        used = sum(s.token_estimate for s in self.slots.values() if s.content)
        slots_info = []
        for name, slot in self.slots.items():
            slots_info.append({
                "name": slot.name,
                "source": slot.source,
                "tokens": slot.token_estimate,
                "max": slot.max_tokens,
                "utilization": round(slot.utilization * 100),
                "category": slot.category,
                "active": bool(slot.content),
            })
        return {
            "total_budget": self.total_budget,
            "used": used,
            "available": self.total_budget - used,
            "utilization": round((used / self.total_budget) * 100) if self.total_budget else 0,
            "slots": slots_info,
        }

    def assemble_context(self) -> str:
        """
        Assemble all active slots into a single context string
        for the LLM, respecting token budgets.
        """
        parts = []
        for slot in self.slots.values():
            if not slot.content:
                continue
            # Truncate if over budget
            content = slot.content
            if slot.token_estimate > slot.max_tokens:
                content = self._truncate_to_budget(content, slot.max_tokens)
            parts.append(content)
        return "\n\n".join(parts)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token for English."""
        return len(text) // 4

    def _truncate_to_budget(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n[...truncated to fit budget]"
