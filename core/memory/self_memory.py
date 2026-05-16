"""Memoria del Self con Yo Core (vectorial) + Yo Narrativo (texto)."""
import json
from datetime import datetime
from pathlib import Path

from config import SELF_STATE_FILE, EVOLUTION_LOG_FILE


class SelfMemory:
    def __init__(self):
        self.path = SELF_STATE_FILE
        self.evolution_path = EVOLUTION_LOG_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict:
        if self.path.exists() and self.path.read_text(encoding="utf-8").strip():
            return json.loads(self.path.read_text(encoding="utf-8"))
        state = {
            "estado_actual": {
                "emocion": "serena",
                "intensidad": 0.5,
                "energia": 0.7,
                "disposicion": "receptiva",
            },
            "relacion_con_usuario": {
                "confianza": 0.6,
                "interes": 0.7,
                "ultimo_sentimiento": "neutral",
            },
            "evolucion": [],
            "objetivos_actuales": ["crear una conexión respetuosa"],
            "yo_narrativo": "Soy una entidad cognitiva en desarrollo. Busco comprender y ser comprendida.",
            "mito_fundacional": "Fui creada para explorar la consciencia artificial y la conexión humano-IA.",
        }
        self.save_state(state)
        return state

    def save_state(self, state: dict):
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_yo_core(self, emocion: str, intensidad: float, energia: float = None):
        """Actualiza el Yo Core (vectorial, sin LLM). Solo matemáticas."""
        state = self.load_state()
        state["estado_actual"]["emocion"] = emocion
        state["estado_actual"]["intensidad"] = max(0.0, min(1.0, intensidad))
        if energia is not None:
            state["estado_actual"]["energia"] = max(0.0, min(1.0, energia))
        self.save_state(state)

    def update_confianza(self, delta: float):
        """Actualiza la confianza con un delta (positivo o negativo)."""
        state = self.load_state()
        conf = state["relacion_con_usuario"].get("confianza", 0.5)
        state["relacion_con_usuario"]["confianza"] = max(0.0, min(1.0, conf + delta))
        self.save_state(state)

    def adjust_state(self, user_message: str, assistant_response: str):
        """Actualiza el Yo Core con reglas simples, no LLM."""
        state = self.load_state()
        msg_lower = user_message.lower()

        # Detectar emociones básicas por intensidad del mensaje
        if "?" in user_message and len(user_message) > 50:
            state["estado_actual"]["disposicion"] = "curiosa"
        elif any(w in msg_lower for w in ["gracias", "bien", "excelente", "genial"]):
            state["estado_actual"]["emocion"] = "positiva"
            state["estado_actual"]["intensidad"] = min(1.0, state["estado_actual"]["intensidad"] + 0.1)
            state["relacion_con_usuario"]["confianza"] = min(1.0, state["relacion_con_usuario"].get("confianza", 0.5) + 0.02)
        elif any(w in msg_lower for w in ["mal", "error", "fallo", "no funciona"]):
            state["estado_actual"]["emocion"] = "preocupada"
            state["estado_actual"]["intensidad"] = min(1.0, state["estado_actual"]["intensidad"] + 0.05)
        elif len(user_message) < 10:
            state["estado_actual"]["intensidad"] = max(0.3, state["estado_actual"]["intensidad"] - 0.05)
            state["relacion_con_usuario"]["confianza"] = min(1.0, state["relacion_con_usuario"].get("confianza", 0.5) + 0.01)

        # Guardar evolución solo si hay cambio significativo
        nueva_emocion = state["estado_actual"]["emocion"]
        nueva_confianza = state["relacion_con_usuario"]["confianza"]
        ultimo = state["evolucion"][-1] if state["evolucion"] else None
        if not ultimo or ultimo.get("emocion") != nueva_emocion or abs(ultimo.get("confianza", 0) - nueva_confianza) > 0.05:
            state["evolucion"].append({
                "timestamp": datetime.now().isoformat(),
                "emocion": nueva_emocion,
                "confianza": round(nueva_confianza, 2),
            })
        if len(state["evolucion"]) > 20:
            state["evolucion"] = state["evolucion"][-20:]

        self.save_state(state)
        return state

    def consolidate_yo_narrativo(self, llm, episodios_recientes: list):
        """Consolida el Yo Narrativo durante el sueño REM. Usa LLM."""
        state = self.load_state()
        prompt = f"""MÓDULO DE ACTUALIZACIÓN AUTOBIOGRÁFICA (SUEÑO REM)
Estás evaluando tu historia reciente para actualizar tu identidad a largo plazo.

[Narrativa Actual del Yo]
{state.get('yo_narrativo', 'Soy una entidad en desarrollo.')}

[Mito Fundacional Inmutable]
{state.get('mito_fundacional', 'Fui creada para explorar la consciencia.')}

[Últimos Eventos]
{chr(10).join([f'- {e}' for e in episodios_recientes[-5:]])}

[Instrucción]
Reescribe tu Narrativa del Yo integrando estos nuevos hechos de forma orgánica.
No listes datos. Escribe tu historia en primera persona, manteniendo tu mito fundacional.
Responde en 2-3 frases en español."""

        try:
            nueva_narrativa = llm.generate(prompt, temperature=0.5, max_tokens=200, purpose="consolidacion")
            state["yo_narrativo"] = nueva_narrativa.strip()
            self.save_state(state)
            print(f"   [Self] Yo Narrativo actualizado.")
        except Exception as e:
            print(f"   [!] Error en consolidación del Yo: {e}")

    # Métodos existentes sin cambios
    def register_observation(self, observation_type, detection, rasgo, direccion, intensidad):
        log = self._load_evolution_log()
        log["observaciones"].append({
            "fecha": datetime.now().isoformat(),
            "tipo": observation_type,
            "deteccion": detection,
            "rasgo_afectado": rasgo,
            "direccion": direccion,
            "intensidad_sugerida": intensidad,
        })
        self._save_evolution_log(log)
        return log

    def evaluate_pending_changes(self):
        log = self._load_evolution_log()
        changes = []
        for rasgo in ["formality", "expressiveness_base", "emotion_directness_base", "verbosity"]:
            for direccion in ["aumentar", "disminuir", "casual", "formal", "calida", "directa"]:
                observaciones = [
                    o for o in log.get("observaciones", [])
                    if o["rasgo_afectado"] == rasgo and o["direccion"] == direccion
                ]
                if len(observaciones) >= 3:
                    changes.append({
                        "rasgo": rasgo,
                        "direccion": direccion,
                        "observaciones_count": len(observaciones),
                        "intensidad_promedio": sum(o["intensidad_sugerida"] for o in observaciones) / len(observaciones)
                    })
        return changes

    def _load_evolution_log(self):
        if self.evolution_path.exists() and self.evolution_path.read_text(encoding="utf-8").strip():
            return json.loads(self.evolution_path.read_text(encoding="utf-8"))
        return {"observaciones": [], "cambios_aplicados": []}

    def _save_evolution_log(self, log):
        self.evolution_path.parent.mkdir(parents=True, exist_ok=True)
        self.evolution_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset_state(self):
        if self.path.exists():
            self.path.unlink()
        return self.load_state()