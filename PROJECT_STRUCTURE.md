# Estructura del Proyecto (Núcleo Cognitivo Mínimo)

Este documento describe la estructura actual del repositorio. Ha sido refactorizado para eliminar el "prompt spaghetti" y centrarse en un flujo de dos pasos: **Intérprete -> Ejecutor**.

## Árbol de Directorios

Sibelium/
├── api/
│   └── server.py                 # Servidor FastAPI y endpoints
├── core/
│   ├── cognitive_loop.py         # Orquestador principal y persistencia
│   ├── llm.py                    # Gestión del modelo local (llama.cpp)
│   ├── flow/
│   │   ├── flow_manager.py       # Orquestador del flujo de conversación
│   │   ├── flow_interaction.py   # Lógica del Intérprete y Ejecutor
│   │   └── flow_stream.py        # Memoria de trabajo a corto plazo (historial)
│   └── memory/
│       ├── episodic_memory.py    # Base de datos vectorial (ChromaDB)
│       ├── self_memory.py        # Estado interno (JSON)
│       └── user_memory.py        # Perfil del usuario (JSON)
├── entitys/
│   └── entity_data_nexus/
│       ├── identity/
│       │   └── persona.json      # Identidad estática (Mito fundacional)
│       ├── memory/               # Archivos JSON de estado e historial
│       └── chroma_db/            # Base de datos vectorial
├── frontend/                     # Interfaz web (HTML/JS/CSS)
├── config.py                     # Variables globales (rutas, modelo, GPU)
├── README.md                     # Filosofía y qué es el MVC
├── ARCHITECTURE.md               # Explicación técnica del flujo de 2 pasos
├── ROADMAP.md                    # Próximos pasos (Agencia, Rust, etc.)
└── PROJECT_STRUCTURE.md          # Este archivo

## Descripción de Módulos y Funciones Clave
1. api/server.py (Punto de Entrada)
Es el servidor FastAPI. Se encarga de recibir las peticiones HTTP del frontend y gestionar las sesiones.

get_or_create_loop(session_id): Carga o crea una instancia de CognitiveLoop en memoria.

POST /api/chat: Recibe el mensaje del usuario, llama a loop.process() y devuelve la respuesta.

GET /api/history: Devuelve el historial de conversación para que el frontend lo renderice.

Nota: Ya no carga modelos de visión, audio ni mods. Solo el LLM principal.

2. core/cognitive_loop.py (El Orquestador)
Es el "Hipocampo". Se encarga de gestionar la memoria y el estado de la entidad.

process(message): Función principal. Llama al FlowManager para generar la respuesta, guarda el historial, y actualiza el estado.

load_persona(): Lee el persona.json estático (identidad).

_save_history_to_disk(): Guarda la conversación en history.json para que el frontend no la pierda al recargar.

get_history() / get_last_state(): Endpoints para el frontend.

3. core/flow/flow_interaction.py (El Cerebro)
Aquí reside la lógica cognitiva. Es el archivo más importante para la conversación.

_generate_response(message):

Paso 1 (Intérprete): Construye un prompt corto para que el 8B decida la accion (conversar o ejecutar) y el tono (empático, técnico, etc.). Devuelve un JSON.

Paso 2 (Ejecutor): Construye un prompt limpio con la directiva del Intérprete y el persona.json. Genera el texto final.

Por qué está así: Separar la decisión de la ejecución evita que el 8B se sature y responda con rigidez.

4. core/flow/flow_manager.py (El Puente)
Es un orquestador mínimo que conecta CognitiveLoop con FlowInteraction.

handle_user_message(message): Recibe el mensaje, actualiza el FlowStream (historial corto) y llama a _generate_response().

start() / stop(): Stubs vacíos (se usaban para los hilos del FlowStream antiguo, ahora desactivados).

5. core/flow/flow_stream.py (Memoria a Corto Plazo)
Mantiene los últimos mensajes de la conversación para que el modelo tenga contexto inmediato.

on_user_interaction(message): Añade el mensaje del usuario al stream.

on_response_sent(response): Añade la respuesta del agente al stream.

get_all_active_summary(): Devuelve los últimos 4 mensajes concatenados (usado por el Intérprete).

6. core/llm.py (El Motor)
Gestiona la carga del modelo GGUF y la generación de texto.

generate(prompt, ...): Llama a llama.cpp. Aplica parámetros de sampling (temperature, repeat_penalty) según lo definido en persona.json.

Nota: Ya no tiene enrutamiento a la nube ni lógica de "estrés cognitivo". Solo inferencia local.

7. core/memory/ (Persistencia)
episodic_memory.py: Usa ChromaDB para guardar interacciones pasadas. Actualmente no se inyecta en el prompt (para no saturar), pero se usa para guardar el histórico.

self_memory.py: Guarda el estado emocional y la confianza (archivo self_state.json).

user_memory.py: Guarda datos del usuario (nombre, preferencias).

8. entitys/entity_data_nexus/identity/persona.json
Es el Mito Fundacional. Contiene:

personality_desc: Quién es la entidad.

output_constraints: Reglas de comportamiento (ej. "No uses 'Como IA'").

llm_sampling_params: Temperaturas específicas por tarea.

## Flujo de una Interacción (Paso a Paso)
El usuario envía "Hola" al frontend.

server.py recibe el mensaje y llama a CognitiveLoop.process("Hola").

CognitiveLoop llama a FlowManager.handle_user_message("Hola").

FlowManager guarda el mensaje en FlowStream (historial corto).

FlowManager llama a FlowInteraction._generate_response("Hola").

Intérprete: El 8B analiza el mensaje y responde {"accion": "conversar", "tono": "Cálido"}.

Ejecutor: El 8B lee la directiva ("sé cálido") y el persona.json, y genera la respuesta final.

CognitiveLoop guarda el historial en disco (history.json) y en ChromaDB.

server.py devuelve la respuesta al frontend.

