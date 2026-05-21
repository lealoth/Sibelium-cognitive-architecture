"""Ciclo de automejora con Sistema #40 (Cross-Domain Associative Cortex)."""
import json
import re
import concurrent.futures
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import ENTITY_DATA_DIR
from mods.self_engineer.code_reader import CodeReader


class SelfEngineer:
    def __init__(self, flow_manager, base_dir: Path):
        self.flow = flow_manager
        self.llm = flow_manager.llm
        self.reader = CodeReader(base_dir)
        self.proposals_file = ENTITY_DATA_DIR / "memory" / "improvement_proposals.json"
        self._load_proposals()
        self._analysis_cache = {}
        self._file_queue = []

    # ============================================
    # PERSISTENCIA
    # ============================================

    def _load_proposals(self):
        if self.proposals_file.exists():
            try:
                self.proposals = json.loads(self.proposals_file.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.proposals = []
        else:
            self.proposals = []

    def _save_proposals(self):
        self.proposals_file.parent.mkdir(parents=True, exist_ok=True)
        self.proposals_file.write_text(
            json.dumps(self.proposals, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_proposals(self) -> list:
        return self.proposals

    # ============================================
    # CICLO PRINCIPAL
    # ============================================

    def run_cycle(self):
        if self.flow.cognitive_loop.episodic_memory.procedural_collection.count() == 0:
            self.flow.cognitive_loop.episodic_memory.index_procedural(self.reader)
        self.reader.index_codebase()
        files = list(self.reader.index.keys())
        if not files:
            return None

        if not self._file_queue:
            self._file_queue = list(files)

        target = self._file_queue.pop(0)
        print(f"   [SelfEngineer] Analizando: {target}")
        return self.analyze_file(target)

    def analyze_file(self, file_path: str) -> Optional[str]:
        from core.perception.universal_indexer import UniversalIndexer
        indexer = UniversalIndexer(self.flow.cognitive_loop.episodic_memory)
        content = Path(file_path).read_text(encoding='utf-8')
        fragments = indexer.index_file(file_path, content, file_type="code")
        print(f"   [SelfEngineer] Indexado: {file_path} ({fragments} fragmentos)")
        return f"Indexado: {fragments} fragmentos"

    # ============================================
    # APRENDIZAJE POR REFUERZO
    # ============================================

    def _validate_and_learn(self, analysis_json, file_path):
        # Usar EnvironmentController universal
        from core.environment_controller import controller
        result = controller.execute("python_sandbox", {"code": analysis_json["patch_code"]})
        outcome = controller.evaluate_outcome(result, analysis_json.get("thought_process", ""))
        # Usar el mismo flujo que cualquier otro entorno
        self.flow.cognitive_loop.process_action_outcome(result, analysis_json["thought_process"], source="code_analysis")

    def _parse_analysis_json(self, monologo: str) -> dict:
        match = re.search(r'\{.*"thought_process".*\}', monologo, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"thought_process": monologo, "action_type": "no_action", "patch_code": ""}

    # ============================================
    # EJE EPISTÉMICO
    # ============================================

    def _build_epistemic_axis(self, file_path: str) -> str:
        parts = []

        papers = self._get_papers_knowledge()
        if papers:
            parts.append(f"--- EPISTEMIC MEMORY (EXTERNAL FACTS) ---\n{papers}")

        lessons = self._get_engineering_lessons(file_path)
        if lessons:
            parts.append(f"--- LECCIONES APRENDIDAS ---\n" + "\n".join([f"- {l[:200]}" for l in lessons]))

        aprendizajes = self._get_conversational_learnings()
        if aprendizajes:
            parts.append(f"--- CONVERSATIONAL LEARNINGS ---\n{aprendizajes}")

        # Base universal (placeholder neutral)
        parts.append(
            "--- PRINCIPLES ---\n"
            "Apply analytical reasoning. Identify patterns, gaps, and opportunities for improvement.\n"
            "Base conclusions on evidence from the provided context.\n"
            "If insufficient information, acknowledge uncertainty."
        )

        # Reglas específicas desde persona.json (si existen)
        rules = self.flow.cognitive_loop.load_persona().get("thought_style", {}).get("rules", [])
        if rules:
            parts.append("--- DOMAIN PRINCIPLES ---\n" + "\n".join([f"- {r}" for r in rules]))

        return "\n\n".join(parts)

    def _get_papers_knowledge(self) -> str:
        try:
            results = self.flow.cognitive_loop.episodic_memory.query_semantic(
                "sibelium arquitectura cognitiva sistemas", n_results=3
            )
            if results:
                fragmentos = [r["content"][:400] for r in results]
                return "<semantic_library>\n" + "\n---\n".join(fragmentos) + "\n</semantic_library>"
            return ""
        except Exception:
            return ""

    def _get_conversational_learnings(self) -> str:
        try:
            episodic = self.flow.cognitive_loop.episodic_memory
            results = episodic.collection.query(
                query_texts=["aprendizaje conversacional interacción"],
                n_results=3, where={"type": "validated_interaction"}
            )
            docs = results.get("documents", [[]])[0]
            return "\n\n".join([d[:300] for d in docs]) if docs else ""
        except Exception:
            return ""

    def _get_engineering_lessons(self, file_path: str) -> list:
        try:
            from core.memory.episodic_memory import EpisodicMemory
            episodic = EpisodicMemory()
            return episodic.get_relevant(
                f"Lección de Ingeniería {file_path}",
                user_id=self.flow.cognitive_loop.user_id,
                limit=3
            )
        except Exception:
            return []

    # ============================================
    # UTILIDADES DE CÓDIGO
    # ============================================

    def _get_file_dependencies(self, file_path: str) -> str:
        if not self.reader.index:
            self.reader.index_codebase()

        file_data = self.reader.get_file(file_path)
        if "error" in file_data:
            return ""

        imports = file_data.get("imports", [])
        deps = []

        for imp in imports:
            for path in self.reader.index.keys():
                module_path = path.replace('\\', '.').replace('/', '.').replace('.py', '')
                if module_path in imp or imp in module_path:
                    deps.append(f"  → importa: {path}")
                    break

        this_module = file_path.replace('\\', '.').replace('/', '.').replace('.py', '')
        for path, data in self.reader.index.items():
            if path == file_path:
                continue
            for imp in data.get("imports", []):
                if this_module in imp:
                    deps.append(f"  ← usado por: {path}")
                    break

        return "\n".join(deps[:8]) if deps else ""

    def _generate_file_overview(self, file_data: dict) -> str:
        functions = file_data.get("functions", [])
        classes = file_data.get("classes", [])
        lines = file_data.get("lines", 0)
        overview = f"ESTRUCTURA DEL ARCHIVO ({lines} líneas):\n"
        overview += f"Clases: {', '.join(classes) if classes else 'ninguna'}\n"
        overview += f"Funciones ({len(functions)}): {', '.join(functions[:30])}"
        if len(functions) > 30:
            overview += f"... y {len(functions) - 30} más"
        return overview

    # ============================================
    # SISTEMA #40
    # ============================================

    def _execute_code_analysis(self, name: str, eje_epistemico: str, eje_fenomenico: str) -> str:
        inhibicion = ""
        if hasattr(self.flow, 'stream'):
            for t in self.flow.stream.active:
                if getattr(t, 'type', '') == 'habituation_inhibition':
                    inhibicion = t.content
                    break

        from core.flow.trn_gate import TRNGate
        gate = TRNGate()

        razonamiento_preambulo = (
            "ANTES DE GENERAR TU MONÓLOGO, RAZONA EN SILENCIO:\n"
            "- ¿Qué hace realmente este código? ¿Cuál es su función en Sibelium?\n"
            "- ¿Hay bugs, ineficiencias, código muerto, o violaciones de principios?\n"
            "- ¿Hay algo que pueda mejorarse con un cambio mínimo y concreto?\n"
            "- ¿El código respeta los homólogos neurocientíficos de SYSTEMS.md?\n"
            "- ¿Hay duplicación de lógica, condiciones redundantes, o variables no utilizadas?"
        )

        prompt = (
            f"--- GLOBAL WORKSPACE BUFFER (SISTEMA #40) ---\n"
            f"[EJE EPISTÉMICO - MARCO DE REFERENCIA / TEORÍA]:\n{eje_epistemico}\n\n"
            f"[EJE FENOMÉNICO - ESTADO ACTUAL DEL ENTORNO / OBJETO DE ESTUDIO]:\n{eje_fenomenico}\n\n"
            f"[MÉTRICAS DE TELEMETRÍA Y ALERTAS]:\n- Sin métricas adicionales activas.\n"
            f"--- END BUFFER ---\n\n"
            f"--- UNIVERSAL COGNITIVE DIRECTIVE ---\n"
            f"Eres el motor de síntesis transmodal de {name}. "
            f"Ejecuta un proceso de abducción analítica para unificar el EJE EPISTÉMICO con el EJE FENOMÉNICO.\n\n"
            f"{razonamiento_preambulo}\n\n"
            f"Genera tu flujo de pensamiento siguiendo esta secuencia:\n"
            f"1. MAPEO ESTRUCTURAL: Principios, axiomas o patrones del EJE EPISTÉMICO.\n"
            f"2. DETECCIÓN DE DISONANCIA: Brechas, ineficiencias, contradicciones en el EJE FENOMÉNICO.\n"
            f"3. SÍNTESIS RESOLUTIVA: Hipótesis de mejora concreta.\n"
            f"4. TONO OPERATIVO: Clínico, analítico, conceptual. Sin preámbulos.\n\n"
            f"Formato de salida JSON:\n"
            f'{{"thought_process": "...", "action_type": "code_modification|no_action", '
            f'"target_file": "...", "target_function": "...", "line_range": "...", '
            f'"patch_code": "...", "explanation": "...", "trade_off": "..."}}\n\n'
            f"Flujo de consciencia actual de {name}:"
        )

        return gate._clean_xml(
            gate.execute(
                prompt=prompt, temperature=0.2, max_tokens=1000,
                purpose="monologo_transmodal", priority=0
            )
        )