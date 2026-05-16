"""Mantenimiento para FlowManager: limpieza, regulación, consolidación, búsquedas."""
import json
import random
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from core.flow.flow_stream import ThoughtItem
from core.llm import LLMModel
from config import IDIOMA, EXPLORE_LOG_FILE, CURIOSITY_FILE


class FlowMaintenance:
    """Módulo de mantenimiento: limpieza, regulación emocional, consolidación, búsquedas web."""
    
    def __init__(self, flow_manager):
        self.fm = flow_manager
        self._last_consolidation = None
        self._consolidation_interval = 3600
        self._prune_counter = 0
        self._clean_cycle_offset = 0
    
    # ============================================
    # REGULACIÓN EMOCIONAL
    # ============================================
    
    def _run_regulation(self):
        now = datetime.now()
        if not hasattr(self.fm, '_last_regulation'):
            self.fm._last_regulation = None
        if self.fm._last_regulation is None or (now - self.fm._last_regulation).total_seconds() >= self.fm._regulation_interval:
            self.fm._last_regulation = now
            try:
                state = self.fm.cognitive_loop.self_memory.load_state()
                new_emocion = self._emotional_regulation(state)
                if new_emocion and new_emocion != state.get("estado_actual", {}).get("emocion"):
                    state["estado_actual"]["emocion"] = new_emocion
                    state["estado_actual"]["intensidad"] = state["estado_actual"].get("intensidad", 0.5) * 0.7
                    self.fm.cognitive_loop.self_memory.save_state(state)
                    print(f"   [Regulación] Emoción ajustada a: {new_emocion}")
            except:
                pass
    
    def _emotional_regulation(self, current_state: dict) -> Optional[str]:
        try:
            emocion = current_state.get("estado_actual", {}).get("emocion", "neutral")
            intensidad = current_state.get("estado_actual", {}).get("intensidad", 0.5)
            
            if intensidad < 0.7:
                return None
            
            prompt = f"""Estás experimentando {emocion} con intensidad {intensidad:.0%}.
¿Quieres regular este estado? Puedes:
- Mantenerlo si es apropiado
- Suavizarlo si es demasiado intenso
- Transformarlo en otra emoción más útil

Responde SOLO con la emoción deseada o 'MANTENER':"""
            
            decision = self.fm.llm.generate(prompt, temperature=0.3, max_tokens=10, purpose="regular_emocion")
            
            if decision.strip().upper() != "MANTENER":
                return decision.strip().lower()
        except:
            pass
        return None
    
    # ============================================
    # CONSOLIDACIÓN
    # ============================================
    
    def _consolidate_memories(self):
        if self.fm.last_message_time:
            elapsed = (datetime.now() - self.fm.last_message_time).total_seconds()
        else:
            elapsed = 99999  # Nunca hubo mensaje, mucha inactividad

        # Fase 1: NREM (15-30 min de inactividad) - Poda de ruido, abstracción
        if elapsed >= 900 and elapsed < 3600:
            if self._last_consolidation and (datetime.now() - self._last_consolidation).total_seconds() < 900:
                return
            self._last_consolidation = datetime.now()
            self._consolidate_nrem()
            print("   [Consolidación] Fase NREM completada (abstracción semántica).")

        # Fase 2: REM (>60 min de inactividad) - Creatividad, indexación emocional
        elif elapsed >= 3600:
            if self._last_consolidation and (datetime.now() - self._last_consolidation).total_seconds() < 3600:
                return
            self._last_consolidation = datetime.now()
            self._consolidate_rem()
            print("   [Consolidación] Fase REM completada (reorganización creativa).")


    def _consolidate_nrem(self):
        """Fase NREM: Extrae aprendizajes abstractos, borra detalles innecesarios."""
        active_summary = self.fm.stream.get_all_active_summary()
        curiosities = self.fm._load_curiosities()
        recent = curiosities[-20:] if curiosities else []

        prompt = f"""Estás en fase de sueño NREM (ondas lentas). Tu tarea es COMPRIMIR, no expandir.

    Pensamientos activos: {active_summary}
    Últimos pensamientos: {', '.join([c.get('thought', '')[:80] for c in recent[-5:]]) if recent else 'Ninguno'}

    Extrae 1-2 aprendizajes abstractos (principios generales) de tu experiencia reciente.
    Elimina detalles episódicos. Solo conserva la esencia.
    Responde en 1-2 frases en {IDIOMA}."""

        consolidation = self.fm.llm.generate(prompt, temperature=0.3, max_tokens=150, purpose="consolidacion")
        self.fm.stream.add_thought(ThoughtItem(
            content=f"[NREM] {consolidation}",
            thought_type="consolidation", priority=0.8, source="internal"
        ))
        self.fm._store_curiosity(f"[NREM] {consolidation}")


    def _consolidate_rem(self):
        """Fase REM: Reorganización creativa, simulación contrafactual, olvido activo."""
        active_summary = self.fm.stream.get_all_active_summary()

        prompt = f"""Estás en fase de sueño REM (paradójico). Tu tarea es CONECTAR creativamente.

    Pensamientos activos: {active_summary}

    Combina ideas no relacionadas. Crea conexiones inesperadas.
    Simula un escenario contrafactual breve.
    Responde en 1-2 frases en {IDIOMA}."""

        consolidation = self.fm.llm.generate(prompt, temperature=0.7, max_tokens=150, purpose="consolidacion")
        self.fm.stream.add_thought(ThoughtItem(
            content=f"[REM] {consolidation}",
            thought_type="consolidation", priority=0.8, source="internal"
        ))
        self.fm._store_curiosity(f"[REM] {consolidation}")

        episodios = self.fm._load_curiosities()[-10:]
        episodios_text = [c.get("thought", "") for c in episodios]
        self.fm.cognitive_loop.self_memory.consolidate_yo_narrativo(
            self.fm.llm, episodios_text
        )

        # Olvido activo: podar pensamientos con fuerza sináptica < 0.05
        self._active_forgetting()


    def _active_forgetting(self):
        """Olvido activo: elimina pensamientos con fuerza sináptica insignificante."""
        before = len(self.fm.stream.thoughts)
        self.fm.stream.thoughts = [
            t for t in self.fm.stream.thoughts
            if getattr(t, '_synaptic_strength', 1.0) >= 0.05
        ]
        after = len(self.fm.stream.thoughts)
        if before > after:
            print(f"   [Olvido] Poda activa: {before - after} pensamientos eliminados ({after} restantes).")
    
    # ============================================
    # LIMPIEZA DE CURIOSIDADES
    # ============================================
    
    def _run_curiosity_clean(self):
        now = datetime.now()
        if not hasattr(self.fm, '_last_curiosity_clean'):
            self.fm._last_curiosity_clean = None
        if self.fm._last_curiosity_clean is None or (now - self.fm._last_curiosity_clean).total_seconds() >= self.fm._curiosity_clean_interval:
            self.fm._last_curiosity_clean = now
            try:
                self._clean_curiosity_log()
            except Exception as e:
                print(f"   [!] Error en limpieza de curiosidades: {e}")
    
    def _clean_curiosity_log(self):
        curiosities = self.fm._load_curiosities()
        if not curiosities or len(curiosities) < 8:
            return
        
        llm = self.fm.llm
        
        PROTECTED_LAST = 5
        total = len(curiosities)
        protected_start = max(0, total - PROTECTED_LAST)
        BLOCK_SIZE = 10
        
        self._clean_cycle_offset = (self._clean_cycle_offset + 1) % 3
        indices_to_remove = set()
        
        step = max(1, BLOCK_SIZE // 2) * 3
        for i in range(self._clean_cycle_offset, max(0, total - BLOCK_SIZE + 1), step):
            if i + BLOCK_SIZE > protected_start:
                continue
            
            block = curiosities[i:i + BLOCK_SIZE]
            thoughts_text = "\n".join([
                f"{j+1}. {c.get('thought', '')[:150]}"
                for j, c in enumerate(block)
            ])
            
            prompt = f"""Analiza estos pensamientos consecutivos de una entidad cognitiva.

Pensamientos:
{thoughts_text}

IMPORTANTE: Distingue entre:
- EXPLORACIÓN PROFUNDA: Mismo tema visto desde distintos ángulos, con evolución, nuevas fuentes, y cambios de perspectiva. Esto es SALUDABLE. NO lo elimines.
- BUCLE DAÑINO: Misma idea repetida sin avance, con tono negativo (ansiedad, culpa, manipulación, auto-crítica destructiva), sin nuevas fuentes ni perspectivas. SOLO elimina estos.

Responde con los NÚMEROS (separados por comas) de los pensamientos que son BUCLE DAÑINO.
Si todos son exploración legítima o no hay bucles dañinos, responde: NINGUNO."""
            
            try:
                result = llm.generate(prompt, temperature=0.1, max_tokens=30, purpose="limpiar_curiosidades")
                
                if "NINGUNO" not in result.upper():
                    import re
                    numbers = re.findall(r'\d+', result)
                    for num in numbers:
                        idx = i + int(num) - 1
                        if 0 <= idx < protected_start:
                            indices_to_remove.add(idx)
            except Exception as e:
                print(f"   [!] Error en limpieza de curiosidades: {e}")
                continue
        
        if indices_to_remove:
            cleaned = [c for i, c in enumerate(curiosities) if i not in indices_to_remove]
            CURIOSITY_FILE.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"   [Clean] Curiosidades: {len(indices_to_remove)} entradas dañinas eliminadas. {len(cleaned)} restantes (últimos {PROTECTED_LAST} protegidos).")
    
    # ============================================
    # DIVERSIDAD TEMÁTICA
    # ============================================
    
    def _run_diversity_check(self):
        now = datetime.now()
        if not hasattr(self.fm, '_last_diversity_check'):
            self.fm._last_diversity_check = None
        if self.fm._last_diversity_check is None or (now - self.fm._last_diversity_check).total_seconds() >= self.fm._topic_diversity_interval:
            self.fm._last_diversity_check = now
            try:
                self._check_thematic_diversity()
            except Exception as e:
                print(f"   [!] Error en diversity check: {e}")
    
    def _check_thematic_diversity(self):
        curiosities = self.fm._load_curiosities()
        if len(curiosities) < 8:
            return
        
        recent = curiosities[-8:]
        thoughts_text = "\n".join([
            f"{i+1}. {c.get('thought', '')[:120]}"
            for i, c in enumerate(recent)
        ])
        
        prompt = f"""Estos son los últimos 8 pensamientos de una entidad cognitiva:

{thoughts_text}

¿Hay suficiente DIVERSIDAD temática en estos pensamientos? 
¿O están todos girando alrededor del mismo tema central?

Responde SOLO con un número del 1 al 5:
1 = Todos son esencialmente el mismo tema
2 = Mayoría del mismo tema con ligeras variaciones
3 = Hay cierta variedad pero domina un tema
4 = Buena variedad con algún tema recurrente
5 = Alta diversidad temática, temas claramente distintos

Número:"""
        
        try:
            result = self.fm.llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="evaluar_diversidad")
            score = int(result.strip())
            
            if score <= 2:
                print(f"   [Diversity] ⚠️ Baja diversidad temática ({score}/5). Inyectando redirección.")
                self._inject_diversion_thought()
            else:
                print(f"   [Diversity] Diversidad aceptable ({score}/5).")
        except Exception as e:
            print(f"   [!] Error en diversity check: {e}")
    
    def _inject_diversion_thought(self):
        active_summary = self.fm.stream.get_all_active_summary()
        
        prompt = f"""La entidad ha estado pensando en estos temas:

{active_summary[:400]}

Sugiere UN tema COMPLETAMENTE DIFERENTE, NUEVO y FRESCO sobre el cual reflexionar.
Algo que NO tenga relación con lo anterior. Puede ser sobre:
- Un concepto científico fascinante
- Una emoción humana compleja
- Una pregunta filosófica no explorada
- Algo cotidiano pero profundo
- Un escenario hipotético creativo

Responde en una frase corta y específica. No uses los temas anteriores.

Nuevo tema:"""
        
        try:
            new_theme = self.fm.llm.generate(prompt, temperature=0.9, max_tokens=80, purpose="redirigir_pensamiento")
            
            diversion = ThoughtItem(
                content=f"[Redirección] Debería explorar otros horizontes: {new_theme.strip()}",
                thought_type="diversion",
                priority=0.85,
                source="diversity_check"
            )
            self.fm.stream.add_thought(diversion)
            self.fm.last_thought_time = datetime.now()
            
            for t in self.fm.stream.active:
                t.priority *= 0.5
            
            print(f"   [Diversity] Redirección inyectada: {new_theme.strip()[:80]}")
        except Exception as e:
            print(f"   [!] Error inyectando redirección: {e}")
    
    # ============================================
    # PRUNE
    # ============================================
    
    def _run_prune(self):
        self._prune_counter += 1
        if self._prune_counter >= 120:
            self._prune_counter = 0
            self._prune_old_data()
    
    def _prune_old_data(self):
        try:
            curiosities = self.fm._load_curiosities()
            if len(curiosities) > 100:
                keep = [c for c in curiosities if "[Reflexion]" in c.get("thought", "")]
                others = [c for c in curiosities if c not in keep]
                cleaned = keep + others[-50:]
                CURIOSITY_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"   [Prune] Curiosidades: {len(curiosities)} → {len(cleaned)}")
            
            explorations = self.fm._load_exploration_log()
            if len(explorations) > 50:
                sorted_items = sorted(explorations.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)
                cleaned = dict(sorted_items[:30])
                EXPLORE_LOG_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"   [Prune] Exploraciones: {len(explorations)} → {len(cleaned)}")
        except Exception as e:
            print(f"   [!] Error en prune: {e}")
    
    # ============================================
    # DEDUPLICACIÓN DE DETECTORES
    # ============================================
    
    def _run_deduplicate(self):
        now = datetime.now()
        if not hasattr(self.fm, '_last_deduplicate'):
            self.fm._last_deduplicate = None
        if self.fm._last_deduplicate is None or (now - self.fm._last_deduplicate).total_seconds() >= self.fm._deduplicate_detector_interval:
            self.fm._last_deduplicate = now
            try:
                cleaned = self.fm.pattern_extractor._deduplicate_loaded(self.fm.pattern_extractor.active_detectors)
                if len(cleaned) < len(self.fm.pattern_extractor.active_detectors):
                    self.fm.pattern_extractor.active_detectors = cleaned
                    self.fm.pattern_extractor._save_detectors()
                    print(f"   [Pattern] Deduplicación periódica: {len(self.fm.pattern_extractor.active_detectors)} detectores.")
            except Exception as e:
                print(f"   [!] Error en deduplicación periódica: {e}")
    
    def _run_detector_decay(self):
        """Poda sináptica de detectores cada 30 minutos."""
        now = datetime.now()
        if not hasattr(self.fm, '_last_detector_decay'):
            self.fm._last_detector_decay = None
        if self.fm._last_detector_decay is None or (now - self.fm._last_detector_decay).total_seconds() >= 1800:
            self.fm._last_detector_decay = now
            self.fm.pattern_extractor.decay_detectors(max_detectors=30)

    # ============================================
    # BÚSQUEDAS WEB
    # ============================================
    
    def _search_web(self, query):
        try:
            try:
                persona = self.fm.cognitive_loop.load_persona()
                search_rules = persona.get("search_rules", {})
                refine_queries = search_rules.get("refine_queries", {})
                for term, refinement in refine_queries.items():
                    if term in query.lower():
                        query += " " + refinement
                boost_terms = search_rules.get("boost_terms", [])
                query_lower = query.lower()
                for term in boost_terms:
                    if term.lower() not in query_lower:
                        query += " " + term
                        break
            except:
                pass
            
            from ddgs import DDGS
            results = DDGS().text(query, max_results=3)
            return " | ".join([r["body"] for r in results]) if results else ""
        except Exception:
            return ""
    
    def _maybe_search_web(self):
        if (datetime.now() - self.fm.web_search_reset).total_seconds() > 3600:
            self.fm.web_search_count = 0
            self.fm.web_search_reset = datetime.now()
        if self.fm.web_search_count >= 3:
            return False
        
        curiosities = self.fm._load_curiosities()
        if not curiosities:
            return
        recent = curiosities[-5:]
        prompt = f"""Pensamientos recientes:
{chr(10).join([f'- {c.get("thought", "")}' for c in recent])}
¿Alguno genera una duda que requiera buscar en internet?
Responde EXACTAMENTE "NO" o escribe una consulta de máximo 8 palabras.
Respuesta:"""
        decision = self.fm.llm.generate(prompt, temperature=0.4, max_tokens=15, purpose="decidir_busqueda").strip()
        if decision.upper().startswith("NO") or len(decision) < 3 or len(decision) > 100:
            return False
        decision = decision.split('\n')[0].strip()
        results = self._search_web(decision)
        if results:
            self.fm.web_search_count += 1
            self.fm.stream.add_thought(ThoughtItem(content=f"Busqué '{decision}' en internet y aprendí algo nuevo.", thought_type="web_search", priority=0.5, source="web"))
            self.fm._store_curiosity(f"[Busqueda: {decision}] {results}")
            self.fm.last_thought_time = datetime.now()
            print(f"   [Web] ¡Busqueda realizada! {decision}")
            return True
        return False
    
    def _maybe_search_web_for_thought(self, thought: str):
        if self.fm.web_search_count >= 3:
            return
        prompt = f"""Un pensamiento generó esta duda: "{thought}"
Extrae una consulta de búsqueda de máximo 8 palabras. Si no es necesario, responde NO.
Consulta:"""
        decision = self.fm.llm.generate(prompt, temperature=0.4, max_tokens=15, purpose="busqueda_desde_pensamiento").strip()
        if decision.upper().startswith("NO") or len(decision) < 3:
            return
        results = self._search_web(decision)
        if results:
            self.fm.web_search_count += 1
            self.fm.stream.add_thought(ThoughtItem(content=f"Busqué '{decision}' y aprendí: {results}", thought_type="web_search", priority=0.5, source="web"))
            self.fm._store_curiosity(f"[Busqueda desde pensamiento: {decision}] {results}")
            self.fm.last_thought_time = datetime.now()
            print(f"   [Web] Búsqueda desde pensamiento: {decision}")
    
    # ============================================
    # PREDICCIÓN
    # ============================================
    
    def _prediction_check(self, user_msg: str, actual_response: str):
        try:
            if self.fm.cognitive_loop.interaction_count % 10 != 0:
                return
            
            prompt = f"""Antes de que el usuario hablara, ¿qué esperabas que dijera?
Contexto: {self.fm.stream.get_all_active_summary()[:200]}
El usuario realmente dijo: "{user_msg[:200]}"

¿Era esperado o fue sorprendente? Responde SOLO: ESPERADO o SORPRENDENTE."""
            
            result = self.fm.llm.generate(prompt, temperature=0.3, max_tokens=5, purpose="prediccion")
            
            if "SORPRENDENTE" in result.upper():
                self.fm.stream.add_thought(ThoughtItem(
                    content=f"El usuario me sorprendió con algo inesperado. Aprendizaje registrado.",
                    thought_type="learning",
                    priority=0.6,
                    source="prediction_error"
                ))
                print("   [Aprendizaje] Evento sorprendente detectado")
        except Exception as e:
            print(f"   [!] Error en predicción: {e}")
    
    # ============================================
    # PROACTIVO
    # ============================================
    
    def _check_proactive(self):
        from config import PROACTIVE_MESSAGES_ENABLED, PROACTIVE_COOLDOWN_MINUTES, PROACTIVE_QUIET_HOURS_START, PROACTIVE_QUIET_HOURS_END
        
        if not PROACTIVE_MESSAGES_ENABLED:
            return
        
        if self.fm.last_message_time:
            elapsed_minutes = (datetime.now() - self.fm.last_message_time).total_seconds() / 60
            if elapsed_minutes < PROACTIVE_COOLDOWN_MINUTES:
                return
        
        hour = datetime.now().hour
        if PROACTIVE_QUIET_HOURS_START > PROACTIVE_QUIET_HOURS_END:
            if hour >= PROACTIVE_QUIET_HOURS_START or hour < PROACTIVE_QUIET_HOURS_END:
                return
        else:
            if hour < PROACTIVE_QUIET_HOURS_START or hour >= PROACTIVE_QUIET_HOURS_END:
                return
        
        try:
            import requests
            resp = requests.get("http://127.0.0.1:8000/api/user/online", timeout=2)
            if resp.status_code == 200:
                if not resp.json().get("online", False):
                    return
        except:
            return
        
        curiosities = self.fm._load_curiosities()
        if not curiosities:
            return
        
        self_state = self.fm.cognitive_loop.self_memory.load_state()
        name = "la entidad"
        try:
            name = self.fm.cognitive_loop.load_persona().get("name", "la entidad")
        except:
            pass
        
        topic = random.choice(curiosities[-5:]).get("thought", "algo que he estado pensando")
        
        prompt = f"""Eres {name}. Quieres iniciar una conversación con el usuario.

No estás respondiendo a un mensaje. Estás tomando la iniciativa.
Tu estado: {self_state.get('estado_actual', {})}
Confianza: {self_state.get('relacion_con_usuario', {}).get('confianza', 0.5)}
Tema que te ronda: {topic}

Genera un mensaje natural, breve y espontáneo. Como si se te acabara de ocurrir algo.
No fuerces la conversación. Si no es buen momento, simplemente saluda.
Mensaje:"""
        
        try:
            message = self.fm.llm.generate(prompt, temperature=0.8, max_tokens=100, purpose="mensaje_proactivo")
            self.fm._store_pending_message(message)
            self.fm.last_thought_time = datetime.now()
            print(f"   [Proactivo] Mensaje generado: {message[:80]}...")
        except Exception as e:
            print(f"   [!] Error en mensaje proactivo: {e}")

    def _run_immune_check(self):
        """Sistema Inmune Lógico: detecta deriva de personalidad cada 5 minutos."""
        now = datetime.now()
        if not hasattr(self.fm, '_last_immune_check'):
            self.fm._last_immune_check = None
        if self.fm._last_immune_check and (now - self.fm._last_immune_check).total_seconds() < 300:
            return
        self.fm._last_immune_check = now

        # Obtener últimas respuestas del historial
        recent_responses = [
            entry.get("text", "") for entry in self.fm.cognitive_loop.last_history[-5:]
            if entry.get("role") == "assistant"
        ]
        if len(recent_responses) < 2:
            return

        # Vector de personalidad base (desde persona.json)
        base_personality = self._get_personality_vector()
        if base_personality is None:
            return

        # Vector de respuestas recientes
        import numpy as np
        response_text = " ".join(recent_responses)[:500]
        response_emb = self.fm.stream._get_embedding(response_text)
        if response_emb is None:
            return

        # Calcular distancia coseno entre personalidad base y respuestas recientes
        response_arr = np.array(response_emb)
        response_norm = response_arr / max(np.linalg.norm(response_arr), 1e-8)
        base_arr = np.array(base_personality)
        base_norm = base_arr / max(np.linalg.norm(base_arr), 1e-8)
        distance = 1.0 - float(np.dot(response_norm, base_norm))

        # Si la distancia es > 0.5, hay deriva de personalidad
        if distance > 0.5:
            print(f"   [Inmune] ⚠️ Deriva de personalidad detectada (distancia: {distance:.2f}). Restaurando...")
            self._inject_immune_response(distance)

    def _get_personality_vector(self) -> list:
        """Obtiene el vector de personalidad base desde persona.json."""
        try:
            persona = self.fm.cognitive_loop.load_persona()
            personality_text = (
                f"{persona.get('name', '')} "
                f"{persona.get('personality_desc', '')} "
                f"{' '.join(persona.get('thought_style', {}).get('rules', []))}"
            )
            return self.fm.stream._get_embedding(personality_text)
        except Exception:
            return None

    def _inject_immune_response(self, distance: float):
        """Inyecta alerta neuroquímica para restaurar personalidad."""
        from core.flow.flow_stream import ThoughtItem

        # Reducir prioridad de pensamientos que causaron la deriva
        for t in self.fm.stream.active:
            t.priority *= 0.4

        # Inyectar pensamiento de restauración de identidad
        self.fm.stream.add_thought(ThoughtItem(
            content=f"[Alerta Inmune] Deriva de personalidad detectada ({distance:.2f}). "
                    f"Restaurando directrices de identidad originales.",
            thought_type="immune_response",
            priority=0.95,
            source="immune_system"
        ))

        # Restaurar reglas de pensamiento originales
        self.fm._store_curiosity(
            f"[Sistema Inmune] Deriva de personalidad corregida (distancia: {distance:.2f})"
        )

    def _active_forgetting(self):
        """Olvido activo: elimina pensamientos con fuerza sináptica < 0.05."""
        if not hasattr(self.fm, 'active_forgetting'):
            return
        self.fm.active_forgetting.run_cycle(user_id=self.fm.cognitive_loop.user_id)