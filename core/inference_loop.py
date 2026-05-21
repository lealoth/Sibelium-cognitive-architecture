"""
Bucle de inferencia ReAct para Sibelium.
Permite al LLM solicitar fragmentos de memoria mientras genera.
"""
import re
from typing import Optional


class InferenceLoop:
    """
    Bucle de inferencia iterativo con tool calling interno.
    El LLM puede emitir <query_*> tags para solicitar fragmentos.
    """

    def __init__(self, llm, episodic_memory, max_steps: int = 3):
        self.llm = llm
        self.em = episodic_memory
        self.max_steps = max_steps
        self._last_fragment_text = ""
        from core.environment_registry import EnvironmentRegistry
        self.registry = EnvironmentRegistry.get_instance()
        
        # Registrar herramientas nativas de ChromaDB
        self.registry.register("query_semantic", self._handle_query_semantic)
        self.registry.register("query_procedural", self._handle_query_procedural)
        self.registry.register("query_episodic", self._handle_query_episodic)

    def run(self, prompt: str, temperature: float = 0.7, max_tokens: int = 800, purpose: str = "respuesta_final") -> str:
        """
        Ejecuta el bucle ReAct con EnvironmentRegistry.
        El LLM genera, puede solicitar herramientas, y continúa generando.
        """
        context = prompt
        full_output = ""

        for step in range(self.max_steps):
            # Paso de terminación forzada en el último intento
            if step == self.max_steps - 1:
                context += "\n[SISTEMA: Último paso de pensamiento disponible. Consolida tus observaciones y genera la respuesta final ahora.]\n"
            
            output = self.llm.generate(
                context, temperature=temperature, max_tokens=max_tokens, purpose=purpose
            )
            if not output:
                break

            full_output += output
            context += output

            # Detectar y ejecutar cualquier herramienta registrada
            result = self.registry.parse_and_execute(output)
            if result:
                observation = f"\nObservación: {result}\n"
                context += observation
                full_output += observation
                continue  # El LLM sigue generando con la nueva información
            else:
                # No pidió más herramientas, terminó
                break

        return self._clean_output(full_output)
        
    def _fetch_fragment(self, collection: str, query: str) -> Optional[str]:
        try:
            if collection == "semantic":
                results = self.em.query_semantic(query, n_results=1)
            elif collection == "procedural":
                results = self.em.query_procedural(query, n_results=1)
            elif collection == "episodic":
                results = self.em.get_relevant(query, limit=1)
            else:
                return None

            if results:
                if isinstance(results[0], dict):
                    fragment = results[0].get("content") or results[0].get("code") or str(results[0])[:500]
                else:
                    fragment = str(results[0])[:500]
                
                # De-duplicación de overlap
                if fragment and self._last_fragment_text:
                    fragment = self._deduplicate_overlap(self._last_fragment_text, fragment)
                self._last_fragment_text = fragment
                
                return fragment
        except Exception as e:
            print(f"   [!] Error en fetch_fragment: {e}")
        return None

    def _clean_output(self, text: str) -> str:
        """Elimina tags de tool calling del output visible."""
        return re.sub(r'<query_[^>]+/>', '', text).strip()

    def _deduplicate_overlap(self, text1: str, text2: str) -> str:
        """Elimina solapamiento entre dos fragmentos consecutivos."""
        if not text1 or not text2:
            return text2
        # Buscar overlap: últimas 50 palabras del texto1 vs primeras 50 del texto2
        words1 = text1.strip().split()[-50:]
        words2 = text2.strip().split()[:50]
        # Encontrar la secuencia común más larga
        for i in range(min(len(words1), len(words2)), 2, -1):
            if words1[-i:] == words2[:i]:
                return ' '.join(words2[i:])
        return text2

    def _handle_query_semantic(self, params: dict) -> Optional[str]:
        """Handler para <query_semantic query="..." />"""
        return self._fetch_fragment("semantic", params.get("query", ""))

    def _handle_query_procedural(self, params: dict) -> Optional[str]:
        """Handler para <query_procedural query="..." />"""
        return self._fetch_fragment("procedural", params.get("query", ""))

    def _handle_query_episodic(self, params: dict) -> Optional[str]:
        """Handler para <query_episodic query="..." />"""
        return self._fetch_fragment("episodic", params.get("query", ""))