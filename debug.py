from core.memory.episodic_memory import EpisodicMemory
em = EpisodicMemory()

# Limpiar procedural_index y semantic_library
for col in [em.procedural_collection, em.semantic_collection]:
    existing = col.get(include=[])
    if existing.get("ids"):
        col.delete(ids=existing["ids"])
        print(f"   [Reset] {len(existing['ids'])} docs eliminados de {col.name}")

print("Listo. Se re-indexará todo desde cero sin duplicados.")
