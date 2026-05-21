"""Gestión multi-modelo para Sibelium."""
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Optional
from config import (
    MODEL_PATH, MODEL_CONTEXT_SIZE, MODEL_THREADS,
    LLM_BACKEND, CLOUD_API_KEY, CLOUD_API_URL,
    CLOUD_MODEL_PREMIUM, CLOUD_MODEL_FREE,
    GPU_BACKEND, GPU_LAYERS_MAIN, ENTITY_DATA_DIR
)

COGNITIVE_TRACE_FILE = Path("entity_data/logs/cognitive_trace.jsonl")


# ============================================
# PROPÓSITOS
# ============================================

# Tareas que van al cloud premium (Gemini)
PREMIUM_PURPOSES = [
    "respuesta_final", "generar_respuesta",
    "analizar_imagen", "auto_mejora",
]

# Propósitos que requieren cloud por propensión a alucinación
ALUCINATION_PRONE_PURPOSES = [
    "simulacion_fondo",
    "prospeccion_fondo",
]

# Todo lo demás va al modelo local
# (no hace falta lista, por defecto)


# ============================================
# SINGLETON
# ============================================

class LLMModel:
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
        if LLMModel._instance is not None:
            return
        LLMModel._instance = self

        from core.llm_metrics import LLMMetrics
        self.metrics = LLMMetrics(ENTITY_DATA_DIR)
        self.prompt_cache = {}
        self._mod_purposes = {"premium": [], "local": []}
        self.model_main = None
        self.backend = LLM_BACKEND
        self.call_log = deque(maxlen=100)
        self._init_dirs()

        if self.backend in ("local", "hybrid"):
            self._init_local()

    def _init_dirs(self):
        COGNITIVE_TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def register_mod_purpose(self, category: str, purpose: str):
        """Permite a los mods registrar propósitos sin modificar el núcleo."""
        if category in self._mod_purposes:
            self._mod_purposes[category].append(purpose)

    # ============================================
    # INICIALIZACIÓN LOCAL
    # ============================================

    def _init_local(self):
        from llama_cpp import Llama

        gpu_kwargs = {}
        if GPU_BACKEND == "vulkan":
            gpu_kwargs["use_vulkan"] = True

        # Modelo principal
        if MODEL_PATH.exists():
            print(f"Cargando modelo principal: {MODEL_PATH}...")
            self.model_main = Llama(
                model_path=str(MODEL_PATH),
                n_ctx=MODEL_CONTEXT_SIZE,
                n_threads=MODEL_THREADS,
                n_gpu_layers=GPU_LAYERS_MAIN,
                verbose=False,
                **gpu_kwargs
            )
            print("Modelo principal cargado.")
        else:
            print(f"⚠️ Modelo principal no encontrado: {MODEL_PATH}")

        
    def load_model(self):
        if self.backend in ("local", "hybrid") and self.model_main is None:
            self._init_local()

    # ============================================
    # SELECCIÓN DE BACKEND
    # ============================================

    def _select_backend(self, purpose: str) -> str:
        """Elige backend según el propósito."""
        if not purpose or LLM_BACKEND == "local":
            return self._fallback_local()

        # Cloud premium
        if purpose in PREMIUM_PURPOSES:
            if CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
                return "cloud_premium"
        if purpose in self._mod_purposes.get("premium", []):
            if CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
                return "cloud_premium"

        # Cloud free (si hay API key)
        if purpose in self._mod_purposes.get("free", []):
            if CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
                return "cloud_free"

        return self._fallback_local()

    def _fallback_local(self) -> str:
        if self.model_main:
            return "main"
        return "local"

    # ============================================
    # GENERACIÓN PRINCIPAL
    # ============================================

    def generate(self, prompt, temperature=0.7, max_tokens=150, purpose=None):
        t_start = time.time()

        # Log de tamaño del prompt
        prompt_chars = len(prompt)
        prompt_tokens_est = prompt_chars // 4  # Estimación: ~4 chars por token
        if prompt_tokens_est > 1000:  # Solo loggear prompts grandes
            print(f"   [LLM] Prompt '{purpose}': ~{prompt_tokens_est} tokens ({prompt_chars} chars)")

        cached = self._get_cached(prompt, purpose)
        if cached:
            print(f"🤖 LLM [cache] - {purpose}")
            self.metrics.record(purpose, "cache", len(prompt) // 4, len(cached) // 4, 0, cached=True)
            return cached

        # Mediador Talámico: reevaluar backend según carga cognitiva
        backend = self._thalamic_route(prompt, purpose, 0.5)

        with LLMModel._lock:
            result = self._generate(prompt, temperature, max_tokens, purpose, backend, t_start)
            if result is None:
                result = ""

        self._set_cached(prompt, purpose, result)

        elapsed = time.time() - t_start
        result_len = len(result) if result else 0
        self.metrics.record(purpose, backend, len(prompt) // 4, result_len, elapsed)
        # Limpiar etiquetas XML del output
        import re
        result = re.sub(r'<(?!/?query_)[^>]+>', '', result)
        return result

    def _generate(self, prompt: str, temperature: float, max_tokens: int, purpose: str, backend: str, t_start: float) -> str:
        response = None

        if backend == "cloud_premium":
            if CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
                response = self._try_cloud(CLOUD_MODEL_PREMIUM, prompt, temperature, max_tokens)
            else:
                print(f"   🔄 Cloud no disponible, usando local")
        elif backend == "cloud_free":
            if CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
                response = self._try_cloud(CLOUD_MODEL_FREE, prompt, temperature, max_tokens)
            else:
                print(f"   🔄 Cloud no disponible, usando local")
        else:
            response = self._generate_local(prompt, temperature, max_tokens, backend)

        if response is None:
            print(f"   🔄 Fallback → modelo local")
            response = self._generate_local(prompt, temperature, max_tokens, "main")
            backend = "main"
        
        result = response or ""
        elapsed = time.time() - t_start
        print(f"🤖 [{backend}] {purpose} | {len(result)} chars | {elapsed:.1f}s")
        return result

    # ============================================
    # GENERACIÓN LOCAL
    # ============================================

    def _generate_local(self, prompt: str, temperature: float, max_tokens: int, backend: str, purpose: str = "") -> Optional[str]:
        """Usa el modelo local apropiado con sampling avanzado."""
        model = self.model_main
        
        kwargs = {
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Min-P + Mirostat para pensamientos creativos
        if purpose in ("simulacion_fondo", "curiosidad_fondo", "prospeccion_fondo", "monologo_unificado"):
            kwargs["mirostat_mode"] = 2
            kwargs["mirostat_tau"] = 5.0
            kwargs["mirostat_eta"] = 0.1
            kwargs["min_p"] = 0.05
            kwargs["repeat_penalty"] = 1.05
        
        # Min-P sin Mirostat para reflexiones
        elif purpose in ("reflexion_fondo", "pensamiento_enriquecido"):
            kwargs["min_p"] = 0.05
            kwargs["repeat_penalty"] = 1.05
        
        # Respuesta final
        elif purpose == "respuesta_final":
            kwargs["repeat_penalty"] = 1.1
        
        try:
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            if "mirostat" in str(e).lower():
                kwargs.pop("mirostat_mode", None)
                kwargs.pop("mirostat_tau", None)
                kwargs.pop("mirostat_eta", None)
                try:
                    result = model.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        **kwargs
                    )
                    return result["choices"][0]["message"]["content"]
                except Exception:
                    pass
            print(f"   ⚠️ Error en modelo local ({type(e).__name__}): {e}")
            return None

    def _thalamic_route(self, prompt: str, purpose: str, context_entropy: float = 0.5) -> str:
        backend = self._select_backend(purpose)
        if backend not in ("main"):
            return backend

        from config import CLOUD_API_KEY, LLM_BACKEND
        if not (CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid")):
            return backend

        # Forzar cloud para propósitos propensos a alucinación
        if purpose in ALUCINATION_PRONE_PURPOSES:
            print(f"   [Talámico] Propósito '{purpose}' → cloud (anti-alucinación)")
            return "cloud_premium"

        # Cálculo de CE para el resto
        prompt_length = len(prompt)
        max_context = 8192
        prompt_ratio = min(1.0, prompt_length / max_context)
        cognitive_stress = getattr(self, '_cognitive_stress', 0.5)
        graph_complexity = 1.0 - context_entropy
        CE = (prompt_ratio * 0.4) + (cognitive_stress * 0.4) + (graph_complexity * 0.2)

        if CE > 0.65:
            print(f"   [Talámico] CE={CE:.2f} > 0.65. Reclutando Cloud...")
            return "cloud_premium"

        return backend


    def set_cognitive_stress(self, stress: float):
        """Actualiza el nivel de estrés cognitivo (0-1)."""
        self._cognitive_stress = max(0.0, min(1.0, stress))

    # ============================================
    # API CLOUD
    # ============================================

    def _try_cloud(self, model_name: str, prompt: str, temperature: float, max_tokens: int) -> Optional[str]:
        """Intenta generar con un modelo cloud."""
        import requests

        headers = {
            "Authorization": f"Bearer {CLOUD_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Sibelium Cognitive Assistant"
        }

        data = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        for attempt in range(2):
            try:
                resp = requests.post(
                    f"{CLOUD_API_URL}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=90
                )

                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code in (502, 504):
                    print(f"   ⚠️ Timeout {model_name} (intento {attempt + 1}/2)")
                    time.sleep(3)
                    continue
                elif resp.status_code == 402:
                    print(f"   ⚠️ Sin créditos: {model_name}")
                    return None
                elif resp.status_code == 429:
                    print(f"   ⚠️ Rate limit: {model_name}")
                    return None
                else:
                    print(f"   ⚠️ {model_name}: HTTP {resp.status_code} - {resp.text[:150]}")
                    return None

            except requests.exceptions.Timeout:
                print(f"   ⚠️ Timeout conexión {model_name}")
                return None
            except requests.exceptions.ConnectionError as e:
                print(f"   ⚠️ Error conexión {model_name}: {e}")
                return None
            except Exception as e:
                print(f"   ⚠️ Error {model_name} ({type(e).__name__}): {str(e)[:150]}")
                return None

        return None

    # ============================================
    # CACHÉ KV
    # ============================================

    CACHEABLE = [
        "curiosidad_fondo", "evaluar_detector",
        "decidir_info", "check_identity", "resumir_contexto",
        "prediccion", "redirigir_pensamiento", "evaluar_diversidad",
        "limpiar_curiosidades", "consolidacion", "regular_emocion",
        "mensaje_proactivo", "decidir_busqueda", "busqueda_desde_pensamiento",
    ]

    def _get_cached(self, prompt: str, purpose: str) -> Optional[str]:
        if purpose not in self.CACHEABLE:
            return None
        key = f"{purpose}:{prompt[:200]}"
        if key in self.prompt_cache:
            cached_time, cached_result = self.prompt_cache[key]
            if time.time() - cached_time < 300:
                return cached_result
        return None

    def _set_cached(self, prompt: str, purpose: str, result: str):
        if purpose not in self.CACHEABLE:
            return
        key = f"{purpose}:{prompt[:200]}"
        self.prompt_cache[key] = (time.time(), result)
        if len(self.prompt_cache) > 50:
            oldest = min(self.prompt_cache, key=lambda k: self.prompt_cache[k][0])
            del self.prompt_cache[oldest]

    # ============================================
    # ACTIVIDAD RECIENTE
    # ============================================

    def get_recent_activity(self, limit: int = 10) -> str:
        recent = list(self.call_log)[-limit:]
        lines = []
        for c in recent:
            ts = c['timestamp'][:19] if isinstance(c['timestamp'], str) else c['timestamp']
            lines.append(f"- [{ts}] [{c.get('backend', '?')}] {c.get('purpose', '?')} ({c.get('elapsed_seconds', 0)}s)")
        return "\n".join(lines) if lines else "Sin actividad registrada."