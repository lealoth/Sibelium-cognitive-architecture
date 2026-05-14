"""Lector de código fuente completo."""
from pathlib import Path
from typing import Dict, List
import re


class CodeReader:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.index: Dict[str, dict] = {}
    
    def index_codebase(self, target_dir: str = "core") -> Dict[str, dict]:
        target_path = self.base_dir / target_dir
        self.index = {}
        
        for py_file in target_path.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.base_dir))
            content = py_file.read_text(encoding="utf-8")
            self.index[rel_path] = {
                "content": content,
                "lines": len(content.split('\n')),
                "functions": self._extract_functions(content),
                "classes": self._extract_classes(content),
                "imports": self._extract_imports(content)
            }
        
        return self.index
    
    def get_file(self, path: str) -> dict:
        if path not in self.index:
            return {"error": f"Archivo no indexado: {path}"}
        return self.index[path]
    
    def search_function(self, name: str) -> list:
        results = []
        for path, data in self.index.items():
            if name in data["functions"]:
                results.append({"file": path, "function": name})
        return results
    
    def get_context_for_llm(self, path: str, max_chars: int = 4000) -> str:
        file_data = self.get_file(path)
        if "error" in file_data:
            return file_data["error"]
        
        content = file_data["content"]
        if len(content) <= max_chars:
            return content
        
        functions = file_data["functions"]
        if functions:
            lines = content.split('\n')
            imports_end = 0
            for i, line in enumerate(lines):
                if line.startswith('import') or line.startswith('from'):
                    imports_end = i + 1
                elif line.strip() and not line.startswith('#'):
                    break
            
            header = '\n'.join(lines[:imports_end + 1])
            body = '\n'.join(lines[imports_end + 1:])
            
            if len(body) > max_chars - len(header):
                body = body[:max_chars - len(header) - 100] + "\n# ... (truncado)"
            
            return header + "\n" + body
        
        return content[:max_chars]
    
    def _extract_functions(self, content: str) -> List[str]:
        return re.findall(r'^\s*def\s+(\w+)\s*\(', content, re.MULTILINE)
    
    def _extract_classes(self, content: str) -> List[str]:
        return re.findall(r'^\s*class\s+(\w+)', content, re.MULTILINE)
    
    def _extract_imports(self, content: str) -> List[str]:
        return re.findall(r'^(?:from\s+\S+\s+)?import\s+(.+)$', content, re.MULTILINE)