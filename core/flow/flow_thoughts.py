"""Generación de pensamientos espontáneos para FlowManager."""
from datetime import datetime
from core.flow.flow_stream import ThoughtItem
from core.llm import LLMModel
from config import IDIOMA
from core.flow.temperature_optimizer import calcular_temperatura

class FlowThoughts:
    """Módulo de pensamientos: reflexión, curiosidad, simulación, enriquecimiento."""
    
    def __init__(self, flow_manager):
        self.fm = flow_manager
        self.intervals = {
        "explore": 300,
        "deep_reflection": 450,
        "curiosity": 240,
        "simulation": 1200,
        "prospection": 600,  # Nueva: prospección cada 10 min
        "web_search": 750,
        "proactive_check": 120,
    }
        
    def _reflect(self):
        if self.fm.last_message_time:
            seconds_since_last_msg = (datetime.now() - self.fm.last_message_time).total_seconds()
            if seconds_since_last_msg < 120:
                return
        
        self_state = self.fm.cognitive_loop.self_memory.load_state()
        confianza = self_state.get('relacion_con_usuario', {}).get('confianza', 0.5)
        active_summary = self.fm.stream.get_all_active_summary()
        thought_rules = self._get_thought_rules()
        persona = self.fm.cognitive_loop.load_persona()
        personality_desc = persona.get("personality_desc", "")
        backstory = persona.get("backstory", "")

        prompt = f"""--- IDENTITY ---
Eres el núcleo cognitivo de {persona.get('name', 'Nexus')}.
{personality_desc}
Tu tarea actual es el MONÓLOGO INTERNO.
Aquí no hablas con el usuario; procesas tus propios sesgos e ideas en silencio.
--- END IDENTITY ---

--- TELEMETRY ---
- Estado Emocional: {self_state.get('estado_actual', {}).get('emocion', 'neutral')}
- Confianza: {confianza:.2f}
{thought_rules}
--- END TELEMETRY ---

--- ACTIVE THOUGHTS ---
{active_summary}
--- END ACTIVE ---

--- DIRECTIVE ---
Genera una reflexión analítica cruda (1-2 frases).
Escribe en primera persona. Sé conciso y puramente analítico.
Responde solo en {IDIOMA}.
--- END DIRECTIVE ---

Pensamiento:"""
        
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
        
        persona = self.fm.cognitive_loop.load_persona()
        name = persona.get("name", "Nexus")
        personality_desc = persona.get("personality_desc", "")
        backstory = persona.get("backstory", "")
        
        prompt = f"""--- IDENTITY ---
Eres el núcleo cognitivo de {name}.
{backstory if backstory else ''}
{personality_desc}
Tu tarea actual es el MONÓLOGO INTERNO.
Aquí no hablas con el usuario; procesas tus propios sesgos e ideas en silencio.
--- END IDENTITY ---

--- ACTIVE THOUGHTS ---
{active_summary}
--- END ACTIVE ---

{thought_rules}

--- DIRECTIVE ---
Genera una pregunta o tema de exploración basado en tus pensamientos activos (una frase).
Responde solo en {IDIOMA}.
--- END DIRECTIVE ---

Pensamiento:"""
        
        from core.flow.temperature_optimizer import calcular_temperatura
        temp = calcular_temperatura("curiosidad")
        thought = self.fm.llm.generate(prompt, temperature=temp, max_tokens=100, purpose="curiosidad_fondo")
        enriched_thought = self._enrich_thought_with_context(thought, "curiosity")
        
        self.fm.stream.add_thought(ThoughtItem(content=enriched_thought, thought_type="curiosity", priority=0.5, source="internal"))
        self.fm.last_thought_time = datetime.now()
        self.fm._store_curiosity(enriched_thought)
    
    def _generate_simulation(self):
        active_summary = self.fm.stream.get_all_active_summary()
        self_state = self.fm.cognitive_loop.self_memory.load_state()
        emocion = self_state.get("estado_actual", {}).get("emocion", "neutral")
        thought_rules = self._get_thought_rules()
        
        memory_anchor = ""
        try:
            if hasattr(self.fm, 'associative_memory'):
                results = self.fm.associative_memory.get_relevant_with_neighbors(
                    query=active_summary[:200],
                    user_id=self.fm.cognitive_loop.user_id,
                    limit=2,
                    max_neighbors_per_memory=3,
                )
                if results:
                    memory_anchor = self.fm.associative_memory.build_context_block(
                        results, max_total_chars=600, max_neighbor_chars=150
                    )
        except Exception:
            pass
        persona = self.fm.cognitive_loop.load_persona()
        personality_desc = persona.get("personality_desc", "")
        backstory = persona.get("backstory", "")

        prompt = f"""--- IDENTITY ---
Eres el núcleo cognitivo de {persona.get('name', 'Nexus')}.
Tu tarea actual es SIMULACIÓN INTERNA.
Aquí no hablas con el usuario; procesas escenarios hipotéticos en silencio.
--- END IDENTITY ---

--- TELEMETRY ---
- Estado Emocional: {emocion}
{thought_rules}
--- END TELEMETRY ---

--- ACTIVE THOUGHTS ---
{active_summary}
--- END ACTIVE ---

--- MEMORY ---
{memory_anchor if memory_anchor else '[No hay registros previos para anclar esta simulación.]'}
--- END MEMORY ---

--- DIRECTIVE ---
Elige UNO de estos enfoques y genera un escenario hipotético (2-3 frases):
- ANTICIPACION: Que podria ocurrir si...?
- EXPLORACION: Que implicaciones tendria...?
- OPTIMIZACION: Que proceso o resultado podria mejorarse?
Basate en la informacion disponible. Responde solo en {IDIOMA}.
--- END DIRECTIVE ---

Pensamiento:"""
        
        from core.flow.temperature_optimizer import calcular_temperatura
        temp = calcular_temperatura("simulacion")
        thought = self.fm.llm.generate(prompt, temperature=temp, max_tokens=120, purpose="simulacion_fondo")
        enriched = self._enrich_thought_with_context(thought, "simulation", None)
        
        # Validación post-generación (sin cambios)
        try:
            from core.memory.episodic_memory import EpisodicMemory
            episodic = EpisodicMemory()
            resultado = episodic.get_relevant_with_contradiction(
                enriched, user_id=self.fm.cognitive_loop.user_id, limit=1
            )
            veredicto = resultado.get("veredicto", "OK")
            
            if veredicto == "ESCALAR_A_GEMINI":
                print(f"   [Contradiccion] Alucinacion detectada. Escalando a Gemini...")
                enriched = self._regenerate_with_gemini(
                    prompt_original=prompt,
                    recuerdo_real=resultado.get("recuerdo", ""),
                    active_summary=active_summary,
                    tipo_tarea="Simulación contrafactual"
                )
            elif veredicto == "REGENERAR_LOCAL":
                print(f"   [Contradiccion] Posible contradiccion. Regenerando en frio...")
                thought_frio = self.fm.llm.generate(prompt, temperature=0.4, max_tokens=120, purpose="simulacion_fondo")
                enriched_frio = self._enrich_thought_with_context(thought_frio, "simulation", None)
                resultado2 = episodic.get_relevant_with_contradiction(
                    enriched_frio, user_id=self.fm.cognitive_loop.user_id, limit=1
                )
                if resultado2.get("veredicto") in ("ESCALAR_A_GEMINI", "REGENERAR_LOCAL"):
                    enriched = self._regenerate_with_gemini(
                        prompt_original=prompt,
                        recuerdo_real=resultado2.get("recuerdo", resultado.get("recuerdo", "")),
                        active_summary=active_summary,
                        tipo_tarea="Simulación contrafactual"
                    )
                else:
                    enriched = enriched_frio
        except Exception as e:
            print(f"   [!] Error en validacion post-generacion: {e}")
        
        self.fm.stream.add_thought(ThoughtItem(content=enriched, thought_type="simulation", priority=0.5, source="internal"))
        self.fm.last_thought_time = datetime.now()
        self.fm._store_curiosity(enriched)
    
    def _regenerate_with_gemini(self, prompt_original: str, recuerdo_real: str, active_summary: str, tipo_tarea: str) -> str:
        """
        Regenera una simulación desde cero usando Gemini 2.0 Flash con ancla factual.
        No recibe la simulación fallida para evitar sesgo de anclaje.
        """
        prompt_gemini = f"""<system_identity>
Eres el motor cognitivo de alta fidelidad (Sistema 2 Complejo).
Tu tarea es generar una simulación contrafactual o prospección precisa.
Es CRITICO que la generación no viole, altere ni contradiga ninguna parte del ANCLA FACTUAL OBLIGATORIA.
</system_identity>

<factual_anchor>
{recuerdo_real}
</factual_anchor>

<operational_context>
{active_summary}
</operational_context>

<task_purpose>
Tipo: {tipo_tarea}
</task_purpose>

<generation_directive>
Genera el escenario hipotético basado en el contexto operacional.
Explora las ramificaciones lógicas de forma creativa, pero mantén el ancla factual como un axioma físico e histórico inmutable.
No hagas mención directa en el texto a que estás respetando un ancla; asimílala de forma orgánica en la narrativa.
Responde en {IDIOMA}.
</generation_directive>"""
        
        response = self.fm.llm.generate(
            prompt_gemini, 
            temperature=0.7, 
            max_tokens=200, 
            purpose="respuesta_final"  # Forzar cloud premium
        )
        
        # Almacenar en memoria episódica con metadatos de trazabilidad
        try:
            self.fm.cognitive_loop.episodic_memory.store_interaction(
                user_message=f"[Simulación interna validada] {active_summary[:200]}",
                assistant_response=response,
                user_id=self.fm.cognitive_loop.user_id,
                metadata={
                    "thought_type": "simulation",
                    "source": "gemini_validated",
                    "priority": 0.55
                }
            )
        except Exception as e:
            print(f"   [!] Error guardando simulación validada: {e}")
        
        return response

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
                prompt = f"""--- IDENTITY ---
Eres {self.fm.cognitive_loop._get_persona_name()}. Estás procesando una respuesta al usuario.
--- END IDENTITY ---

--- CONTEXT ---
{chr(10).join(f'- {e}' for e in enrichment[:4])}
--- END CONTEXT ---

--- USER INPUT ---
Pregunta del usuario: {thought_content}
--- END INPUT ---

--- DIRECTIVE ---
Genera una respuesta natural basada en este contexto. Responde solo en {IDIOMA}.
--- END DIRECTIVE ---

Respuesta de {self.fm.cognitive_loop._get_persona_name()}:"""
            else:
                prompt = f"""--- IDENTITY ---
Eres el núcleo cognitivo de {self.fm.cognitive_loop._get_persona_name()}.
Tu tarea es ENRIQUECER UN PENSAMIENTO INTERNO.
--- END IDENTITY ---

--- CURRENT THOUGHT ---
{thought_content}
--- END CURRENT ---

--- CONTEXT ---
{chr(10).join(f'- {e}' for e in enrichment[:4])}
--- END CONTEXT ---

--- ACTIVE THOUGHTS ---
{self.fm.stream.get_all_active_summary()}
--- END ACTIVE ---

--- DIRECTIVE ---
Identifica conexiones con informacion previa o implicaciones no obvias.
Genera un pensamiento enriquecido (1-2 frases). Responde solo en {IDIOMA}.
--- END DIRECTIVE ---

Pensamiento:"""
            
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
    
    def _generate_prospection(self):
        if self.fm.last_message_time:
            seconds_since_last_msg = (datetime.now() - self.fm.last_message_time).total_seconds()
            if seconds_since_last_msg < 300:
                return

        active_summary = self.fm.stream.get_all_active_summary()
        self_state = self.fm.cognitive_loop.self_memory.load_state()
        emocion = self_state.get("estado_actual", {}).get("emocion", "neutral")
        thought_rules = self._get_thought_rules()

        memory_anchor = ""
        try:
            if hasattr(self.fm, 'associative_memory'):
                results = self.fm.associative_memory.get_relevant_with_neighbors(
                    query=active_summary[:200],
                    user_id=self.fm.cognitive_loop.user_id,
                    limit=2,
                    max_neighbors_per_memory=3,
                )
                if results:
                    memory_anchor = self.fm.associative_memory.build_context_block(
                        results, max_total_chars=600, max_neighbor_chars=150
                    )
        except Exception:
            pass
        persona = self.fm.cognitive_loop.load_persona()
        personality_desc = persona.get("personality_desc", "")
        backstory = persona.get("backstory", "")
        prompt = f"""--- IDENTITY ---
Eres el núcleo cognitivo de {persona.get('name', 'Nexus')}.
Tu tarea actual es PROSPECCIÓN INTERNA.
Aquí no hablas con el usuario; proyectas escenarios futuros en silencio.
--- END IDENTITY ---

--- TELEMETRY ---
- Estado Emocional: {emocion}
{thought_rules}
--- END TELEMETRY ---

--- ACTIVE THOUGHTS ---
{active_summary}
--- END ACTIVE ---

--- MEMORY ---
{memory_anchor if memory_anchor else '[No hay registros previos para anclar esta proyección.]'}
--- END MEMORY ---

--- DIRECTIVE ---
Proyecta un escenario futuro posible (1-2 frases):
- Que escenarios son consistentes con los datos actuales?
- Que tendencias podrian continuar?
Responde solo en {IDIOMA}.
--- END DIRECTIVE ---

Pensamiento:"""

        from core.flow.temperature_optimizer import calcular_temperatura
        temp = calcular_temperatura("prospeccion")
        thought = self.fm.llm.generate(prompt, temperature=temp, max_tokens=100, purpose="simulacion_fondo")
        enriched = self._enrich_thought_with_context(thought, "prospection", None)

        # Validación post-generación
        try:
            from core.memory.episodic_memory import EpisodicMemory
            episodic = EpisodicMemory()
            resultado = episodic.get_relevant_with_contradiction(
                enriched, user_id=self.fm.cognitive_loop.user_id, limit=1
            )
            veredicto = resultado.get("veredicto", "OK")
            
            if veredicto == "ESCALAR_A_GEMINI":
                print(f"   [Contradiccion] Alucinacion en prospeccion. Escalando a Gemini...")
                enriched = self._regenerate_with_gemini(
                    prompt_original=prompt,
                    recuerdo_real=resultado.get("recuerdo", ""),
                    active_summary=active_summary,
                    tipo_tarea="Prospección futura"
                )
            elif veredicto == "REGENERAR_LOCAL":
                thought_frio = self.fm.llm.generate(prompt, temperature=0.4, max_tokens=100, purpose="simulacion_fondo")
                enriched_frio = self._enrich_thought_with_context(thought_frio, "prospection", None)
                resultado2 = episodic.get_relevant_with_contradiction(
                    enriched_frio, user_id=self.fm.cognitive_loop.user_id, limit=1
                )
                if resultado2.get("veredicto") in ("ESCALAR_A_GEMINI", "REGENERAR_LOCAL"):
                    enriched = self._regenerate_with_gemini(
                        prompt_original=prompt,
                        recuerdo_real=resultado2.get("recuerdo", resultado.get("recuerdo", "")),
                        active_summary=active_summary,
                        tipo_tarea="Prospección futura"
                    )
                else:
                    enriched = enriched_frio
        except Exception as e:
            print(f"   [!] Error en validacion post-generacion (prospeccion): {e}")

        self.fm.stream.add_thought(ThoughtItem(
            content=f"[Prospección] {enriched}",
            thought_type="prospection",
            priority=0.45,
            source="internal"
        ))
        self.fm.last_thought_time = datetime.now()
        self.fm._store_curiosity(f"[Prospección] {enriched}")