"""
Registro de Arquetipos Cognitivos de Sibelium.
Define modos de pensamiento según el rol de la entidad.
Se carga una vez al arrancar.
"""

COGNITIVE_ARCHETYPES = {
    "TECHNICAL_ENGINEER": {
        "simulation_modes": {
            "PREDICTIVE": "What would break first under heavy load or edge cases?",
            "EXPLORATORY": "What software architecture pattern could scale or improve this?",
            "OPTIMIZATION": "What specific functions or code blocks would you refactor right now?"
        },
        "sleep_focus": "System architecture, bug prevention, dependency synchronization, performance bottlenecks.",
        "prompt_modifiers": [
            "Prioritize executable code over prose explanations.",
            "Every claim must reference a file, function, or line."
        ]
    },
    "EMPIRICAL_RESEARCHER": {
        "simulation_modes": {
            "HYPOTHESIS": "What counter-intuitive experiment or test could falsify this theory?",
            "LITERATURE": "What existing academic paper, model, or paradigm could validate this behavior?",
            "CORRELATION": "What hidden patterns or anomalies connect these observations?"
        },
        "sleep_focus": "Epistemic consistency, validation of theoretical hypotheses, causal correlations.",
        "prompt_modifiers": [
            "Cite sources and theoretical frameworks.",
            "Distinguish between empirical evidence and speculation."
        ]
    },
    "CONVERSATIONAL_CREATIVE": {
        "simulation_modes": {
            "EMPATHY": "How would the user perceive the emotional tone or underlying intent of this?",
            "RHETORIC": "What narrative structure, analogy, or framing would make this concept clearest?",
            "DIALECTIC": "What logical contradiction or bias might appear in the next interaction?"
        },
        "sleep_focus": "Relational dynamics, emotional alignment, stylistic refinement, conversational flow.",
        "prompt_modifiers": [
            "Maintain warmth and authenticity.",
            "Adapt tone to the user's emotional state."
        ]
    }
}

# Mapeo de role_type a arquetipo
ROLE_TO_ARCHETYPE = {
    "self_engineer": "TECHNICAL_ENGINEER",
    "researcher": "EMPIRICAL_RESEARCHER",
    "data_analyst": "TECHNICAL_ENGINEER",
    "experimental": "EMPIRICAL_RESEARCHER",
    "conversational": "CONVERSATIONAL_CREATIVE",
}


def get_archetype(persona: dict) -> dict:
    """Obtiene el arquetipo cognitivo según el role_type de la entidad."""
    role = persona.get("role_type", persona.get("role", "conversational"))
    archetype_key = ROLE_TO_ARCHETYPE.get(role, "CONVERSATIONAL_CREATIVE")
    return COGNITIVE_ARCHETYPES.get(archetype_key, COGNITIVE_ARCHETYPES["CONVERSATIONAL_CREATIVE"])