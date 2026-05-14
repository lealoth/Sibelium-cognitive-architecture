# mods/self_engineer/code_minifier.py
import re

class CodeMinifier:
    """Reduce tokens de código sin perder información de análisis."""
    
    @staticmethod
    def minify(code: str) -> str:
        lines = code.split('\n')
        result = []
        
        for line in lines:
            # Eliminar líneas en blanco
            if not line.strip():
                continue
            
            # Eliminar líneas que son solo comentarios
            if line.strip().startswith('#'):
                # Mantener comentarios tipo TODO/FIXME/HACK
                if any(marker in line for marker in ['TODO', 'FIXME', 'HACK', 'BUG', 'WARNING']):
                    result.append(line)
                continue
            
            # Eliminar comentarios inline (pero no strings)
            if '#' in line and '"' not in line.split('#')[0] and "'" not in line.split('#')[0]:
                line = line.split('#')[0].rstrip()
                if not line.strip():
                    continue
            
            # Eliminar docstrings multi-línea
            if line.strip().startswith('"""') or line.strip().startswith("'''"):
                continue
            if line.strip().endswith('"""') or line.strip().endswith("'''"):
                continue
            
            result.append(line)
        
        return '\n'.join(result)
    
    @staticmethod
    def compress_ratio(original: str, minified: str) -> float:
        """Porcentaje de reducción."""
        return (1 - len(minified) / len(original)) * 100 if original else 0