"""Extracción y validación de patrones desde reflexiones del LLM."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from config import DETECTORS_LOG_FILE


# ============================================
# VALIDADOR
# ============================================

class PatternValidator:
    """Evalúa si un patrón extraído es seguro y útil."""

    def __init__(self):
        self.FORBIDDEN_PATTERNS: List[str] = []
        self.SENSITIVE_PATTERNS: List[str] = []
        self._load_rules()

    def _load_rules(self):
        try:
            from config import PERSONA_FILE
            if PERSONA_FILE.exists():
                persona = json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
                rules = persona.get("validation_rules", {})
                self.FORBIDDEN_PATTERNS = rules.get("forbidden_patterns", [])
                self.SENSITIVE_PATTERNS = rules.get("sensitive_patterns", [])
        except Exception:
            pass

    def validate(self, condition_text: str, reaction_text: str) -> tuple:
        cond = condition_text.lower()
        react = reaction_text.lower()

        for forbidden in self.FORBIDDEN_PATTERNS:
            if forbidden in cond or forbidden in react:
                return False, f"Palabra prohibida: '{forbidden}'", False

        requires_supervision = any(s in cond or s in react for s in self.SENSITIVE_PATTERNS)

        if len(condition_text) < 15:
            return False, "Condición demasiado vaga", False
        if react in cond:
            return False, "Patrón circular", False

        return True, "Aprobado", requires_supervision


# ============================================
# PERÍODO DE PRUEBA
# ============================================

class SupervisedPatternTrial:
    """Período de prueba para patrones sensibles."""

    def __init__(self, detector: dict, trial_hours: int = 24):
        self.detector = detector
        self.trial_start = datetime.now()
        self.trial_period = timedelta(hours=trial_hours)
        self.true_positives = 0
        self.false_positives = 0

    def record(self, context, was_relevant: bool):
        if was_relevant:
            self.true_positives += 1
        else:
            self.false_positives += 1

    def is_complete(self) -> bool:
        return datetime.now() - self.trial_start > self.trial_period

    def evaluate(self) -> tuple:
        total = self.true_positives + self.false_positives
        if total < 5:
            return False, "Datos insuficientes"
        precision = self.true_positives / total
        if precision < 0.6:
            return False, f"Precisión baja: {precision:.0%}"
        return True, f"Precisión aceptable: {precision:.0%}"

    @staticmethod
    def check_relevance(condition: str, reaction: str, ctx: str) -> bool:
        from core.llm import LLMModel
        prompt = f"""¿Este patrón es relevante ahora?
Patrón: "{condition} -> {reaction}"
Contexto: {ctx[:200]}
Responde UTIL o INUTIL."""
        result = LLMModel.get_instance().generate(prompt, temperature=0.3, max_tokens=10)
        return "UTIL" in result.upper()


# ============================================
# EXTRACTOR DE PATRONES
# ============================================

class PatternExtractor:
    """Extrae patrones de reflexiones y los convierte en detectores."""

    def __init__(self):
        self.active_detectors: List[dict] = []
        self.trial_detectors: List[SupervisedPatternTrial] = []
        self.validator = PatternValidator()
        self._loaded = False
        self._detector_rotation = 0

    # ============================================
    # CARGA / GUARDADO
    # ============================================

    def _load_detectors(self):
        if self._loaded:
            return
        self._loaded = True

        if not DETECTORS_LOG_FILE.exists():
            print("   [Pattern] 0 detectores cargados.")
            return

        try:
            data = json.loads(DETECTORS_LOG_FILE.read_text(encoding="utf-8"))
            cleaned = self._deduplicate_loaded(data)
            for item in cleaned:
                d = self._create_detector(item["condition_text"], item["reaction_text"])
                if d:
                    d["times_triggered"] = item.get("times_triggered", 0)
                    d["active"] = item.get("active", True)
                    d["created_at"] = datetime.fromisoformat(item["created_at"])
                    d["hebb_strength"] = item.get("hebb_strength", 1.0)
                    self.active_detectors.append(d)
            print(f"   [Pattern] {len(self.active_detectors)} cargados, {len(data) - len(cleaned)} redundantes eliminados.")
            self._save()
        except Exception as e:
            print(f"   [!] Error cargando detectores: {e}")

    def _save(self):
        data = [{
            "condition_text": d["condition_text"],
            "reaction_text": d["reaction_text"],
            "created_at": d["created_at"].isoformat(),
            "times_triggered": d["times_triggered"],
            "active": d["active"],
            "hebb_strength": d.get("hebb_strength", 1.0)
        } for d in self.active_detectors]
        DETECTORS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        DETECTORS_LOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ============================================
    # CREACIÓN
    # ============================================

    def _create_detector(self, condition: str, reaction: str) -> Optional[dict]:
        return {
            "condition_text": condition,
            "reaction_text": reaction,
            "created_at": datetime.now(),
            "times_triggered": 0,
            "active": True,
            "hebb_strength": 1.0,
            "_condition_embedding": None
        }

    def analyze_reflection(self, reflection_text: str) -> Optional[dict]:
        from core.llm import LLMModel
        llm = LLMModel.get_instance()

        prompt = f"""Durante tu reflexión escribiste:
