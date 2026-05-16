"""Métricas agregadas de uso de LLM."""
import json
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

class LLMMetrics:
    """Métricas en tiempo real de uso de modelos LLM."""
    
    def __init__(self, storage_path: Path):
        self.storage = storage_path / "memory" / "llm_metrics.json"
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
    
    def _load(self) -> dict:
        if self.storage.exists():
            try:
                return json.loads(self.storage.read_text(encoding="utf-8"))
            except:
                pass
        return {
            "started_at": datetime.now().isoformat(),
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "cache_hits": 0,
            "by_backend": {},
            "by_purpose": {}
        }
    
    def _save(self):
        self.storage.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def record(self, purpose: str, backend: str, input_tokens: int, output_tokens: int, elapsed: float, cached: bool = False):
        """Registra una llamada al LLM."""
        self.data["total_calls"] += 1
        self.data["total_input_tokens"] += input_tokens
        self.data["total_output_tokens"] += output_tokens
        if cached:
            self.data["cache_hits"] += 1
        
        # Por backend
        if backend not in self.data["by_backend"]:
            self.data["by_backend"][backend] = {
                "calls": 0, "input_tokens": 0, "output_tokens": 0, "total_time": 0
            }
        self.data["by_backend"][backend]["calls"] += 1
        self.data["by_backend"][backend]["input_tokens"] += input_tokens
        self.data["by_backend"][backend]["output_tokens"] += output_tokens
        self.data["by_backend"][backend]["total_time"] += elapsed
        
        # Por propósito
        if purpose not in self.data["by_purpose"]:
            self.data["by_purpose"][purpose] = {
                "calls": 0, "input_tokens": 0, "output_tokens": 0, "total_time": 0,
                "by_backend": {}
            }
        self.data["by_purpose"][purpose]["calls"] += 1
        self.data["by_purpose"][purpose]["input_tokens"] += input_tokens
        self.data["by_purpose"][purpose]["output_tokens"] += output_tokens
        self.data["by_purpose"][purpose]["total_time"] += elapsed
        
        backend_key = backend
        if backend_key not in self.data["by_purpose"][purpose]["by_backend"]:
            self.data["by_purpose"][purpose]["by_backend"][backend_key] = {
                "calls": 0, "total_time": 0
            }
        self.data["by_purpose"][purpose]["by_backend"][backend_key]["calls"] += 1
        self.data["by_purpose"][purpose]["by_backend"][backend_key]["total_time"] += elapsed
        
        # Guardar cada 10 llamadas
        if self.data["total_calls"] % 10 == 0:
            self._save()
    
    def get_summary(self) -> str:
        """Devuelve un resumen legible de las métricas."""
        lines = []
        lines.append(f"=== LLM METRICS ===")
        lines.append(f"Total calls: {self.data['total_calls']} ({self.data['cache_hits']} cached)")
        lines.append(f"Total tokens: {self.data['total_input_tokens']} in / {self.data['total_output_tokens']} out")
        lines.append(f"")
        
        for backend, stats in self.data.get("by_backend", {}).items():
            calls = stats["calls"]
            if calls > 0:
                avg_time = stats["total_time"] / calls
                lines.append(f"[{backend}]: {calls} calls, avg {avg_time:.1f}s, {stats['input_tokens']} in / {stats['output_tokens']} out")
        
        lines.append(f"")
        
        for purpose, stats in sorted(self.data.get("by_purpose", {}).items(), key=lambda x: x[1]["calls"], reverse=True)[:10]:
            calls = stats["calls"]
            if calls > 0:
                avg_time = stats["total_time"] / calls
                backends = ", ".join([f"{b}({s['calls']})" for b, s in stats.get("by_backend", {}).items()])
                lines.append(f"[{purpose}]: {calls} calls, avg {avg_time:.1f}s [{backends}]")
        
        return "\n".join(lines)
    
    def save(self):
        """Guarda explícitamente (llamar al apagar)."""
        self._save()