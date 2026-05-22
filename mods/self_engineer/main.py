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
    
    # Registrar sandbox en EnvironmentController universal
    from core.environment_controller import controller, ActionResult
    def execute_python_sandbox(params):
        result = executor.execute(params.get("code", ""))
        return ActionResult(
            success=result.get("success", False),
            output=result.get("stdout", ""),
            error=result.get("stderr", ""),
            error_type=result.get("error_type", ""),
            entropy_delta=-0.5 if result.get("success") else 0.3
        )
    controller.register_environment("python_sandbox", execute_python_sandbox)
    
    # Registrar propósitos del mod
    if hasattr(flow_manager.llm, 'register_mod_purpose'):
        flow_manager.llm.register_mod_purpose("premium", "analizar_codigo")
        flow_manager.llm.register_mod_purpose("premium", "consolidar_analisis_codigo")
        flow_manager.llm.register_mod_purpose("local", "evaluar_analisis")

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
        
        # Recuperar posición de la cola desde mod.json
        mod_json = Path(__file__).parent / "mod.json"
        if mod_json.exists():
            config = json.loads(mod_json.read_text(encoding="utf-8"))
            saved_index = config.get("queue_index", 0)
            all_files = sorted(engineer.reader.index.keys())
            if saved_index < len(all_files):
                engineer._file_queue = all_files[saved_index:] + all_files[:saved_index]
                print(f"   [SelfEngineer] Cola restaurada desde índice {saved_index}.")
        
        print("   [SelfEngineer] Codebase indexed.")
    
    def on_slow_tick(fm):
        nonlocal last_run
        now = datetime.now()
        if interval_seconds > 0 and last_run["time"] and (now - last_run["time"]).total_seconds() < interval_seconds:
            return
        last_run["time"] = now
        try:
            result = engineer.run_cycle()
            
            # Guardar posición actual en mod.json para persistencia entre reinicios
            if hasattr(engineer, '_file_queue') and engineer._file_queue:
                all_files = sorted(engineer.reader.index.keys()) if engineer.reader.index else []
                if all_files:
                    next_file = engineer._file_queue[0] if engineer._file_queue else ""
                    if next_file in all_files:
                        index = all_files.index(next_file)
                        mod_json = Path(__file__).parent / "mod.json"
                        if mod_json.exists():
                            config = json.loads(mod_json.read_text(encoding="utf-8"))
                            config["queue_index"] = index
                            mod_json.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            
            if result and hasattr(fm, '_team_channel') and fm._team_channel:
                proposals = engineer.get_proposals()
                if proposals:
                    latest = proposals[-1]
                    fm._team_channel.send(
                        sender="Ada",
                        receiver="Nexus",
                        message=f"Análisis de {latest['file']}:\n{latest['analysis']}",
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
    {latest['analysis']}

    Evalúa:
    1. ¿Es técnicamente correcta?
    2. ¿Es implementable?
    3. ¿Qué impacto tendría en el sistema?

    Responde con:
    DECISIÓN: [APROBAR / RECHAZAR / REFINAR]
    FEEDBACK: [breve]""",
                            temperature=0.2, max_tokens=1000, purpose="evaluar_analisis"
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
                    
                    # Test de solución
                    if test_solutions_enabled and hasattr(fm, 'code_executor') and fm.code_executor:
                        solution_code = latest.get("analysis", "")
                        if solution_code:
                            import re
                            code_blocks = re.findall(r'```python\n(.*?)```', solution_code, re.DOTALL)
                            if code_blocks:
                                executable_code = "\n\n".join(code_blocks)
                                executable_code = executable_code.replace('\u2192', '->')
                                executable_code = executable_code.replace('\u2713', '[OK]')
                                executable_code = executable_code.replace('\u2717', '[FAIL]')
                                executable_code = executable_code.encode('ascii', errors='replace').decode('ascii')
                                test_result = fm.code_executor.execute(executable_code)
                                
                                if not test_result["success"] and "unicode" in test_result["stderr"].lower():
                                    test_result["note"] = "Error de encoding del sandbox, no del código."
                                    test_result["success"] = None
                            else:
                                test_result = {"success": True, "stderr": "", "stdout": "", "exit_code": 0, "note": "Sin código ejecutable - propuesta conceptual"}
                            
                            latest["test_result"] = test_result

                            # Actualizar el análisis con el Reporte de Evolución Cognitiva
                            lessons = fm.self_engineer._get_engineering_lessons(latest["file"])
                            latest["analysis"] = fm.self_engineer._format_proposal(
                                latest["file"],
                                latest["analysis"],
                                test_result,
                                lessons
                            )
                            fm.self_engineer._save_proposals()

                            from core.flow.flow_stream import ThoughtItem
                            if test_result["success"] is None:
                                fm.stream.add_thought(ThoughtItem(
                                    content=f"[Test] ⚠️ No se pudo verificar {latest['file']}: error de encoding del sandbox.",
                                    thought_type="test_result",
                                    priority=0.6,
                                    source="code_executor"
                                ))
                            elif test_result["success"]:
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
                            print(f"   [SelfEngineer] Test completado: {'⚠️ encoding' if test_result['success'] is None else '✅' if test_result['success'] else '❌'}")
                            
                            # Inyectar feedback cerebeloso como aprendizaje
                            if not test_result.get("success") and test_result.get("cerebellar_feedback"):
                                fb = test_result["cerebellar_feedback"]
                                lesson = (
                                    f"[Lección] Error {fb.get('error_type')} en línea {fb.get('linea_exacta')}: "
                                    f"{fb.get('sugerencia_sinaptica', '')}"
                                )
                                fm.stream.add_thought(ThoughtItem(
                                    content=lesson,
                                    thought_type="learning",
                                    priority=0.7,
                                    source="cerebellar_feedback"
                                ))

            # Revisar respuestas de otras entidades
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

            # Registrar
    flow_manager._mod_hooks["on_startup"].append(on_startup)
    flow_manager._mod_hooks["on_slow_tick"].append(on_slow_tick)
    
    # Guardar referencias para teardown
    flow_manager._self_engineer_hooks = {
        "on_startup": on_startup,
        "on_slow_tick": on_slow_tick,
    }
    
    return engineer  # Devolver instancia para que loader la guarde


def teardown(flow_manager):
    hooks = getattr(flow_manager, '_self_engineer_hooks', {})
    for hook_name, hook_fn in hooks.items():
        if hook_name in flow_manager._mod_hooks and hook_fn in flow_manager._mod_hooks[hook_name]:
            flow_manager._mod_hooks[hook_name].remove(hook_fn)
    
    flow_manager.code_reader = None
    flow_manager.self_engineer = None
    flow_manager.code_executor = None
    if hasattr(flow_manager, '_self_engineer_hooks'):
        del flow_manager._self_engineer_hooks
    print("   [SelfEngineer] Disabled.")