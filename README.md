# Sibelium: Núcleo Cognitivo Mínimo (MVC)

## ¿Qué es esto?
Sibelium es una arquitectura cognitiva open-source diseñada para simular la cognición humana en hardware de consumo. Sibelium intenta emular el **flujo de procesamiento** de una mente: percibe, interpreta, decide y ejecuta.

Este repositorio contiene el **Minimum Viable Cognition (MVC)**: una arquitectura radicalmente simplificada, diseñada para ser el punto de partida de un agente cognitivo.

## Filosofía de Diseño: Menos es Más
La versión anterior de Sibelium intentaba emular el cerebro añadiendo decenas de módulos (sistemas de saliencia, redes de tránsito talámico, sistemas inmunes). El resultado fue un "prompt spaghetti": el LLM se ahogaba en contextos contradictorios y respondía con rigidez.

La lección aprendida es que un modelo de 8B no necesita 40 módulos. Por ahora solo es:
1. Una identidad clara (sin ruido ontológico).
2. Un intérprete que decida qué hacer.
3. Un ejecutor que hable.

## El Flujo de 2 Pasos (Intérprete -> Ejecutor)
1. **El Intérprete:** Recibe el mensaje del usuario y el historial. Usa un prompt de baja temperatura para decidir dos cosas en formato JSON: la **acción** (conversar o ejecutar tarea) y el **tono** (ej. "técnico", "empático").
2. **El Ejecutor:** Recibe la directiva del Intérprete. Usa un prompt limpio (sin instrucciones contradictorias) para generar la respuesta final. Aquí es donde reside la creatividad y fluidez del modelo.

## Estado Actual (Qué funciona)
- **Identidad Consistente:** El 8B se identifica como la entidad (Nexus), no como un LLM.
- **Fluidez y Crítica:** Al eliminar el ruido, el modelo recupera su capacidad de razonamiento abstracto, filosofar y cuestionar al usuario de forma natural.
- **Rendimiento:** Tiempos de inferencia reducidos al no procesar llamadas recurrentes.
