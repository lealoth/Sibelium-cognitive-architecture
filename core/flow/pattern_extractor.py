"""Extracción y validación de patrones desde reflexiones del LLM."""
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from config import DETECTORS_LOG_FILE

class PatternValidator:
    """Evalúa si un patrón extraído es seguro y útil."""
    def __init__(self):
        self._load_validation_rules()
    
    def _load_validation_rules(self):
        try:
            from config import PERSONA_FILE
            if PERSONA_FILE.exists():
                persona = json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
                rules = persona.get("validation_rules", {})
                self.FORBIDDEN_PATTERNS = rules.get("forbidden_patterns", [])
                self.SENSITIVE_PATTERNS = rules.get("sensitive_patterns", [])
                return
        except:
            pass
        
        # Fallback por defecto
        self.FORBIDDEN_PATTERNS = []
        self.SENSITIVE_PATTERNS = []
    
    def validate(self, condition_text: str, reaction_text: str):
        condition_lower = condition_text.lower()
        reaction_lower = reaction_text.lower()
        
        for forbidden in self.FORBIDDEN_PATTERNS:
            if forbidden in condition_lower or forbidden in reaction_lower:
                return False, f"Contiene palabra prohibida: '{forbidden}'", False
        
        requires_supervision = False
        for sensitive in self.SENSITIVE_PATTERNS:
            if sensitive in condition_lower or sensitive in reaction_lower:
                requires_supervision = True
                break
        
        if len(condition_text) < 15:
            return False, "Condición demasiado vaga o corta", False
        
        if reaction_lower in condition_lower:
            return False, "Patrón circular detectado", False
        
        return True, "Aprobado", requires_supervision


class SupervisedPatternTrial:
    """Período de prueba para patrones sensibles."""
    
    def __init__(self, detector: dict, trial_period_hours: int = 24):
        self.detector = detector
        self.trial_start = datetime.now()
        self.trial_period = timedelta(hours=trial_period_hours)
        self.thoughts_generated: List[Dict] = []
        self.false_positives = 0
        self.true_positives = 0
    
    def record_activation(self, context, was_relevant: bool):
        self.thoughts_generated.append({
            "timestamp": datetime.now().isoformat(),
            "context": str(context)[:100],
            "was_relevant": was_relevant
        })
        if was_relevant:
            self.true_positives += 1
        else:
            self.false_positives += 1
    
    def is_trial_complete(self) -> bool:
        return datetime.now() - self.trial_start > self.trial_period
    
    def evaluate_trial(self):
        total = self.true_positives + self.false_positives
        if total < 5:
            return False, "Datos insuficientes para evaluar"
        precision = self.true_positives / total
        if precision < 0.6:
            return False, f"Precisión insuficiente: {precision:.0%}"
        return True, f"Precisión aceptable: {precision:.0%}"
    
    @staticmethod
    def check_relevance_with_llm(condition_text: str, reaction_text: str, recent_context: str) -> bool:
        from core.llm import LLMModel
        prompt = f"""Evalua si este patron es relevante ahora:
Patron: "{condition_text} -> {reaction_text}"
Contexto: {recent_context[:200]}
Responde UTIL o INUTIL."""
        llm = LLMModel.get_instance()
        result = llm.generate(prompt, temperature=0.3, max_tokens=10)
        return "UTIL" in result.upper()


