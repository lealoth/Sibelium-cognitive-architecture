"""Flujo de consciencia: ThoughtItem y FlowStream."""
import math
import uuid
from datetime import datetime
from typing import List, Optional


class ThoughtItem:
    """Una unidad de pensamiento con prioridad, decaimiento y fuerza sináptica."""

    def __init__(self, content: str, thought_type: str = "general",
                 priority: float = 0.5, source: str = "internal"):
        self.id = str(uuid.uuid4())[:8]
        self.content = content
        self.type = thought_type
        self.priority = max(0.0, min(1.0, priority))
        self.source = source
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.decay_rate = 0.15
        self.related_to: List[str] = []
        self.triggered_response = False

        # Fuerza sináptica (Ebbinghaus)
        self._synaptic_strength = 0.3
        self._access_count = 0
        self._tau = 60.0  # Constante de estabilidad (minutos)
        self._potential = 0.0  # Potencial de acción (activación difusa)
        self._embedding = None  # Cache del embedding

    def decay(self, minutes_elapsed: float):
        self.priority = max(0.0, self.priority - (self.decay_rate * minutes_elapsed))

    def reinforce(self, boost: float = 0.15):
        self.priority = min(1.0, self.priority + boost)
        self.last_accessed = datetime.now()

    # ============================================
    # Fuerza Sináptica (Curva de Ebbinghaus)
    # ============================================

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content[:200],
            "type": self.type,
            "priority": round(self.priority, 2),
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "related_to": self.related_to
        }


class FlowStream:
    """El río de consciencia de la Entidad."""
    _embedding_function = None  # Cache compartido entre todas las instancias

    def __init__(self, max_active: int = 15):
        self.thoughts: List[ThoughtItem] = []
        self.active: List[ThoughtItem] = []
        self.current_topic: Optional[ThoughtItem] = None
        self.max_active = max_active
        self.user_present = False
        self.last_user_interaction: Optional[datetime] = None

    # ============================================
    # Gestión de pensamientos
    # ============================================

    def add_thought(self, thought: ThoughtItem, skip_filters: bool = False) -> bool:
        if not skip_filters:
            if not self.is_novel_enough(thought.content):
                return False
            if hasattr(self, '_flow_manager') and self._flow_manager.satiety:
                entropy = self._flow_manager._get_context_entropy()
                if not self._flow_manager.satiety.can_generate(thought.type, entropy):
                    return False
        self.thoughts.append(thought)
        self._auto_link(thought)
        self._update_active()
        self._prune()
        if hasattr(self, '_flow_manager') and self._flow_manager.satiety:
            self._flow_manager.satiety.register(thought.type)
        return True

    def _update_active(self):
        self.active = [t for t in self.thoughts if t.priority * getattr(t, '_dmn_attenuation', 1.0) > 0.08]
        self.active.sort(key=lambda t: t.priority, reverse=True)
        self.active = self.active[:self.max_active]
        self.current_topic = self.active[0] if self.active else None

    def _get_embedding(self, text: str) -> Optional[list]:
        """Obtiene embedding con caché de la función (no se reinstancia)."""
        try:
            if FlowStream._embedding_function is None:
                from chromadb.utils import embedding_functions
                FlowStream._embedding_function = embedding_functions.DefaultEmbeddingFunction()
            emb = FlowStream._embedding_function([text])[0]
            return list(emb)
        except Exception:
            return None

    def get_all_active_summary(self) -> str:
        if not self.active:
            return "Sin pensamientos activos."
        parts = []
        for t in self.active[:8]:
            prefix = {
                "user_interaction": "[Usuario dijo]",
                "post_interaction": "[Yo respondí]",
                "reflection": "[Reflexión interna]",
                "curiosity": "[Curiosidad interna]",
                "simulation": "[Simulación interna]",
                "prospection": "[Prospección interna]",
                "consolidation": "[Consolidación]",
                "belief_update": "[Corrección]",
                "immune_restore": "[Sistema]",
                "wake": "[Sistema]",
            }.get(t.type, "[Interno]")
            parts.append(f"{prefix} {t.content[:60]}")
        return " | ".join(parts)
    # ============================================
    # Interacción con el usuario
    # ============================================

    def on_user_interaction(self, user_msg: str):
        self.user_present = True
        self.last_user_interaction = datetime.now()

        msg_words = set(user_msg.lower().split())
        for t in self.active:
            if len(msg_words & set(t.content.lower().split())) >= 3:
                t.reinforce(0.2)

        attention = ThoughtItem(
            content=f"Usuario: {user_msg[:100]}",
            thought_type="user_interaction",
            priority=0.9,
            source="user"
        )
        self.add_thought(attention)

    def on_response_sent(self, response: str):
        self.user_present = False
        for t in self.thoughts:
            if t.type == "user_interaction":
                t.priority = max(0.0, t.priority - 0.4)

        post = ThoughtItem(
            content=f"Respondí sobre: {response[:100]}",
            thought_type="post_interaction",
            priority=0.45,
            source="post_interaction"
        )
        self.add_thought(post)
        self._update_active()

    def to_dict(self) -> dict:
        return {
            "active_count": len(self.active),
            "total_count": len(self.thoughts),
            "current_topic": self.current_topic.content[:100] if self.current_topic else None,
            "user_present": self.user_present,
            "active_thoughts": [t.to_dict() for t in self.active[:10]]
        }