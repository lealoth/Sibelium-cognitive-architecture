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
    def minify_aggressive(code: str) -> str:
        """Minificación agresiva para modelo local. Elimina type hints, docstrings, logs, comentarios."""
        import re
        
        # Eliminar docstrings multi-línea
        code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)
        
        # Eliminar type hints (pero no los dos puntos de slices o dicts)
        code = re.sub(r':\s*\w+\s*=', '=', code)
        code = re.sub(r'->\s*[\w\[\], ]+:', ':', code)
        
        # Eliminar líneas de print/logging
        code = re.sub(r'^\s*print\(.*\).*\n?', '', code, flags=re.MULTILINE)
        
        # Eliminar comentarios inline
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        
        # Colapsar líneas vacías múltiples
        code = re.sub(r'\n\s*\n', '\n', code)
        
        return code.strip()

    @staticmethod
    def compress_ratio(original: str, minified: str) -> float:
        """Porcentaje de reducción."""
        return (1 - len(minified) / len(original)) * 100 if original else 0