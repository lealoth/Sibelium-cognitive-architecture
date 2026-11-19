"""Gestión del modelo LLM local para Sibelium (MVC)."""
import time
import threading
from collections import deque
from typing import Optional
from config import (
    MODEL_PATH, MODEL_CONTEXT_SIZE, MODEL_THREADS,
    GPU_BACKEND, GPU_LAYERS_MAIN, ENTITY_DATA_DIR
)


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

        self.model_main = None
        self.call_log = deque(maxlen=100)
        self.prompt_cache = {}
        self._init_local()

    def _init_local(self):
        from llama_cpp import Llama

        gpu_kwargs = {}
        if GPU_BACKEND == "vulkan":
            gpu_kwargs["use_vulkan"] = True

        if MODEL_PATH.exists():
            print(f"Cargando modelo principal: {MODEL_PATH}...")
            self.model_main = Llama(
                model_path=str(MODEL_PATH),
                n_ctx=MODEL_CONTEXT_SIZE,
                n_threads=MODEL_THREADS,
                n_gpu_layers=GPU_LAYERS_MAIN,
                type_k=8,   # Cuantización KV Cache a q8_0
                type_v=8,   # Cuantización KV Cache a q8_0
                verbose=False,
                **gpu_kwargs
            )
            print("Modelo principal cargado.")
        else:
            print(f"⚠️ Modelo principal no encontrado: {MODEL_PATH}")

    def load_model(self):
        if self.model_main is None:
            self._init_local()

    # ============================================
    # GENERACIÓN PRINCIPAL
    # ============================================

    def generate(self, prompt, temperature=0.7, max_tokens=150, purpose=None, sampling_params=None):
        t_start = time.time()

        # Log de tamaño del prompt (solo si es grande, para no ensuciar)
        prompt_tokens_est = len(prompt) // 4
        if prompt_tokens_est > 1000:
            print(f"   [LLM] Prompt '{purpose}': ~{prompt_tokens_est} tokens")

        # Caché KV para tareas repetitivas (opcional, ahora vacío)
        cached = self._get_cached(prompt, purpose)
        if cached:
            print(f"🤖 LLM [cache] - {purpose}")
            return cached

        with LLMModel._lock:
            result = self._generate_local(prompt, temperature, max_tokens, purpose, sampling_params)
            if result is None:
                result = ""

        self._set_cached(prompt, purpose, result)

        elapsed = time.time() - t_start
        print(f"🤖 [local] {purpose} | {len(result)} chars | {elapsed:.1f}s")
        
        # Limpiar etiquetas XML residuales
        import re
        result = re.sub(r'<(?!/?query_)[^>]+>', '', result)
        return result

    def _generate_local(self, prompt: str, temperature: float, max_tokens: int, purpose: str = "", sampling_params: dict = None) -> Optional[str]:
        model = self.model_main
        if model is None:
            return "Error: Modelo no cargado."

        kwargs = {
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Aplicar parámetros dinámicos de persona.json si existen
        if sampling_params and purpose in sampling_params:
            params = sampling_params[purpose]
            kwargs["temperature"] = params.get("temperature", temperature)
            kwargs["repeat_penalty"] = params.get("repeat_penalty", 1.0)
            kwargs["min_p"] = params.get("min_p", 0.0)
        else:
            # Fallback por defecto (muy básico)
            if purpose == "respuesta_final":
                kwargs["repeat_penalty"] = 1.15
            elif purpose == "interprete":
                kwargs["temperature"] = 0.1

        try:
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"   ⚠️ Error en modelo local ({type(e).__name__}): {e}")
            return None

    # ============================================
    # CACHÉ BÁSICO
    # ============================================

    CACHEABLE = ["interprete"] # Solo cachear el intérprete para ahorrar tiempo

    def _get_cached(self, prompt: str, purpose: str) -> Optional[str]:
        if purpose not in self.CACHEABLE:
            return None
        key = f"{purpose}:{prompt[:200]}"
        if key in self.prompt_cache:
            cached_time, cached_result = self.prompt_cache[key]
            if time.time() - cached_time < 60: # Cache de 1 minuto
                return cached_result
        return None

    def _set_cached(self, prompt: str, purpose: str, result: str):
        if purpose not in self.CACHEABLE:
            return
        key = f"{purpose}:{prompt[:200]}"
        self.prompt_cache[key] = (time.time(), result)
        if len(self.prompt_cache) > 20:
            oldest = min(self.prompt_cache, key=lambda k: self.prompt_cache[k][0])
            del self.prompt_cache[oldest]