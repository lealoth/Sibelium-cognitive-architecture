"""CognitiveLoop: Orquestador principal de la arquitectura cognitiva Sibelium."""
import json
import threading
from datetime import datetime
from pathlib import Path

from core.memory.episodic_memory import EpisodicMemory
from core.memory.self_memory import SelfMemory
from core.memory.user_memory import UserMemory
from core.models.cognitive_state import CognitiveState, Interaction
from core.perception.time_perception import get_time_context
from core.perception.user_analysis import analyze_user_message
from core.llm import LLMModel
from core.flow.flow_manager import FlowManager
from config import ENTITY_DATA_DIR, PERSONA_FILE

REFLECTION_INTERVAL = 5


class CognitiveLoop:
    """Orquestador principal. Coordina FlowManager, memoria y post-procesos."""

    def __init__(self, user_id: str = "default", start_flow: bool = True):
        self.user_id = user_id
        self.user_dir = ENTITY_DATA_DIR / "memory" / "users" / user_id
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.user_dir / "history.json"
        self.interaction_count_path = self.user_dir / "interaction_count.json"
        self.conversation_summary = ""

        # Memorias (UserMemory recibe user_id)
        self.episodic_memory = EpisodicMemory()
        self.user_memory = UserMemory(user_id=user_id)
        self.self_memory = SelfMemory()

        # Estado
        self.last_state = None
        self.last_thoughts_current = []
        self.last_thoughts_history = []
        self.last_history = []
        self.interaction_count = self._load_interaction_count()
        self._load_history_from_disk()

        # FlowManager
        self.flow_manager = FlowManager(self)
        if start_flow:
            self.flow_manager.start()

        # Cargar short_term_history desde history.json
        self.short_term_history = []
        if self.last_history:
            # Tomar los últimos 8 mensajes (4 intercambios)
            for entry in self.last_history[-8:]:
                self.short_term_history.append({
                    "role": entry.get("role", "user"),
                    "text": entry.get("text", "")[:200]
                })

    # ============================================
    # PERSISTENCIA
    # ============================================

    # Nuevo método:
    def _get_short_term_history(self, persona_name: str, user_name: str) -> str:
        if not self.short_term_history:
            return "[Conversación recién iniciada.]"
        lines = []
        for entry in self.short_term_history[-8:]:
            role = persona_name if entry["role"] == "assistant" else user_name
            lines.append(f"{role}: {entry['text'][:200]}")
        return "\n".join(lines)

    def _update_short_term_history(self, message: str, response: str):
        self.short_term_history.append({"role": "user", "text": message})
        self.short_term_history.append({"role": "assistant", "text": response})
        if len(self.short_term_history) > 8:
            self.short_term_history = self.short_term_history[-8:]

    def _load_history_from_disk(self):
        try:
            if self.history_path.exists():
                stored = json.loads(self.history_path.read_text(encoding="utf-8"))
                self.last_history = stored.get("history", []) or []
                self.last_thoughts_history = stored.get("thought_history", []) or []
                self.last_thoughts_current = []
                self.last_state = stored.get("cognitive_state")
        except Exception as e:
            print(f"⚠️ No se pudo cargar el historial: {e}")
            self._reset_state()

    def _save_history_to_disk(self):
        try:
            safe_state = {
                "persona_name": self.last_state.get("persona", {}).get("name"),
                "current_message": self.last_state.get("current_interaction", {}).get("message"),
                "timestamp": self.last_state.get("current_interaction", {}).get("timestamp"),
                "recent_summary": self.last_state.get("recent_summary", ""),
                "time_context": self.last_state.get("time_context", ""),
            } if self.last_state else None

            self.history_path.write_text(json.dumps({
                "history": self.last_history[-100:],
                "thought_history": self.last_thoughts_history,
                "cognitive_state": safe_state,
                "interaction_count": self.interaction_count,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"⚠️ No se pudo guardar el historial: {e}")

    def _load_interaction_count(self):
        try:
            if self.interaction_count_path.exists():
                return json.loads(self.interaction_count_path.read_text(encoding="utf-8")).get("count", 0)
        except:
            pass
        return 0

    def _save_interaction_count(self):
        self.interaction_count_path.parent.mkdir(parents=True, exist_ok=True)
        self.interaction_count_path.write_text(json.dumps({"count": self.interaction_count}))

    def _reset_state(self):
        self.last_history = []
        self.last_thoughts_history = []
        self.last_thoughts_current = []
        self.last_state = None

    # ============================================
    # PERSONA
    # ============================================

    def load_persona(self) -> dict:
        if PERSONA_FILE.exists() and PERSONA_FILE.read_text(encoding="utf-8").strip():
            return json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
        return self._default_persona()

    def _default_persona(self) -> dict:
        return {
            "name": "Sibelium",
            "personality_desc": "Una presencia serena y analítica que siempre busca comprender antes de responder.",
            "traits": {
                "openness": 0.8, "conscientiousness": 0.9, "extraversion": 0.5,
                "agreeableness": 0.7, "neuroticism": 0.3,
                "expressiveness_base": 0.5, "emotion_directness_base": 0.6,
            },
            "behavior_rules": {
                "formality": "casual", "verbosity": "medium", "conflict_style": "assertive",
                "self_disclosure_level": "medium", "initiation_style": "proactive",
                "exclamation_threshold": 0.6, "emotion_direct_threshold": 0.5,
            },
            "language_rules": {
                "forbidden_words": [],
                "signature_phrases": [],
                "prefer_implicit_over_explicit": False,
            },
        }

    # ============================================
    # PROCESO PRINCIPAL
    # ============================================

    def process(self, message: str) -> dict:
        now = datetime.now()
        self.interaction_count += 1
        self._save_interaction_count()

        persona = self.load_persona()
        analysis = analyze_user_message(message)
        user_profile = self.user_memory.load_profile()
        self_profile = self.self_memory.load_state()
        recent_summary = self._get_recent_summary()

        cognitive_state = CognitiveState(
            persona=persona,
            user_perception={**user_profile, "last_analysis": analysis},
            self_perception=self_profile,
            time_context=get_time_context(user_profile.get("relacion", {}).get("ultimo_contacto")),
            current_interaction=Interaction(message=message, timestamp=now.isoformat()),
            relevant_memories=[],
            recent_summary=recent_summary,
        )

        # 1. Generar respuesta (PRIMERO)
        result = self.flow_manager.handle_user_message(message)
        response = result.get("response", "") if result else ""
        if not response or not response.strip():
            response = "Lo siento, me quedé sin palabras."

        # 2. Actualizar historial corto SINCRÓNICAMENTE
        self._update_short_term_history(message, response)

        # 3. Usar result (YA está definido)
        self.last_thoughts_current = result.get("thought_history", []) if result else []
        if not self.last_thoughts_current:
            self.last_thoughts_current = [t.to_dict() for t in self.flow_manager.stream.active[:5]]
        self.last_state = cognitive_state.model_dump()
        self.flow_manager.update_last_message_time()

        return_result = {
            "response": response,
            "thought_history": self.last_thoughts_current,
            "cognitive_state": self.last_state,
        }

        # 4. Post-procesamiento DIFERIDO (Hilo Secundario)
        threading.Thread(
            target=self._deferred_post_process,
            args=(message, response, analysis, cognitive_state, now),
            daemon=True
        ).start()

        return return_result

    def _deferred_post_process(self, message: str, response: str, analysis: dict, cognitive_state, now):
        """Consolidación diferida asíncrona (Hipocampo). No bloquea la respuesta."""
        try:
            # 1. Post-procesamiento original (percepción, estado, memoria)
            self._post_process(message, response, analysis, cognitive_state, now)

            # 2. Actualizar grafo (NetworkX PageRank)
            # self.flow_manager.stream._auto_link_all()

            # 3. Actualizar estrés cognitivo para el Mediador Talámico
            if hasattr(self.flow_manager, '_get_context_entropy'):
                entropy = self.flow_manager._get_context_entropy()
                stress = 1.0 - entropy
                self.flow_manager.llm.set_cognitive_stress(stress)

            self._update_short_term_history(message, response)
            outcome = self.evaluate_conversational_outcome(message, response)
            self.consolidate_conversational_learning(message, response, outcome)

        except Exception as e:
            print(f"⚠️ Error en post-procesamiento diferido: {e}")

    def _get_recent_summary(self) -> str:
        recent = self.last_history[-6:]
        if not recent:
            return ""
        
        persona_name = self._get_persona_name()
        
        return " | ".join([
            f"{persona_name if e['role'] == 'assistant' else 'Usuario'}: {e['text']}"
            for e in recent
        ])

    def _get_persona_name(self) -> str:
        try:
            return self.load_persona().get("name", "Entidad")
        except:
            return "Entidad" 

    # ============================================
    # POST-PROCESOS
    # ============================================

    def _post_process(self, message: str, response: str, analysis: dict, cognitive_state, now):
        if len(response) < 80:
            return False

        if self._is_anomaly(response):
            print("⚠️ Anomalía detectada. Post-procesos omitidos.")
            return

        try:
            self.user_memory.update_profile(message, analysis)
            self._update_user_perception(message, analysis)
            self.self_memory.adjust_state(message, response)
        except Exception as e:
            print(f"⚠️ Error en memorias: {e}")

        if (self.interaction_count % REFLECTION_INTERVAL == 0
                or self._detect_important_moment(message, response)):
            print("🤔 Reflexión de aprendizaje...")
            self._reflect_and_learn(cognitive_state, response)

        self.last_history.append({"role": "user", "text": message, "timestamp": now.isoformat()})
        self.last_history.append({"role": "assistant", "text": response, "timestamp": now.isoformat()})
        self.last_thoughts_history.append({
            "timestamp": now.isoformat(),
            "user_message": message[:100],
            "thoughts": self.last_thoughts_current
        })
        if len(self.last_thoughts_history) > 20:
            self.last_thoughts_history = self.last_thoughts_history[-20:]

        try:
            self._save_history_to_disk()
        except Exception as e:
            print(f"⚠️ Error guardando historial: {e}")

        self._update_conversation_summary(message, response)

        # Limpiar respuesta de bloques de formato antes de almacenar
        import re
        cleaned_response = re.sub(r'---\s*\w+\s*---', '', response)
        cleaned_response = cleaned_response.strip()


        try:
            self.episodic_memory.store_interaction(message, cleaned_response, user_id=self.user_id)
        except Exception as e:
            print(f"⚠️ Error guardando en memoria episódica: {e}")

        print("🏁 Post-procesos completados")

    def _is_anomaly(self, response: str) -> bool:
        # Desactivado: la prevención de anomalías se maneja desde los prompts
        return False

    def _detect_important_moment(self, message, response):
        prompt = f"""<system_identity>
Eres el detector de momentos importantes.
</system_identity>

<interaction>
Mensaje: "{message[:200]}"
</interaction>

<evaluation_directive>
¿Esta interacción merece una reflexión inmediata sobre cambios de personalidad?
Responde SI o NO.
</evaluation_directive>"""
        result = LLMModel.get_instance().generate(prompt, temperature=0.1, max_tokens=3, purpose="detectar_importancia")
        return "SI" in result.upper()

    # ============================================
    # APRENDIZAJE Y PERCEPCIÓN
    # ============================================

    def _reflect_and_learn(self, cognitive_state, last_response):
        llm = LLMModel.get_instance()
        user_msg = cognitive_state.current_interaction.message

        prompt = f"""<system_identity>
Eres el sistema de reflexión y aprendizaje.
</system_identity>

<recent_interaction>
Mensaje del usuario: "{user_msg}"
Tu respuesta: "{last_response}"
</recent_interaction>

<current_state>
Tu estado actual: {cognitive_state.self_perception.get('estado_actual', {})}
</current_state>

<reflection_directive>
Evalúa si debes ajustar tu personalidad:
¿Detectas alguna solicitud implícita o explícita de cambio en tu forma de ser?
¿Has notado que te adaptas al estilo del usuario?
¿Ha cambiado la forma en que te diriges al usuario o él a ti? ¿Usas algún apodo o nombre distinto?

Responde en JSON exacto:
{{"should_change": true/false, "type": "directo/mimetismo/ninguno", "rasgo": "...", "direccion": "...", "intensidad": 0.0-1.0, "deteccion": "...", "nombres_usados": {{"yo": "...", "usuario": "..."}}}}
</reflection_directive>"""
        try:
            result = llm.generate(prompt, temperature=0.5, max_tokens=200, purpose="reflexion_aprendizaje")
            import re as _re
            json_match = _re.search(r'\{.*\}', result, _re.DOTALL)
            if not json_match:
                return

            data = json.loads(json_match.group(0))

            if data.get("should_change") and data.get("type") != "ninguno":
                self.self_memory.register_observation(
                    observation_type=data["type"],
                    detection=data.get("deteccion", ""),
                    rasgo=data["rasgo"],
                    direccion=data["direccion"],
                    intensidad=data.get("intensidad", 0.3),
                )
                print(f"   📝 Observación: {data['rasgo']} → {data['direccion']}")
                for change in self.self_memory.evaluate_pending_changes():
                    print(f"   🔄 Cambio pendiente: {change['rasgo']} ({change['observaciones_count']} obs)")

            nombres = data.get("nombres_usados", {})
            if nombres:
                self._register_names(nombres)
        except Exception as e:
            print(f"⚠️ Error en reflexión: {e}")

    def _register_names(self, nombres: dict):
        nombre_usuario = nombres.get("usuario", "").strip()
        nombre_yo = nombres.get("yo", "").strip()
        
        contexto = self._get_recent_summary()
        llm = LLMModel.get_instance()
        
        persona_name = self._get_persona_name()
        
        if nombre_usuario and len(nombre_usuario) > 1:
            if not self._is_valid_name(nombre_usuario):
                return
            
            prompt = f"""<system_identity>
Eres el validador de nombres.
</system_identity>

<name_to_validate>
En una conversación, alguien llamó al usuario así: "{nombre_usuario}"
</name_to_validate>

<conversation_context>
{contexto}
</conversation_context>

<evaluation_directive>
¿Es esto un nombre propio, apodo, o forma personal de llamar a alguien?
Responde SOLO SI o NO.
</evaluation_directive>"""
            result = llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="validar_nombre")
            if "SI" in result.upper():
                profile = self.user_memory.load_profile()
                apodos = profile.get("datos_personales", {}).get("apodos", [])
                if nombre_usuario.lower() not in [a.get("nombre", "").lower() for a in apodos]:
                    apodos.append({"nombre": nombre_usuario, "origen": "entidad", "fecha": datetime.now().isoformat()})
                    profile["datos_personales"]["apodos"] = apodos
                    self.user_memory.save_profile(profile)
                    print(f"   📝 {persona_name} llama al usuario: {nombre_usuario}")

        if nombre_yo and len(nombre_yo) > 1:
            if not self._is_valid_name(nombre_yo):
                return
            
            prompt = f"""<system_identity>
Eres el validador de nombres.
</system_identity>

<name_to_validate>
En una conversación, alguien usó este término para referirse a {persona_name}: "{nombre_yo}"
</name_to_validate>

<conversation_context>
{contexto}
</conversation_context>

<evaluation_directive>
¿Es esto un nombre propio, apodo, o forma personal de llamar a alguien?
Responde SOLO SI o NO.
</evaluation_directive>"""
            result = llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="validar_nombre")
            if "SI" in result.upper():
                state = self.self_memory.load_state()
                if "apodos_propios" not in state:
                    state["apodos_propios"] = []
                if nombre_yo.lower() not in [a.get("nombre", "").lower() for a in state["apodos_propios"]]:
                    state["apodos_propios"].append({"nombre": nombre_yo, "fecha": datetime.now().isoformat()})
                    self.self_memory.save_state(state)
                    print(f"   📝 {persona_name} recibe el apodo: {nombre_yo}")

    def _is_valid_name(self, name: str) -> bool:
        """Filtra nombres inválidos por estructura, no por contenido."""
        name = name.strip()
        
        if len(name) < 2:
            return False
        
        if len(name) > 25:
            return False
        
        if len(name.split()) > 4:
            return False
        
        if len(name) == 1:
            return False
        
        return True

    def _update_user_perception(self, message: str, analysis: dict):
        profile = self.user_memory.load_profile()
        old_impresion = profile.get("comportamiento_observado", {}).get("impresion_general", "")
        llm = LLMModel.get_instance()

        prompt = f"""<system_identity>
Eres el analizador de percepción de usuario.
</system_identity>

<previous_perception>
{old_impresion[:100]}
</previous_perception>

<new_data>
Último mensaje: "{message[:150]}"
Intención: {analysis.get('intention', '')}
Emoción: {analysis.get('emotion', '')}
</new_data>

<generation_directive>
Describe al usuario en UNA frase breve (máximo 120 caracteres).
Sé específico y personal. No repitas frases anteriores.
</generation_directive>"""

        try:
            nueva = llm.generate(prompt, temperature=0.5, max_tokens=60, purpose="percepcion_usuario").strip()
            # Truncar a 200 caracteres máximo
            nueva = nueva[:200].rsplit('.', 1)[0] if len(nueva) > 120 else nueva
            
            if nueva and nueva != old_impresion:
                if "historial_percepciones" not in profile:
                    profile["historial_percepciones"] = []
                profile["historial_percepciones"].append({
                    "fecha": datetime.now().isoformat(),
                    "anterior": old_impresion[:150],
                    "nueva": nueva
                })
                if len(profile["historial_percepciones"]) > 10:
                    profile["historial_percepciones"] = profile["historial_percepciones"][-10:]

            profile["comportamiento_observado"]["impresion_general"] = nueva
            profile["comportamiento_observado"]["temas_interes"] = analysis.get("topics", "")[:80]
            profile["comportamiento_observado"]["ultimo_analisis"] = {
                "intencion": analysis.get("intention", ""),
                "emocion": analysis.get("emotion", ""),
                "fecha": datetime.now().isoformat()
            }
            self.user_memory.save_profile(profile)
        except Exception as e:
            print(f"   ⚠️ Error en percepción: {e}")

    # ============================================
    # API PÚBLICA
    # ============================================

    def get_last_state(self):
        return self.last_state

    def get_last_thoughts(self):
        return self.last_thoughts_current

    def get_history(self):
        return self.last_history

    def reset(self):
        self.user_memory.reset_profile()
        self.self_memory.reset_state()
        self.episodic_memory.reset()
        self._reset_state()
        self.interaction_count = 0
        try:
            self.history_path.write_text(json.dumps({
                "history": [], "thought_history": [], "cognitive_state": None, "interaction_count": 0
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Error al reiniciar: {e}")

    def _update_conversation_summary(self, message: str, response: str):
        """Mantiene un resumen progresivo de la conversación con etiquetas semánticas."""
        if not self.conversation_summary:
            self.conversation_summary = f"Usuario: {message[:100]}\nEntidad: {response[:100]}"
            return
        
        try:
            llm = LLMModel.get_instance()
            
            prompt = f"""Resumen anterior:
    {self.conversation_summary}

    Nuevo intercambio:
    Usuario: {message[:150]}
    Entidad: {response[:150]}

    Actualiza el resumen. Máximo 300 caracteres.
    Resumen actualizado:"""
            
            self.conversation_summary = llm.generate(prompt, temperature=0.2, max_tokens=150, purpose="interpretar")
            
            tags_prompt = f"Resumen: {self.conversation_summary}\n\nExtrae 2-3 etiquetas temáticas (una palabra cada una).\nEtiquetas:"
            tags = llm.generate(tags_prompt, temperature=0.1, max_tokens=15, purpose="interpretar")
            self.conversation_summary += f" [Tags: {tags.strip()}]"
        except:
            pass

    def evaluate_conversational_outcome(self, user_message: str, assistant_response: str) -> dict:
        """Analizador de Recompensa Conversacional basado en embeddings."""
        try:
            msg_emb = self.flow_manager.stream._get_embedding(user_message)
            if msg_emb is None:
                return {"outcome": "implicit_success", "feedback": "Sin señal.", "importance": 0.4}
            
            import numpy as np
            msg_arr = np.array(msg_emb)
            msg_norm = msg_arr / max(np.linalg.norm(msg_arr), 1e-8)
            
            # Vectores de sentimiento (multilingües)
            positive_anchor = self.flow_manager.stream._get_embedding(
                "excelente buen trabajo correcto gracias funciona perfecto bien hecho exactly great thanks perfect"
            )
            negative_anchor = self.flow_manager.stream._get_embedding(
                "mal error no funciona equivocado incorrecto no sirve pésimo wrong bad incorrect"
            )
            
            if positive_anchor and negative_anchor:
                pos_arr = np.array(positive_anchor)
                neg_arr = np.array(negative_anchor)
                pos_norm = pos_arr / max(np.linalg.norm(pos_arr), 1e-8)
                neg_norm = neg_arr / max(np.linalg.norm(neg_arr), 1e-8)
                
                sim_positive = float(np.dot(msg_norm, pos_norm))
                sim_negative = float(np.dot(msg_norm, neg_norm))
                
                if sim_negative > sim_positive and sim_negative > 0.5:
                    return {"outcome": "prediction_error", "feedback": "El usuario rechazó la respuesta.", "importance": 0.7}
                elif sim_positive > sim_negative and sim_positive > 0.5:
                    return {"outcome": "success", "feedback": "Respuesta bien recibida.", "importance": 0.6}
            
            # Si no hay señal clara
            is_correction = any(ind in user_message.lower() for ind in ["no es", "corrige", "en realidad"])
            if is_correction:
                return {"outcome": "prediction_error", "feedback": "Corrección detectada.", "importance": 0.7}
            
            return {"outcome": "implicit_success", "feedback": "Continuidad sin señal clara.", "importance": 0.4}
        except Exception:
            return {"outcome": "implicit_success", "feedback": "Error en evaluación.", "importance": 0.4}

    def consolidate_conversational_learning(self, user_message: str, assistant_response: str, outcome: dict):
        """Consolida aprendizaje conversacional. Solo éxitos van a ChromaDB."""
        if outcome["outcome"] == "prediction_error":
            from core.flow.flow_stream import ThoughtItem
            self.flow_manager.stream.add_thought(ThoughtItem(
                content=f"[Error de predicción] {outcome['feedback'][:200]}",
                thought_type="error_feedback", priority=0.85, source="conversational_learning"
            ))
            return
        
        learning_content = f"APRENDIZAJE CONVERSACIONAL\nUsuario: {user_message[:300]}\nRespuesta: {assistant_response[:300]}\nFeedback: {outcome['feedback']}"
        try:
            self.episodic_memory.store_interaction(
                user_message="[Aprendizaje conversacional]",
                assistant_response=learning_content,
                user_id=self.user_id,
                metadata={
                    "source": "conversational_learning",
                    "type": "validated_interaction",
                    "outcome": outcome.get("outcome", ""),
                    "importance": outcome.get("importance", 0.5),
                }
            )
        except Exception as e:
            print(f"⚠️ Error guardando en memoria episódica: {e}")

    def process_action_outcome(self, action_result, context_intent: str, source: str = "generic"):
        """
        Procesa el resultado de cualquier acción (conversación, código, dibujo, etc.)
        usando el EnvironmentController universal.
        """
        from core.environment_controller import controller
        
        outcome = controller.evaluate_outcome(action_result, context_intent)
        
        if outcome == "DOPAMINERGIC_REWARD":
            # Consolidar en episodic_memory
            self.episodic_memory.store_interaction(
                user_message=f"[Acción validada] {source}",
                assistant_response=f"Resultado exitoso: {str(action_result.output)[:500]}",
                user_id=self.user_id,
                metadata={
                    "source": "action_learning",
                    "type": "validated_action",
                    "environment": source,
                    "success": True,
                    "importance": 0.7,
                }
            )
        elif outcome in ("PREDICTION_ERROR", "CRITICAL_FAILURE"):
            # Inyectar en working_memory, NO guardar en ChromaDB
            from core.flow.flow_stream import ThoughtItem
            self.flow_manager.stream.add_thought(ThoughtItem(
                content=f"[Error] {source}: {action_result.error[:200]}",
                thought_type="error_feedback",
                priority=0.85,
                source="action_learning"
            ))


    def _distill_to_semantic(self):
        """
        Filtro de Destilación (Sistema #35).
        Promueve aprendizajes de episodic_memory a semantic_library
        solo si el mismo principio aparece en 3+ contextos diferentes.
        """
        try:
            # Buscar aprendizajes validados recientes
            results = self.episodic_memory.collection.query(
                query_texts=["aprendizaje validado"],
                n_results=20,
                where={"type": "validated_learning"}
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            
            if len(docs) < 3:
                return
            
            # Agrupar por similitud semántica
            embeddings = []
            for doc in docs:
                emb = self.flow_manager.stream._get_embedding(doc[:500])
                if emb:
                    embeddings.append(emb)
            
            if len(embeddings) < 3:
                return
            
            import numpy as np
            
            # Buscar grupos de 3+ aprendizajes con alta similitud entre sí
            for i in range(len(embeddings) - 2):
                group = [i]
                for j in range(i + 1, len(embeddings)):
                    a = np.array(embeddings[i]) / max(np.linalg.norm(embeddings[i]), 1e-8)
                    b = np.array(embeddings[j]) / max(np.linalg.norm(embeddings[j]), 1e-8)
                    sim = np.dot(a, b)
                    if sim > 0.85:  # Mismo principio abstracto
                        group.append(j)
                
                if len(group) >= 3:
                    # Verificar que son de contextos diferentes (archivos distintos)
                    files = [metas[idx].get("file_affected", "") for idx in group if idx < len(metas)]
                    unique_files = set(files)
                    
                    if len(unique_files) >= 2:  # Al menos 2 archivos diferentes
                        # Promover a semantic_library
                        principle = docs[group[0]][:600]
                        self.episodic_memory.store_semantic(
                            content=f"[Principio validado multi-contexto]\n{principle}",
                            metadata={
                                "source": "distillation",
                                "type": "abstract_principle",
                                "evidence_count": len(group),
                                "source_files": ", ".join(unique_files),
                                "importance": 0.85,
                            }
                        )
                        print(f"   [Destilación] Principio promovido a semantic_library ({len(group)} evidencias, {len(unique_files)} archivos).")
                        return
        except Exception as e:
            print(f"   [!] Error en destilación: {e}")