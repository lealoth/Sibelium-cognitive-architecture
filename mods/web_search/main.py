"""Web Search Mod — Herramienta de búsqueda web nativa."""
from pathlib import Path
from datetime import datetime


def setup(flow_manager):
    mod_json = Path(__file__).parent / "mod.json"
    config = {}
    if mod_json.exists():
        import json
        config = json.loads(mod_json.read_text(encoding="utf-8")).get("config", {})
    
    max_per_hour = config.get("max_searches_per_hour", 20)
    search_count = 0
    search_reset = datetime.now()
    
    def handle_web_search(params: dict) -> str:
        """Handler para <web_search query="..." />"""
        nonlocal search_count, search_reset
        
        if (datetime.now() - search_reset).total_seconds() > 3600:
            search_count = 0
            search_reset = datetime.now()
        
        if search_count >= max_per_hour:
            return "[WebSearch] Límite de búsquedas por hora alcanzado."
        
        query = params.get("query", "")
        if not query:
            return ""
        
        return _execute_search(query, flow_manager)
    
    def _execute_search(query: str, fm) -> str:
        """Ejecuta búsqueda web y guarda en semantic_library."""
        nonlocal search_count
        
        # Optimizar query si es muy larga
        search_query = _optimize_query(query, fm)
        
        try:
            from ddgs import DDGS
            results = DDGS().text(search_query, max_results=3)
            search_count += 1
            
            if results:
                snippets = []
                for r in results:
                    body = r.get("body", "")[:300]
                    if body:
                        snippets.append(body)
                
                result_text = "\n".join(snippets)
                
                # Guardar en semantic_library
                try:
                    fm.cognitive_loop.episodic_memory.store_semantic(
                        content=f"[WebSearch] Query: {search_query}\nResultados:\n{result_text}",
                        metadata={
                            "source": "web_search",
                            "type": "external_knowledge",
                            "query": search_query[:100],
                            "importance": 0.5,
                        }
                    )
                except Exception:
                    pass
                
                print(f"   [WebSearch] '{search_query[:60]}...' → {len(snippets)} resultados")
                return result_text
            return ""
        except Exception as e:
            print(f"   [WebSearch] Error: {e}")
            return ""
    
    def _optimize_query(query: str, fm) -> str:
        """Extrae keywords si la query es muy larga."""
        if len(query) <= 200:
            return query
        
        try:
            extraction_prompt = f"""Extract 5-8 technical keywords or a short search phrase.
Return ONLY the keywords/phrase, nothing else. Example: "Python Redis LRU cache implementation thread safe"

Request: {query[:500]}

Search phrase:"""
            extracted = fm.llm.generate(
                extraction_prompt, temperature=0.1, max_tokens=30, purpose="extraer_query"
            )
            if extracted and len(extracted) > 5:
                return extracted.strip()
        except Exception:
            pass
        return query[:200]
    
    # Registrar en EnvironmentRegistry
    try:
        from core.environment_registry import EnvironmentRegistry
        registry = EnvironmentRegistry.get_instance()
        registry.register("web_search", handle_web_search)
        print(f"   [WebSearch] Herramienta <web_search> registrada.")
    except Exception as e:
        print(f"   [WebSearch] Error registrando herramienta: {e}")
    
    return handle_web_search


def teardown(flow_manager):
    try:
        from core.environment_registry import EnvironmentRegistry
        EnvironmentRegistry.get_instance().unregister("web_search")
        print("   [WebSearch] Herramienta desregistrada.")
    except Exception:
        pass