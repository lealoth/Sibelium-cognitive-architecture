"""Control de saturación de pensamientos con índice dinámico."""
from datetime import datetime
from typing import Dict


class ThoughtSatiety:
    """Saciedad adaptativa basada en entropía del contexto."""

    def __init__(self):
        self.recent_thoughts_by_type: Dict[str, datetime] = {}
        self.cooldowns_base = {
            "reaction": 30,
            "association": 60,
            "curiosity": 240,
            "reflection": 900,
            "exploration": 600,
            "detected_pattern": 600,
            "visual": 15,
            "user_interaction": 5,
        }

    def can_generate(self, thought_type: str, context_entropy: float = 0.5) -> bool:
        """Verifica con saciedad dinámica basada en entropía del contexto."""
        last_time = self.recent_thoughts_by_type.get(thought_type)
        if last_time is None:
            return True

        base_cooldown = self.cooldowns_base.get(thought_type, 60)
        entropy_factor = max(0.0, 1.0 - context_entropy)
        dynamic_cooldown = base_cooldown * (1.0 + entropy_factor * 2.0)

        elapsed = (datetime.now() - last_time).total_seconds()
        return elapsed >= dynamic_cooldown

    def register(self, thought_type: str):
        self.recent_thoughts_by_type[thought_type] = datetime.now()

    def get_next_available(self) -> float:
        if not self.recent_thoughts_by_type:
            return 0
        now = datetime.now()
        min_wait = float('inf')
        for thought_type, last_time in self.recent_thoughts_by_type.items():
            base = self.cooldowns_base.get(thought_type, 60)
            elapsed = (now - last_time).total_seconds()
            wait = max(0, base - elapsed)
            min_wait = min(min_wait, wait)
        return min_wait if min_wait != float('inf') else 0