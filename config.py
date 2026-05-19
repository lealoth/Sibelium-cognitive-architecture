import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Modelo LLM
MODEL_PATH = BASE_DIR / "models" / "Llama-3.1-8B-Instruct-Q4_K_M.gguf"    # Modelo principal local
MODEL_PATH_REASONING = BASE_DIR / "models" / "Llama-3.1-8B-Instruct-Q4_K_M.gguf"  # Modelo de razonamiento local
MODEL_PATH_JSON = BASE_DIR / "models" / "Llama-3.1-8B-Instruct-Q4_K_M.gguf" # modelo especializado en respuestas JSON local de poca complejidad / Debido a errores, todas sus funciones están temporalmente delegadas al llm local principal
MODEL_CONTEXT_SIZE = 8192
MODEL_THREADS = 8  # Ajustar según CPU
MODEL_GPU_LAYERS = -1  # -1 = todas las capas en GPU si hay

# Cuántas capas de cada modelo van a la GPU (-1 = todas, 0 = ninguna, N = número de capas)
GPU_LAYERS_MAIN = 30       # La mitad de las ~32 capas de Llama 8B a GPU
GPU_LAYERS_REASONING = 0   # Modelos pequeños a CPU
GPU_LAYERS_JSON = 0        # Modelos pequeños a CPU

# Backend de GPU (vulkan o cuda)
GPU_BACKEND = "vulkan"

# Backend: "local", "cloud", o "hybrid"
LLM_BACKEND = "hybrid"

# Cloud API (compatible con OpenAI)
CLOUD_API_KEY = "your-api-key"  # Tu API key de modelo en la nube principal (asegúrate de mantenerla segura y no exponerla públicamente)
CLOUD_MODEL_FREE = "deepseek/deepseek-v4-flash:free" # Modelo gratuito en la nube para tareas simples o como respaldo cuando el premium no está disponible
CLOUD_MODEL_PREMIUM = "google/gemini-2.0-flash-001" # Modelo premium en la nube para tareas complejas o cuando el local no es suficiente, se recomienda usar un modelo con buena capacidad de razonamiento y comprensión contextual para complementar al local
CLOUD_API_URL = "https://openrouter.ai/api/v1"  # o "https://api.openai.com", etc.

# Personalidad
MAX_PERSONALITY_RETRIES = 3 # Cuántas veces intentar ajustar la personalidad antes de rendirse, no está integrado en el código aun.
PERSONALITY_CHECK_ENABLED = True

# Idioma principal para todas las respuestas
IDIOMA = "español"

# Memoria
MEMORY_MAX_RESULTS = 5
MEMORY_SIMILARITY_THRESHOLD = 0.7

# Base de datos
DATABASE_URL = f"sqlite:///{BASE_DIR}/chatbot.db"

# Servidor
HOST = "127.0.0.1"
PORT = 8000

# Pensamiento y respuesta
THOUGHT_TEMPERATURE = 0.5
RESPONSE_TEMPERATURE = 0.7
MAX_VERIFICATION_RETRIES = 1

# Archivos de datos
ENTITY_DATA_DIR = BASE_DIR / "entitys" / "entity_data_nexus"  # Cambia "entity_data_nexus" por "entity_data_ada" para la otra entidad
PERSONA_FILE = ENTITY_DATA_DIR / "identity" / "persona.json"
USERS_DIR = ENTITY_DATA_DIR / "memory" / "users"
SELF_STATE_FILE = ENTITY_DATA_DIR / "memory" / "self_state.json"
CHROMA_PATH = ENTITY_DATA_DIR / "chroma_db"
EVOLUTION_LOG_FILE = ENTITY_DATA_DIR / "memory" / "evolution_log.json"
DETECTORS_LOG_FILE = ENTITY_DATA_DIR / "memory" / "detectors.json"
STATE_SNAPSHOT_FILE = ENTITY_DATA_DIR / "memory" / "state_snapshot.json"
COGNITIVE_TRACE_FILE = ENTITY_DATA_DIR / "logs" / "cognitive_trace.json"
EXPLORE_DIR = ENTITY_DATA_DIR / "nexus_world"
EXPLORE_LOG_FILE = ENTITY_DATA_DIR / "memory" / "exploration_log.json"
CURIOSITY_FILE = ENTITY_DATA_DIR / "memory" / "curiosity_log.json"
STATE_SNAPSHOT_FILE = ENTITY_DATA_DIR / "memory" / "state_snapshot.json"
PENDING_MESSAGES_FILE = ENTITY_DATA_DIR / "memory" / "pending_messages.json"
BACKGROUND_DEBUG_LOG = ENTITY_DATA_DIR / "logs" / "background_debug.jsonl"
SCAFFOLDING_FILE = ENTITY_DATA_DIR / "memory" / "scaffolding.json"

# Mensajes proactivos (la entidad puede iniciar conversación)
PROACTIVE_MESSAGES_ENABLED = False
PROACTIVE_COOLDOWN_MINUTES = 120  # Minutos mínimos desde el último mensaje del usuario
PROACTIVE_QUIET_HOURS_START = 22  # Hora en que deja de enviar mensajes (22 = 10 PM)
PROACTIVE_QUIET_HOURS_END = 8     # Hora en que vuelve a enviar mensajes (8 = 8 AM)

# Mods activos
ENABLED_MODS = []  # ["self_engineer"] para activar
# ENABLED_MODS_NEXUS = ["director", "team_channel", "self_engineer"]
# ENABLED_MODS_ADA = ["team_channel", "self_engineer"]

EXPERIMENTAL_MONITOR = False
