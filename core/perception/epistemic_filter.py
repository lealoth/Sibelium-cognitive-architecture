"""
Filtro Epistémico y Enrutador de Queries de Sibelium.
Evalúa si una duda del monólogo interno requiere búsqueda web
y abstrae componentes privados hacia conceptos universales.
"""
import json
from typing import Optional, Dict, Any


def evaluar_y_formular_busqueda(duda_cruda: str, contexto_archivo: str, llm) -> Optional[Dict[str, Any]]:
    """
    Evalúa si una duda requiere búsqueda web externa.
    Si requiere, abstrae nombres privados (Sibelium, slow_tick) a conceptos universales.
    
    Returns:
        Dict con requiere_web, razon, queries_universales
        None si no se pudo evaluar
    """
    # Obtener contexto de la entidad
    persona = self.fm.cognitive_loop.load_persona()
    entity_name = persona.get("name", "la entidad")
    entity_role = persona.get("role_type", "conversational")

    # Nombres de archivos/funciones desde el contexto activo (si los hay)
    active_files = set()
    for t in self.fm.stream.active[:5]:
        # Extraer referencias a archivos del contenido del pensamiento
        import re
        found = re.findall(r'([\w]+\.py)', t.content)
        active_files.update(found)

    project_context = ", ".join(list(active_files)[:3]) if active_files else "el proyecto local"

    prompt = f"""Eres el Filtro Epistémico de {entity_name}. Analiza esta duda del monólogo interno y determina si requiere investigación web externa o si es autoconclusiva/deductible localmente.

    Si requiere búsqueda, ABSTRAE los nombres de funciones, variables y del proyecto ({project_context}) hacia conceptos universales de la industria de IA, Ingeniería de Software y Bases de Datos Vectoriales.

    Evalúa la complejidad de la duda:
    - Baja (sintaxis, parámetros) → profundidad_requerida: 1
    - Media (optimización, bugs) → profundidad_requerida: 2-3
    - Alta (arquitectura, estado del arte) → profundidad_requerida: 4-5

    Genera SOLO un JSON con esta estructura exacta:
    {{
    "requiere_web": true/false,
    "razon": "Explicación breve",
    "queries_universales": ["query1", "query2"],
    "profundidad_requerida": 1
    }}

    [CONTEXTO]: {contexto_archivo}
    [DUDA]: {duda_cruda}

    JSON:"""

    try:
        result = llm.generate(prompt, temperature=0.1, max_tokens=200, purpose="evaluar_busqueda")
        
        # Extraer JSON de la respuesta
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return data
    except Exception as e:
        print(f"   [EpistemicFilter] Error: {e}")
    
    return None