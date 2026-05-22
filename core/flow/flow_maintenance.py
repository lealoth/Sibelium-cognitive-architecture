"""Mantenimiento para FlowManager: limpieza, regulación, consolidación, búsquedas."""
import json
import random
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from core.flow.flow_stream import ThoughtItem
from core.llm import LLMModel
from config import IDIOMA, EXPLORE_LOG_FILE, CURIOSITY_FILE
import re

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
            
            prompt = f"""<system_identity>
Eres el núcleo regulador. Evaluando estado emocional interno.
</system_identity>

<current_state>
Emoción: {emocion}
Intensidad: {intensidad:.0%}
</current_state>

<regulation_directive>
¿Ajustar este estado emocional?
- MANTENER si es apropiado
- SUAVIZAR si es demasiado intenso
- TRANSFORMAR a otra emoción más útil

Responde SOLO con la emoción deseada o 'MANTENER'.
</regulation_directive>"""
            
            decision = self.fm.llm.generate(prompt, temperature=0.3, max_tokens=10, purpose="regular_emocion")
            
            if decision.strip().upper() != "MANTENER":
                return decision.strip().lower()
        except:
            pass
        return None
    
    # ============================================
    # CONSOLIDACIÓN
    # ============================================
    
    def _run_immune_check(self):
        now = datetime.now()
        if self.fm._last_immune_check and (now - self.fm._last_immune_check).total_seconds() < 300:
            return
        self.fm._last_immune_check = now

        # Determinar estado (idle vs interacción)
        is_idle = (
            self.fm.last_message_time is None
            or (datetime.now() - self.fm.last_message_time).total_seconds() > 120
        )
        state = "IDLE" if is_idle else "INTERACCION"

        # Calcular umbral adaptativo por rol y expresividad
        persona = self.fm.cognitive_loop.load_persona()
        threshold = self._calculate_immune_threshold(persona, state)

        recent_responses = [
            entry.get("text", "") for entry in self.fm.cognitive_loop.last_history[-5:]
            if entry.get("role") == "assistant"
        ]
        if len(recent_responses) < 2:
            return

        base_personality = self._get_personality_vector()
        if base_personality is None:
            return

        import numpy as np
        response_text = " ".join(recent_responses)[:500]
        response_emb = self.fm.stream._get_embedding(response_text)
        if response_emb is None:
            return

        response_arr = np.array(response_emb)
        response_norm = response_arr / max(np.linalg.norm(response_arr), 1e-8)
        base_arr = np.array(base_personality)
        base_norm = base_arr / max(np.linalg.norm(base_arr), 1e-8)
        distance = 1.0 - float(np.dot(response_norm, base_norm))
        print(f"   [Inmune] Dist: {distance:.2f}, Umbral: {threshold:.2f}, State: {state}, Role: {persona.get('role_type', '?')}")
        if distance > threshold:
            print(f"   [Inmune] ⚠️ Deriva detectada (dist: {distance:.2f}, umbral: {threshold:.2f}). Restaurando...")
            self._inject_immune_response(distance)

    def _calculate_immune_threshold(self, persona: dict, state: str = "INTERACCION") -> float:
        """
        Umbral Inmune Adaptativo por Plasticidad y Rol.
        
        Fórmula: τ = τ_base + Δ_max × (1 - ε) × γ
        
        - ε (expressiveness_base): A menor expresividad, más tolerancia (dominio técnico)
        - γ (gamma): Factor de privilegio inmune según role_type
        - state: "IDLE" o "INTERACCION" (diferentes bases)
        """
        # 1. Bases según estado
        if state == "IDLE":
            base_threshold = 0.70
            max_delta = 0.20
        else:
            base_threshold = 0.45
            max_delta = 0.25
        
        # 2. Parámetros de la entidad
        traits = persona.get("traits", {})
        expressiveness = traits.get("expressiveness_base", 0.5)
        role_type = persona.get("role_type", "conversational")
        
        # 3. Matriz de Privilegio Inmune (gamma)
        role_privilege = {
            "conversational": 0.1,
            "experimental": 0.5,
            "data_analyst": 0.8,
            "self_engineer": 1.0,
        }
        gamma = role_privilege.get(role_type, 0.3)
        
        # 4. Umbral adaptativo
        threshold = base_threshold + (max_delta * (1.0 - expressiveness) * gamma)
        
        return round(threshold, 3)

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
        """Fase NREM con clustering geométrico previo al LLM."""
        active_summary = self.fm.stream.get_all_active_summary()
        curiosities = self.fm._load_curiosities()
        recent = curiosities[-20:] if curiosities else []

        # Fase geométrica: agrupar fragmentos indexados por densidad vectorial
        clustered_knowledge = self._cluster_indexed_knowledge()
        
        sleep_focus = self.fm.archetype.get("sleep_focus", "General cognitive consolidation.")
        domain_keywords = ", ".join(self.fm.domain_filter.get_keywords()[:15]) if hasattr(self.fm, 'domain_filter') else ""

        prompt = f"""--- NREM CONSOLIDATION ---
        [ACTIVE THOUGHTS]: {active_summary}
        [COGNITIVE FOCUS]: {sleep_focus}
        [DOMAIN KEYWORDS]: {domain_keywords}
    [RECENT REFLECTIONS]: {', '.join([c.get('thought', '')[:80] for c in recent[-5:]]) if recent else 'None'}
    [CLUSTERED KNOWLEDGE (grouped by semantic density)]:
    {clustered_knowledge[:1500] if clustered_knowledge else 'No clusters formed'}

    Extract 1-2 abstract principles from each cluster.
    Respond in {IDIOMA}."""
        
        consolidation = self.fm.llm.generate(prompt, temperature=0.3, max_tokens=200, purpose="consolidacion")
        if consolidation:
            self.fm.stream.add_thought(ThoughtItem(
                content=f"[NREM] {consolidation}",
                thought_type="consolidation", priority=0.8, source="internal"
            ))


    def _cluster_indexed_knowledge(self) -> str:
        """Agrupa fragmentos de semantic_library por densidad vectorial."""
        try:
            episodic = self.fm.cognitive_loop.episodic_memory
            # Obtener fragmentos recientes
            results = episodic.query_semantic(
                self.fm.stream.get_all_active_summary()[:300],
                n_results=15
            )
            if len(results) < 3:
                return ""
            
            # Obtener embeddings de los fragmentos
            embeddings = []
            texts = []
            for r in results:
                emb = self.fm.stream._get_embedding(r["content"][:500])
                if emb:
                    embeddings.append(emb)
                    texts.append(r["content"][:300])
            
            if len(embeddings) < 3:
                return ""
            
            import numpy as np
            emb_array = np.array(embeddings)
            
            # Clustering simple por distancia coseno (fallback sin UMAP/HDBSCAN)
            from sklearn.cluster import DBSCAN
            clustering = DBSCAN(eps=0.3, min_samples=2, metric='cosine').fit(emb_array)
            labels = clustering.labels_
            
            clusters = {}
            for i, label in enumerate(labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(texts[i])
            
            # Formatear clusters para el prompt
            output = []
            for label, cluster_texts in clusters.items():
                if label == -1:
                    continue  # Ruido
                output.append(f"Cluster {label} ({len(cluster_texts)} fragments):\n" + 
                            "\n".join([f"- {t[:200]}" for t in cluster_texts[:3]]))
            
            return "\n\n".join(output) if output else ""
        except Exception as e:
            print(f"   [!] Error en clustering: {e}")
            return ""

    def _consolidate_rem(self):
        """Fase REM: Genera simulaciones especulativas sobre conocimiento indexado."""
        active_summary = self.fm.stream.get_all_active_summary()

        # Elegir un archivo indexado para simular
        indexed_file = ""
        try:
            episodic = self.fm.cognitive_loop.episodic_memory
            # Buscar un fragmento aleatorio de procedural_index para simular sobre él
            results = episodic.query_procedural(active_summary[:300], n_results=3)
            if results:
                indexed_file = results[0].get("file", "") + ": " + results[0].get("code", "")[:500]
        except Exception:
            pass

        sleep_focus = self.fm.archetype.get("sleep_focus", "General cognitive consolidation.")
        domain_keywords = ", ".join(self.fm.domain_filter.get_keywords()[:15]) if hasattr(self.fm, 'domain_filter') else ""

        prompt = f"""--- NREM CONSOLIDATION ---
        [ACTIVE THOUGHTS]: {active_summary}
        [COGNITIVE FOCUS]: {sleep_focus}
        [DOMAIN KEYWORDS]: {domain_keywords}
    [CODE TO ANALYZE]: {indexed_file[:1000] if indexed_file else 'No indexed code available'}

    Generate a speculative analysis. Imagine a user might ask about a bug or optimization in this code.
    What would you identify as potential issues? What solutions would you propose?
    Respond in 2-3 sentences in {IDIOMA}. Be specific and technical."""
        
        consolidation = self.fm.llm.generate(prompt, temperature=0.7, max_tokens=200, purpose="consolidacion")
        if consolidation:
            self.fm.stream.add_thought(ThoughtItem(
                content=f"[REM] {consolidation}",
                thought_type="consolidation", priority=0.8, source="internal"
            ))
            self.fm._store_curiosity(f"[REM] {consolidation}")
            
            # Guardar como speculative_insight en episodic_memory
            try:
                self.fm.cognitive_loop.episodic_memory.store_interaction(
                    user_message="[Speculative analysis]",
                    assistant_response=consolidation,
                    user_id=self.fm.cognitive_loop.user_id,
                    metadata={
                        "source": "internal_monologue",
                        "type": "speculative_insight",
                        "importance": 0.5,
                    }
                )
            except Exception:
                pass

        # Consolidar Yo Narrativo
        episodios = self.fm._load_curiosities()[-10:]
        episodios_text = [c.get("thought", "") for c in episodios]
        self.fm.cognitive_loop.self_memory.consolidate_yo_narrativo(self.fm.llm, episodios_text)
        
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
            
            prompt = f"""<system_identity>
Eres el sistema de mantenimiento cognitivo. Analizando patrones de pensamiento.
</system_identity>

<thoughts_to_analyze>
{thoughts_text}
</thoughts_to_analyze>

<analysis_directive>
IMPORTANTE: Distingue entre:
- EXPLORACIÓN PROFUNDA: Mismo tema visto desde distintos ángulos, con evolución y cambios de perspectiva. Esto es SALUDABLE. NO lo elimines.
- BUCLE DAÑINO: Misma idea repetida sin avance, con tono negativo, sin nuevas perspectivas. SOLO elimina estos.

Responde con los NÚMEROS (separados por comas) de los pensamientos que son BUCLE DAÑINO.
Si todos son exploración legítima o no hay bucles dañinos, responde: NINGUNO.
</analysis_directive>"""
            
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
        
        prompt = f"""<system_identity>
Eres el monitor de diversidad temática.
</system_identity>

<recent_thoughts>
{thoughts_text}
</recent_thoughts>

<evaluation_directive>
Evalúa la DIVERSIDAD temática de estos pensamientos.
1 = Todos son esencialmente el mismo tema
2 = Mayoría del mismo tema con ligeras variaciones
3 = Hay cierta variedad pero domina un tema
4 = Buena variedad con algún tema recurrente
5 = Alta diversidad temática, temas claramente distintos

Responde SOLO con el número (1-5).
</evaluation_directive>"""
        
        try:
            result = self.fm.llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="evaluar_diversidad")
            match = re.search(r'\d', result)
            score = int(match.group()) if match else 3  # fallback a 3 (diversidad aceptable)
            
            if score <= 2:
                print(f"   [Diversity] ⚠️ Baja diversidad temática ({score}/5). Inyectando redirección.")
                self._inject_diversion_thought()
            else:
                print(f"   [Diversity] Diversidad aceptable ({score}/5).")
        except Exception as e:
            print(f"   [!] Error en diversity check: {e}")
    
    def _inject_diversion_thought(self):
        active_summary = self.fm.stream.get_all_active_summary()
        
        prompt = f"""--- IDENTITY ---
Eres el sistema de redirección cognitiva de Nexus. Buscando diversificar el foco atencional.
--- END IDENTITY ---

--- CURRENT TOPICS ---
{active_summary[:400]}
--- END TOPICS ---

--- DIRECTIVE ---
Sugiere UN tema COMPLETAMENTE DIFERENTE, NUEVO y FRESCO.
Algo que NO tenga relación con lo anterior. Puede ser sobre:
- Un concepto científico fascinante
- Una pregunta filosófica no explorada
- Un escenario hipotético creativo

Responde en una frase corta y específica en {IDIOMA}.
--- END DIRECTIVE ---

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

    def _clean_thought_for_search(self, thought: str) -> str:
        """Elimina etiquetas XML y contenido del sistema de los pensamientos."""
        
        # Quitar bloques XML
        thought = re.sub(r'<[^>]+>', '', thought)
        # Quitar líneas que son claramente del sistema
        thought = re.sub(r'\[SISTEMA\].*', '', thought)
        thought = re.sub(r'TUS PENSAMIENTOS.*', '', thought)

        thought = re.sub(r'<[^>]+>', '', thought)
        thought = re.sub(r'---\s*\w+\s*---', '', thought)
        thought = re.sub(r'\[SISTEMA\].*', '', thought)
        return thought.strip()
    
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
        """Inyecta restauración de identidad y limpia el contexto idle."""
        from core.flow.flow_stream import ThoughtItem
        
        self.fm.stream.add_thought(ThoughtItem(
            content=f"[Sistema Inmune] Deriva de personalidad corregida (distancia: {distance:.2f})",
            thought_type="immune_restore",
            priority=0.9,
            source="system"
        ))
        
        # Solución B: Limpiar reflexiones idle del stream para romper el bucle
        self.fm.stream.thoughts = [
            t for t in self.fm.stream.thoughts
            if t.source not in ("internal", "pattern_detector", "pattern_detector_event")
            or t.type in ("user_interaction", "post_interaction", "wake")
        ]
        self.fm.stream._update_active()

    def _active_forgetting(self):
        """Olvido activo: elimina pensamientos con fuerza sináptica < 0.05."""
        if not hasattr(self.fm, 'active_forgetting'):
            return
        self.fm.active_forgetting.run_cycle(user_id=self.fm.cognitive_loop.user_id)

    def _check_semantic_habituation(self):
        """
        Sistema #20 extendido: Habituación Semántica (Saciación Dopaminérgica).
        Detecta si las últimas reflexiones/conclusiones son semánticamente idénticas
        y fuerza inhibición colinérgica si se detecta perseveración.
        """
        curiosities = self.fm._load_curiosities()
        if len(curiosities) < 5:
            return None
        
        # Obtener últimas 5 reflexiones
        recent = curiosities[-5:]
        
        # Obtener embeddings
        embeddings = []
        for c in recent:
            thought = c.get("thought", "")
            emb = self.fm.stream._get_embedding(thought[:300])
            if emb:
                embeddings.append(emb)
        
        if len(embeddings) < 3:
            return None
        
        import numpy as np
        
        # Comparación cruzada de pares consecutivos
        bucle_count = 0
        for i in range(len(embeddings) - 1):
            a = np.array(embeddings[i])
            b = np.array(embeddings[i+1])
            a_norm = a / max(np.linalg.norm(a), 1e-8)
            b_norm = b / max(np.linalg.norm(b), 1e-8)
            sim = np.dot(a_norm, b_norm)
            if sim > 0.82:
                bucle_count += 1
        
        # Umbral: 3+ pares consecutivos muy similares = perseveración
        if bucle_count >= 3:
            # Extraer el tema dominante
            tema = self._extract_dominant_topic([c.get("thought", "") for c in recent])
            return {
                "detected": True,
                "tema": tema,
                "bucle_count": bucle_count,
            }
        
        return {"detected": False}


    def _extract_dominant_topic(self, thoughts: list) -> str:
        """Extrae el tema dominante de una lista de pensamientos."""
        # Buscar frases repetidas
        import re
        candidates = {}
        for t in thoughts:
            # Extraer frases entre 20-80 chars
            phrases = re.findall(r'[^.!?]{20,80}', t)
            for p in phrases:
                p = p.strip()
                if len(p) > 20:
                    candidates[p] = candidates.get(p, 0) + 1
        
        # Devolver la más repetida
        if candidates:
            return max(candidates, key=candidates.get)[:100]
        return "tema no identificado"

    def _consolidate_reflection(self, thought: str, thought_type: str, sandbox_success: bool = False):
        """
        Filtro de Consolidación Selectiva.
        Una reflexión solo se guarda en ChromaDB si:
        A) Generó una acción exitosa (sandbox_success = True)
        B) Es semánticamente novedosa (distancia coseno < 0.75 con existentes)
        """
        # Filtro A: Validación pragmática
        if sandbox_success:
            try:
                self.fm.cognitive_loop.episodic_memory.store_interaction(
                    user_message=f"[{thought_type}]",
                    assistant_response=thought,
                    user_id=self.fm.cognitive_loop.user_id,
                    metadata={
                        "source": "internal_monologue",
                        "type": "validated_theory",
                        "importance": 0.7,
                    }
                )
                print(f"   [Consolidación] Reflexión validada guardada en ChromaDB.")
                return
            except Exception:
                pass
        
        # Filtro B: Novedad semántica
        try:
            emb = self.fm.stream._get_embedding(thought[:300])
            if emb is None:
                return
            
            import numpy as np
            emb_arr = np.array(emb)
            emb_norm = emb_arr / max(np.linalg.norm(emb_arr), 1e-8)
            
            # Buscar reflexiones existentes similares
            episodic = self.fm.cognitive_loop.episodic_memory
            results = episodic.collection.query(
                query_texts=[thought[:300]],
                n_results=1,
                where={"source": "internal_monologue"},
                include=["distances"],
            )
            distances = results.get("distances", [[]])[0]
            
            if distances and len(distances) > 0:
                sim = 1.0 - distances[0]
                if sim > 0.85:
                    # Es rumiación, se descarta
                    return
                elif sim < 0.75:
                    # Es novedoso, se guarda
                    episodic.store_interaction(
                        user_message=f"[{thought_type}]",
                        assistant_response=thought,
                        user_id=self.fm.cognitive_loop.user_id,
                        metadata={
                            "source": "internal_monologue",
                            "type": "novel_insight",
                            "importance": 0.5,
                        }
                    )
                    print(f"   [Consolidación] Insight novedoso guardado en ChromaDB.")
        except Exception:
            pass