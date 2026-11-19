"""CognitiveLoop: Orquestador principal de la arquitectura Sibelium (MVC)."""
import json
import threading
from datetime import datetime
from pathlib import Path

from core.memory.episodic_memory import EpisodicMemory
from core.memory.self_memory import SelfMemory
from core.memory.user_memory import UserMemory
from core.flow.flow_manager import FlowManager
from config import ENTITY_DATA_DIR, PERSONA_FILE
from core.gliner_singleton import get_gliner


class CognitiveLoop:
    """Orquestador principal. Coordina FlowManager, memoria e historial."""

    def __init__(self, user_id: str = "default", start_flow: bool = True):
        self.user_id = user_id
        self.user_dir = ENTITY_DATA_DIR / "memory" / "users" / user_id
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.user_dir / "history.json"
        self.interaction_count_path = self.user_dir / "interaction_count.json"

        # Memorias
        self.episodic_memory = EpisodicMemory()
        self.user_memory = UserMemory(user_id=user_id)
        self.self_memory = SelfMemory()

        # Estado
        self.last_state = None
        self.last_thoughts_current = []
        self.last_history = []
        self.short_term_history = []
        self.interaction_count = self._load_interaction_count()
        
        self._load_history_from_disk()

        # Inicializar FlowManager (ahora recibe la instancia de gliner)
        self.flow_manager = FlowManager(self, gliner_model=get_gliner())
        if start_flow:
            self.flow_manager.start()

    # ============================================
    # PERSISTENCIA BÁSICA
    # ============================================

    def _get_short_term_history(self, persona_name: str, user_name: str) -> str:
        """Devuelve el historial reciente para el prompt."""
        if not self.short_term_history:
            return "[Conversación recién iniciada.]"
        lines = []
        # Solo los últimos 4 mensajes (2 turnos) para no saturar al 8B
        for entry in self.short_term_history[-4:]:
            role = persona_name if entry["role"] == "assistant" else user_name
            lines.append(f"{role}: {entry['text'][:200]}")
        return "\n".join(lines)

    def _update_short_term_history(self, message: str, response: str):
        self.short_term_history.append({"role": "user", "text": message})
        self.short_term_history.append({"role": "assistant", "text": response})
        if len(self.short_term_history) > 10: # Mantener un buffer de 5 turnos
            self.short_term_history = self.short_term_history[-10:]

    def _load_history_from_disk(self):
        try:
            if self.history_path.exists():
                stored = json.loads(self.history_path.read_text(encoding="utf-8"))
                self.last_history = stored.get("history", []) or []
                self.last_thoughts_current = stored.get("thought_history", []) or []
                self.last_state = stored.get("cognitive_state")
                
                # Cargar el historial corto desde los últimos mensajes del disco
                for entry in self.last_history[-10:]:
                    self.short_term_history.append({
                        "role": entry.get("role", "user"),
                        "text": entry.get("text", "")
                    })
        except Exception as e:
            print(f"⚠️ No se pudo cargar el historial: {e}")
            self._reset_state()

    def _save_history_to_disk(self):
        try:
            safe_state = {
                "timestamp": datetime.now().isoformat(),
                "current_message": self.last_state.get("current_interaction", {}).get("message") if self.last_state else None,
            }

            self.history_path.write_text(json.dumps({
                "history": self.last_history[-100:],
                "thought_history": self.last_thoughts_current[-20:],
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
        self.last_thoughts_current = []
        self.last_state = None
        self.short_term_history = []

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
            "personality_desc": "Una presencia serena y analítica.",
            "output_constraints": [],
            "llm_sampling_params": {}
        }
        
    def _get_persona_name(self) -> str:
        try:
            return self.load_persona().get("name", "Entidad")
        except:
            return "Entidad"

    # ============================================
    # PROCESO PRINCIPAL (MVC)
    # ============================================

    def process(self, message: str) -> dict:
        now = datetime.now()
        self.interaction_count += 1
        self._save_interaction_count()

        # 1. Generar respuesta a través del FlowManager (Intérprete -> Ejecutor)
        result = self.flow_manager.handle_user_message(message)
        response = result.get("response", "")
        if not response or not response.strip():
            response = "Lo siento, tuve un problema al procesar mi respuesta."

        # 2. Actualizar historial corto
        self._update_short_term_history(message, response)

        # 3. Guardar en historial largo (Para el frontend)
        self.last_history.append({"role": "user", "text": message, "timestamp": now.isoformat()})
        self.last_history.append({"role": "assistant", "text": response, "timestamp": now.isoformat()})
        
        # 4. Guardar en disco
        self._save_history_to_disk()

        # 5. Actualizar estado
        self.last_thoughts_current = result.get("thought_history", [])
        self.last_state = {"current_interaction": {"message": message, "timestamp": now.isoformat()}}

        # 6. Guardar en memoria episódica (ChromaDB)
        try:
            self.episodic_memory.store_interaction(message, response, user_id=self.user_id)
        except Exception as e:
            print(f"⚠️ Error guardando en memoria episódica: {e}")

        return {
            "response": response,
            "thought_history": self.last_thoughts_current,
            "cognitive_state": self.last_state,
        }

    # ============================================
    # API PÚBLICA (Para el Frontend)
    # ============================================

    def get_last_state(self):
        return self.last_state

    def get_last_thoughts(self):
        return self.last_thoughts_current

    def get_history(self):
        return self.last_history

    def reset(self):
        """Reinicia toda la memoria de la entidad para esta sesión."""
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