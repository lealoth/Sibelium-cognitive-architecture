import json
from pathlib import Path
from datetime import datetime

from config import SELF_STATE_FILE, EVOLUTION_LOG_FILE


class SelfMemory:
    def __init__(self):
        self.path = SELF_STATE_FILE
        self.evolution_path = EVOLUTION_LOG_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self):
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
        }
        self.save_state(state)
        return state

    def save_state(self, state):
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        
    def adjust_state(self, user_message: str, assistant_response: str):
        state = self.load_state()
        
        prompt = f"""Evalúa cómo esta interacción afecta el estado emocional y la confianza.

Mensaje del usuario: "{user_message[:300]}"
Tu respuesta: "{assistant_response[:300]}"

Estado anterior:
- Emoción: {state['estado_actual'].get('emocion', 'neutral')}
- Confianza: {state['relacion_con_usuario'].get('confianza', 0.5)}

Devuelve SOLO un JSON con los nuevos valores:
{{"emocion": "positiva/negativa/neutral/defensiva/serena", "confianza": 0.0-1.0, "intensidad": 0.0-1.0, "disposicion": "receptiva/distanciada/curiosa", "objetivo": "frase corta con el objetivo actual"}}

JSON:"""
        
        try:
            from core.llm import LLMModel
            llm = LLMModel.get_instance()
            result = llm.generate(prompt, temperature=0.3, max_tokens=80, purpose="ajustar_estado")
            
            import re
            import json
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                
                # Actualizar con límites seguros
                new_confianza = max(0.0, min(1.0, data.get("confianza", state["relacion_con_usuario"]["confianza"])))
                new_intensidad = max(0.0, min(1.0, data.get("intensidad", state["estado_actual"].get("intensidad", 0.5))))
                
                state["estado_actual"]["emocion"] = data.get("emocion", state["estado_actual"]["emocion"])
                state["estado_actual"]["intensidad"] = new_intensidad
                state["estado_actual"]["disposicion"] = data.get("disposicion", state["estado_actual"].get("disposicion", "receptiva"))
                state["relacion_con_usuario"]["confianza"] = new_confianza
                state["relacion_con_usuario"]["ultimo_sentimiento"] = data.get("emocion", "neutral")
                
                if data.get("objetivo"):
                    state["objetivos_actuales"] = [data["objetivo"]]
                
                print(f"   📊 Estado ajustado: emoción={state['estado_actual']['emocion']}, confianza={new_confianza:.2f}")
        except Exception as e:
            print(f"   ⚠️ Error en adjust_state LLM: {e}, usando ajuste mínimo")
            # Fallback: ajuste neutral mínimo
            state["relacion_con_usuario"]["confianza"] = min(1.0, state["relacion_con_usuario"].get("confianza", 0.5) + 0.005)
        
        # Mantener historial
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

    def register_observation(self, observation_type, detection, rasgo, direccion, intensidad):
        """Registra una observación sobre posible cambio de personalidad."""
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
        """Evalúa si hay observaciones acumuladas que justifiquen un cambio permanente."""
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