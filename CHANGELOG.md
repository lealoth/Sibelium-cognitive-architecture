# Changelog — Sibelium v2.0

## Kernel Cognitivo Homólogo (Refactorización Mayor)

### 4 Colecciones de Memoria
- `episodic_memory` (Hipocampo): Interacciones fragmentadas, aprendizajes validados
- `procedural_index` (Ganglios Basales): Código/APIs/comandos fragmentados por AST
- `semantic_library` (Córtex Temporal): Papers fragmentados por encabezados Markdown
- `working_memory` (Córtex Prefrontal): Prompt activo en RAM

### Fragmentación Semántica
- `SemanticChunker` con overlap de 200 tokens y navegación bidireccional
- Interacciones >2000 chars se fragmentan antes de guardar

### Bucle de Inferencia ReAct
- `InferenceLoop` con máximo 3 pasos y terminación forzada
- `EnvironmentRegistry` para herramientas dinámicas sin modificar el core
- De-duplicación de overlap entre fragmentos contiguos

### Ciclo de Aprendizaje Universal
- `EnvironmentController` con `ActionResult` estandarizado
- Evaluación dopaminérgica: éxito → `episodic_memory`, fallo → `working_memory`
- `consolidate_conversational_learning` para interacciones

### Self-Engineer
- Análisis por capas: Repository Map → query_procedural → resonancia cruzada
- Integrado con `EnvironmentController` universal
- Sandbox registrado como entorno dinámico

### Mejoras adicionales
- Decaimiento temporal en recuperación de memoria
- `code_index` renombrado a `procedural_index`
- Limpieza XML que preserva tags de tool calling
- DeepReader para archivos extensos