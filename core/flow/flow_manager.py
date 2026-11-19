"""FlowManager: Orquestador mínimo."""
from datetime import datetime
from core.flow.flow_stream import FlowStream
from core.flow.flow_interaction import FlowInteraction
from core.llm import LLMModel

class FlowManager:
    def __init__(self, cognitive_loop, gliner_model=None):
        self.cognitive_loop = cognitive_loop
        self.llm = LLMModel.get_instance()
        
        # Solo mantenemos el stream (memoria a corto plazo) y la interacción
        self.stream = FlowStream()
        self.interaction = FlowInteraction(self)
        
        self.running = False
        self.last_message_time = None
        
        # Stubs para que el código que llama no falle
        self.satiety = type('obj', (object,), {'can_generate': lambda *args: False, 'register': lambda *args: None})()
        self.pattern_extractor = type('obj', (object,), {'check_all': lambda *args: [], 'find_similar_pattern': lambda *args: None, 'analyze_reflection': lambda *args: None})()
        self.domain_filter = type('obj', (object,), {'get_keywords': lambda: []})()
        self.archetype = {}

    def start(self): pass # Desactivado por ahora
    def stop(self): pass

    def handle_user_message(self, message: str) -> dict:
        self.last_message_time = datetime.now()
        
        # 1. Guardar en historial corto
        self.stream.on_user_interaction(message)
        
        # 2. Generar respuesta
        result = self.interaction._generate_response(message)
        response_text = str(result.get("response", ""))
        
        # 3. Guardar respuesta en historial
        self.stream.on_response_sent(response_text)
        
        return result

    def update_last_message_time(self):
        self.last_message_time = datetime.now()
    
    # Stubs para evitar errores en otros archivos
    def _load_curiosities(self): return []
    def _store_curiosity(self, *args): pass