"""
Sistema #35: TRN-Gate (Filtro de Compuerta Atencional)
Homólogo al Núcleo Reticular Talámico (TRN).

Regula el flujo de llamadas al LLM mediante priorización biológica:
- P1 (Crítica): Respuesta al usuario, monólogo unificado. Apropiativa.
- P2 (Alta): Post-procesos ejecutivos.
- P3 (Media): Búsquedas, extracción de patrones. Solo si no hay P1.
- P4 (Baja): Simulaciones, análisis de fondo. Se pausan al entrar mensaje.

Además:
- Unifica llamadas redundantes (memoización por contexto).
- Pausa procesos de fondo cuando entra un estímulo externo.
"""

import threading
import time
from enum import Enum
from collections import defaultdict
import re

class Priority(Enum):
    CRITICAL = 1   # P1: Foco Foveal / Alerta
    HIGH = 2       # P2: Procesamiento Ejecutivo
    MEDIUM = 3     # P3: Consolidación / Táctica
    LOW = 4        # P4: Red por Defecto (DMN)


class TRNGate:
    """
    Orquestador de llamadas al LLM con priorización atencional.
    Singleton thread-safe.
    """
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        if TRNGate._instance is not None:
            return
        TRNGate._instance = self

        # Estado de atención
        self.external_stimulus_active = False
        self.stimulus_lock = threading.Lock()

        # Colas por prioridad
        self._queues = {
            Priority.CRITICAL: [],
            Priority.HIGH: [],
            Priority.MEDIUM: [],
            Priority.LOW: [],
        }

        # Resultados cacheados para unificación
        self._active_requests = {}  # key -> threading.Event + result
        self._active_requests_lock = threading.Lock()

        # Callback para ejecutar realmente la llamada al LLM
        self._llm_executor = None

    # ============================================
    # REGISTRO DE ESTÍMULOS
    # ============================================

    def on_user_message(self):
        """Notifica que el usuario envió un mensaje. Pausa procesos de fondo."""
        with self.stimulus_lock:
            self.external_stimulus_active = True

    def on_response_sent(self):
        """Notifica que la respuesta fue enviada. Reanuda procesos de fondo."""
        with self.stimulus_lock:
            self.external_stimulus_active = False

    def is_stimulus_active(self) -> bool:
        with self.stimulus_lock:
            return self.external_stimulus_active

    # ============================================
    # EJECUCIÓN CON PRIORIDAD
    # ============================================

    def set_executor(self, executor):
        """Registra la función que ejecuta llamadas al LLM."""
        self._llm_executor = executor

    def execute(self, prompt: str, temperature: float, max_tokens: int,
                purpose: str, priority: Priority = Priority.LOW) -> str:
        """
        Ejecuta una llamada al LLM con la prioridad especificada.
        
        Si hay un estímulo externo activo y la prioridad es LOW,
        la tarea se encola hasta que el estímulo cese.
        """
            # Si hay estímulo activo y es prioridad baja, DESCARTAR (no encolar)
        if self.is_stimulus_active() and priority in (Priority.LOW, Priority.MEDIUM):
            print(f"   [TRN] Descartando {purpose} (prioridad {priority.value}) - estímulo externo activo")
            return ""  # No ejecutar, no encolar
        # Si hay estímulo activo y es prioridad baja, pausar
        if self.is_stimulus_active() and priority == Priority.LOW:
            return self._enqueue_and_wait(prompt, temperature, max_tokens, purpose, priority)

        return self._execute_internal(prompt, temperature, max_tokens, purpose)

    def _execute_internal(self, prompt: str, temperature: float, max_tokens: int,
                          purpose: str) -> str:
        """Ejecución real con unificación de llamadas redundantes."""
        if self._llm_executor is None:
            raise RuntimeError("TRNGate: no executor registered")

        # Clave de unificación para evitar llamadas redundantes
        unify_key = f"{purpose}:{prompt[:200]}"

        with self._active_requests_lock:
            if unify_key in self._active_requests:
                # Ya hay una llamada en curso con este propósito+prompt
                event, _ = self._active_requests[unify_key]
                # Esperar al resultado compartido (fuera del lock)
                event_ref = event
            else:
                event = threading.Event()
                self._active_requests[unify_key] = (event, None)
                event_ref = None

        if event_ref is not None:
            # Esperar el resultado de la llamada en curso
            event_ref.wait(timeout=60)
            with self._active_requests_lock:
                if unify_key in self._active_requests:
                    _, result = self._active_requests[unify_key]
                    # Limpiar después de consumir
                    del self._active_requests[unify_key]
                    return result if result is not None else ""
            return ""

        # Ejecutar la llamada
        try:
            result = self._llm_executor(prompt, temperature, max_tokens, purpose)
        except Exception as e:
            result = ""

        # Notificar a los suscriptores
        with self._active_requests_lock:
            if unify_key in self._active_requests:
                event, _ = self._active_requests[unify_key]
                self._active_requests[unify_key] = (event, result)
                event.set()

        return result

    def _enqueue_and_wait(self, prompt: str, temperature: float, max_tokens: int,
                          purpose: str, priority: Priority) -> str:
        """Encola una tarea de baja prioridad hasta que cese el estímulo."""
        # Para tareas LOW, simplemente esperar un poco y ejecutar
        # o descartar si el contexto cambió
        for _ in range(30):  # Esperar hasta 30 segundos
            if not self.is_stimulus_active():
                return self._execute_internal(prompt, temperature, max_tokens, purpose)
            time.sleep(1)
        # Si después de 30s sigue el estímulo, ejecutar de todas formas
        return self._execute_internal(prompt, temperature, max_tokens, purpose)

    # ============================================
    # MONÓLOGO ANALÍTICO UNIFICADO
    # ============================================

    def execute_unified_monologue(self, message: str, user_name: str, name: str,
                              personality_desc: str, backstory: str,
                              active_summary: str, traits: dict = None,
                              behavior: dict = None, speech_text: str = "",
                              epistemic_bounds="", short_term_history: str = "") -> dict:
        """
        Ejecuta el monólogo analítico unificado.
        Fusiona 6 llamadas en 1:
        - PRAGMÁTICA (saludo, idioma, emoción)
        - KEYWORDS (3 conceptos para ChromaDB)
        - PATRÓN (intención oculta)
        - REFLEXIÓN (pensamiento enriquecido)
        """
        traits = traits or {}
        behavior = behavior or {}

        prompt = f"""<system_identity>
Eres {name}.
{personality_desc}
{backstory}

Rasgos: Apertura: {traits.get('openness', 0.5):.0%} | Responsabilidad: {traits.get('conscientiousness', 0.5):.0%} | Extraversión: {traits.get('extraversion', 0.5):.0%} | Amabilidad: {traits.get('agreeableness', 0.5):.0%} | Neuroticismo: {traits.get('neuroticism', 0.5):.0%}
Estilo: {behavior.get('formality', 'casual')}, {behavior.get('verbosity', 'media')} extensión.
Expresividad: {traits.get('expressiveness_base', 0.5):.0%} | Franqueza emocional: {traits.get('emotion_directness_base', 0.5):.0%}

<speech_examples>
{speech_text if speech_text else "No hay ejemplos definidos."}
</speech_examples>
</system_identity>

<epistemic_bounds>
{epistemic_bounds}
</epistemic_bounds>

<sensory_input>
{user_name} dice: "{message}"
</sensory_input>

<active_context>
{active_summary[:500]}
</active_context>

<short_term_history>
{short_term_history}
</short_term_history>

<analytical_directive>
Genera tu monólogo interno. Escribe lo que realmente piensas sobre lo que dice el usuario,
filtrado a través de tu identidad, tus rasgos y tu backstory.
Escribe en primera persona, de forma abstracta y metacognitiva.
Incluye:
[PRAGMÁTICA]: (SALUDA o NO_SALUDA, idioma, emoción)
[KEYWORDS]: (3 conceptos clave o NINGUNO)
[REFLEXIÓN]: (Tu pensamiento real sobre esto. 1-2 frases. Sé cruda y honesta.)
</analytical_directive>

<thought_stream>"""
        
        result = self.execute(
            prompt=prompt,
            temperature=0.3,
            max_tokens=200,
            purpose="monologo_unificado",
            priority=Priority.CRITICAL
        )

        return self._parse_unified_monologue(result)

    def _parse_unified_monologue(self, raw: str) -> dict:        
        # Eliminar cualquier "<" del prompt que pueda haberse filtrado
        raw = re.sub(r'<[^>]+>', '', raw)
        
        
        parsed = {
            "pragmatica": "",
            "saluda": False,
            "idioma": "ES",
            "emocion": "neutral",
            "keywords": [],
            "patron": "",
            "reflexion": "",
            "raw": raw,
        }

        # Extraer PRAGMÁTICA
        prag_match = re.search(r'\[PRAGMÁTICA\]:\s*(.+?)(?=\[KEYWORDS\]|\[PATRÓN\]|\[REFLEXIÓN\]|$)', raw, re.DOTALL)
        if prag_match:
            prag = prag_match.group(1).strip()
            parsed["pragmatica"] = prag
            parsed["saluda"] = "SALUDA" in prag.upper() and "NO_SALUDA" not in prag.upper()
            
            # Detectar idioma
            if "EN" in prag.upper() and "ES" not in prag.upper():
                parsed["idioma"] = "EN"
            
            # Detectar emoción
            emociones = ["alegría", "tristeza", "enojo", "miedo", "curiosidad", "neutral",
                        "joy", "sadness", "anger", "fear", "curiosity"]
            for em in emociones:
                if em.lower() in prag.lower():
                    parsed["emocion"] = em.lower()
                    break

        # Extraer KEYWORDS
        kw_match = re.search(r'\[KEYWORDS\]:\s*(.+?)(?=\[PATRÓN\]|\[REFLEXIÓN\]|$)', raw, re.DOTALL)
        if kw_match:
            kw_text = kw_match.group(1).strip()
            # Filtrar etiquetas del sistema
            kw_text = re.sub(r'<[^>]+>', '', kw_text)
            kw_text = re.sub(r'thought_stream|system_identity|analytical_directive|generation_directive', '', kw_text, flags=re.IGNORECASE)
            if kw_text.upper() != "NINGUNO" and kw_text.strip():
                parsed["keywords"] = [k.strip() for k in kw_text.split(",") if k.strip() and len(k.strip()) > 2]

        # Extraer PATRÓN
        pat_match = re.search(r'\[PATRÓN\]:\s*(.+?)(?=\[REFLEXIÓN\]|$)', raw, re.DOTALL)
        if pat_match:
            parsed["patron"] = pat_match.group(1).strip()

        # Extraer REFLEXIÓN
        ref_match = re.search(r'\[REFLEXIÓN\]:\s*(.+?)$', raw, re.DOTALL)
        if ref_match:
            parsed["reflexion"] = ref_match.group(1).strip()

        return parsed