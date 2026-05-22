"""
EnvironmentController — Interfaz universal de validación de acciones.
Cualquier mod o sandbox se registra aquí para que el core evalúe
el resultado de una acción sin conocer los detalles del dominio.

Homólogo: Corteza Motora + Sistema Dopaminérgico Central.
"""

from typing import Dict, Any, Optional


class ActionResult:
    """Estructura unificada de resultado de acción."""
    def __init__(self, success: bool, output: Any = None, error: str = "",
                 error_type: str = "", entropy_delta: float = 0.0):
        self.success = success
        self.output = output
        self.error = error
        self.error_type = error_type
        self.entropy_delta = entropy_delta  # Negativo = mejoró, Positivo = empeoró
        self.has_critical_error = not success and error != ""


class EnvironmentController:
    """
    Controlador de entorno universal.
    Evalúa acciones de cualquier dominio y determina si consolidar o descartar.
    """
    
    def __init__(self):
        self._registered_environments: Dict[str, callable] = {}
        self._default_evaluator = None
    
    def register_environment(self, name: str, execute_fn: callable):
        """
        Registra un entorno de ejecución.
        
        Args:
            name: Nombre del entorno (ej. "python_sandbox", "krita_canvas", "blender_3d")
            execute_fn: Función que recibe (action_params: dict) y devuelve ActionResult
        """
        self._registered_environments[name] = execute_fn
        print(f"   [EnvController] Entorno registrado: {name}")
    
    def execute(self, environment: str, action_params: dict) -> ActionResult:
        """
        Ejecuta una acción en un entorno registrado.
        """
        if environment not in self._registered_environments:
            return ActionResult(
                success=False,
                error=f"Entorno no registrado: {environment}",
                error_type="UnknownEnvironment"
            )
        
        try:
            return self._registered_environments[environment](action_params)
        except Exception as e:
            return ActionResult(
                success=False, error=str(e),
                error_type=type(e).__name__
            )
    
    def evaluate_outcome(self, action_result: ActionResult, context_intent: str = "",
                         reward_threshold: float = 0.80) -> str:
        """
        Evalúa universalmente el resultado de una acción.
        
        Returns:
            "DOPAMINERGIC_REWARD" → Consolidar en episodic_memory
            "PREDICTION_ERROR" → Solo working_memory, descartar
            "CRITICAL_FAILURE" → Error duro, inyectar feedback
        """
        if action_result.has_critical_error:
            return "CRITICAL_FAILURE"
        
        # Si el entorno ya calculó el delta de entropía
        if action_result.entropy_delta != 0.0:
            if action_result.entropy_delta < 0:  # Entropía reducida = mejoró
                return "DOPAMINERGIC_REWARD"
            else:
                return "PREDICTION_ERROR"
        
        # Si hay output y contexto, evaluar con LLM
        if action_result.output and context_intent:
            reward_score = self._evaluate_with_llm(
                str(action_result.output)[:500],
                context_intent[:500]
            )
            if reward_score > reward_threshold:
                return "DOPAMINERGIC_REWARD"
        
        return "PREDICTION_ERROR"
    
    def _evaluate_with_llm(self, output: str, intent: str) -> float:
        """Evalúa si el output cumple la intención original."""
        try:
            from core.llm import LLMModel
            llm = LLMModel.get_instance()
            prompt = f"""Evalúa si este resultado cumple la intención original.
Intención: {intent[:300]}
Resultado: {output[:300]}
Responde SOLO un número del 0.0 al 1.0 donde 1.0 es cumplimiento total."""
            result = llm.generate(prompt, temperature=0.1, max_tokens=5, purpose="evaluar_resultado")
            return float(result.strip().replace(",", "."))
        except Exception:
            return 0.5


# Singleton
controller = EnvironmentController()