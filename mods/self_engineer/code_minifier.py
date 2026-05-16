"""Minificador de código para SelfEngineer."""
import hashlib
import re


class CodeMinifier:
    """Reduce tokens de código sin perder información de análisis."""
    
    _lingua = None
    _cache = {}
    _max_cache_size = 20
    
    @classmethod
    def _get_lingua(cls):
        """Carga LLMLingua una sola vez (lazy loading)."""
        if cls._lingua is None:
            try:
                import os
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
                
                from llmlingua import PromptCompressor
                cls._lingua = PromptCompressor("gpt2", device_map="cpu")
                print("   [Minifier] LLMLingua cargado (gpt2, CPU).")
            except ImportError:
                print("   [Minifier] LLMLingua no instalado. Usando fallback.")
                return None
            except Exception as e:
                print(f"   [Minifier] LLMLingua no disponible: {e}")
                return None
        return cls._lingua
    
    @classmethod
    def _get_cache_key(cls, code: str) -> str:
        """Genera una clave de caché basada en el hash del código."""
        return hashlib.md5(code.encode()).hexdigest()
    
    @classmethod
    def _cache_get(cls, key: str) -> str:
        """Obtiene un resultado del caché."""
        return cls._cache.get(key)
    
    @classmethod
    def _cache_set(cls, key: str, value: str):
        """Guarda un resultado en el caché."""
        if len(cls._cache) >= cls._max_cache_size:
            # Eliminar la entrada más antigua
            oldest_key = next(iter(cls._cache))
            del cls._cache[oldest_key]
        cls._cache[key] = value
    
    @staticmethod
    def minify(code: str) -> str:
        """Minificación suave: elimina comentarios y docstrings."""
        # Verificar caché
        cache_key = CodeMinifier._get_cache_key(code)
        cached = CodeMinifier._cache_get(cache_key)
        if cached:
            return cached
        
        lines = code.split('\n')
        result = []
        
        for line in lines:
            if not line.strip():
                continue
            if line.strip().startswith('#'):
                if any(marker in line for marker in ['TODO', 'FIXME', 'HACK', 'BUG', 'WARNING']):
                    result.append(line)
                continue
            if '#' in line and '"' not in line.split('#')[0] and "'" not in line.split('#')[0]:
                line = line.split('#')[0].rstrip()
                if not line.strip():
                    continue
            if line.strip().startswith('"""') or line.strip().startswith("'''"):
                continue
            if line.strip().endswith('"""') or line.strip().endswith("'''"):
                continue
            result.append(line)
        
        minified = '\n'.join(result)
        CodeMinifier._cache_set(cache_key, minified)
        return minified
    
    @staticmethod
    def minify_aggressive(code: str) -> str:
        """Minificación con LLMLingua para archivos pequeños, fallback suave para grandes."""
        cache_key = CodeMinifier._get_cache_key(code)
        cached = CodeMinifier._cache_get(cache_key)
        if cached:
            return cached
        
        # Si el código es muy largo, usar minificación suave directamente
        if len(code) > 5000:
            minified = CodeMinifier.minify(code)
            CodeMinifier._cache_set(cache_key, minified)
            return minified
        
        lingua = CodeMinifier._get_lingua()
        
        if lingua is None:
            minified = CodeMinifier.minify(code)
            CodeMinifier._cache_set(cache_key, minified)
            return minified
        
        try:
            compressed = lingua.compress_prompt(
                code,
                rate=0.5,
                force_tokens=['def ', 'class ', 'import ', 'return ', 'self.', 'True', 'False', 'None'],
            )
            CodeMinifier._cache_set(cache_key, compressed)
            return compressed
        except Exception as e:
            print(f"   [Minifier] Error en LLMLingua: {e}. Usando fallback.")
            minified = CodeMinifier.minify(code)
            CodeMinifier._cache_set(cache_key, minified)
            return minified
    
    @staticmethod
    def compress_ratio(original: str, minified: str) -> float:
        """Porcentaje de reducción."""
        return (1 - len(minified) / len(original)) * 100 if original else 0