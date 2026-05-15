# core/llm.py
import threading
import time
from datetime import datetime
from pathlib import Path
from collections import deque
import json
from config import (
    MODEL_PATH, MODEL_CONTEXT_SIZE, MODEL_THREADS, MODEL_GPU_LAYERS,
    LLM_BACKEND, CLOUD_API_KEY, CLOUD_MODEL_PREMIUM, CLOUD_MODEL_FREE, CLOUD_API_URL,
    MODEL_PATH_REASONING, MODEL_PATH_JSON, GPU_BACKEND, GPU_LAYERS_MAIN, GPU_LAYERS_REASONING, GPU_LAYERS_JSON, COGNITIVE_TRACE_FILE
)


class LLMModel:
    _instance = None
    _lock = threading.Lock()

    # Propósitos que usan cloud premium (pago)
    PREMIUM_PURPOSES = [
        "respuesta_final",
        "reflexion_aprendizaje",
        "analizar_imagen",
        "generar_respuesta"
    ]

    # Propósitos que usan cloud gratuito
    CLOUD_FREE_PURPOSES = [
        "interpretar", "evaluar", "decidir",
        "pensamiento_interpretar", "pensamiento_evaluar", "pensamiento_decidir",
        "decidir_info", "percepcion_usuario", "verificar_respuesta"
    ]

    # Propósitos de razonamiento ligero (modelo local pequeño)
    REASONING_PURPOSES = [
        "verificar_certeza", "clarificar_memory_activity"
    ]
    
    # Propósitos de JSON (modelo local pequeño)
    JSON_PURPOSES = [
        "ajustar_estado",
    ]

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
        self.model_reasoning = None
        self.model_json = None
        self.backend = LLM_BACKEND
        self.call_log = deque(maxlen=100)
        COGNITIVE_TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        if self.backend in ("local", "hybrid"):
            self._init_local()

    def _init_local(self):
        from llama_cpp import Llama
        
        gpu_kwargs = {}
        if GPU_BACKEND == "vulkan":
            gpu_kwargs["use_vulkan"] = True

        # Modelo principal (Llama 8B)
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
        
        # Si reasoning y json son el mismo archivo, cargar una sola vez
        if MODEL_PATH_REASONING == MODEL_PATH_JSON:
            if MODEL_PATH_REASONING.exists():
                print(f"Cargando modelo ligero compartido: {MODEL_PATH_REASONING}...")
                self.model_reasoning = Llama(
                    model_path=str(MODEL_PATH_REASONING),
                    n_ctx=2048,
                    n_threads=MODEL_THREADS,
                    n_gpu_layers=GPU_LAYERS_REASONING,
                    verbose=False,
                    **gpu_kwargs
                )
                self.model_json = self.model_reasoning
                print("Modelo ligero compartido cargado (razonamiento + JSON).")
            else:
                print(f"⚠️ Modelo ligero compartido no encontrado: {MODEL_PATH_REASONING}")
                self.model_reasoning = self.model_main
                self.model_json = self.model_main
                print("Usando modelo principal como fallback para tareas ligeras.")
        else:
            # Cargar por separado
            if MODEL_PATH_REASONING.exists():
                print(f"Cargando modelo de razonamiento: {MODEL_PATH_REASONING}...")
                self.model_reasoning = Llama(
                    model_path=str(MODEL_PATH_REASONING),
                    n_ctx=2048,
                    n_threads=MODEL_THREADS,
                    n_gpu_layers=GPU_LAYERS_REASONING,
                    verbose=False,
                    **gpu_kwargs
                )
                print("Modelo de razonamiento cargado.")
            else: 
                self.model_reasoning = self.model_main
                print(f"⚠️ Modelo de razonamiento no encontrado, usando modelo principal como fallback.")

            if MODEL_PATH_JSON.exists():
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
            else: 
                self.model_json = self.model_main
                print(f"⚠️ Modelo JSON no encontrado, usando modelo principal como fallback.")

        print("Todos los modelos locales disponibles cargados.")

    def load_model(self):
        """Carga los modelos según el backend configurado."""
        if self.backend in ("local", "hybrid") and self.model_main is None:
            self._init_local()
        elif self.backend == "cloud":
            print("Modo cloud: sin modelo local.")

    
    def generate(self, prompt, temperature=0.7, max_tokens=150, purpose=None):
        t_start = time.time()
        backend = self._select_backend(purpose)
        
        with LLMModel._lock:
            return self._generate_locked(prompt, temperature, max_tokens, purpose, backend, t_start)

    def _generate_locked(self, prompt, temperature, max_tokens, purpose, backend, t_start):
        """Generación real dentro del lock."""
        print(f"🤖 LLM generate [{backend}] - purpose: {purpose}, max_tokens: {max_tokens}")
        if backend == "main" and purpose == "respuesta_final":
            result = self._generate_local_fallback(prompt, temperature, max_tokens, purpose)
            if result:
                return result
            
        response = None
        
        if backend == "cloud_premium":
            response = self._try_cloud_model(CLOUD_MODEL_PREMIUM, prompt, temperature, max_tokens)
            if response is not None:
                pass
            else:
                print(f"   🔄 Fallback Premium → Free...")
                response = self._try_cloud_model(CLOUD_MODEL_FREE, prompt, temperature, max_tokens)
                if response is not None:
                    backend = "cloud_free"
        
        elif backend == "cloud_free":
            response = self._try_cloud_model(CLOUD_MODEL_FREE, prompt, temperature, max_tokens)
            if response is not None:
                pass
            else:
                print(f"   🔄 Fallback Free → Premium...")
                response = self._try_cloud_model(CLOUD_MODEL_PREMIUM, prompt, temperature, max_tokens)
                if response is not None:
                    backend = "cloud_premium"
        
        if response is None:
            if backend.startswith("cloud"):
                print(f"   🔄 Fallback final → modelo local...")
            response = self._generate_local(prompt, temperature, max_tokens, purpose)
            backend = self._select_backend(purpose)
            if backend in ("cloud_premium", "cloud_free"):
                backend = "main"
        
        elapsed = time.time() - t_start
        print(f"🤖 Generación exitosa [{backend}], length: {len(response) if response else 0}")
        
        self._log_call(
            purpose=purpose or "unknown",
            prompt_length=len(prompt),
            response_length=len(response) if response else 0,
            temperature=temperature,
            max_tokens=max_tokens,
            elapsed=elapsed,
            backend=backend
        )
        
        return response

    def _select_backend(self, purpose):
        """Elige backend según el propósito de la llamada."""

        # Forzar percepción de usuario a modelo principal (evita rechazos de Llama 3.1)
        if purpose == "percepcion_usuario":
            if self.model_main:
                return "main"
            return "local"

        # Premium
        if purpose in self.PREMIUM_PURPOSES and CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
            return "cloud_premium"
        
        # Cloud gratuito
        if purpose in self.CLOUD_FREE_PURPOSES and CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"):
            return "cloud_free"
        
        # Razonamiento local
        if purpose in self.REASONING_PURPOSES and self.model_reasoning:
            return "reasoning"
        
        # JSON local
        if purpose in self.JSON_PURPOSES and self.model_json:
            return "json"
        
        # Fallback a modelo principal local
        if self.model_main:
            return "main"
        
        return "local"

    def _generate_local(self, prompt, temperature, max_tokens, purpose=None):
        """Usa el modelo local apropiado según el propósito."""
        backend = self._select_backend(purpose)
        
        if backend == "reasoning" and self.model_reasoning:
            model = self.model_reasoning
        elif backend == "json" and self.model_json:
            model = self.model_json
        else:
            model = self.model_main
        
        if model is None:
            return "Error: modelo no disponible."
        
        result = model.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return result["choices"][0]["message"]["content"]

    def _try_cloud_model(self, model_name, prompt, temperature, max_tokens):
        """Intenta generar con un modelo cloud específico. Retorna None si falla."""
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
        
        try:
            resp = requests.post(
                f"{CLOUD_API_URL}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            elif resp.status_code == 402:
                print(f"   ⚠️ Sin créditos para {model_name}")
                return None
            elif resp.status_code == 429:
                print(f"   ⚠️ Rate limit para {model_name}")
                return None
            else:
                print(f"   ⚠️ Error {resp.status_code} para {model_name}")
                return None
                
        except Exception as e:
            print(f"   ⚠️ Error cloud ({type(e).__name__}): {str(e)[:80]}")
            return None

    def _log_call(self, purpose, prompt_length, response_length, temperature, max_tokens, elapsed, backend="local"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "purpose": purpose,
            "backend": backend,
            "prompt_length": prompt_length,
            "response_length": response_length,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "elapsed_seconds": round(elapsed, 2)
        }
        
        self.call_log.append(entry)
        if len(self.call_log) > 100:
            self.call_log = self.call_log[-100:]
        
        try:
            with open(COGNITIVE_TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ No se pudo guardar trace: {e}")

    def get_recent_activity(self, limit=10):
        recent = self.call_log[-limit:]
        lines = []
        for c in recent:
            timestamp = c['timestamp'][:19] if isinstance(c['timestamp'], str) else c['timestamp']
            purpose = c.get('purpose', 'unknown')
            backend = c.get('backend', 'local')
            elapsed = c.get('elapsed_seconds', 0)
            summary = c.get('summary', '')
            
            if purpose == "pensamiento_fondo" and summary:
                lines.append(f"- [{timestamp}] [fondo] {summary}")
            else:
                lines.append(f"- [{timestamp}] [{backend}] {purpose} ({elapsed}s)")
        return "\n".join(lines) if lines else "Sin actividad registrada aún."
    
    def _generate_local_fallback(self, prompt: str, temperature: float, max_tokens: int, purpose: str = "respuesta_final") -> str:
        """Plan B cuando el cloud no está disponible. 2 llamadas: generar + verificar."""
        try:
            response_text = self._generate_local(prompt, temperature, max_tokens, purpose)
            
            if not response_text:
                return ""
            
            verification_prompt = f"""Evalúa si esta respuesta es coherente y precisa:
    Respuesta: "{response_text[:300]}"
    Responde SOLO SI o NO."""
            
            verification = self._generate_local(verification_prompt, 0.0, 3, "verificar_respuesta")
            
            if "NO" in verification.upper():
                return response_text + " (⚠️ verificación fallida)"
            
            return response_text
        except Exception:
            return response_text if response_text else ""