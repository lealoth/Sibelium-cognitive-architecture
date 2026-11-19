# Roadmap: Hacia la Agencia Cognitiva

## Fase 1: Validación del MVC (Actual)
- [x] Refactorización a flujo de 2 pasos.
- [x] Eliminación del "prompt spaghetti" y módulos muertos.
- [x] El 8B mantiene identidad y fluidez conversacional.
- [ ] **Pendiente:** Validar la tasa de éxito en tareas técnicas (JSON, código simple) sin que el Intérprete se confunda.

## Fase 2: Capacidad Agéntica (Siguiente)
Para que Nexus sea un agente, debe poder interactuar con el entorno.
- [ ] **Implementar ToolRegistry:** Un registro de herramientas (leer archivo, escribir archivo, ejecutar código Python).
- [ ] **Modificar el Intérprete:** Añadir una nueva acción: `"usar_herramienta"`.
- [ ] **Bucle ReAct:** Si el Intérprete elige usar una herramienta, el Ejecutor debe generar el código de la herramienta, el sistema lo ejecuta, y el resultado se le devuelve al modelo para que genere la respuesta final.
- *Criterio de éxito:* Nexus escribe un archivo `.py` y lo ejecuta sin alucinar.

## Fase 3: Aprendizaje Relacional
- [ ] **Rediseñar `social_learning.py`:** Eliminar la dependencia de 5 usuarios. Usar un umbral de confianza basado en el `UserMemory`.
- [ ] **Reconectar `_post_process`:** Si el usuario da feedback positivo/negativo, guardar la norma en `persona_learned.json`.
- [ ] **Modificar el Intérprete:** Que lea `persona_learned.json` para ajustar el `tono` por defecto.

## Fase 4: Migración a Rust
- [ ] Evaluar `llama-cpp-4` o `mistral.rs`.
- [ ] Migrar el motor de inferencia para eliminar la sobrecarga de Python y mejorar los tiempos de respuesta en hardware modesto.
- [ ] Migrar la lógica del Intérprete/Ejecutor usando enums y tipos fuertes.