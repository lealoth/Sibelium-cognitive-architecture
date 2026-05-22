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
        from core.inference_loop import InferenceLoop
        loop = InferenceLoop(self.fm.llm, self.fm.cognitive_loop.episodic_memory)
        response_text = loop.run(prompt, temperature=0.8, max_tokens=800, purpose="respuesta_final")

        # Detectar "Search for:" y ejecutar búsqueda web automática
        import re
        search_match = re.search(r'Search for:\s*(.+?)(?:\n|$)', response_text, re.IGNORECASE)
        if search_match:
            query = search_match.group(1).strip()
            print(f"   [WebSearch] Detectada solicitud: '{query[:80]}...'")
            try:
                from core.environment_registry import EnvironmentRegistry
                registry = EnvironmentRegistry.get_instance()
                result = registry.parse_and_execute(f'<web_search query="{query}" />')
                if result:
                    response_text += f"\n\n[Resultados de búsqueda web]:\n{result[:800]}"
                    print(f"   [WebSearch] Resultados inyectados en la respuesta.")
            except Exception as e:
                print(f"   [WebSearch] Error: {e}")

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
        
        network = needs.get("needs", "PERSONAL") if isinstance(needs, dict) else "PERSONAL"
        
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
        directives = persona.get("system_directives", {})
        if directives:
            style = directives.get("cognitive_style", "")
            constraints = directives.get("output_constraints", [])
            if style or constraints:
                prompt += f"--- OPERATIVE CONSTRAINTS ---\n"
                if style:
                    prompt += f"Style: {style}\n"
                if constraints:
                    prompt += "\n".join([f"- {c}" for c in constraints])
                prompt += f"\n--- END OPERATIVE CONSTRAINTS ---\n"

        computational = persona.get("computational_bounds", "")
        if computational:
            prompt += f"--- COMPUTATIONAL BOUNDS ---\n{computational}\n--- END COMPUTATIONAL BOUNDS ---\n"

        prompt += f"--- HISTORY ---\n{self.fm.cognitive_loop._get_short_term_history(name, user_name)}\n--- END HISTORY ---\n"

        # Secciones condicionales según macro-red
        for tag, content in fetched.items():
            if content:
                prompt += f"--- {tag} ---\n{content}\n--- END {tag} ---\n"

        if isinstance(needs, dict):
            networks_str = needs.get("needs", "PERSONAL")
        else:
            networks_str = str(needs)
        networks = [n.strip() for n in networks_str.split(",")]

        # Aprendizajes si PERSONAL está en las redes
        if "PERSONAL" in networks:
            aprendizajes = self._fetch_learnings(message)
            if aprendizajes:
                prompt += f"--- LEARNINGS ---\n{aprendizajes}\n--- END LEARNINGS ---\n"

        # Priming semántico si WORK o PERSONAL están
        if "WORK" in networks or "PERSONAL" in networks:
            semantic_context = self._fetch_semantic_context(message)
            if semantic_context:
                prompt += f"--- KNOWLEDGE ---\n{semantic_context}\n--- END KNOWLEDGE ---\n"

        try:
            confidence = self.fm.cognitive_loop.episodic_memory.calculate_query_confidence(message)
            print(f"   [Epistemic] Confidence: {confidence:.2f} | Threshold: 0.45 | Boundary: {'YES' if confidence < 0.45 else 'NO'}")
        except Exception:
            confidence = 0.5

        # Anclas de intención puras (verbos universales, sin dominio)
        opt_anchor = self.fm.stream._get_embedding(
            "optimize improve fix solve reduce enhance configure update upgrade accelerate"
        )
        insp_anchor = self.fm.stream._get_embedding(
            "explain describe how does work what is list show find query analyze"
        )

        # Vector de dominio (top 10 keywords del DomainFilter)
        domain_keywords = self.fm.domain_filter.get_keywords()[:10] if hasattr(self.fm, 'domain_filter') else []
        domain_str = " ".join(domain_keywords) if domain_keywords else ""
        domain_anchor = self.fm.stream._get_embedding(domain_str) if domain_str else None

        if opt_anchor and insp_anchor:
            msg_emb = self.fm.stream._get_embedding(message)
            msg_arr = np.array(msg_emb)
            msg_arr = msg_arr / np.linalg.norm(msg_arr)
            
            opt_arr = np.array(opt_anchor) / np.linalg.norm(opt_anchor)
            insp_arr = np.array(insp_anchor) / np.linalg.norm(insp_anchor)
            
            sim_opt = float(np.dot(msg_arr, opt_arr))
            sim_insp = float(np.dot(msg_arr, insp_arr))
            
            is_optimization_intent = (sim_opt > sim_insp) and (sim_opt > 0.38)
            
            if domain_anchor is not None:
                domain_arr = np.array(domain_anchor) / np.linalg.norm(domain_anchor)
                sim_domain = float(np.dot(msg_arr, domain_arr))
                in_domain = sim_domain > 0.45
            else:
                in_domain = True  # Sin dominio definido, asumir que todo aplica
            
            force_web_search = is_optimization_intent and in_domain
        else:
            force_web_search = False

        # Decisión final de búsqueda web
        if confidence < 0.45 or force_web_search:
            web_context = self._fetch_web_context(message)
            if web_context:
                prompt += f"""--- EXTERNAL KNOWLEDGE (web search) ---
        {web_context}
        --- END EXTERNAL KNOWLEDGE ---

        --- DIRECTIVE ---
        Compare your internal memory with the external knowledge above.
        If your internal memory only describes the current state but does not contain
        the solution, base your answer on the external knowledge.
        """
            elif confidence < 0.45:
                prompt += f"""--- EPISTEMIC BOUNDARY ---
        WARNING: No reliable records or web results. State your uncertainty.
        --- END EPISTEMIC BOUNDARY ---
        """

        recent_errors = self._get_recent_prediction_errors()
        if recent_errors:
            prompt += f"""--- RECENT CORRECTIONS (HIGH PRIORITY) ---
        {recent_errors}
        --- END CORRECTIONS ---
        """

        prompt += f"""--- USER INPUT ---
    {user_name}: "{message}"
    --- END INPUT ---

    --- DIRECTIVE ---
    Responde a {user_name}.
    1. Habla DESDE el personaje, no SOBRE tus instrucciones.
    2. Si hay INTERNAL ACTIVITY LOG, analiza esos datos para responder sobre tu actividad. Transmite los datos de forma fluida y natural, sin listar marcas de tiempo ni nombres técnicos.
    3. Cuando el usuario te pregunte sobre TI (tus pensamientos, tus emociones, tu perspectiva), responde desde TU punto de vista. No proyectes en el usuario.
    4. IDIOMA: {idioma_nombre}."""
        modifiers = self.fm.archetype.get("prompt_modifiers", [])
        if modifiers:
            for i, mod in enumerate(modifiers, start=5):
                prompt += f"{i}. {mod}\n"
        prompt +="""--- END DIRECTIVE ---"""

        print(f"   [Prompt] Red activa: {network}")
        print(f"   [Prompt] Tamaño estimado: ~{len(prompt)//4} tokens")
        secciones_activas = [tag for tag, content in fetched.items() if content]
        print(f"   [Prompt] Secciones inyectadas: {', '.join(secciones_activas) if secciones_activas else 'NINGUNA (solo base)'}")
        print(f"   [Prompt] Tamaño: ~{len(prompt)//4} tokens")
        return prompt

    def _get_recent_prediction_errors(self) -> str:
        """Recupera errores de predicción recientes del stream activo."""
        errors = []
        for t in self.fm.stream.active[-5:]:
            if getattr(t, 'type', '') == 'error_feedback':
                errors.append(t.content[:300])
        return "\n".join(errors) if errors else ""

    def _fetch_web_context(self, query: str) -> str:
        # Añadir contexto del dominio para desambiguar
        domain_context = ""
        if hasattr(self.fm, 'domain_filter'):
            keywords = self.fm.domain_filter.get_keywords()[:5]
            if keywords:
                domain_context = " ".join(keywords)
        
        search_query = f"{query} {domain_context}" if domain_context else query
        
        try:
            from ddgs import DDGS
            results = DDGS().text(search_query[:200], max_results=3)
            if results:
                snippets = []
                for r in results:
                    body = r.get("body", "")[:300]
                    if body:
                        snippets.append(body)
                result = "\n".join(snippets) if snippets else ""
                print(f"   [WebContext] Buscado: '{search_query[:60]}...' → {len(snippets)} snippets")
                return result
            print(f"   [WebContext] Buscado: '{search_query[:60]}...' → SIN RESULTADOS")
        except Exception as e:
            print(f"   [WebContext] Error: {e}")
        return ""

    def _fetch_learnings(self, message: str) -> str:
        """Recupera aprendizajes conversacionales previos (top 2, máx 300 chars)."""
        try:
            episodic = self.fm.cognitive_loop.episodic_memory
            results = episodic.collection.query(
                query_texts=[message[:300]],
                n_results=2,
                where={"type": "validated_interaction"}
            )
            docs = results.get("documents", [[]])[0]
            if docs:
                return "\n---\n".join([d[:300] for d in docs])
        except Exception:
            pass
        return ""

    def _fetch_semantic_context(self, message: str) -> str:
        """Busca conocimiento relevante en semantic_library."""
        try:
            episodic = self.fm.cognitive_loop.episodic_memory
            results = episodic.query_semantic(query=message[:500], n_results=3)
            if results:
                return "\n---\n".join([r["content"][:400] for r in results])
        except Exception:
            pass
        return ""
    # ============================================
    # ROUTER + FETCH
    # ============================================

    def _build_router_profiles(self) -> dict:
        """
        Construye perfiles de ruteo dinámicos basados en el ecosistema de la entidad.
        Sin hardcodeo. Se adapta al rol, herramientas y colecciones de cada entidad.
        """
        persona = self.fm.cognitive_loop.load_persona()
        name = persona.get("name", "Entidad")
        personality = persona.get("personality_desc", "")
        role_type = persona.get("role_type", "")
        capabilities = persona.get("capabilities", [])
        epistemic = persona.get("epistemic_bounds", "")
        
        profiles = {
            "PERSONAL": [
                "quién eres tú, tu nombre, tu identidad, autoconciencia y estados de ánimo",
                "nuestra conversación, mi relación contigo, tus pensamientos internos",
                personality[:200] if personality else f"personalidad de {name}",
            ],
            "WORK": [
                "ejecutar mi tarea principal, mi rol asignado, lógica, análisis y razonamiento complejo",
                "resolver el problema planteado, procesar la información técnica de mi especialidad",
            ],
            "EXTERNAL": [
                "buscar información fuera, usar herramientas externas, interactuar con el entorno",
                "internet, búsqueda web, noticias, consulta externa, archivos externos",
            ],
        }
        
        # Inyectar por tipo de rol (dinámico, sin if/else masivo)
        role_keywords = {
            "self_engineer": [
                "código fuente, refactorización de funciones, bugs, algoritmos y scripts",
                "análisis de arquitectura de software, archivos del repositorio, métodos y clases",
                "optimización de rendimiento, complejidad algorítmica, token usage",
            ],
            "researcher": [
                "análisis de papers, documentación técnica, teoría y conceptos abstractos",
                "metodología científica, revisión de literatura, hipótesis y conclusiones",
            ],
            "data_analyst": [
                "análisis estadístico, bases de datos, gráficos, métricas y archivos CSV",
                "procesamiento de datos cuantitativos, tendencias y modelos predictivos",
            ],
        }
        
        if role_type in role_keywords:
            profiles["WORK"].extend(role_keywords[role_type])
        
        # Inyectar por capabilities (genérico, sin hardcodeo)
        capability_keywords = {
            "code_reading": "código fuente, archivos Python, lectura de scripts y módulos",
            "code_analysis": "análisis de código, bugs, refactorización, optimización",
            "file_indexing": "indexación de archivos, fragmentos de código, documentación",
            "research": "investigación, papers, documentación técnica, teoría",
            "conversation": "conversación, diálogo, interacción con el usuario, preguntas y respuestas",
        }
        
        for cap in capabilities:
            if cap in capability_keywords:
                profiles["WORK"].append(capability_keywords[cap])
        
        # Inyectar por herramientas registradas (EXTERNAL dinámico)
        try:
            from core.environment_registry import EnvironmentRegistry
            registry = EnvironmentRegistry.get_instance()
            for tool_name in registry.registered_tools:
                profiles["EXTERNAL"].append(f"usar la herramienta {tool_name}")
        except Exception:
            pass
        
        # Inyectar epistemic_bounds como contexto WORK
        if epistemic:
            profiles["WORK"].append(epistemic[:200])
        
        return profiles

    def _decide_info_needs(self, user_msg: str, context: str = "") -> dict:
        """Router por Multi-Ejemplares con Max-Pooling y Umbral Adaptativo."""
        profiles = self._build_router_profiles()
        
        try:
            msg_emb = self.fm.stream._get_embedding(user_msg)
            if msg_emb is None:
                return {"needs": "PERSONAL", "temporal_focus": "recent"}
            
            import numpy as np
            import math
            
            msg_arr = np.array(msg_emb)
            msg_norm = msg_arr / max(np.linalg.norm(msg_arr), 1e-8)
            
            if not hasattr(self, '_exemplar_cache'):
                self._exemplar_cache = {}
            
            scores = {}
            for network, exemplars in profiles.items():
                network_scores = []
                for ex in exemplars:
                    cache_key = f"{network}:{ex[:80]}"
                    if cache_key not in self._exemplar_cache:
                        ex_emb = self.fm.stream._get_embedding(ex)
                        if ex_emb is None:
                            continue
                        ex_arr = np.array(ex_emb)
                        ex_norm = ex_arr / max(np.linalg.norm(ex_arr), 1e-8)
                        self._exemplar_cache[cache_key] = ex_norm
                    
                    ex_norm = self._exemplar_cache[cache_key]
                    sim = float(np.dot(msg_norm, ex_norm))
                    network_scores.append(sim)
                
                scores[network] = max(network_scores) if network_scores else 0.0
            
            # Umbral Adaptativo por Entropía
            activated = self._dynamic_threshold(scores)
            
            print(f"   [Router] \"{user_msg}...\"")
            print(f"   [Router] Scores: " + " | ".join([f"{k}:{v:.2f}" for k, v in scores.items()]))
            print(f"   [Router] Activados: {', '.join(activated)}")
            
            from core.memory.episodic_memory import determinar_temporal_focus
            temporal_focus = determinar_temporal_focus(user_msg)
            
            needs_str = ", ".join(activated)
            return {"needs": needs_str, "temporal_focus": temporal_focus}
        
        except Exception:
            return {"needs": "PERSONAL", "temporal_focus": "recent"}


    def _dynamic_threshold(self, scores: dict) -> list:
        """
        Umbral Adaptativo basado en Entropía de Shannon.
        - Alta entropía (scores similares) → umbral bajo → más redes activadas
        - Baja entropía (ganador claro) → umbral alto → solo la red dominante
        
        Fórmula: τ = α_max - (H_norm × (α_max - α_min))
        """
        import numpy as np
        import math
        
        networks = list(scores.keys())
        raw_scores = np.array(list(scores.values()))
        
        # Softmax con temperatura T=0.1 para acentuar diferencias
        T = 0.1
        e_scores = np.exp(raw_scores / T)
        probs = e_scores / np.sum(e_scores)
        
        # Entropía de Shannon
        entropy = -np.sum(probs * np.log2(probs + 1e-9))
        
        # Entropía normalizada (máx para N=3 es log2(3) ≈ 1.585)
        max_entropy = math.log2(len(networks))
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        # Umbral dinámico: α_min=0.35, α_max=0.60
        alpha_min = 0.35
        alpha_max = 0.60
        threshold = alpha_max - (norm_entropy * (alpha_max - alpha_min))
        
        # Activar redes que superen el umbral
        activated = [net for net, score in scores.items() if score >= threshold]
        
        # Si ninguna supera, activar la de mayor score
        if not activated:
            activated = [max(scores, key=scores.get)]
        
        return activated

    def _fetch_info(self, needed: dict, user_msg: str) -> dict:
        networks = needed.get("needs", ["PERSONAL"])
        if isinstance(networks, str):
            networks = [n.strip() for n in networks.split(",")]
        
        temporal_focus = needed.get("temporal_focus", "recent")
        fetched = {}
        
        for network in networks:
            if network == "PERSONAL":
                fetched["SELF"] = self._fetch_self(user_msg)
                fetched["USER"] = self._fetch_user(user_msg)
                fetched["MEMORY"] = self._fetch_memory(user_msg, temporal_focus)
            elif network == "WORK":
                fetched["MEMORY"] = self._fetch_memory(user_msg, temporal_focus)
                fetched["SEMANTIC"] = self._fetch_semantic_context(user_msg)
                fetched["CODE"] = self._fetch_code_context(user_msg)
            elif network == "EXTERNAL":
                fetched["WEB"] = self._fetch_web(user_msg)
                fetched["FILE"] = self._fetch_files(user_msg)
        
        return fetched

    def _fetch_code_context(self, user_msg: str) -> str:
        """Busca fragmentos de código en procedural_index con firmas pre-digeridas."""
        try:
            episodic = self.fm.cognitive_loop.episodic_memory
            results = episodic.query_procedural(user_msg, n_results=3)
            if results:
                fragmentos = []
                for r in results:
                    code = r.get('code', '')
                    # Extraer firmas para pre-digestión
                    signatures = self._extract_signatures(code)
                    fragmentos.append(
                        f"[{r.get('file', '')} - {r.get('function', '')} (L{r.get('line_range', '')})]:\n"
                        f"{signatures}\n"
                        f"---\n"
                        f"{code}"
                    )
                return "\n\n".join(fragmentos)
        except Exception:
            pass
        return ""

    def _extract_signatures(self, code_fragment: str) -> str:
        """Extrae firmas de métodos y clases de un fragmento de código."""
        import re
        signatures = []
        for line in code_fragment.split('\n'):
            stripped = line.strip()
            if stripped.startswith('def ') or stripped.startswith('class '):
                signatures.append(stripped[:120])
        if signatures:
            return "Available signatures:\n" + "\n".join(signatures)
        return ""
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
        """
        Recupera memorias con vecindad asociativa (Sistema #33) y foco temporal modulado.
        Incluye LTP Hebbiana: refuerza importancia de las memorias inyectadas.
        """
        try:
            results = self.associative_memory.get_relevant_with_neighbors(
                query=user_msg,
                user_id=self.fm.cognitive_loop.user_id,
                limit=5,
                max_neighbors_per_memory=5,
                temporal_focus=temporal_focus,
            )
            if not results:
                older = self._progressive_memory_search(user_msg)
                if older:
                    fragmentos = [m[:400] for m in older[:3]]
                    return "<episodic_memory>\n" + "\n---\n".join(fragmentos) + "\n</episodic_memory>"
                return ""

            # LTP Hebbiana: reforzar importancia de las 3 memorias inyectadas
            memorias_inyectadas = results[:3]
            ids_a_actualizar = []
            metadatas_a_actualizar = []
            
            for r in memorias_inyectadas:
                meta = r.get("metadata", {}) or {}
                importancia_actual = meta.get("importance", 0.5)
                nueva_imp = min(1.0, importancia_actual + 0.05)
                nueva_meta = {**meta, "importance": nueva_imp}
                ids_a_actualizar.append(r["primary_id"])
                nueva_meta["last_accessed"] = datetime.now().isoformat()
                metadatas_a_actualizar.append(nueva_meta)
            
            if ids_a_actualizar:
                try:
                    em = self.fm.associative_memory._em
                    em.collection.update(ids=ids_a_actualizar, metadatas=metadatas_a_actualizar)
                except Exception:
                    pass

            # Top 3-5 fragmentos, máximo 400 chars cada uno
            fragmentos = []
            for r in results[:5]:
                texto = r["primary"] if isinstance(r, dict) else r
                fragmentos.append(texto[:400])

            return "<episodic_memory>\n" + "\n---\n".join(fragmentos) + "\n</episodic_memory>"

        except Exception as e:
            print(f"   [!] Error en _fetch_memory asociativa: {e}")
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
        examples = persona.get("speech_examples", "")
        if not examples:
            return ""
        # Si es un string simple, devolverlo tal cual
        if isinstance(examples, str):
            return examples
        # Si es una lista de dicts (formato antiguo)
        if isinstance(examples, list) and examples:
            return "\n\n".join([
                f'Input: "{ex.get("user", "")}"\n{name}: "{ex.get("assistant", "")}"'
                for ex in examples[:2]
            ])
        return ""

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