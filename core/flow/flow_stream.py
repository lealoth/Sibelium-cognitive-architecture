"""Flujo de consciencia: ThoughtItem y FlowStream."""
import uuid
from datetime import datetime
from typing import Optional, List


class ThoughtItem:
    """Una unidad de pensamiento con prioridad y decaimiento."""
    
    def __init__(self, content: str, thought_type: str = "general", 
                 priority: float = 0.5, source: str = "internal"):
        self.id = str(uuid.uuid4())[:8]
        self.content = content
        self.type = thought_type
        self.priority = max(0.0, min(1.0, priority))
        self.source = source
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.decay_rate = 0.02
        self.related_to: List[str] = []
        self.triggered_response = False
    
    def decay(self, minutes_elapsed: float):
        """Pierde prioridad con el tiempo."""
        self.priority = max(0.0, self.priority - (self.decay_rate * minutes_elapsed))
    
    def reinforce(self, boost: float = 0.15):
        """Gana prioridad cuando es relevante."""
        self.priority = min(1.0, self.priority + boost)
        self.last_accessed = datetime.now()

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
    
    def __init__(self, max_active: int = 15):
        self.thoughts: List[ThoughtItem] = []
        self.active: List[ThoughtItem] = []
        self.current_topic: Optional[ThoughtItem] = None
        self.max_active = max_active
        self.user_present = False
        self.last_user_interaction: Optional[datetime] = None
    
    def add_thought(self, thought: ThoughtItem):
        """Añade un pensamiento al flujo."""
        self.thoughts.append(thought)
        self._update_active()
        self._prune()
    
    def _update_active(self):
        """Actualiza la lista de pensamientos activos (prioridad > 0.08)."""
        self.active = [t for t in self.thoughts if t.priority > 0.08]
        self.active.sort(key=lambda t: t.priority, reverse=True)
        self.active = self.active[:self.max_active]
        self.current_topic = self.active[0] if self.active else None
    
    def _prune(self):
        """Elimina pensamientos olvidados y limita el total."""
        self.thoughts = [t for t in self.thoughts if t.priority > 0.0]
        if len(self.thoughts) > 50:
            self.thoughts = self.thoughts[-50:]
    
    def decay_all(self, minutes_elapsed: float):
        """Aplica decaimiento a todos los pensamientos."""
        for t in self.thoughts:
            t.decay(minutes_elapsed)
        self._update_active()
    
    def get_context_for_response(self) -> str:
        """Devuelve los pensamientos activos relevantes para responder al usuario."""
        if not self.active:
            return "Sin pensamientos activos relevantes."
        lines = []
        for t in self.active[:5]:
            lines.append(f"[P:{t.priority:.1f}] {t.content[:100]}")
        return "\n".join(lines)
    
    def get_all_active_summary(self) -> str:
        """Resumen de todos los pensamientos activos."""
        if not self.active:
            return "Sin pensamientos activos."
        return " | ".join([f"{t.content[:60]}" for t in self.active[:8]])
    
    def on_user_interaction(self, user_msg: str):
        """El flujo reacciona a la interacción del usuario."""
        self.user_present = True
        self.last_user_interaction = datetime.now()
        
        # Reforzar pensamientos relacionados
        msg_words = set(user_msg.lower().split())
        for t in self.active:
            thought_words = set(t.content.lower().split())
            overlap = len(msg_words & thought_words)
            if overlap >= 3:
                t.reinforce(0.2)
        
        # Crear pensamiento de atención
        attention = ThoughtItem(
            content=f"Usuario: {user_msg[:100]}",
            thought_type="user_interaction",
            priority=0.9,
            source="user"
        )
        self.add_thought(attention)
    
    def on_response_sent(self, response: str):
        """Después de responder, el flujo absorbe la experiencia."""
        self.user_present = False
        
        # El pensamiento de atención decae rápido
        for t in self.thoughts:
            if t.type == "user_interaction":
                t.priority = max(0.0, t.priority - 0.4)
        
        # Crear pensamiento post-interacción
        post = ThoughtItem(
            content=f"Respondí sobre: {response[:100]}",
            thought_type="post_interaction",
            priority=0.45,
            source="post_interaction"
        )
        self.add_thought(post)
        self._update_active()
    
    def is_similar_to_recent(self, content: str, threshold: int = 2, max_check: int = 10) -> bool:
        """Verifica si un pensamiento es similar a alguno reciente (inhibición latente)."""
        recent = self.thoughts[-max_check:]
        if len(recent) < 3:
            return False
        
        from core.flow.fast_processors import FastCognitiveProcessors
        fast = FastCognitiveProcessors()
        
        # NIVEL 1: Similitud léxica
        # Comparar contra todos los pensamientos en la ventana
        lexical_matches = 0
        matched_thoughts = []
        for thought in recent:
            if fast.is_related(content, thought.content, threshold=threshold):
                lexical_matches += 1
                matched_thoughts.append(thought.content[:80])
        
        # Si hay 4 o más coincidencias léxicas → bloqueo inmediato
        if lexical_matches >= 4:
            return True
        
        # Si hay 2-3 coincidencias → ambiguo, verificar con LLM
        if lexical_matches >= 2:
            return self._check_semantic_similarity(content, matched_thoughts)
        
        # Si hay 0-1 coincidencias → probablemente no es similar
        # Pero verificar si hay un bucle temático (palabras diferentes, mismo tema)
        if self._detect_thematic_loop(content, recent, fast):
            return self._check_semantic_similarity(content, [t.content[:80] for t in recent[-5:]])
        
        return False


    def _check_semantic_similarity(self, new_content: str, recent_contents: list) -> bool:
        """Usa LLM para determinar si el nuevo pensamiento es semánticamente similar a los recientes."""
        from core.llm import LLMModel
        
        recent_text = "\n".join([f"- {c[:100]}" for c in recent_contents[-5:]])
        
        prompt = f"""¿Este nuevo pensamiento es ESENCIALMENTE EL MISMO TEMA que los pensamientos recientes?

    Pensamientos recientes:
    {recent_text}

    Nuevo pensamiento: "{new_content[:200]}"

    ¿Está el nuevo pensamiento dando vueltas sobre la misma idea central que los anteriores?
    Responde SOLO SI o NO."""
        
        try:
            result = LLMModel.get_instance().generate(
                prompt, temperature=0.1, max_tokens=3, purpose="inhibicion_latente"
            )
            return "SI" in result.upper()
        except:
            # Si el LLM falla, ser conservador y permitir el pensamiento
            return False


    def _detect_thematic_loop(self, content: str, recent: list, fast) -> bool:
        """Detecta si hay un posible bucle temático aunque las palabras varíen.
        
        Busca patrones donde los pensamientos recientes forman una secuencia
        de pensamientos que giran sobre el mismo concepto abstracto.
        """
        if len(recent) < 5:
            return False
        
        # Contar cuántos pensamientos recientes comparten al menos 2 palabras clave con el nuevo
        new_keywords = set(fast.extract_keywords(content, max_keywords=5))
        if not new_keywords:
            return False
        
        thematic_count = 0
        for thought in recent[-8:]:
            old_keywords = set(fast.extract_keywords(thought.content, max_keywords=5))
            if len(new_keywords & old_keywords) >= 2:
                thematic_count += 1
        
        # Si 5 o más pensamientos comparten palabras clave, posible bucle
        return thematic_count >= 5

    def get_grouped_active(self) -> list:
        """Agrupa pensamientos activos por similitud temática (chunking)."""
        if len(self.active) < 2:
            return [(t, [t]) for t in self.active]
        
        from core.flow.fast_processors import FastCognitiveProcessors
        fast = FastCognitiveProcessors()
        
        groups = []
        used = set()
        
        for i, thought in enumerate(self.active):
            if i in used:
                continue
            group = [thought]
            used.add(i)
            
            for j, other in enumerate(self.active):
                if j in used:
                    continue
                if fast.is_related(thought.content, other.content, threshold=3):
                    group.append(other)
                    used.add(j)
            
            groups.append((thought, group))
        
        return groups

    def boost_by_salience(self, message: str):
        """Aumenta la prioridad de pensamientos cuando el mensaje tiene alta carga emocional
        para esta entidad específica, según su historia y personalidad."""
        if not message or len(message) < 3:
            return
        
        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        
        entity_context = ""
        if hasattr(self, '_get_entity_context'):
            try:
                entity_context = self._get_entity_context()
            except:
                pass
        
        prompt = f"""Evalúa si este mensaje tiene una carga emocional alta PARA ESTA ENTIDAD ESPECÍFICA.

{entity_context}

Mensaje del usuario: "{message[:300]}"

Considera:
- La historia personal de la entidad con este usuario
- Sus patrones emocionales aprendidos
- Su estado emocional actual
- Lo que para ella, específicamente, podría ser doloroso, alarmante, o emocionante

Responde SOLO con un número del 0.0 al 1.0 donde:
0.0 = mensaje neutral para esta entidad
1.0 = carga emocional extrema para esta entidad

Número:"""
        
        try:
            result = llm.generate(prompt, temperature=0.1, max_tokens=5, purpose="evaluar_saliencia")
            boost = float(result.strip().replace(",", "."))
            boost = max(0.0, min(1.0, boost))
        except:
            boost = 0.0
        
        if boost >= 0.5:
            salience_thought = ThoughtItem(
                content=f"[Alerta] El mensaje del usuario tiene una carga emocional de {boost:.0%} para mí. Atención requerida.",
                thought_type="salience_alert",
                priority=0.5 + (boost * 0.5),
                source="bottom_up_attention"
            )
            self.add_thought(salience_thought)
            
            if boost >= 0.7:
                for thought in self.active:
                    thought.reinforce(boost * 0.3)

    def to_dict(self) -> dict:
        return {
            "active_count": len(self.active),
            "total_count": len(self.thoughts),
            "current_topic": self.current_topic.content[:100] if self.current_topic else None,
            "user_present": self.user_present,
            "active_thoughts": [t.to_dict() for t in self.active[:10]]
        }
    
    def suppress_topic(self, topic: str, reduction: float = 0.9):
        """Reduce la prioridad de pensamientos sobre un tema corregido."""
        topic_lower = topic.lower()
        for thought in self.thoughts:
            if topic_lower in thought.content.lower():
                thought.priority *= (1 - reduction)