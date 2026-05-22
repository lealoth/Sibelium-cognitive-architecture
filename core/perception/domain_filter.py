"""
Filtro Semántico-Periférico Dinámico.
Destila palabras clave del dominio de la entidad al arrancar (8B local, una vez)
y las compila en un regex para evaluación ultrarrápida en cada tick (sin LLM).
"""
import re
from typing import List, Optional


class DomainFilter:
    """Filtro de dominio dinámico. Se inicializa una vez por entidad."""
    
    def __init__(self, persona: dict, llm=None):
        self.keywords: List[str] = []
        self.regex: Optional[re.Pattern] = None
        self._boot(persona, llm)
    
    def _boot(self, persona: dict, llm=None):
        """
        Fase de arranque: destila palabras clave del dominio de la entidad.
        Usa el 8B local una sola vez.
        """
        role = persona.get("role_type", persona.get("role", ""))
        desc = persona.get("personality_desc", persona.get("description", ""))
        
        if not role and not desc:
            # Sin información de dominio, filtrar solo por tokens técnicos universales
            self.keywords = [
                "error", "bug", "exception", "latency", "optimize", "refactor",
                "implement", "configure", "deprecate", "version", "api", "library",
                "function", "method", "parameter", "import", "module", "package"
            ]
            self._compile()
            return
        
        if llm:
            try:
                boot_prompt = f"""Analyze the entity's role and description: "{role}. {desc}".
Generate a list of 20-30 keywords, technical terms, libraries, or scientific concepts 
that STRICTLY belong to their professional domain and indicate that a doubt requires 
deep technical or scientific research.
Return ONLY the words separated by commas, no introduction."""
                
                result = llm.generate(boot_prompt, temperature=0.1, max_tokens=100, purpose="domain_boot")
                if result:
                    self.keywords = [w.strip().lower() for w in result.split(",") if len(w.strip()) > 2]
            except Exception:
                pass
        
        # Fallback: tokens universales
        if not self.keywords:
            self.keywords = [
                "error", "bug", "exception", "latency", "optimize", "refactor",
                "implement", "configure", "deprecate", "version", "api", "library",
                "function", "method", "parameter", "import", "module", "package"
            ]
        
        self._compile()
        print(f"   [DomainFilter] {len(self.keywords)} keywords compiladas para {persona.get('name', 'entidad')}")
    
    def _compile(self):
        """Compila las keywords en un regex optimizado."""
        escaped = [re.escape(kw) for kw in self.keywords]
        pattern = r'\b(' + '|'.join(escaped) + r')\b'
        self.regex = re.compile(pattern, re.IGNORECASE)
    
    def is_technical(self, text: str) -> bool:
        """Evalúa si el texto contiene términos del dominio técnico. Microsegundos."""
        if not self.regex:
            return False
        return bool(self.regex.search(text))
    
    def get_keywords(self) -> List[str]:
        return self.keywords