"{reflection_text[:500]}"

¿Identificaste algún patrón repetitivo?
- CONDICION: (qué debe cumplirse)
- REACCIÓN: (qué pensamiento generar)
Si no hay patrón: SIN_PATRON"""

        result = llm.generate(prompt, temperature=0.4, max_tokens=100, purpose="extraer_patron")
        if "SIN_PATRON" in result.upper():
            return None

        condition, reaction = self._parse_rule(result)
        if not condition or not reaction:
            return None

        if self._is_duplicate(condition):
            print(f"   [Pattern] Descartado (duplicado): {condition[:60]}")
            return None

        ok, msg, supervised = self.validator.validate(condition, reaction)
        if not ok:
            print(f"   [Pattern] Rechazado: {msg}")
            return None

        detector = self._create_detector(condition, reaction)
        if detector is None:
            return None

        if supervised:
            print(f"   [Pattern] En prueba: {condition[:60]}")
            self.trial_detectors.append(SupervisedPatternTrial(detector))
        else:
            self.active_detectors.append(detector)
            self._save()
            print(f"   [Pattern] Aprobado: {condition[:60]}")

        return detector

    def _parse_rule(self, text: str) -> tuple:
        condition, reaction = None, None
        for line in text.split('\n'):
            line = line.strip()
            if 'CONDICION' in line.upper():
                condition = line.split(":", 1)[-1].strip()
            elif 'REACCION' in line.upper():
                reaction = line.split(":", 1)[-1].strip()
        return condition, reaction

    # ============================================
    # DEDUPLICACIÓN
    # ============================================

    def _deduplicate_loaded(self, data: list) -> list:
        if len(data) <= 1:
            return data

        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        redundant = set()

        for i, item in enumerate(data):
            others = [d for j, d in enumerate(data) if j != i][:15]
            others_text = "\n".join([
                f"{idx+1}. {d.get('condition_text', '')[:100]} | {d.get('reaction_text', '')[:100]}"
                for idx, d in enumerate(others)
            ])
            prompt = f"""¿Este detector es FUNCIONALMENTE REDUNDANTE con alguno de la lista?
DETECTOR: "{item.get('condition_text', '')[:120]}" → "{item.get('reaction_text', '')[:120]}"
LISTA:
{others_text}
Responde SOLO SI o NO."""
            try:
                if "SI" in llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="deduplicar_detectores").upper():
                    redundant.add(i)
            except Exception:
                continue

        return [item for i, item in enumerate(data) if i not in redundant]

    def _is_duplicate(self, condition: str) -> bool:
        if not self.active_detectors:
            return False
        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        recent = self.active_detectors[-5:]
        conditions = "\n".join([f"{i+1}. {d.get('condition_text', '')[:120]}" for i, d in enumerate(recent)])
        prompt = f"""¿Alguno de estos detectores es redundante con este nuevo?
