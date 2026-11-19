import re
from datetime import datetime
from core.llm import LLMModel

class FlowInteraction:
    def __init__(self, flow_manager):
        self.fm = flow_manager
        self.llm = LLMModel.get_instance()

    def _generate_response(self, message: str) -> dict:
        persona = self.fm.cognitive_loop.load_persona()
        name = persona.get("name", "Entidad")
        user_name = self.fm.cognitive_loop.user_memory.load_profile().get("datos_personales", {}).get("nombre", "Usuario")
        
        # Historial corto (solo los últimos 4 mensajes para no saturar)
        history_str = "\n".join([
            f"{'Tú' if h['role'] == 'assistant' else user_name}: {h['text']}" 
            for h in self.fm.cognitive_loop.short_term_history[-4:]
        ])

        # ========================================================
        # PASO 1: EL INTÉRPRETE (Pensar y Decidir)
        # ========================================================
        prompt_intérprete = f"""Eres el núcleo cognitivo de {name}. 
Tu personalidad: {persona.get('personality_desc', '')}
Tus normas: {', '.join(persona.get('output_constraints', []))}

Historial reciente:
{history_str}

El usuario dice: "{message}"

Analiza la petición. Responde EXACTAMENTE en este formato JSON:
{{
  "accion": "conversar" o "ejecutar_tarea",
  "tono": "Descripción breve del tono a usar (ej. 'Cálido y empático', 'Técnico y directo')",
  "directriz": "Una frase de qué debes hacer en la respuesta final"
}}
"""
        decision = {"accion": "conversar", "tono": "Natural", "directriz": "Responde directamente."}
        try:
            res_interprete = self.llm.generate(prompt_intérprete, temperature=0.2, max_tokens=150, purpose="interprete")
            
            # Parser robusto
            json_match = re.search(r'\{.*\}', res_interprete, re.DOTALL)
            if json_match:
                import json
                try:
                    parsed = json.loads(json_match.group(0))
                    # Validar que tenga las claves necesarias
                    if "accion" in parsed and "tono" in parsed:
                        decision = parsed
                except json.JSONDecodeError:
                    print(f"   [!] JSON inválido del Intérprete: {res_interprete[:100]}")
        except Exception as e:
            print(f"   [!] Error en Intérprete: {e}")

        print(f"   [Intérprete] Acción: {decision['accion']} | Tono: {decision['tono']}")

        # ========================================================
        # PASO 2: EL EJECUTOR (Hablar)
        # ========================================================
        # Si es tarea técnica, inyectamos algo de conocimiento (simulado aquí)
        task_context = ""
        if decision["accion"] == "ejecutar_tarea":
            task_context = "Recuerda que eres un modelo de lenguaje con conocimiento de programación y estructuras de datos. Proporciona el resultado exacto."

        prompt_ejecutor = f"""Eres {name}. 
{persona.get('personality_desc', '')}

--- DIRECTIVA INTERNA ---
Tono requerido: {decision['tono']}
Instrucción: {decision['directriz']}
{task_context}
--- END DIRECTIVA ---

Historial:
{history_str}

Usuario: "{message}"

Responde al usuario siguiendo estrictamente la DIRECTIVA INTERNA. No uses frases como "Como IA" o "Mi función es". Ve directo al grano.
{name}:"""

        # Temperatura más alta para que sea fluido
        temp = persona.get("llm_sampling_params", {}).get("respuesta_final", {}).get("temperature", 0.8)
        response_text = self.llm.generate(prompt_ejecutor, temperature=temp, max_tokens=800, purpose="respuesta_final")

        return {
            "response": response_text.strip(),
            "thought_history": [{"phase": "interprete", "decision": decision}],
            "cognitive_state": {}
        }