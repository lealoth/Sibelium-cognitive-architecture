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
    auto_research_enabled = config.get("auto_research_enabled", True)
    reactive_search_enabled = config.get("reactive_search_enabled", True)
    
    search_count = 0
    search_reset = datetime.now()
    
    def handle_web_search(params: dict) -> str:
        """Handler para <web_search query="..." />"""
        nonlocal search_count, search_reset
        
        # Resetear contador cada hora
        if (datetime.now() - search_reset).total_seconds() > 3600:
            search_count = 0
            search_reset = datetime.now()
        
        if search_count >= max_per_hour:
            return "[WebSearch] Límite de búsquedas por hora alcanzado."
        
        query = params.get("query", "")
        if not query:
            return ""
        
        try:
            from ddgs import DDGS
            results = DDGS().text(query, max_results=3)
            search_count += 1
            
            if results:
                snippets = []
                for r in results:
                    title = r.get("title", "")[:100]
                    body = r.get("body", "")[:300]
                    if body:
                        snippets.append(f"- {title}\n  {body}")
                
                result_text = "\n".join(snippets)
                
                # Si auto-research está activo, guardar en semantic_library
                if auto_research_enabled:
                    try:
                        flow_manager.cognitive_loop.episodic_memory.store_semantic(
                            content=f"[WebSearch] Query: {query}\nResultados:\n{result_text}",
                            metadata={
                                "source": "web_search",
                                "type": "external_knowledge",
                                "query": query[:100],
                                "importance": 0.5,
                            }
                        )
                    except Exception:
                        pass
                
                print(f"   [WebSearch] '{query[:60]}...' → {len(snippets)} resultados")
                return result_text
            return "[WebSearch] Sin resultados."
        except Exception as e:
            print(f"   [WebSearch] Error: {e}")
            return f"[WebSearch] Error: {e}"
    
    # Registrar en EnvironmentRegistry
    try:
        from core.environment_registry import EnvironmentRegistry
        registry = EnvironmentRegistry.get_instance()
        registry.register("web_search", handle_web_search)
        print(f"   [WebSearch] Herramienta <web_search> registrada.")
    except Exception as e:
        print(f"   [WebSearch] Error registrando herramienta: {e}")
    
    # Registrar hooks para auto-research en pensamientos de fondo
    if auto_research_enabled:
        def on_fast_tick(fm):
            # El auto-research se activa desde flow_thoughts._auto_resolve_doubt()
            pass
        
        flow_manager._mod_hooks["on_fast_tick"].append(on_fast_tick)
    
    return handle_web_search


def teardown(flow_manager):
    try:
        from core.environment_registry import EnvironmentRegistry
        EnvironmentRegistry.get_instance().unregister("web_search")
        print("   [WebSearch] Herramienta desregistrada.")
    except Exception:
        pass