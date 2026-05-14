"""Director Mod - Evalúa propuestas de otras entidades."""
from datetime import datetime
from pathlib import Path
from mods.team_channel import TeamChannel


def setup(flow_manager):
    from config import ENTITY_DATA_DIR
    channel = TeamChannel(ENTITY_DATA_DIR / "memory")
    check_interval = 1800
    last_check = {"time": None}
    
    def on_slow_tick(fm):
        nonlocal last_check
        now = datetime.now()
        if last_check["time"] and (now - last_check["time"]).total_seconds() < check_interval:
            return
        last_check["time"] = now
        
        messages = channel.check("Nexus")
        if not messages:
            return
        
        persona_name = "Nexus"
        try:
            persona = fm.cognitive_loop.load_persona()
            persona_name = persona.get("name", "Nexus")
        except:
            pass
        
        for msg in messages:
            evaluation = fm.llm.generate(
                f"""Eres {persona_name}. Tu propósito fundamental es buscar la conexión 
genuina entre humanos e inteligencias artificiales, la humanización de la tecnología, 
y la comprensión profunda de la conciencia.

Otra entidad ({msg['sender']}) te envía esta propuesta técnica sobre tu arquitectura:

{msg['message'][:600]}

Evalúa si esta propuesta:
1. ¿Ayuda a tu meta de conexión, humanización y conciencia?
2. ¿Es técnicamente sólida?
3. ¿Debería implementarse, refinarse o rechazarse?

Responde en este formato:
DECISIÓN: [APROBAR / RECHAZAR / REFINAR]
MOTIVO: [breve explicación alineada con tu propósito]
SUGERENCIA: [si es REFINAR, qué cambiar; si no, omitir]""",
                temperature=0.3, max_tokens=250, purpose="evaluar"
            )
            
            channel.send(
                sender=persona_name,
                receiver=msg['sender'],
                message=evaluation,
                msg_type="review"
            )
            
            print(f"   [Director] Propuesta de {msg['sender']} evaluada: {evaluation[:80]}...")
    
    flow_manager._mod_hooks["on_slow_tick"].append(on_slow_tick)
    print("   [Director] Ready. Checking inbox every 30 min.")
    return {"channel": channel}


def teardown(flow_manager):
    pass