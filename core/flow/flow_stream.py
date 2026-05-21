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
        self.decay_rate = 0.02
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

    def decay_synaptic(self):
        """S(t) = S_base * e^(-t/tau). Tau se ajusta por accesos."""
        minutes_elapsed = (datetime.now() - self.last_accessed).total_seconds() / 60.0
        adjusted_tau = self._tau * (1.0 + self._access_count * 0.5)
        decay = math.exp(-minutes_elapsed / max(adjusted_tau, 1.0))
        self._synaptic_strength = max(0.0, min(1.0, self._synaptic_strength * decay))

    def reinforce_synaptic(self, boost: float = 0.15):
        """Potenciación a Largo Plazo (LTP): S += alpha * (1 - S)."""
        self._synaptic_strength += boost * (1.0 - self._synaptic_strength)
        self._synaptic_strength = min(1.0, self._synaptic_strength)
        self._access_count += 1
        self.last_accessed = datetime.now()

    def should_prune(self) -> bool:
        """Podar si la fuerza sináptica es demasiado baja."""
        self.decay_synaptic()
        return self._synaptic_strength < 0.1

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

    def add_thought(self, thought: ThoughtItem):
        self.thoughts.append(thought)
        # Conectar automáticamente con pensamientos similares recientes
        self._auto_link(thought)
        self._update_active()
        self._prune()
        self._trigger_pattern_detectors(thought)

    def _trigger_pattern_detectors(self, thought: ThoughtItem):
        """Evalúa detectores por evento vectorial (Sistema 1 biológico)."""
        try:
            # Solo si hay un pattern_extractor disponible
            from core.flow.pattern_extractor import PatternExtractor
            # Obtener embedding del pensamiento
            emb = thought._embedding or self._get_embedding(thought.content)
            if emb is None:
                return
            
            import numpy as np
            
            # Acceder al pattern_extractor a través de la referencia del flow_manager
            # (esto requiere que FlowStream tenga una referencia al FlowManager)
            if not hasattr(self, '_flow_manager'):
                return
            
            detectors = self._flow_manager.pattern_extractor.active_detectors
            
            for detector in detectors:
                if not detector.get("active"):
                    continue
                
                # Obtener o cachear embedding de la condición
                cond_emb = detector.get("_condition_embedding")
                if cond_emb is None:
                    cond_emb = self._get_embedding(detector.get("condition_text", ""))
                    if cond_emb is None:
                        continue
                    detector["_condition_embedding"] = cond_emb
                
                # Dot product
                sim = np.dot(emb, cond_emb) / (max(np.linalg.norm(emb), 1e-8) * max(np.linalg.norm(cond_emb), 1e-8))
                
                if sim >= 0.82:
                    detector["times_triggered"] = detector.get("times_triggered", 0) + 1
                    detector["hebb_strength"] = detector.get("hebb_strength", 1.0) + 0.1
                    
                    # Generar pensamiento automático (Sistema 1)
                    reaction = ThoughtItem(
                        content=f"[Automático] {detector.get('reaction_text', '')[:150]}",
                        thought_type="detected_pattern",
                        priority=0.35,
                        source="pattern_detector_event"
                    )
                    self.add_thought(reaction)
                else:
                    # LTD: debilitar detector no activado
                    detector["hebb_strength"] = max(0.1, detector.get("hebb_strength", 1.0) - 0.01)
        except Exception:
            pass  # Silencioso, no interrumpe el flujo principal

    def _auto_link(self, thought: ThoughtItem):
        """Conecta automáticamente con pensamientos similares recientes."""
        if len(self.thoughts) < 2:
            return
        recent = self.thoughts[-10:-1]  # Los 10 anteriores, sin contar este
        for other in recent:
            # Conexión por co-ocurrencia temporal (misma ventana de 5 min)
            if (thought.created_at - other.created_at).total_seconds() < 300:
                thought.related_to.append(other.id)
            # Conexión por similitud semántica
            elif self._are_semantically_related(thought.content, other.content):
                thought.related_to.append(other.id)

    def _are_semantically_related(self, text1: str, text2: str, threshold: float = 0.6) -> bool:
        """Determina si dos textos están semánticamente relacionados."""
        emb1 = self._get_embedding(text1)
        emb2 = self._get_embedding(text2)
        if emb1 is None or emb2 is None:
            return False
        import numpy as np
        sim = np.dot(emb1, emb2) / (max(np.linalg.norm(emb1), 1e-8) * max(np.linalg.norm(emb2), 1e-8))
        return sim >= threshold

    def _update_active(self):
        self.active = [t for t in self.thoughts if t.priority * getattr(t, '_dmn_attenuation', 1.0) > 0.08]
        self.active.sort(key=lambda t: t.priority, reverse=True)
        self.active = self.active[:self.max_active]
        self.current_topic = self.active[0] if self.active else None

    def _prune(self):
        # Poda sináptica: eliminar pensamientos con fuerza < 0.1
        self.thoughts = [t for t in self.thoughts if not t.should_prune()]
        # Limitar total
        self.thoughts = [t for t in self.thoughts if t.priority > 0.0]
        if len(self.thoughts) > 50:
            self.thoughts = self.thoughts[-50:]

    def decay_all(self, minutes_elapsed: float):
        for t in self.thoughts:
            t.decay(minutes_elapsed)
        self._update_active()

    # ============================================
    # Filtro de Novedad Semántica (Teoría ART)
    # ============================================

    def is_novel_enough(self, content: str, threshold: float = 0.85) -> bool:
        """¿Vale la pena procesar este pensamiento o ya existe uno similar?"""
        recent = self.thoughts[-20:]
        if len(recent) < 3:
            return True

        new_emb = self._get_embedding(content)
        if new_emb is None:
            return True

        import numpy as np
        for thought in recent:
            existing = thought._embedding
            if existing is None or (isinstance(existing, list) and len(existing) == 0):
                continue
            sim = np.dot(new_emb, existing) / (max(np.linalg.norm(new_emb), 1e-8) * max(np.linalg.norm(existing), 1e-8))
            if sim >= threshold:
                thought.reinforce(0.1)
                thought.reinforce_synaptic(0.1)
                # Incrementar contador de rechazo ART
                if hasattr(self, '_flow_manager') and hasattr(self._flow_manager, '_art_stats'):
                    self._flow_manager._art_stats["rejected"] += 1
                return False
        # Incrementar contador total
        if hasattr(self, '_flow_manager') and hasattr(self._flow_manager, '_art_stats'):
            self._flow_manager._art_stats["total"] += 1
        return True

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

    # ============================================
    # Potencial de Acción (Activación Difusa)
    # ============================================

    def propagate_activation(self, source: ThoughtItem, energy: float = 1.0, decay: float = 0.4) -> List[ThoughtItem]:
        """Difunde energía de activación por el grafo de pensamientos."""
        source._potential = getattr(source, '_potential', 0.0) + energy

        for thought in self.thoughts:
            if thought.id == source.id:
                continue
            weight = 0.6 if thought.id in source.related_to else 0.1
            thought._potential = getattr(thought, '_potential', 0.0) + (energy * weight * decay)

        conscious = [t for t in self.thoughts if getattr(t, '_potential', 0.0) > 0.75]

        for t in self.thoughts:
            t._potential = getattr(t, '_potential', 0.0) * 0.5

        return conscious

    # ============================================
    # Contexto y resúmenes
    # ============================================

    def get_context_for_response(self) -> str:
        if not self.active:
            return "Sin pensamientos activos relevantes."
        return "\n".join([f"[P:{t.priority:.1f}] {t.content[:100]}" for t in self.active[:5]])

    def get_all_active_summary(self) -> str:
        if not self.active:
            return "Sin pensamientos activos."
        return " | ".join([t.content[:60] for t in self.active[:8]])

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

    # ============================================
    # Inhibición latente
    # ============================================

    def is_similar_to_recent(self, content: str, threshold: int = 2, max_check: int = 10) -> bool:
        recent = self.thoughts[-max_check:]
        if len(recent) < 3:
            return False

        from core.flow.fast_processors import FastCognitiveProcessors
        fast = FastCognitiveProcessors()

        lexical_matches = 0
        matched_thoughts = []
        for thought in recent:
            if fast.is_related(content, thought.content, threshold=threshold):
                lexical_matches += 1
                matched_thoughts.append(thought.content[:80])

        if lexical_matches >= 4:
            return True
        if lexical_matches >= 2:
            return self._check_semantic_similarity(content, matched_thoughts)
        if self._detect_thematic_loop(content, recent, fast):
            return self._check_semantic_similarity(content, [t.content[:80] for t in recent[-5:]])

        return False

    def _check_semantic_similarity(self, new_content: str, recent_contents: list) -> bool:
        from core.llm import LLMModel
        recent_text = "\n".join([f"- {c[:100]}" for c in recent_contents[-5:]])
        prompt = f"""¿Este nuevo pensamiento es ESENCIALMENTE EL MISMO TEMA que los pensamientos recientes?

Pensamientos recientes:
{recent_text}

Nuevo pensamiento: "{new_content[:200]}"

Responde SOLO SI o NO."""
        try:
            result = LLMModel.get_instance().generate(prompt, temperature=0.1, max_tokens=3, purpose="inhibicion_latente")
            return "SI" in result.upper()
        except Exception:
            return False

    def _detect_thematic_loop(self, content: str, recent: list, fast) -> bool:
        if len(recent) < 5:
            return False
        new_keywords = set(fast.extract_keywords(content, max_keywords=5))
        if not new_keywords:
            return False
        thematic_count = 0
        for thought in recent[-8:]:
            old_keywords = set(fast.extract_keywords(thought.content, max_keywords=5))
            if len(new_keywords & old_keywords) >= 2:
                thematic_count += 1
        return thematic_count >= 5

    # ============================================
    # Chunking
    # ============================================

    def get_grouped_active(self) -> list:
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

    # ============================================
    # Saliencia
    # ============================================

    def boost_by_salience(self, message: str):
        if not message or len(message) < 3:
            return

        from core.llm import LLMModel
        llm = LLMModel.get_instance()

        entity_context = ""
        if hasattr(self, '_get_entity_context'):
            try:
                entity_context = self._get_entity_context()
            except Exception:
                pass

        prompt = f"""Evalúa si este mensaje tiene una carga emocional alta PARA ESTA ENTIDAD ESPECÍFICA.

{entity_context}

Mensaje del usuario: "{message[:300]}"

Responde SOLO con un número del 0.0 al 1.0:
Número:"""

        try:
            result = llm.generate(prompt, temperature=0.1, max_tokens=5, purpose="evaluar_saliencia")
            boost = float(result.strip().replace(",", "."))
            boost = max(0.0, min(1.0, boost))
        except Exception:
            boost = 0.0

        if boost >= 0.5:
            salience_thought = ThoughtItem(
                content=f"[Alerta] El mensaje del usuario tiene una carga emocional de {boost:.0%} para mí.",
                thought_type="salience_alert",
                priority=0.5 + (boost * 0.5),
                source="bottom_up_attention"
            )
            self.add_thought(salience_thought)
            if boost >= 0.7:
                for thought in self.active:
                    thought.reinforce(boost * 0.3)

    # ============================================
    # Supresión de tópicos
    # ============================================

    def suppress_topic(self, topic: str, reduction: float = 0.9):
        topic_lower = topic.lower()
        for thought in self.thoughts:
            if topic_lower in thought.content.lower():
                thought.priority *= (1.0 - reduction)

    # ============================================
    # Serialización
    # ============================================

    def to_dict(self) -> dict:
        return {
            "active_count": len(self.active),
            "total_count": len(self.thoughts),
            "current_topic": self.current_topic.content[:100] if self.current_topic else None,
            "user_present": self.user_present,
            "active_thoughts": [t.to_dict() for t in self.active[:10]]
        }
    
    # ============================================
    # PageRank - Ideas Fuerza
    # ============================================

    def get_core_ideas(self, top_n: int = 3) -> List[str]:
        """Extrae las ideas más importantes del grafo usando PageRank."""
        if len(self.thoughts) < 3:
            return [t.content[:100] for t in self.thoughts]

        try:
            import networkx as nx

            G = nx.DiGraph()
            for t in self.thoughts[-50:]:
                G.add_node(t.id, content=t.content)
                for related_id in t.related_to:
                    if related_id in G:
                        G.add_edge(t.id, related_id, weight=0.5)

            if G.number_of_edges() == 0:
                # Sin aristas, usar fuerza sináptica como ranking
                ranked = sorted(self.thoughts[-20:], key=lambda t: t._synaptic_strength, reverse=True)
                return [t.content[:120] for t in ranked[:top_n]]

            scores = nx.pagerank(G, alpha=0.85, weight='weight')
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

            ideas = []
            for node_id, _ in ranked[:top_n]:
                for t in self.thoughts:
                    if t.id == node_id:
                        ideas.append(t.content[:120])
                        break
            return ideas if ideas else [t.content[:100] for t in self.thoughts[-3:]]
        except ImportError:
            # Fallback sin networkx
            ranked = sorted(self.thoughts[-20:], key=lambda t: t._synaptic_strength, reverse=True)
            return [t.content[:120] for t in ranked[:top_n]]