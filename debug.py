from core.memory.episodic_memory import EpisodicMemory
em = EpisodicMemory()
results = em.query_procedural("llm.py", n_results=5)
for r in results:
    print(f"{r.get('file', '?')} - {r.get('function', '?')} - {r.get('code', '')[:100]}")