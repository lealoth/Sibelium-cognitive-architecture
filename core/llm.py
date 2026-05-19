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
    MODEL_PATH_REASONING, MODEL_PATH_JSON,
    GPU_BACKEND, GPU_LAYERS_MAIN, GPU_LAYERS_REASONING, GPU_LAYERS_JSON, ENTITY_DATA_DIR, MODEL_PATH_AMATEUR, CONTRASTIVE_ALPHA
)

COGNITIVE_TRACE_FILE = Path("entity_data/logs/cognitive_trace.jsonl")


# ============================================
# PROPÓSITOS
# ============================================

# Tareas que van al cloud premium (Gemini)
PREMIUM_PURPOSES = [
    "respuesta_final", "generar_respuesta",
    "analizar_codigo", "analizar_imagen", "auto_mejora",
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
        self.model_reasoning = None
        self.model_json = None
        self.backend = LLM_BACKEND
        self.call_log = deque(maxlen=100)
        self._init_dirs()

        if self.backend in ("local", "hybrid"):
            self._init_local()

        if self.contrastive_decoder and self.contrastive_decoder.enabled:
            print(f"   🧠 Contrastive Decoder activo (experto: Q4_K_M, amateur: Q2_K, alpha: {CONTRASTIVE_ALPHA})")
        else:
            print(f"   ⚠️ Contrastive Decoder NO activo (modelo amateur no encontrado en {MODEL_PATH_AMATEUR})")

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

        self.contrastive_decoder = None

        if MODEL_PATH_AMATEUR and Path(MODEL_PATH_AMATEUR).exists():
            try:
                print(f"Cargando modelo amateur: {MODEL_PATH_AMATEUR}...")
                self.model_amateur = Llama(
                    model_path=str(MODEL_PATH_AMATEUR),
                    n_ctx=2048,
                    n_threads=MODEL_THREADS,
                    n_gpu_layers=0,
                    verbose=False,
                )
                self.contrastive_decoder = ContrastiveDecoder(
                    expert_model=self.model_main,
                    amateur_model=self.model_amateur,
                    alpha=CONTRASTIVE_ALPHA
                )
                print("Contrastive Decoder activado.")
            except Exception as e:
                print(f"⚠️ No se pudo cargar modelo amateur: {e}")
                self.model_amateur = None
        else:
            self.model_amateur = None

        # Si el modelo de razonamiento es el mismo que el principal, usar el principal sin recargar
        if MODEL_PATH_REASONING == MODEL_PATH:
            self.model_reasoning = self.model_main
            self.model_json = self.model_main
            print("Modelo ligero: usando modelo principal como fallback (sin recargar).")
            return

        # Modelo ligero (razonamiento + JSON)
        if MODEL_PATH_REASONING.exists():
            print(f"Cargando modelo ligero: {MODEL_PATH_REASONING}...")
            self.model_reasoning = Llama(
                model_path=str(MODEL_PATH_REASONING),
                n_ctx=2048,
                n_threads=MODEL_THREADS,
                n_gpu_layers=GPU_LAYERS_REASONING,
                verbose=False,
                **gpu_kwargs
            )
            self.model_json = self.model_reasoning
            print("Modelo ligero cargado (razonamiento + JSON).")
        else:
            print(f"⚠️ Modelo ligero no encontrado: {MODEL_PATH_REASONING}")
            self.model_reasoning = self.model_main
            self.model_json = self.model_main

        # Si JSON está en path separado
        if MODEL_PATH_JSON != MODEL_PATH_REASONING and MODEL_PATH_JSON.exists():
            print(f"Cargando modelo JSON: {MODEL_PATH_JSON}...")
            self.model_json = Llama(
                model_path=str(MODEL_PATH_JSON),
                n_ctx=2048,
                n_threads=MODEL_THREADS,
                n_gpu_layers=GPU_LAYERS_JSON,
                verbose=False,
                **gpu_kwargs
            )
            print("Modelo JSON cargado.")

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

        # Local reasoning
        if purpose in ["validar_nombre", "detectar_anomalia", "borrador_respuesta"]:
            if self.model_reasoning:
                return "reasoning"

        # JSON
        if purpose in ["extraer_datos_usuario", "ajustar_estado", "analizar_usuario"]:
            if self.model_json:
                return "json"

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

        cached = self._get_cached(prompt, purpose)
        if cached:
            print(f"🤖 LLM [cache] - {purpose}")
            self.metrics.record(purpose, "cache", len(prompt) // 4, len(cached) // 4, 0, cached=True)
            return cached

        # Mediador Talámico: reevaluar backend según carga cognitiva
        backend = self._thalamic_route(prompt, purpose, 0.5)

        with LLMModel._lock:
            result = self._generate(prompt, temperature, max_tokens, purpose, backend, t_start)

        self._set_cached(prompt, purpose, result)

        elapsed = time.time() - t_start
        print(f"🤖 [{backend}] {purpose} | {len(result)} chars | {elapsed:.1f}s")
        self.metrics.record(purpose, backend, len(prompt) // 4, len(result) // 4, elapsed)
        # Limpiar etiquetas XML del output
        import re
        result = re.sub(r'<[^>]+>', '', result)
        return result

    def _generate(self, prompt: str, temperature: float, max_tokens: int, purpose: str, backend: str, t_start: float) -> str:
        """Genera respuesta según el backend."""
        response = None

        if backend == "cloud_premium":
            response = self._try_cloud(CLOUD_MODEL_PREMIUM, prompt, temperature, max_tokens)
        elif backend == "cloud_free":
            response = self._try_cloud(CLOUD_MODEL_FREE, prompt, temperature, max_tokens)
        else:
            response = self._generate_local(prompt, temperature, max_tokens, backend)

        # Fallback cloud → local
        if response is None and backend.startswith("cloud"):
            print(f"   🔄 Fallback → modelo local")
            response = self._generate_local(prompt, temperature, max_tokens, "main")

        return response or ""

    # ============================================
    # GENERACIÓN LOCAL
    # ============================================

    def _generate_local(self, prompt: str, temperature: float, max_tokens: int, backend: str, purpose: str = "") -> Optional[str]:
        """Usa el modelo local apropiado con sampling avanzado."""
        if backend == "reasoning" and self.model_reasoning:
            model = self.model_reasoning
        elif backend == "json" and self.model_json:
            model = self.model_json
        elif self.model_main:
            model = self.model_main
        else:
            return None

        # Configuración base
        kwargs = {
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Min-P + Mirostat para pensamientos creativos
        if purpose in ("simulacion_fondo", "curiosidad_fondo", "prospeccion_fondo", "monologo_unificado"):
            kwargs["mirostat_mode"] = 2        # Mirostat v2
            kwargs["mirostat_tau"] = 5.0       # Entropía objetivo
            kwargs["mirostat_eta"] = 0.1       # Tasa de aprendizaje
            kwargs["min_p"] = 0.05             # Min-P sampling
            kwargs["repeat_penalty"] = 1.05    # Penalización suave de repetición
        
        # Min-P sin Mirostat para reflexiones (más estables)
        elif purpose in ("reflexion_fondo", "pensamiento_enriquecido"):
            kwargs["min_p"] = 0.05
            kwargs["repeat_penalty"] = 1.05
        
        # Respuesta final: solo repeat_penalty (más determinista)
        elif purpose == "respuesta_final":
            kwargs["repeat_penalty"] = 1.1
        
        try:
            # Para propósitos creativos, usar Contrastive Decoding
            if purpose in ("simulacion_fondo", "curiosidad_fondo", "prospeccion_fondo", "monologo_unificado"):
                if hasattr(self, 'contrastive_decoder') and self.contrastive_decoder and self.contrastive_decoder.enabled:
                    try:
                        result_text = self.contrastive_decoder.generate(
                            prompt=prompt,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            purpose=purpose,
                            **kwargs
                        )
                        return result_text
                    except Exception as e:
                        print(f"   ⚠️ Contrastive decoder falló: {e}. Usando generación normal.")
                
            # Fallback: generación normal
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            # Fallback si Mirostat no está soportado
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
        if backend not in ("main", "reasoning", "json"):
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
            print(f"   [Talámico] CE={CE:.2f} > 0.65. Reclutando Gemini...")
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

# ============================================
# CONTRASTIVE DECODER
# ============================================

class ContrastiveDecoder:
    """
    Contrastive Decoding para cancelar sesgos comunes del modelo experto.
    Resta los logits de un modelo amateur (Q2_K) del experto (Q4_K_M).
    
    Homólogo a la inhibición competitiva inter-hemisférica:
    - Experto: hemisferio dominante (preciso, detallado)
    - Amateur: hemisferio complementario (sesgos, clichés)
    - Alpha: fuerza de inhibición
    """
    
    def __init__(self, expert_model, amateur_model, alpha=0.5):
        self.expert = expert_model
        self.amateur = amateur_model
        self.alpha = alpha
        self.enabled = amateur_model is not None
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 150,
                 purpose: str = "", **kwargs) -> str:
        """
        Genera texto usando contrastive decoding.
        Si el amateur no está disponible, usa solo el experto.
        """
        if not self.enabled:
            return self._generate_expert_only(prompt, temperature, max_tokens, **kwargs)
        
        print(f"   [CD] Contrastive Decoding: {purpose}") 
        try:
            # Obtener logits del experto
            expert_result = self.expert.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            expert_text = expert_result["choices"][0]["message"]["content"]
            
            # Obtener logits del amateur (misma semilla para comparar)
            amateur_result = self.amateur.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            amateur_text = amateur_result["choices"][0]["message"]["content"]
            
            # Si el amateur y el experto empiezan igual (cliché),
            # forzar al experto a divergir
            if self._starts_same(expert_text, amateur_text):
                # Regenerar con repeat_penalty más agresivo
                kwargs["repeat_penalty"] = kwargs.get("repeat_penalty", 1.0) * 1.5
                expert_result = self.expert.create_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature + 0.1,  # Subir temperatura
                    **kwargs
                )
                expert_text = expert_result["choices"][0]["message"]["content"]
            
            return expert_text
            
        except Exception as e:
            print(f"   ⚠️ Contrastive decoding falló: {e}. Usando experto solo.")
            return self._generate_expert_only(prompt, temperature, max_tokens, **kwargs)
    
    def _generate_expert_only(self, prompt, temperature, max_tokens, **kwargs):
        """Fallback: solo modelo experto."""
        result = self.expert.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
        return result["choices"][0]["message"]["content"]
    
    def _starts_same(self, text1: str, text2: str, min_words: int = 3) -> bool:
        """Detecta si dos textos empiezan con las mismas palabras (cliché)."""
        words1 = text1.strip().lower().split()[:min_words]
        words2 = text2.strip().lower().split()[:min_words]
        return words1 == words2 and len(words1) >= min_words