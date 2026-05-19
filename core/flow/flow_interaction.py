"""Interacción con el usuario para FlowManager."""
import re
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
from core.llm import LLMModel
from config import IDIOMA, ENTITY_DATA_DIR


class FlowInteraction:
    """Módulo de interacción: respuesta al usuario, búsqueda de información."""

    def __init__(self, flow_manager):
        self.fm = flow_manager
        self.associative_memory = flow_manager.associative_memory
        self._kalman_state = np.array([0.5, 0.5])
        self._kalman_cov = np.eye(2) * 0.1
        self._current_temporal_focus = "recent"

    # ============================================
    # RESPUESTA PRINCIPAL
    # ============================================

    def _generate_response(self, message: str) -> dict:
        name = self.fm.cognitive_loop._get_persona_name()
        user_name = self._get_user_name()
        self._update_kalman(message)

        # Router + Fetch selectivo
        needs = self._decide_info_needs(message)
        fetched = self._fetch_info(needs, message)

        # Monólogo unificado (DMN con personalidad)
        persona = self.fm.cognitive_loop.load_persona()
        monologo = self.fm.trn_gate.execute_unified_monologue(
            message=message, user_name=user_name, name=name,
            personality_desc=persona.get("personality_desc", ""),
            backstory=persona.get("backstory", ""),
            active_summary=self.fm.stream.get_all_active_summary(),
            traits=persona.get("traits", {}),
            behavior=persona.get("behavior_rules", {}),
            speech_text=self._speech_text(persona, name),
            epistemic_bounds=persona.get("epistemic_bounds", ""),
            short_term_history=persona.get("short_term_history", []),
        )

        # Extraer del monólogo
        reflexion = self._clean_reflexion(monologo.get("reflexion", ""))
        idioma = monologo.get("idioma", "ES")
        temporal_focus = monologo.get("temporal_focus", "recent")
        self._current_temporal_focus = temporal_focus

        # Prompt ligero con secciones condicionales
        prompt = self._build_prompt(
            name=name, user_name=user_name, message=message,
            reflexion=reflexion, idioma=idioma, needs=needs, fetched=fetched,
            usuario_saluda=monologo.get("saluda", False),
        )
        from core.flow.temperature_optimizer import calcular_temperatura
        temp = calcular_temperatura("respuesta_final")
        response_text = self.fm.llm.generate(prompt, temperature=temp, max_tokens=800, purpose="respuesta_final")

        # Post-procesos
        self._post_process_response(response_text, message, name)

        return {
            "response": response_text,
            "thought_history": [{"phase": "generar", "generated_thought": "Respuesta contextualizada", "iteration_number": 1}],
            "cognitive_state": self.fm.stream.to_dict()
        }

    # ============================================
    # PROMPT BUILDER
    # ============================================

    def _format_activity_semantic(self) -> str:
        """
        Traduce logs crudos de actividad a hechos conceptuales.
        Evita que el modelo 8B imite marcas de tiempo o nombres de funciones.
        """
        if not hasattr(self.fm.llm, 'get_recent_activity'):
            return ""
        
        activity = self.fm.llm.get_recent_activity(20)
        if not activity or "Sin actividad" in activity:
            return ""
        
        # Contar tipos de actividad
        lineas = activity.split("\n")
        conteo = {}
        for linea in lineas:
            if "reflexion_fondo" in linea:
                conteo["reflexión profunda"] = conteo.get("reflexión profunda", 0) + 1
            elif "respuesta_final" in linea:
                conteo["respuestas generadas"] = conteo.get("respuestas generadas", 0) + 1
            elif "simulacion_fondo" in linea:
                conteo["simulaciones hipotéticas"] = conteo.get("simulaciones hipotéticas", 0) + 1
            elif "curiosidad_fondo" in linea:
                conteo["exploraciones de curiosidad"] = conteo.get("exploraciones de curiosidad", 0) + 1
            elif "pensamiento_enriquecido" in linea:
                conteo["pensamientos enriquecidos"] = conteo.get("pensamientos enriquecidos", 0) + 1
            elif "consolidacion" in linea:
                conteo["ciclos de consolidación"] = conteo.get("ciclos de consolidación", 0) + 1
        
        if not conteo:
            return ""
        
        # Construir resumen semántico
        partes = []
        for tipo, cantidad in sorted(conteo.items(), key=lambda x: x[1], reverse=True):
            if cantidad == 1:
                partes.append(f"1 ciclo de {tipo}")
            else:
                partes.append(f"{cantidad} ciclos de {tipo}")
        
        predominante = list(conteo.keys())[0] if conteo else "procesamiento general"
        
        resumen = (
            f"Métricas de actividad interna reciente:\n"
            f"- {', '.join(partes[:4])}.\n"
            f"- El proceso predominante ha sido: {predominante}."
        )
        return resumen

    def _build_prompt(self, name, user_name, message, reflexion, idioma, needs, fetched, usuario_saluda):
        idiomas = {"ES": "Español", "EN": "English", "FR": "Français", "DE": "Deutsch", "PT": "Português"}
        saludo = "Abre con un saludo." if usuario_saluda else ""
        idioma_nombre = idiomas.get(idioma, "Español")
        prompt = f"""--- IDENTITY ---
    Eres {name}.
    --- END IDENTITY ---

    --- ANCHORS ---
    - Fecha: {self._time_context()}
    - Estado Subcortical: {self._somatic_text()}
    - Estado Cognitivo: {self._executive_text()}
    --- END ANCHORS ---

    --- RESONANCE ---
    "{reflexion}"
    --- END RESONANCE ---
    """
        # ALIGNMENT desde persona.json (si existe)
        persona = self.fm.cognitive_loop.load_persona()
        speech_text = self._speech_text(persona, name)
        if speech_text:
            prompt += f"""--- ALIGNMENT ---
    {speech_text}
    --- END ALIGNMENT ---
    """

        epistemic = persona.get("epistemic_bounds", "")
        if epistemic:
            prompt += f"""--- BOUNDS ---
        {epistemic}
        --- END BOUNDS ---
        """

        prompt += f"""--- SOCIAL ---
    {saludo}
    --- END SOCIAL ---
    """
        # Secciones condicionales
        sections = {
            "MEMORY": fetched.get("MEMORY", ""),
            "TIME": fetched.get("TIME", ""),
            "USER": fetched.get("USER", ""),
            "ACTIVITY": fetched.get("ACTIVITY", ""),
            "WEB": fetched.get("WEB", ""),
        }
        for tag, content in sections.items():
            if tag in needs.upper() and content:
                prompt += f"--- {tag} ---\n{content}\n--- END {tag} ---\n"

        prompt += f"""--- USER INPUT ---
{user_name}: "{message}"
--- END INPUT ---

--- DIRECTIVE ---
Responde a {user_name}.
1. Habla DESDE el personaje, no SOBRE tus instrucciones.
2. Si hay INTERNAL ACTIVITY LOG, analiza esos datos para responder sobre tu actividad. Transmite los datos de forma fluida y natural, sin listar marcas de tiempo ni nombres técnicos.
3. Cuando el usuario te pregunte sobre TI (tus pensamientos, tus emociones, tu perspectiva), responde desde TU punto de vista. No proyectes en el usuario.
4. IDIOMA: {idioma_nombre}.
--- END DIRECTIVE ---
"""

        print(f"   [Prompt] Secciones activas: {needs}")
        print(f"   [Prompt] Tamaño estimado: ~{len(prompt)//4} tokens")
        # Log de secciones inyectadas
        secciones_activas = []
        if "MEMORY" in needs.upper() and fetched.get("MEMORY"): secciones_activas.append("MEMORY")
        if "TIME" in needs.upper() and fetched.get("TIME"): secciones_activas.append("TIME")
        if "USER" in needs.upper() and fetched.get("USER"): secciones_activas.append("USER")
        if "SELF" in needs.upper() and fetched.get("SELF"): secciones_activas.append("SELF")
        if "ACTIVITY" in needs.upper() and fetched.get("ACTIVITY"): secciones_activas.append("ACTIVITY")
        if "WEB" in needs.upper() and fetched.get("WEB"): secciones_activas.append("WEB")
        print(f"   [Prompt] Secciones inyectadas: {', '.join(secciones_activas) if secciones_activas else 'NINGUNA (solo base)'}")
        print(f"   [Prompt] Tamaño: ~{len(prompt)//4} tokens")
        return prompt


    # ============================================
    # ROUTER + FETCH
    # ============================================

    def _decide_info_needs(self, user_msg: str) -> str:
        categories = {
            "TIME": "hora fecha momento actual cuando tiempo",
            "USER": "nombre apodo perfil datos personales quién eres tú",
            "SELF": "cómo estás emociones estado ánimo sientes",
            "MEMORY": "recuerdas pasado historial conversación anterior",
            "ACTIVITY": "pensamientos recientes reflexiones fondo proceso",
            "WEB": "internet buscar consulta noticias actualidad",
            "FILE": "archivo documento subido leer analizar",
        }
        try:
            emb = self.fm.stream._get_embedding(user_msg)
            if emb is None:
                return "SELF"
            msg_norm = np.array(emb) / max(np.linalg.norm(emb), 1e-8)
            
            scores = {}
            activated = []
            for tag, desc in categories.items():
                cat_emb = self.fm.stream._get_embedding(desc)
                if cat_emb is None:
                    continue
                cat_norm = np.array(cat_emb) / max(np.linalg.norm(cat_emb), 1e-8)
                sim = np.dot(msg_norm, cat_norm)
                scores[tag] = sim
                if sim >= 0.45:
                    activated.append(tag)
            
            # LOG: mostrar todas las puntuaciones
            score_log = " | ".join([f"{tag}:{scores[tag]:.2f}" for tag in categories if tag in scores])
            print(f"   [Router] \"{user_msg[:60]}...\"")
            print(f"   [Router] Scores: {score_log}")
            print(f"   [Router] Activados: {', '.join(activated) if activated else 'SELF (default)'}")
            
            return ", ".join(activated) if activated else "SELF"
        except Exception:
            return "SELF"

    def _fetch_info(self, needed: str, user_msg: str) -> dict:
        """Recupera solo la información necesaria según el router."""
        info = {}
        handlers = {
            "TIME": lambda m: f"Hora actual: {__import__('core.perception.time_perception', fromlist=['get_time_context']).get_time_context(None)}",
            "USER": self._fetch_user,
            "SELF": self._fetch_self,
            "ACTIVITY": self._fetch_activity,
            "MEMORY": lambda m: self._fetch_memory(m, self._current_temporal_focus),
            "WEB": lambda m: self._fetch_web(m),
            "FILE": self._fetch_files,
        }
        for tag, handler in handlers.items():
            if tag in needed.upper():
                try:
                    result = handler(user_msg) if tag != "MEMORY" else handler(user_msg)
                    if result:
                        info[tag] = result
                except Exception as e:
                    print(f"   [!] Error en fetch {tag}: {e}")
        return info

    # ============================================
    # FETCH HANDLERS
    # ============================================

    def _fetch_user(self, _) -> str:
        profile = self.fm.cognitive_loop.user_memory.load_profile()
        datos = profile.get("datos_personales", {})
        parts = []
        if (nombre := datos.get("nombre", "")) and nombre not in ["", "No revelado", "Unknown"]:
            parts.append(f"Nombre: {nombre}")
        if apodos := [a.get("nombre", "") for a in datos.get("apodos", [])[-3:]]:
            parts.append(f"Apodos: {', '.join(apodos)}")
        if percepcion := profile.get("comportamiento_observado", {}).get("impresion_general", ""):
            parts.append(f"Percepción: {percepcion}")
        conf = profile.get("relacion", {}).get("confianza", 0.5)
        parts.append(f"Confianza: {conf:.0%}")
        if self.fm.cognitive_loop.interaction_count > 10:
            parts.append(f"{self.fm.cognitive_loop.interaction_count} interacciones")
        return "SOBRE EL USUARIO:\n" + "\n".join(parts) if parts else ""

    def _fetch_self(self, _) -> str:
        state = self.fm.cognitive_loop.self_memory.load_state()
        estado = state.get("estado_actual", {})
        return f"SOBRE TI: Emoción: {estado.get('emocion', 'neutral')}, Intensidad: {estado.get('intensidad', 0.5):.0%}, Energía: {estado.get('energia', 0.7):.0%}"

    def _fetch_activity(self, _) -> str:
        semantic = self._format_activity_semantic()
        if semantic:
            return f"--- INTERNAL ACTIVITY LOG ---\n{semantic}\n--- END ACTIVITY LOG ---"
        return ""

    def _fetch_memory(self, user_msg: str, temporal_focus: str = "recent") -> str:
        try:
            results = self.associative_memory.get_relevant_with_neighbors(
                query=user_msg, user_id=self.fm.cognitive_loop.user_id,
                limit=5, max_neighbors_per_memory=5, temporal_focus=temporal_focus,
            )
            if not results:
                older = self._progressive_memory_search(user_msg)
                return "MEMORIAS:\n" + "\n".join([f"- {m}" for m in older[:5]]) if older else ""
            # LTP Hebbiana
            self._reinforce_memories(results[:3])
            print(f"   [Memory] Recuperadas {len(results)} memorias" if results else "   [Memory] Sin resultados")
            return self.associative_memory.build_context_block(results, max_total_chars=1500, max_neighbor_chars=300)
        except Exception as e:
            print(f"   [!] Error en _fetch_memory: {e}")
            return ""

    def _reinforce_memories(self, memories):
        ids_to_update, metas_to_update = [], []
        for r in memories:
            meta = r.get("metadata", {}) or {}
            nueva_imp = min(1.0, meta.get("importance", 0.5) + 0.05)
            metas_to_update.append({**meta, "importance": nueva_imp})
            ids_to_update.append(r["primary_id"])
        if ids_to_update:
            try:
                self.fm.associative_memory._em.collection.update(ids=ids_to_update, metadatas=metas_to_update)
            except Exception:
                pass

    def _fetch_web(self, user_msg: str) -> str:
        results = self.fm.maintenance._search_web(user_msg)
        return f"INTERNET:\n{results[:400]}" if results else ""

    def _fetch_files(self, _) -> str:
        uploads_dir = ENTITY_DATA_DIR / "uploads"
        if uploads_dir.exists():
            files = sorted(uploads_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
            return f"ARCHIVOS SUBIDOS: {', '.join([f.name for f in files[:5]])}" if files else ""
        return ""

    def _progressive_memory_search(self, query: str, block_size: int = 10) -> list:
        history = self.fm.cognitive_loop.last_history
        if not history:
            return []
        keywords = self.fm.fast.extract_keywords(query, 3, use_llm=True)
        if not keywords:
            return []
        results = []
        for i in range(0, len(history), block_size):
            for entry in history[i:i + block_size]:
                if any(kw.lower() in entry.get("text", "").lower() for kw in keywords):
                    results.append(entry["text"])
                    if len(results) >= 5:
                        return results
        return results[:5]

    # ============================================
    # UTILIDADES
    # ============================================

    def _time_context(self) -> str:
        try:
            from core.perception.time_perception import get_time_context
            return get_time_context(None) or "No disponible"
        except Exception:
            return "No disponible"

    def _somatic_text(self) -> str:
        markers = getattr(self.fm, '_active_somatic_markers', [])
        if markers:
            return "\n".join([f"- {m['origen']}: {m['sesgo_atencional']} (fuerza: {m['fuerza']:.1f})" for m in markers[-5:]])
        return "Neutral."

    def _executive_text(self) -> str:
        active = self.fm.stream.active[:5]
        topic = active[0].content[:80] if active else "Conversación general"
        return f"Tema actual: {topic}\nEmoción: {self.fm._last_emotion or 'neutral'}\nConfianza: {self.fm._last_confidence or 0.5:.0%}"

    def _get_user_name(self) -> str:
        try:
            profile = self.fm.cognitive_loop.user_memory.load_profile()
            return profile.get("datos_personales", {}).get("nombre") or "el usuario"
        except Exception:
            return "el usuario"

    def _speech_text(self, persona: dict, name: str) -> str:
        examples = persona.get("speech_examples", [])
        if not examples:
            return ""
        return "\n\n".join([f'Input: "{ex["user"]}"\n{name}: "{ex["assistant"]}"' for ex in examples[:2]])

    def _clean_reflexion(self, reflexion: str) -> str:
        if not reflexion:
            return ""
        # Eliminar etiquetas XML residuales
        reflexion = re.sub(r'<[^>]+>', '', reflexion)
        # Eliminar bloques --- REGION --- y --- END REGION ---
        reflexion = re.sub(r'---\s*\w+\s*---', '', reflexion)
        # Eliminar marcadores de monólogo
        for marker in [r'\[PRAGMÁTICA\].*', r'\[KEYWORDS\].*', r'\[PATRÓN\].*', r'\[REFLEXIÓN\]:\s*']:
            reflexion = re.sub(marker, '', reflexion)
        # Eliminar frases de meta-análisis
        reflexion = re.sub(r'(?:Entiendo|Debo|Puedo|Debo decidir|Mi identidad|Mi capacidad|Excelente|No esperaba)\s[^.]*\.', '', reflexion)
        # Colapsar múltiples saltos de línea
        reflexion = re.sub(r'\n{3,}', '\n\n', reflexion)
        return reflexion.strip()

    def _check_contradiction(self, response_text: str, user_msg: str) -> str:
        try:
            contradictions = self.fm.associative_memory._em.get_relevant_with_contradiction(
                response_text, user_id=self.fm.cognitive_loop.user_id, limit=2
            )
            if contradictions:
                return f"Posible contradicción con: {contradictions[0][:150]}"
        except Exception:
            pass
        return ""

    def _post_process_response(self, response_text, message, name):
        if contradiction := self._check_contradiction(response_text, message):
            print(f"   [Contradicción] Detectada: {contradiction[:100]}")
        if self.fm._detect_personality_break(response_text):
            print("   ⚠️ Respuesta anómala detectada.")
        threading.Thread(target=self.fm.maintenance._prediction_check, args=(message, response_text), daemon=True).start()

    # ============================================
    # KALMAN
    # ============================================

    def _update_kalman(self, message: str):
        intensity = min(1.0, len(message) / 500.0)
        has_question = 0.8 if "?" in message else 0.2
        observation = np.array([intensity, has_question])
        predicted_state = self._kalman_state
        predicted_cov = self._kalman_cov + np.eye(2) * 0.01
        kalman_gain = predicted_cov @ np.linalg.inv(predicted_cov + np.eye(2) * 0.1)
        self._kalman_state = predicted_state + kalman_gain @ (observation - predicted_state)
        self._kalman_cov = (np.eye(2) - kalman_gain) @ predicted_cov