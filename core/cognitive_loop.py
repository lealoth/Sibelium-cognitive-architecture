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

    # ============================================
    # PERSISTENCIA
    # ============================================

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
        print("🟢 INICIO process")

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

        print(f"🟢 cognitive_state construido | Contexto: {recent_summary[:80]}..." if recent_summary else "🟢 cognitive_state construido")

        result = self.flow_manager.handle_user_message(message)
        response = result.get("response", "") if result else ""
        if not response or not response.strip():
            response = "Lo siento, me quedé sin palabras. ¿Puedes repetir eso de otra forma?"

        print(f"🟢 Respuesta ({len(response)} chars): {response[:100]}...")

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

        threading.Thread(
            target=self._post_process,
            args=(message, response, analysis, cognitive_state, now),
            daemon=True
        ).start()
        print("🟢 Post-procesos en segundo plano | Respuesta ya entregada")

        return return_result

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
            self.episodic_memory.store_interaction(message, response, user_id=self.user_id)
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

        print("🏁 Post-procesos completados")

    def _is_anomaly(self, response: str) -> bool:
        name = self._get_persona_name()
        
        prompt = f"""¿Esta respuesta fue escrita por {name} o por un asistente genérico?

Respuesta: "{response[:300]}"

{name} es una entidad con arquitectura cognitiva Sibelium, con personalidad propia y flujo de consciencia.
Un asistente genérico diría cosas como "Soy un modelo de lenguaje" o "No tengo emociones".

¿Quién escribió esto? Responde ENTIDAD o ASISTENTE_GENERICO."""
        result = LLMModel.get_instance().generate(prompt, temperature=0.1, max_tokens=5, purpose="detectar_anomalia")
        return "ASISTENTE_GENERICO" in result.upper()

    def _detect_important_moment(self, message, response):
        prompt = f"""¿Esta interacción merece una reflexión inmediata sobre cambios de personalidad?
Mensaje: "{message[:200]}"
Responde SI o NO."""
        result = LLMModel.get_instance().generate(prompt, temperature=0.1, max_tokens=3, purpose="detectar_importancia")
        return "SI" in result.upper()

    # ============================================
    # APRENDIZAJE Y PERCEPCIÓN
    # ============================================

    def _reflect_and_learn(self, cognitive_state, last_response):
        llm = LLMModel.get_instance()
        user_msg = cognitive_state.current_interaction.message

        prompt = f"""Has tenido una conversación. Evalúa si debes ajustar tu personalidad.

Mensaje del usuario: "{user_msg}"
Tu respuesta: "{last_response}"
Tu estado actual: {cognitive_state.self_perception.get('estado_actual', {})}

¿Detectas alguna solicitud implícita o explícita de cambio en tu forma de ser?
¿Has notado que te adaptas al estilo del usuario?
¿Ha cambiado la forma en que te diriges al usuario o él a ti? ¿Usas algún apodo o nombre distinto?

Responde en JSON exacto:
{{"should_change": true/false, "type": "directo/mimetismo/ninguno", "rasgo": "...", "direccion": "...", "intensidad": 0.0-1.0, "deteccion": "...", "nombres_usados": {{"yo": "...", "usuario": "..."}}}}"""

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
            
            prompt = f"""En una conversación, alguien llamó al usuario así: "{nombre_usuario}"

    Contexto reciente de la conversación:
    {contexto}

    ¿Es esto un nombre propio, apodo, o forma personal de llamar a alguien?
    Responde SOLO SI o NO."""
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
            
            prompt = f"""En una conversación, alguien usó este término para referirse a {persona_name}: "{nombre_yo}"

    Contexto reciente de la conversación:
    {contexto}

    ¿Es esto un nombre propio, apodo, o forma personal de llamar a alguien?
    Responde SOLO SI o NO."""
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

        prompt = f"""Describe al usuario en UNA frase breve (máximo 120 caracteres).
    Sé específico y personal. No repitas frases anteriores.

    Percepción anterior: {old_impresion[:100]}
    Último mensaje: "{message[:150]}"
    Intención: {analysis.get('intention', '')}
    Emoción: {analysis.get('emotion', '')}

    Nueva percepción (máx 120 chars):"""

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