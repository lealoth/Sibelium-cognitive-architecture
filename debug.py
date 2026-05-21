from core.memory.episodic_memory import EpisodicMemory
from config import ENTITY_DATA_DIR, CURIOSITY_FILE
from pathlib import Path
import json

em = EpisodicMemory()

# Limpiar las 3 colecciones
for col in [em.collection, em.procedural_collection, em.semantic_collection]:
    try:
        existing = col.get(include=[])
        if existing.get("ids"):
            col.delete(ids=existing["ids"])
            print(f"   [Reset] {len(existing['ids'])} docs eliminados de {col.name}")
    except Exception as e:
        print(f"   [!] Error: {e}")

# Limpiar historial
history_path = ENTITY_DATA_DIR / "memory" / "users" / "ada" / "history.json"
if history_path.exists():
    history_path.write_text(json.dumps({"history": [], "thought_history": [], "cognitive_state": None, "interaction_count": 0}))

# Limpiar curiosidades
if CURIOSITY_FILE.exists():
    CURIOSITY_FILE.write_text("[]")

# Limpiar propuestas
proposals_file = ENTITY_DATA_DIR / "memory" / "improvement_proposals.json"
if proposals_file.exists():
    proposals_file.write_text("[]")

# Limpiar exploration log
exploration_log = ENTITY_DATA_DIR / "memory" / "exploration_log.json"
if exploration_log.exists():
    exploration_log.write_text("{}")

# Limpiar detectores
from config import DETECTORS_LOG_FILE
if DETECTORS_LOG_FILE.exists():
    DETECTORS_LOG_FILE.unlink()

print("✅ Reset completo de Ada. Lista para indexar desde cero.")