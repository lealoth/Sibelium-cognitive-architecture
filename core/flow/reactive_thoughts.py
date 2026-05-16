"""Micro-pensamientos algorítmicos de reacción inmediata (Sistema 1 / Subcortical)."""
from datetime import datetime
from typing import Optional


class ReactiveThoughts:
    """Gatillos de Alerta Somática. Generan marcadores, no texto."""

    @staticmethod
    def on_confidence_change(old_val: float, new_val: float) -> Optional[dict]:
        diff = new_val - old_val
        if abs(diff) <= 0.15:
            return None
        if diff > 0:
            return {
                "origen": "subcortical_confianza",
                "sesgo_atencional": "MAYOR_ASERTIVIDAD",
                "fuerza": min(1.0, diff * 3),
            }
        else:
            return {
                "origen": "subcortical_confianza",
                "sesgo_atencional": "AUTOCRITICA_REVISION",
                "fuerza": min(1.0, abs(diff) * 3),
            }

    @staticmethod
    def on_emotion_change(old_emotion: str, new_emotion: str) -> Optional[dict]:
        if old_emotion == new_emotion:
            return None
        return {
            "origen": "subcortical_emocion",
            "sesgo_atencional": "CAMBIO_AFECTIVO",
            "fuerza": 0.6,
            "detalle": f"{old_emotion}->{new_emotion}"
        }

    @staticmethod
    def on_long_silence(minutes: float) -> Optional[dict]:
        if minutes <= 30:
            return None
        return {
            "origen": "subcortical_silencio",
            "sesgo_atencional": "MODO_RELACION_CON_RECUERDOS",
            "fuerza": min(1.0, minutes / 120),
        }

    @staticmethod
    def on_time_marker(hour: int) -> Optional[dict]:
        markers = {
            6: ("DESPERTAR_PROGRESIVO", 0.5),
            12: ("CENIT_ATENCIONAL", 0.6),
            20: ("INTROSPECCION_CREPUSCULAR", 0.7),
            0: ("INTROSPECCION_PROFUNDA", 0.9),
        }
        if hour in markers:
            sesgo, fuerza = markers[hour]
            return {
                "origen": "ritmo_circadiano",
                "sesgo_atencional": sesgo,
                "fuerza": fuerza,
            }
        return None

    @staticmethod
    def on_user_typing() -> dict:
        return {
            "origen": "subcortical_interaccion",
            "sesgo_atencional": "ATENCION_INMEDIATA",
            "fuerza": 0.8,
        }

    @staticmethod
    def on_file_appears(filename: str) -> dict:
        return {
            "origen": "subcortical_novedad",
            "sesgo_atencional": "CURIOSIDAD_EXPLORATORIA",
            "fuerza": 0.7,
            "detalle": filename,
        }