Nuevo: "{condition[:150]}"
Existentes:
{conditions}
Responde SOLO SI o NO."""
        try:
            return "SI" in llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="verificar_duplicado").upper()
        except Exception:
            return False

    # ============================================
    # EVALUACIÓN (CHECK_ALL)
    # ============================================

    def check_all(self, context: dict) -> list:
        """Evalúa detectores activos y en prueba."""
        thoughts = []
        thoughts.extend(self._check_active(context))
        thoughts.extend(self._check_trials(context))
        return thoughts

    def _check_active(self, context: dict) -> list:
        active = [d for d in self.active_detectors if d.get("active")]
        if not active:
            return []

        if len(active) >= 10:
            return self._check_batch(active, context)
        return self._check_individual(active, context)

    def _check_batch(self, detectors: list, context: dict) -> list:
        from core.flow.flow_stream import ThoughtItem
        from core.llm import LLMModel
        thoughts = []
        llm = LLMModel.get_instance()

        for batch in [detectors[i:i + 10] for i in range(0, len(detectors), 10)]:
            text = "\n".join([f"{i+1}. {d['condition_text'][:120]}" for i, d in enumerate(batch)])
            prompt = f"""Evalúa si estas condiciones se cumplen en el contexto actual.
Contexto: {context.get('active_thoughts', '')[:250]}
Mensaje: {context.get('user_msg', '')[:150]}
Emoción: {context.get('emotion', 'neutral')}

{text}

Responde SOLO los números de las que se cumplen, separados por comas, o NINGUNA."""
            result = llm.generate(prompt, temperature=0.1, max_tokens=30, purpose="evaluar_detectores_lote")
            for idx in self._parse_numbers(result, len(batch)):
                d = batch[idx]
                d["times_triggered"] = d.get("times_triggered", 0) + 1
                d["hebb_strength"] = d.get("hebb_strength", 1.0) + 0.1
                thoughts.append(ThoughtItem(
                    content=f"[Algoritmo] {d['reaction_text'][:150]}",
                    thought_type="detected_pattern", priority=0.3, source="pattern_detector"
                ))
        return thoughts

    def _check_individual(self, detectors: list, context: dict) -> list:
        from core.flow.flow_stream import ThoughtItem
        from core.llm import LLMModel
        thoughts = []
        llm = LLMModel.get_instance()

        for d in detectors[:5]:
            if not d.get("active"):
                continue
            prompt = f"""¿Se cumple esta condición?
