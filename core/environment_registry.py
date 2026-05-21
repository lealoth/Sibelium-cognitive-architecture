"""
EnvironmentRegistry — Registro dinámico de herramientas.
Permite a mods externos registrar acciones que el LLM puede invocar
sin modificar el core de Sibelium.
"""
import re
from typing import Dict, Any, Optional


class EnvironmentRegistry:
    """Registro universal de herramientas para el bucle ReAct."""
    
    _instance = None
    _tools: Dict[str, callable] = {}
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, tool_name: str, handler: callable):
        """
        Registra una herramienta que el LLM puede invocar vía XML.
        
        Args:
            tool_name: Nombre del tag (ej. "query_semantic", "krita_draw_line")
            handler: Función que recibe (params: dict) y devuelve str
        """
        self._tools[tool_name] = handler
        print(f"   [EnvRegistry] Herramienta registrada: <{tool_name}>")
    
    def unregister(self, tool_name: str):
        if tool_name in self._tools:
            del self._tools[tool_name]
    
    def parse_and_execute(self, output: str) -> Optional[str]:
        """
        Detecta cualquier tag <herramienta params... /> en el output del LLM
        y ejecuta la herramienta registrada correspondiente.
        """
        match = re.search(r'<(\w+)\s+([^>]+)/>', output)
        if not match:
            return None
        
        tool_name = match.group(1)
        params_str = match.group(2)
        
        # Parsear atributos estilo key="value"
        params = {}
        for attr_match in re.finditer(r'(\w+)="([^"]*)"', params_str):
            params[attr_match.group(1)] = attr_match.group(2)
        
        if tool_name not in self._tools:
            print(f"   [EnvRegistry] Herramienta no registrada: {tool_name}")
            return None
        
        try:
            result = self._tools[tool_name](params)
            return str(result)[:500] if result else None
        except Exception as e:
            print(f"   [EnvRegistry] Error ejecutando {tool_name}: {e}")
            return None
    
    @property
    def registered_tools(self) -> list:
        return list(self._tools.keys())