class PatternExtractor:
    """Extrae patrones de reflexiones del LLM y los convierte en detectores."""
    
    def __init__(self):
        self.active_detectors = []
        self.trial_detectors = []
        self.validator = PatternValidator()
        self._loaded = False
        self._initialized = False
    
    def _load_detectors(self):
        """Carga detectores desde disco. Solo se ejecuta una vez."""
        if self._loaded:
            return
        self._loaded = True
        
        if not DETECTORS_LOG_FILE.exists():
            return
        
        try:
            data = json.loads(DETECTORS_LOG_FILE.read_text(encoding="utf-8"))
            cleaned = self._deduplicate_loaded(data)
            
            for item in cleaned:
                detector = self._create_detector(item["condition_text"], item["reaction_text"])
                if detector:
                    detector["times_triggered"] = item.get("times_triggered", 0)
                    detector["active"] = item.get("active", True)
                    detector["created_at"] = datetime.fromisoformat(item["created_at"])
                    self.active_detectors.append(detector)
            
            eliminados = len(data) - len(cleaned)
            print(f"   [Pattern] {len(self.active_detectors)} detectores cargados. {eliminados} redundantes eliminados.")
            self._save_detectors()
        except Exception as e:
            print(f"   [!] Error cargando detectores: {e}")
            
    def _deduplicate_loaded(self, data: list) -> list:
        """Elimina detectores redundantes: 1 llamada LLM por detector.
        """
        if len(data) <= 1:
            return data
        
        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        
        redundant_indices = set()
        total_comparisons = 0
        
        for i, item in enumerate(data):
            # El "resto" son todos menos este
            others = [d for j, d in enumerate(data) if j != i]
            
            # Limitar a los 15 más cercanos para no saturar el prompt
            # Priorizar los adyacentes en el tiempo (los similares tienden a crearse juntos)
            nearby = others[:15] if len(others) > 15 else others
            
            others_text = "\n".join([
                f"{idx+1}. CONDICIÓN: \"{d.get('condition_text', '')[:100]}\" | REACCIÓN: \"{d.get('reaction_text', '')[:100]}\""
                for idx, d in enumerate(nearby)
            ])
            
            prompt = f"""¿Este detector es FUNCIONALMENTE REDUNDANTE con ALGUNO de la lista?

    Un detector es redundante si ALGUNO de la lista detecta ESENCIALMENTE lo mismo y genera el MISMO tipo de reacción. Compartir un tema general (como "introspección" o "relaciones") NO es redundancia.

    DETECTOR A EVALUAR:
    - CONDICIÓN: "{item.get('condition_text', '')[:120]}"
    - REACCIÓN: "{item.get('reaction_text', '')[:120]}"

    LISTA DE COMPARACIÓN:
    {others_text}

    ¿El Detector A es redundante con ALGUNO de la lista? Responde SOLO SI o NO."""
            
            try:
                result = llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="deduplicar_detectores")
                total_comparisons += 1
                if "SI" in result.upper():
                    redundant_indices.add(i)
            except:
                total_comparisons += 1
                continue
        
        cleaned = [item for i, item in enumerate(data) if i not in redundant_indices]
        eliminados = len(data) - len(cleaned)
        
        print(f"   [Pattern] Deduplicación: {eliminados} redundantes eliminados ({total_comparisons} comparaciones, 1 por detector).")
        
        return cleaned

    def _is_duplicate(self, condition_text: str) -> bool:
        """Verifica si ya existe un detector semánticamente similar mediante LLM."""
        if not self.active_detectors:
            return False
        
        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        
        # Solo verificar contra los detectores más recientes (máximo 5)
        recent_detectors = self.active_detectors[-5:]
        
        for detector in recent_detectors:
            prompt = f"""¿Estos dos patrones detectan esencialmente lo mismo?

    Patrón existente: "{detector.get('condition_text', '')[:150]}"
    Patrón nuevo: "{condition_text[:150]}"

    ¿Son redundantes?
    Responde SOLO SI o NO."""
            
            try:
                result = llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="verificar_duplicado")
                if "SI" in result.upper():
                    return True
            except:
                continue
        
        return False

    
    def _save_detectors(self):
        """Guarda los detectores activos en disco."""
        data = []
        for d in self.active_detectors:
            data.append({
                "condition_text": d["condition_text"],
                "reaction_text": d["reaction_text"],
                "created_at": d["created_at"].isoformat(),
                "times_triggered": d["times_triggered"],
                "active": d["active"]
            })
        DETECTORS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        DETECTORS_LOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def analyze_reflection(self, reflection_text: str) -> Optional[Dict]:
        from core.llm import LLMModel
        
        prompt = f"""Durante tu reflexion, escribiste:
"{reflection_text[:500]}"

Identificaste algun patron repetitivo? Si es asi, describelo:
- CONDICION: (que debe cumplirse, en lenguaje natural)
- REACCION: (que pensamiento generar)

Si no hay patron, responde: SIN_PATRON
Regla:"""
        
        llm = LLMModel.get_instance()
        result = llm.generate(prompt, temperature=0.4, max_tokens=100, purpose="extraer_patron")
        
        if "SIN_PATRON" in result.upper():
            return None
        
        condition_text, reaction_text = self._parse_rule(result)
        if not condition_text or not reaction_text:
            return None
        
        # Verificar duplicados temáticos
        if self._is_duplicate(condition_text):
            print(f"   [Pattern] Descartado por duplicado temático: {condition_text[:60]}")
            return None
        
        approved, motivo, requires_supervision = self.validator.validate(condition_text, reaction_text)
        
        if not approved:
            print(f"   [Pattern] RECHAZADO: {motivo}")
            return None
        
        detector = self._create_detector(condition_text, reaction_text)
        if detector is None:
            return None
        
        if requires_supervision:
            print(f"   [Pattern] En prueba: {condition_text[:60]}")
            trial = SupervisedPatternTrial(detector)
            self.trial_detectors.append(trial)
        else:
            self.active_detectors.append(detector)
            self._save_detectors()
            print(f"   [Pattern] APROBADO: {condition_text[:60]}")
        
        return detector
    
    def _parse_rule(self, llm_output: str):
        condition = None
        reaction = None
        for line in llm_output.split('\n'):
            line = line.strip()
            if 'CONDICION' in line.upper():
                condition = line.split(":", 1)[-1].strip()
            elif 'REACCION' in line.upper():
                reaction = line.split(":", 1)[-1].strip()
        return condition, reaction
    
    def _create_detector(self, condition_text: str, reaction_text: str) -> Optional[Dict]:
        """Crea un detector que usa el LLM para evaluar patrones."""
        return {
            "condition_text": condition_text,
            "reaction_text": reaction_text,
            "created_at": datetime.now(),
            "times_triggered": 0,
            "active": True,
            "use_llm": True
        }
    
    def _retry_code_generation(self, faulty_code: str, error_msg: str) -> str:
        """Pide al LLM que corrija el código defectuoso."""
        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        
        prompt = f"""El siguiente código Python generó un error: {error_msg}

Código defectuoso:
{faulty_code}

Corrige el error. Escribe SOLO el código corregido, sin explicaciones.
Asegúrate de que cada línea esté completa y la sintaxis sea correcta.
Código corregido:"""
        
        return llm.generate(prompt, temperature=0.1, max_tokens=100, purpose="corregir_detector")
    
    def check_all_batch(self, context: Dict) -> list:
        """Evalúa todos los detectores en lotes para minimizar llamadas LLM.
        
        Divide los detectores en grupos de 10 para no sobrecargar el prompt.
        Cada lote se evalúa en una sola llamada LLM.
        """
        from core.flow.flow_stream import ThoughtItem
        from core.llm import LLMModel
        thoughts = []
        
        active_detectors = [d for d in self.active_detectors if d.get("active")]
        if not active_detectors:
            return thoughts
        
        # Agrupar detectores en lotes de 10
        BATCH_SIZE = 10
        batches = [active_detectors[i:i + BATCH_SIZE] for i in range(0, len(active_detectors), BATCH_SIZE)]
        
        for batch in batches:
            # Construir el prompt para el lote
            detectors_text = "\n".join([
                f"{i+1}. \"{d['condition_text'][:120]}\""
                for i, d in enumerate(batch)
            ])
            
            prompt = f"""Evalúa si estas condiciones se cumplen en el contexto actual.

    Contexto:
    - Pensamientos activos: {context.get('active_thoughts', '')[:250]}
    - Mensaje del usuario: {context.get('user_msg', '')[:150]}
    - Emoción actual: {context.get('emotion', 'neutral')}

    Condiciones a evaluar:
    {detectors_text}

    Responde SOLO con los números de las condiciones que se cumplen, separados por comas.
    Si no se cumple ninguna, responde: NINGUNA

    Números:"""
            
            result = LLMModel.get_instance().generate(
                prompt, temperature=0.1, max_tokens=30, purpose="evaluar_detectores_lote"
            )
            
            # Procesar resultados
            triggered_indices = self._parse_batch_result(result, len(batch))
            
            for idx in triggered_indices:
                if 0 <= idx < len(batch):
                    detector = batch[idx]
                    detector["times_triggered"] = detector.get("times_triggered", 0) + 1
                    thoughts.append(ThoughtItem(
                        content=f"[Algoritmo] {detector['reaction_text'][:150]}",
                        thought_type="detected_pattern",
                        priority=0.3,
                        source="pattern_detector"
                    ))
        
        # Procesar detectores en prueba (trial)
        # Los trials se evalúan individualmente porque son pocos y requieren más contexto
        for trial in self.trial_detectors[:]:
            detector = trial.detector
            if not detector.get("active"):
                continue
            
            is_relevant = SupervisedPatternTrial.check_relevance_with_llm(
                detector["condition_text"], detector["reaction_text"], str(context)[:200]
            )
            trial.record_activation(context, is_relevant)
            
            if is_relevant:
                detector["times_triggered"] = detector.get("times_triggered", 0) + 1
                thoughts.append(ThoughtItem(
                    content=f"[Prueba] {detector['reaction_text'][:150]}",
                    thought_type="detected_pattern",
                    priority=0.2,
                    source="pattern_trial"
                ))
            
            if trial.is_trial_complete():
                passed, motivo = trial.evaluate_trial()
                if passed:
                    self.active_detectors.append(detector)
                    self._save_detectors()
                    print(f"   [Pattern] PROMOVIDO: {detector['condition_text'][:60]}")
                else:
                    print(f"   [Pattern] DESCARTADO: {motivo}")
                self.trial_detectors.remove(trial)
        
        return thoughts


    def _parse_batch_result(self, result: str, max_index: int) -> list:
        """Parsea el resultado del lote y devuelve índices válidos."""
        result = result.strip().upper()
        
        if "NINGUNA" in result or "NINGUNO" in result:
            return []
        
        indices = []
        for part in result.replace(" ", "").split(","):
            try:
                idx = int(part) - 1  # Convertir a índice 0-based
                if 0 <= idx < max_index:
                    indices.append(idx)
            except ValueError:
                continue
        
        return indices


    def check_all(self, context: Dict) -> list:
        """Evalúa los detectores activos y en prueba."""
        # Si hay 10 o más detectores, usar procesamiento por lotes
        if len([d for d in self.active_detectors if d.get("active")]) >= 10:
            thoughts = self.check_all_batch(context)
        else:
            thoughts = self._check_all_individual(context)
        
        # Procesar trials (siempre, independientemente del método)
        thoughts.extend(self._check_trials(context))
        
        return thoughts


    def _check_trials(self, context: Dict) -> list:
        """Evalúa los detectores en período de prueba."""
        from core.flow.flow_stream import ThoughtItem
        thoughts = []
        
        for trial in self.trial_detectors[:]:
            detector = trial.detector
            if not detector.get("active"):
                continue
            
            is_relevant = SupervisedPatternTrial.check_relevance_with_llm(
                detector["condition_text"], detector["reaction_text"], str(context)[:200]
            )
            trial.record_activation(context, is_relevant)
            
            if is_relevant:
                detector["times_triggered"] = detector.get("times_triggered", 0) + 1
                thoughts.append(ThoughtItem(
                    content=f"[Prueba] {detector['reaction_text'][:150]}",
                    thought_type="detected_pattern",
                    priority=0.2,
                    source="pattern_trial"
                ))
            
            if trial.is_trial_complete():
                passed, motivo = trial.evaluate_trial()
                if passed:
                    self.active_detectors.append(detector)
                    self._save_detectors()
                    print(f"   [Pattern] PROMOVIDO: {detector['condition_text'][:60]}")
                else:
                    print(f"   [Pattern] DESCARTADO: {motivo}")
                self.trial_detectors.remove(trial)
        
        return thoughts


    def _check_all_individual(self, context: Dict) -> list:
        """Evaluación individual de detectores con rotación circular."""
        from core.flow.flow_stream import ThoughtItem
        from core.llm import LLMModel
        thoughts = []
        
        # Obtener detectores a evaluar en este ciclo (rotación circular)
        detectors_to_check = self._get_detectors_to_check()
        
        for detector in detectors_to_check:
            if not detector.get("active"):
                continue
            
            if detector.get("use_llm"):
                prompt = f"""¿Se cumple esta condición en el contexto actual?

    Condición: "{detector['condition_text'][:150]}"
    Contexto: {context.get('active_thoughts', '')[:250]}
    Mensaje del usuario: {context.get('user_msg', '')[:150]}
    Emoción: {context.get('emotion', 'neutral')}

    Responde SOLO SI o NO."""
                
                result = LLMModel.get_instance().generate(
                    prompt, temperature=0.1, max_tokens=3, purpose="evaluar_detector"
                )
                if "SI" in result.upper():
                    detector["times_triggered"] = detector.get("times_triggered", 0) + 1
                    thoughts.append(ThoughtItem(
                        content=f"[Algoritmo] {detector['reaction_text'][:150]}",
                        thought_type="detected_pattern",
                        priority=0.3,
                        source="pattern_detector"
                    ))
        
        return thoughts
    
    def find_similar_pattern(self, context: Dict) -> Optional[str]:
        """
        Busca si la situación actual se parece a algún patrón aprendido,
        aunque no sea idéntico. Permite aplicar lecciones de un dominio a otro.
        """
        if not self.active_detectors:
            return None
        
        active_thoughts = context.get("active_thoughts", "")
        user_msg = context.get("user_msg", "")
        
        if not active_thoughts and not user_msg:
            return None
        
        combined = f"{active_thoughts} {user_msg}"
        
        for detector in self.active_detectors:
            condition = detector.get("condition_text", "").lower()
            
            condition_words = set(condition.split()) - {"me", "de", "que", "en", "el", "la", "los", "las", "un", "una", "y", "o", "a", "es", "por", "con", "no", "se", "su", "lo", "para", "del", "al", "como", "más", "pero", "si", "ya", "muy", "todo", "hay", "le", "esa", "ese", "eso", "está", "estoy", "son"}
            
            matches = sum(1 for word in condition_words if word in combined.lower())
            total = len(condition_words) if condition_words else 1
            similarity = matches / total
            
            if 0.3 < similarity < 0.8 and detector.get("times_triggered", 0) > 0:
                return f"Esto me recuerda a un patrón que aprendí: cuando {condition[:100]}... tal vez pueda aplicar esa lección aquí."
        
        return None

    def prune_stale(self):
        """Elimina detectores inactivos o inútiles."""
        for detector in self.active_detectors[:]:
            if detector["times_triggered"] > 100:
                detector["active"] = False
            age = (datetime.now() - detector["created_at"]).days
            if age > 7 and detector["times_triggered"] < 3:
                self.active_detectors.remove(detector)
        
        self._save_detectors()

    def _get_detectors_to_check(self) -> list:
        """Devuelve los detectores a evaluar en este ciclo, rotando para cubrirlos todos."""
        if not hasattr(self, '_detector_rotation_index'):
            self._detector_rotation_index = 0
        
        active = [d for d in self.active_detectors if d.get("active")]
        if not active:
            return []
        
        # Cuántos evaluar este ciclo (máximo 5, o todos si son menos)
        batch_size = min(5, len(active))
        
        # Rotación circular
        start = self._detector_rotation_index % len(active)
        indices = [(start + i) % len(active) for i in range(batch_size)]
        
        # Avanzar para el próximo ciclo
        self._detector_rotation_index = (self._detector_rotation_index + batch_size) % len(active)
        
        return [active[i] for i in indices]