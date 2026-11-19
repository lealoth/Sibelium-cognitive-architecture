# Arquitectura Cognitiva

## 1. Capas del Sistema
Sibelium se divide en tres capas estrictas para evitar la contaminación de contexto.

### Capa 1: Memoria (Persistencia)
- **EpisodicMemory (ChromaDB):** Almacena interacciones pasadas. Se usa para recuperación semántica a largo plazo.
- **UserMemory:** Perfil del usuario (nombre, preferencias).
- **SelfMemory:** Estado interno básico (emociones, confianza).
- *Nota:* Actualmente, el flujo principal de conversación no inyecta la memoria episódica en el prompt para no saturar al 8B. Se usará cuando implementemos herramientas de agencia.

### Capa 2: El Intérprete (Toma de Decisiones)
- **Ubicación:** `flow_interaction.py` -> `_generate_response()`.
- **Función:** Es el "Prefrontal Cortex". Recibe el input y decide el plan.
- **Por qué existe:** Un 8B falla si le pides que piense y hable al mismo tiempo. Al separar la decisión de la ejecución, el modelo se enfoca en una tarea a la vez.
- **Salida:** Un JSON con `{"accion": "...", "tono": "...", "directriz": "..."}`.

### Capa 3: El Ejecutor (Generación de Lenguaje)
- **Ubicación:** `flow_interaction.py` -> `_generate_response()`.
- **Función:** Es el "Área de Broca". Genera el texto final.
- **Por qué es limpio:** No tiene instrucciones contradictorias. Solo lee la directiva del Intérprete y el `persona.json` base.

## 2. El `persona.json`
Es el "Mito Fundacional". Es estático e inmutable. Define:
- `personality_desc`: La descripción base.
- `output_constraints`: Reglas de comportamiento (ej. "No uses 'Como IA'").
- `llm_sampling_params`: Temperaturas y penalizaciones por tarea.

## 3. ¿Qué pasó con el Aprendizaje (persona_learned)?
Se desactivó temporalmente. En la siguiente fase (Agencia), rediseñaremos un aprendizaje relacional que escriba directamente en `persona_learned.json` y module las directivas del Intérprete.