Condición: "{d['condition_text'][:150]}"
Contexto: {context.get('active_thoughts', '')[:250]}
Responde SOLO SI o NO."""
            result = llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="evaluar_detector")
            if "SI" in result.upper():
                d["times_triggered"] = d.get("times_triggered", 0) + 1
                d["hebb_strength"] = d.get("hebb_strength", 1.0) + 0.1
                thoughts.append(ThoughtItem(
                    content=f"[Algoritmo] {d['reaction_text'][:150]}",
                    thought_type="detected_pattern", priority=0.3, source="pattern_detector"
                ))
        return thoughts

    def _check_trials(self, context: dict) -> list:
        from core.flow.flow_stream import ThoughtItem
        thoughts = []

        for trial in self.trial_detectors[:]:
            d = trial.detector
            if not d.get("active"):
                continue
            relevant = SupervisedPatternTrial.check_relevance(
                d["condition_text"], d["reaction_text"], str(context)[:200]
            )
            trial.record(context, relevant)
            if relevant:
                d["times_triggered"] = d.get("times_triggered", 0) + 1
                thoughts.append(ThoughtItem(
                    content=f"[Prueba] {d['reaction_text'][:150]}",
                    thought_type="detected_pattern", priority=0.2, source="pattern_trial"
                ))
            if trial.is_complete():
                passed, msg = trial.evaluate()
                if passed:
                    self.active_detectors.append(d)
                    self._save()
                    print(f"   [Pattern] Promovido: {d['condition_text'][:60]}")
                else:
                    print(f"   [Pattern] Descartado: {msg}")
                self.trial_detectors.remove(trial)

        return thoughts

    def _parse_numbers(self, text: str, max_idx: int) -> list:
        text = text.strip().upper()
        if "NINGUNA" in text or "NINGUNO" in text:
            return []
        import re
        return [int(n) - 1 for n in re.findall(r'\d+', text) if 1 <= int(n) <= max_idx]

    # ============================================
    # DISPARO SEMÁNTICO POR EVENTO (SISTEMA 1)
    # ============================================

    def trigger_by_event(self, thought) -> list:
        """Evalúa detectores por evento vectorial (Sistema 1 biológico)."""
        from core.flow.flow_stream import ThoughtItem
        thoughts = []

        emb = getattr(thought, '_embedding', None)
        if emb is None:
            return thoughts

        emb_arr = np.array(emb)
        emb_norm = emb_arr / max(np.linalg.norm(emb_arr), 1e-8)

        for d in self.active_detectors:
            if not d.get("active"):
                continue

            cond_emb = d.get("_condition_embedding")
            if cond_emb is None:
                cond_emb = self._get_embedding(d.get("condition_text", ""))
                if cond_emb is None:
                    continue
                d["_condition_embedding"] = cond_emb

            cond_arr = np.array(cond_emb)
            cond_norm = cond_arr / max(np.linalg.norm(cond_arr), 1e-8)
            sim = np.dot(emb_norm, cond_norm)

            if sim >= 0.82:
                d["times_triggered"] = d.get("times_triggered", 0) + 1
                d["hebb_strength"] = d.get("hebb_strength", 1.0) + 0.1
                thoughts.append(ThoughtItem(
                    content=f"[Automático] {d.get('reaction_text', '')[:150]}",
                    thought_type="detected_pattern", priority=0.35, source="pattern_detector_event"
                ))
            else:
                # LTD: debilitar detector no activado
                d["hebb_strength"] = max(0.1, d.get("hebb_strength", 1.0) - 0.01)

        return thoughts

    def _get_embedding(self, text: str) -> Optional[list]:
        try:
            from chromadb.utils import embedding_functions
            return embedding_functions.DefaultEmbeddingFunction()([text])[0]
        except Exception:
            return None

    # ============================================
    # GENERALIZACIÓN
    # ============================================

    def find_similar_pattern(self, context: dict) -> Optional[str]:
        if not self.active_detectors:
            return None
        combined = f"{context.get('active_thoughts', '')} {context.get('user_msg', '')}"
        if not combined.strip():
            return None

        for d in self.active_detectors:
            cond = set(d.get("condition_text", "").lower().split()) - {
                "me", "de", "que", "en", "el", "la", "los", "las", "un", "una",
                "y", "o", "a", "es", "por", "con", "no", "se", "su", "lo", "para",
                "del", "al", "como", "más", "pero", "si", "ya", "muy", "todo", "hay", "le"
            }
            if not cond:
                continue
            sim = sum(1 for w in cond if w in combined.lower()) / len(cond)
            if 0.3 < sim < 0.8 and d.get("times_triggered", 0) > 0:
                return f"Esto me recuerda a un patrón que aprendí: cuando {d['condition_text'][:100]}..."

        return None

    # ============================================
    # PODA
    # ============================================

    def decay_detectors(self, max_detectors: int = 30):
        """Poda Hebbiana: sobreviven los más fuertes."""
        if len(self.active_detectors) <= max_detectors:
            return

        self.active_detectors.sort(
            key=lambda d: d.get("hebb_strength", 1.0) * d.get("times_triggered", 0),
            reverse=True
        )
        removed = self.active_detectors[max_detectors:]
        self.active_detectors = self.active_detectors[:max_detectors]
        self._save()
        if removed:
            print(f"   [Pattern] Poda Hebbiana: {len(removed)} eliminados, {len(self.active_detectors)} restantes.")