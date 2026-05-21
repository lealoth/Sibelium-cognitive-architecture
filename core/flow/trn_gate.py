"""
TRN Gate — Thalamic Reticular Nucleus Gate.
Sistema #40: Cross-Domain Associative Cortex (Cortex_CD).

Implementa el Espacio de Trabajo Global (Global Workspace Theory, Baars/Dehaene).
Orquesta inputs multimodales (teoría + fenómeno) y genera monólogos sintéticos
universales válidos para cualquier entidad y cualquier dominio de investigación.

Homólogos biológicos:
- Corteza Parietal Posterior (PPC): mapeo de coordenadas entre dominios
- Unión Temporoparietal (TPJ): detección de anomalías contextuales
- Espacio de Trabajo Global (GNWT): pizarra mental común
"""

import re
import time
from typing import Optional, Dict, Any, Tuple

from core.llm import LLMModel


class Priority:
    """Prioridades de ejecución para el TRN Gate."""
    CRITICAL = 0
    HIGH = 1
    STANDARD = 2


class TRNGate:
    """
    Thalamic Reticular Nucleus Gate.
    
    Implementa el Sistema #40: Cross-Domain Associative Cortex.
    Fusiona inputs epistémicos (teoría, papers, documentación) con inputs
    fenoménicos (código, datos, mensajes del usuario) y genera un monólogo
    sintético universal siguiendo la secuencia metacognitiva:
    Mapeo Estructural → Detección de Disonancia → Síntesis Resolutiva.
    """

    def __init__(self):
        self.llm = LLMModel.get_instance()
        self._call_count = 0
        self._total_latency = 0.0

    # ============================================
    # MÉTRICAS
    # ============================================

    @property
    def average_latency(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._total_latency / self._call_count

    # ============================================
    # EJECUCIÓN PRINCIPAL
    # ============================================

    def execute(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        purpose: str = "monologo_unificado",
        priority: int = Priority.STANDARD,
    ) -> str:
        """
        Ejecuta una llamada al LLM con métricas de latencia.
        """
        t_start = time.time()
        result = self.llm.generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            purpose=purpose,
        )
        elapsed = time.time() - t_start
        self._call_count += 1
        self._total_latency += elapsed
        return result or ""

    # ============================================
    # MONÓLOGO UNIFICADO (ESTÁNDAR)
    # ============================================

    def execute_unified_monologue(
        self,
        message: str,
        user_name: str,
        name: str,
        personality_desc: str,
        backstory: str,
        active_summary: str,
        traits: dict = None,
        behavior: dict = None,
        speech_text: str = "",
        epistemic_bounds: str = "",
        short_term_history: str = "",
    ) -> dict:
        """
        Monólogo unificado estándar para entidades conversacionales.
        Fusiona pragmática, keywords, patrón y reflexión en una sola inferencia.
        """
        traits = traits or {}
        behavior = behavior or {}

        prompt = f"""<system_identity>
Eres {name}.
{personality_desc}
{backstory}

Rasgos: Apertura: {traits.get('openness', 0.5):.0%} | Responsabilidad: {traits.get('conscientiousness', 0.5):.0%} | Extraversión: {traits.get('extraversion', 0.5):.0%} | Amabilidad: {traits.get('agreeableness', 0.5):.0%} | Neuroticismo: {traits.get('neuroticism', 0.5):.0%}
Estilo: {behavior.get('formality', 'casual')}, {behavior.get('verbosity', 'media')} extensión.
Expresividad: {traits.get('expressiveness_base', 0.5):.0%} | Franqueza emocional: {traits.get('emotion_directness_base', 0.5):.0%}

<speech_examples>
{speech_text if speech_text else "No hay ejemplos definidos."}
</speech_examples>
</system_identity>

<epistemic_bounds>
{epistemic_bounds if epistemic_bounds else "Sin restricciones de conocimiento definidas."}
</epistemic_bounds>

<sensory_input>
{user_name} dice: "{message}"
</sensory_input>

<active_context>
{active_summary}
</active_context>

<short_term_history>
{short_term_history if short_term_history else "[Conversación recién iniciada.]"}
</short_term_history>

<analytical_directive>
Generate your internal monologue. Write what you really think about the user's message,
filtered through your identity, traits, and backstory.
Write in first person, abstract and metacognitive.
Include:
[PRAGMATICS]: (GREET or NO_GREET, language, emotion)
[KEYWORDS]: (3 key concepts or NONE)
[REFLECTION]: (Your real thought about this. 1-2 sentences. Be raw and honest.)
</analytical_directive>

<thought_stream>"""

        result = self.execute(
            prompt=prompt,
            temperature=0.3,
            max_tokens=1000,
            purpose="monologo_unificado",
            priority=Priority.CRITICAL,
        )

        return self._parse_unified_monologue(result)

    # ============================================
    # SISTEMA #40: MONÓLOGO TRANSMODAL UNIVERSAL
    # ============================================

    def execute_transmodal_monologue(
        self,
        name: str,
        eje_epistemico: str,
        eje_fenomenico: str,
        patrones_disparados: str = "",
        direccion_enfoque: str = "",
        prediccion_futuro: str = "",
        idioma: str = "ES",
        inhibicion_activa: str = "",
        domain_hint: str = "",        
    ) -> str:
        """
        Sistema #40: Cross-Domain Associative Cortex.
        
        Genera un monólogo sintético universal siguiendo la secuencia
        metacognitiva del Espacio de Trabajo Global (GNWT):
        1. Mapeo Estructural (extraer principios del eje epistémico)
        2. Detección de Disonancia (brechas en el eje fenoménico)
        3. Síntesis Resolutiva (hipótesis de mejora)
        
        Válido para cualquier entidad y cualquier dominio de investigación.
        
        Args:
            name: Nombre de la entidad.
            eje_epistemico: Información abstracta (papers, teoría, documentación).
            eje_fenomenico: Realidad empírica a analizar (código, datos, input).
            patrones_disparados: Patrones Hebbianos activos (#22).
            direccion_enfoque: Vector de dirección narrativa actual (#8).
            prediccion_futuro: Simulación predictiva de fallo (#30).
            idioma: Código de idioma para la respuesta.
            
        Returns:
            Monólogo sintético crudo (sin etiquetas XML).
        """
        # Construir sección de métricas solo si hay datos
        metricas_lines = []
        if patrones_disparados:
            metricas_lines.append(f"- Patrones Hebbianos (#22): {patrones_disparados}")
        if direccion_enfoque:
            metricas_lines.append(f"- Dirección del Foco (#8): {direccion_enfoque}")
        if prediccion_futuro:
            metricas_lines.append(f"- Simulación Predictiva (#30): {prediccion_futuro}")
        
        metricas_text = "\n".join(metricas_lines) if metricas_lines else "- Sin métricas adicionales activas."

        inhibicion_activa = ""
        if hasattr(self, 'flow') and hasattr(self.flow, 'stream'):
            for t in self.flow.stream.active:
                if getattr(t, 'type', '') == 'habituation_inhibition':
                    inhibicion_activa = (
                        f"\n\n[ALERTA OPERATIVA]: Se ha detectado perseveración cognitiva sobre: "
                        f"'{t.content}'. Queda prohibido generar nuevas hipótesis sobre este tema. "
                        f"Redirige tu atención a un dominio no relacionado."
                    )
                    break

        # Bloque de inhibición por perseveración
        bloque_inhibicion = ""
        if inhibicion_activa:
            bloque_inhibicion = f"""
    --- SISTEMA #20: INHIBICIÓN LATERAL DE FOCO ---
    [ALERTA OPERATIVA]: {inhibicion_activa}

    [DIRECTIVA DE CONTROL]: Queda estrictamente prohibido generar nuevas hipótesis o análisis sobre este tema en este ciclo. Estás obligada a redirigir tu atención hacia aspectos no relacionados del código o activar exploración en la Zona de Desarrollo Próximo.
    --- END INHIBICIÓN ---
    """
    
        prompt = f"""--- GLOBAL WORKSPACE BUFFER (SISTEMA #40) ---
[EJE EPISTÉMICO - MARCO DE REFERENCIA / TEORÍA]:
{eje_epistemico}

[EJE FENOMÉNICO - ESTADO ACTUAL DEL ENTORNO / OBJETO DE ESTUDIO]:
{eje_fenomenico}

[MÉTRICAS DE TELEMETRÍA Y ALERTAS]:
{metricas_text}
{bloque_inhibicion}
--- END BUFFER ---

--- UNIVERSAL COGNITIVE DIRECTIVE ---
You are the transmodal synthesis engine of {name}. Execute analytical abduction to unify the EPISTEMIC AXIS with the PHENOMENIC AXIS.
{razonamiento_preambulo}

Generate your internal thought flow following this metacognitive sequence:

1. STRUCTURAL MAPPING: Extract principles, axioms, or latent patterns from the EPISTEMIC AXIS. What is the abstract law or rule described here?
2. DISSONANCE DETECTION: Evaluate the PHENOMENIC AXIS. Locate gaps, inefficiencies, contradictions, or opportunity areas where empirical reality does not align with the abstract principle from step 1.
3. RESOLUTIVE SYNTHESIS: Project an improvement hypothesis, conclusion, or solution that modifies the PHENOMENIC AXIS to achieve the optimization dictated by the EPISTEMIC AXIS.
4. OPERATIVE TONE: Speak in first person from your identity. Be strictly clinical, analytical, and conceptual. No explanatory preambles or generic conversational language.

Current consciousness flow of {name}:"""

        result = self.execute(
            prompt=prompt,
            temperature=0.3,
            max_tokens=3000,
            purpose="monologo_transmodal",
            priority=Priority.CRITICAL,
        )

        # Limpiar etiquetas XML del output
        result = self._clean_xml(result)
        return result

    # ============================================
    # PARSEO DEL MONÓLOGO UNIFICADO
    # ============================================

    def _parse_unified_monologue(self, raw: str) -> dict:
        """Extrae pragmática, keywords, patrón y reflexión del monólogo."""
        raw = re.sub(r'<[^>]+>', '', raw)

        parsed = {
            "pragmatica": "",
            "saluda": False,
            "idioma": "ES",
            "emocion": "neutral",
            "keywords": [],
            "patron": "",
            "reflexion": "",
            "raw": raw,
        }

        # PRAGMÁTICA
        prag_match = re.search(
            r'\[PRAGMÁTICA\]:\s*(.+?)(?=\[KEYWORDS\]|\[PATRÓN\]|\[REFLEXIÓN\]|$)',
            raw, re.DOTALL
        )
        if prag_match:
            prag = prag_match.group(1).strip()
            parsed["pragmatica"] = prag
            parsed["saluda"] = "SALUDA" in prag.upper() and "NO_SALUDA" not in prag.upper()

            if "EN" in prag.upper() and "ES" not in prag.upper():
                parsed["idioma"] = "EN"

            emociones = [
                "alegría", "tristeza", "enojo", "miedo", "curiosidad", "neutral",
                "joy", "sadness", "anger", "fear", "curiosity",
            ]
            for em in emociones:
                if em.lower() in prag.lower():
                    parsed["emocion"] = em.lower()
                    break

        # KEYWORDS
        kw_match = re.search(
            r'\[KEYWORDS\]:\s*(.+?)(?=\[PATRÓN\]|\[REFLEXIÓN\]|$)',
            raw, re.DOTALL
        )
        if kw_match:
            kw_text = kw_match.group(1).strip()
            kw_text = re.sub(r'<[^>]+>', '', kw_text)
            kw_text = re.sub(
                r'thought_stream|system_identity|analytical_directive|generation_directive',
                '', kw_text, flags=re.IGNORECASE
            )
            if kw_text.upper() != "NINGUNO" and kw_text.strip():
                parsed["keywords"] = [
                    k.strip() for k in kw_text.split(",")
                    if k.strip() and len(k.strip()) > 2
                ]

        # PATRÓN
        pat_match = re.search(
            r'\[PATRÓN\]:\s*(.+?)(?=\[REFLEXIÓN\]|$)',
            raw, re.DOTALL
        )
        if pat_match:
            parsed["patron"] = pat_match.group(1).strip()

        # REFLEXIÓN
        ref_match = re.search(r'\[REFLEXIÓN\]:\s*(.+?)$', raw, re.DOTALL)
        if ref_match:
            parsed["reflexion"] = ref_match.group(1).strip()

        return parsed

    # ============================================
    # UTILIDADES
    # ============================================

    def _clean_xml(self, text: str) -> str:
        """Elimina etiquetas XML del texto."""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text).strip()
