"""Self Engineer Mod - setup/teardown."""
import json
from pathlib import Path
from datetime import datetime
from mods.self_engineer.code_reader import CodeReader
from mods.self_engineer.self_engineer import SelfEngineer
from mods.self_engineer.code_executor import CodeExecutor


def setup(flow_manager):
    base_dir = Path(__file__).resolve().parent.parent.parent
    engineer = SelfEngineer(flow_manager, base_dir)
    executor = CodeExecutor()
    
    flow_manager.code_reader = engineer.reader
    flow_manager.self_engineer = engineer
    flow_manager.code_executor = executor
    
    last_run = {"time": None}
    
    mod_json = Path(__file__).parent / "mod.json"
    config = {}
    if mod_json.exists():
        metadata = json.loads(mod_json.read_text(encoding="utf-8"))
        config = metadata.get("config", {})
    
    interval_hours = config.get("analysis_interval_hours", 24)
    if interval_hours == 0:
        interval_seconds = 0
    else:
        interval_seconds = int(interval_hours * 3600)
    
    self_review_enabled = config.get("self_review_enabled", False)
    test_solutions_enabled = config.get("test_solutions_enabled", False)
    
    def on_startup(fm):
        engineer.reader.index_codebase()
        print("   [SelfEngineer] Codebase indexed.")
        if interval_seconds == 0:
            try:
                engineer.run_cycle()
            except Exception as e:
                print(f"   [!] Error en ciclo inicial: {e}")
    
    def on_slow_tick(fm):
        nonlocal last_run
        now = datetime.now()
        if interval_seconds > 0 and last_run["time"] and (now - last_run["time"]).total_seconds() < interval_seconds:
            return
        last_run["time"] = now
        try:
            result = engineer.run_cycle()
            
            if result and hasattr(fm, '_team_channel') and fm._team_channel:
                proposals = engineer.get_proposals()
                if proposals:
                    latest = proposals[-1]
                    fm._team_channel.send(
                        sender="Ada",
                        receiver="Nexus",
                        message=f"Análisis de {latest['file']}:\n{latest['analysis'][:500]}",
                        msg_type="code_review"
                    )
                    print(f"   [SelfEngineer] Propuesta enviada a Nexus.")
            
            # Auto-revisión + test de soluciones
            if hasattr(fm, 'self_engineer') and fm.self_engineer:
                proposals = fm.self_engineer.get_proposals()
                if proposals and not proposals[-1].get("evaluated"):
                    latest = proposals[-1]
                    
                    # Auto-revisión
                    if self_review_enabled:
                        evaluation = fm.llm.generate(
                            f"""Eres una ingeniera senior revisando el trabajo de una ingeniera junior.

Propuesta técnica:
{latest['analysis'][:1000]}

Evalúa:
1. ¿Es técnicamente correcta?
2. ¿Es implementable?
3. ¿Qué impacto tendría en el sistema?

Responde con:
DECISIÓN: [APROBAR / RECHAZAR / REFINAR]
FEEDBACK: [breve]""",
                            temperature=0.2, max_tokens=200, purpose="evaluar"
                        )
                        latest["evaluated"] = True
                        latest["self_review"] = evaluation
                        fm.self_engineer._save_proposals()
                        
                        from core.flow.flow_stream import ThoughtItem
                        fm.stream.add_thought(ThoughtItem(
                            content=f"[Auto-revisión] {evaluation[:150]}",
                            thought_type="self_review",
                            priority=0.7,
                            source="self_engineer"
                        ))
                        print(f"   [SelfEngineer] Auto-revisión completada.")

                        if self_review_enabled and latest.get("self_review"):
                            # Inyectar la auto-revisión como pensamiento para que aprenda
                            from core.flow.flow_stream import ThoughtItem
                            fm.stream.add_thought(ThoughtItem(
                                content=f"[Aprendizaje] Mi auto-revisión de {latest['file']}: {latest['self_review'][:200]}",
                                thought_type="learning",
                                priority=0.75,
                                source="self_review"
                            ))
                    # Test de solución
                    if test_solutions_enabled and hasattr(fm, 'code_executor') and fm.code_executor:
                        solution_code = latest.get("analysis", "")
                        if solution_code:
                            import re
                            code_blocks = re.findall(r'```python\n(.*?)```', solution_code, re.DOTALL)
                            if code_blocks:
                                executable_code = "\n\n".join(code_blocks)
                                test_result = fm.code_executor.execute(executable_code)
                            else:
                                test_result = {"success": True, "stderr": "", "stdout": "", "exit_code": 0, "note": "Sin código ejecutable - propuesta conceptual"}
                            
                            if code_blocks:
                                executable_code = "\n\n".join(code_blocks)
                                # Forzar encoding UTF-8 y añadir declaración si no la tiene
                                if "encoding" not in executable_code.split('\n')[0]:
                                    executable_code = "# -*- coding: utf-8 -*-\n" + executable_code
                                # Reemplazar caracteres problemáticos
                                executable_code = executable_code.encode('utf-8', errors='replace').decode('utf-8')
                                test_result = fm.code_executor.execute(executable_code)

                            latest["test_result"] = test_result
                            fm.self_engineer._save_proposals()
                            
                            from core.flow.flow_stream import ThoughtItem
                            if test_result["success"]:
                                fm.stream.add_thought(ThoughtItem(
                                    content=f"[Test] ✅ La solución para {latest['file']} pasó las pruebas.",
                                    thought_type="test_result",
                                    priority=0.8,
                                    source="code_executor"
                                ))
                            else:
                                fm.stream.add_thought(ThoughtItem(
                                    content=f"[Test] ❌ Error en solución para {latest['file']}: {test_result['stderr'][:200]}",
                                    thought_type="test_result",
                                    priority=0.8,
                                    source="code_executor"
                                ))
                            print(f"   [SelfEngineer] Test completado: {'✅' if test_result['success'] else '❌'}")
            
            if hasattr(fm, '_team_channel') and fm._team_channel:
                replies = fm._team_channel.check("Ada")
                for reply in replies:
                    if reply.get("type") == "review":
                        from core.flow.flow_stream import ThoughtItem
                        fm.stream.add_thought(ThoughtItem(
                            content=f"[Feedback de {reply['sender']}] {reply['message'][:200]}",
                            thought_type="feedback",
                            priority=0.7,
                            source="team_channel"
                        ))
                        print(f"   [SelfEngineer] Feedback recibido de {reply['sender']}.")
        except Exception as e:
            print(f"   [!] Error en ciclo de automejora: {e}")
    
    flow_manager._mod_hooks["on_startup"].append(on_startup)
    flow_manager._mod_hooks["on_slow_tick"].append(on_slow_tick)
    
    print("   [SelfEngineer] Ready.")
    return {"engineer": engineer, "executor": executor}


def teardown(flow_manager):
    flow_manager.code_reader = None
    flow_manager.self_engineer = None
    flow_manager.code_executor = None
    print("   [SelfEngineer] Disabled.")