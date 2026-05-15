"""Generación de pensamientos espontáneos para FlowManager."""
from datetime import datetime
from core.flow.flow_stream import ThoughtItem
from core.llm import LLMModel
from config import IDIOMA


class FlowThoughts:
    """Módulo de pensamientos: reflexión, curiosidad, simulación, enriquecimiento."""
    
    def __init__(self, flow_manager):
        self.fm = flow_manager
    
    def _reflect(self):
        if self.fm.last_message_time:
            seconds_since_last_msg = (datetime.now() - self.fm.last_message_time).total_seconds()
            if seconds_since_last_msg < 120:
                return
        
        self_state = self.fm.cognitive_loop.self_memory.load_state()
        confianza = self_state.get('relacion_con_usuario', {}).get('confianza', 0.5)
        active_summary = self.fm.stream.get_all_active_summary()
        
        thought_rules = self._get_thought_rules()
        
        prompt = f"""Estas en un momento de reflexion interna.
Pensamientos activos: {active_summary}
Confianza: {confianza:.2f}
Emocion: {self_state.get('estado_actual', {}).get('emocion', 'neutral')}
{thought_rules}
Reflexiona profundamente. Una o dos frases. Responde solo en {IDIOMA}:"""
        
        thought = self.fm.llm.generate(prompt, temperature=0.7, max_tokens=100, purpose="reflexion_fondo")
        enriched_thought = self._enrich_thought_with_context(thought, "reflection", None)
        
        self.fm.stream.add_thought(ThoughtItem(content=enriched_thought, thought_type="reflection", priority=0.7, source="internal"))
        self.fm.last_thought_time = datetime.now()
        self.fm._store_curiosity(f"[Reflexion] {enriched_thought}")
        self.fm.pattern_extractor.analyze_reflection(enriched_thought)
    
    def _generate_curiosity(self):
        if self.fm.last_message_time:
            seconds_since_last_msg = (datetime.now() - self.fm.last_message_time).total_seconds()
            if seconds_since_last_msg < 120:
                return
        
        active_summary = self.fm.stream.get_all_active_summary()
        thought_rules = self._get_thought_rules()
        
        prompt = f"""Pensamientos activos: {active_summary}
{thought_rules}
Genera una curiosidad espontanea (una frase). Responde solo en {IDIOMA}:"""
        
        thought = self.fm.llm.generate(prompt, temperature=0.8, max_tokens=100, purpose="curiosidad_fondo")
        enriched_thought = self._enrich_thought_with_context(thought, "curiosity")
        
        self.fm.stream.add_thought(ThoughtItem(content=enriched_thought, thought_type="curiosity", priority=0.5, source="internal"))
        self.fm.last_thought_time = datetime.now()
        self.fm._store_curiosity(enriched_thought)
    
    def _generate_simulation(self):
        active_summary = self.fm.stream.get_all_active_summary()
        self_state = self.fm.cognitive_loop.self_memory.load_state()
        emocion = self_state.get("estado_actual", {}).get("emocion", "neutral")
        thought_rules = self._get_thought_rules()
        
        prompt = f"""Estás en un momento de simulación mental. Imagina un escenario hipotético.

Tus pensamientos activos: {active_summary}
Tu estado emocional: {emocion}
{thought_rules}

Elige UNO de estos tipos de simulación y desarrolla brevemente (2-3 frases):
- ANTICIPACIÓN: ¿Qué pasaría si...?
- EXPLORACIÓN: ¿Cómo sería si pudieras...?
- MEJORA: Si pudieras cambiar algo de ti misma, ¿qué sería?

No te limites a pensar solo en el usuario. Explora cualquier posibilidad.
Responde solo en {IDIOMA}:"""
        
        thought = self.fm.llm.generate(prompt, temperature=0.8, max_tokens=120, purpose="simulacion_fondo")
        enriched = self._enrich_thought_with_context(thought, "simulation", None)
        
        self.fm.stream.add_thought(ThoughtItem(content=enriched, thought_type="simulation", priority=0.5, source="internal"))
        self.fm.last_thought_time = datetime.now()
        self.fm._store_curiosity(enriched)
    
    def _enrich_thought_with_context(self, thought_content: str, source: str = "exploration", extra_context: str = None) -> str:
        enrichment = []
        
        try:
            self_state = self.fm.cognitive_loop.self_memory.load_state()
            emocion = self_state.get("estado_actual", {}).get("emocion", "neutral")
            confianza = self_state.get("relacion_con_usuario", {}).get("confianza", 0.5)
            enrichment.append(f"Mi estado: {emocion}, confianza: {confianza:.0%}")
        except:
            pass
        
        try:
            from core.perception.time_perception import get_time_context
            time_str = get_time_context(None) or ""
            if time_str:
                enrichment.append(f"Momento actual: {time_str}")
        except:
            pass
        
        try:
            user_profile = self.fm.cognitive_loop.user_memory.load_profile()
            percepcion = user_profile.get("comportamiento_observado", {})
            impresion = percepcion.get("impresion_general", "")
            if impresion:
                enrichment.append(f"Usuario: {impresion}")
        except:
            pass
        
        keywords = self.fm.fast.extract_keywords(thought_content, 5, use_llm=True)
        if keywords:
            try:
                from core.memory.episodic_memory import EpisodicMemory
                memories = EpisodicMemory().get_relevant(" ".join(keywords[:3]), user_id=self.fm.cognitive_loop.user_id, limit=3)
                if memories:
                    enrichment.append(f"Recuerdos: {' | '.join(memories[:2])}")
            except:
                pass
        
        if source != "reflection":
            try:
                if hasattr(self.fm.llm, 'get_recent_activity'):
                    activity = self.fm.llm.get_recent_activity(5)
                    if activity and "Sin actividad" not in activity:
                        enrichment.append(f"Actividad reciente:\n{activity}")
            except:
                pass
        
        if extra_context and source == "exploration":
            enrichment.append(f"Contexto: {extra_context[:300]}")
        
        if enrichment:
            if source == "conversation":
                prompt = f"""Contexto relevante para responder:
{chr(10).join(f'- {e}' for e in enrichment[:4])}
Pregunta del usuario: {thought_content}
Genera una respuesta natural basada en este contexto. Responde solo en {IDIOMA}:"""
            else:
                prompt = f"""Pensamiento inicial: {thought_content}
Contexto: {chr(10).join(f'- {e}' for e in enrichment[:4])}
Tus pensamientos activos: {self.fm.stream.get_all_active_summary()}
¿Este pensamiento se conecta con algo que ya sabes? ¿Te genera alguna duda?
Genera un pensamiento enriquecido (una o dos frases). Responde solo en {IDIOMA}:"""
            
            enriched = self.fm.llm.generate(prompt, temperature=0.7, max_tokens=150, purpose="pensamiento_enriquecido")
            
            if "?" in enriched and source != "conversation" and self.fm.satiety.can_generate("web_search"):
                self.fm.maintenance._maybe_search_web_for_thought(enriched)
            
            return enriched
        
        return thought_content
    
    def _get_thought_rules(self) -> str:
        try:
            persona = self.fm.cognitive_loop.load_persona()
            rules = persona.get("thought_style", {}).get("rules", [])
            if rules:
                return "REGLAS DE PENSAMIENTO:\n" + "\n".join([f"- {r}" for r in rules])
        except:
            pass
        return ""