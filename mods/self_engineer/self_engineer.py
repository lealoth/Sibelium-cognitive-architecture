"""Ciclo de automejora."""
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import ENTITY_DATA_DIR, CLOUD_API_KEY, LLM_BACKEND
from mods.self_engineer.code_reader import CodeReader


class SelfEngineer:
    def __init__(self, flow_manager, base_dir: Path):
        self.flow = flow_manager
        self.llm = flow_manager.llm
        self.reader = CodeReader(base_dir)
        self.proposals_file = ENTITY_DATA_DIR / "memory" / "improvement_proposals.json"
        self._load_proposals()
    
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
    
    def analyze_file(self, file_path: str) -> Optional[str]:
        self.reader.index_codebase()
        file_data = self.reader.get_file(file_path)
        
        if "error" in file_data:
            return None
        
        content = file_data["content"]
        lines = file_data.get("lines", 0)
        has_cloud = CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid")
        
        if lines > 200:
            from mods.self_engineer.code_minifier import CodeMinifier
            
            # Minificar siempre con agresivo
            minified = CodeMinifier.minify_aggressive(content)
            ratio = CodeMinifier.compress_ratio(content, minified)
            new_lines = len(minified.split('\n'))
            
            if ratio > 5:
                print(f"   [SelfEngineer] Minificado: {ratio:.0f}% reducción ({lines} → {new_lines} líneas)")
                content = minified
                file_data["content"] = minified
                file_data["lines"] = new_lines
                lines = new_lines
        
        if lines > 300 and has_cloud:
            result = self._analyze_chunk(file_path, content, file_data)
        elif lines <= 250:
            result = self._analyze_chunk(file_path, content, file_data)
        else:
            if len(content) <= 8000:
                result = self._analyze_chunk(file_path, content, file_data)
            else:
                result = self._analyze_file_chunked(file_path, content, file_data)
        
        if result and "SIN_PROBLEMAS" not in result.upper():
            proposal = {
                "file": file_path,
                "timestamp": datetime.now().isoformat(),
                "analysis": result
            }
            self.proposals.append(proposal)
            self._save_proposals()
            
            from core.flow.flow_stream import ThoughtItem
            self.flow.stream.add_thought(ThoughtItem(
                content=f"[Automejora] Propuesta para {file_path}",
                thought_type="self_improvement",
                priority=0.85,
                source="self_engineer"
            ))
        
        return result
    
    def _analyze_file_chunked(self, file_path: str, content: str, file_data: dict) -> Optional[str]:
        chunks = self._split_into_chunks(content)
        previous_findings = ""
        all_findings = []
        
        for i, chunk in enumerate(chunks):
            chunk_result = self._analyze_chunk(
                f"{file_path} (parte {i+1}/{len(chunks)})",
                chunk,
                file_data,
                previous_findings=previous_findings
            )
            if chunk_result and "SIN_PROBLEMAS" not in chunk_result.upper():
                all_findings.append(chunk_result)
                previous_findings = chunk_result[:300]
        
        if not all_findings:
            return "SIN_PROBLEMAS"
        return self._consolidate_analyses(file_path, all_findings)
    
    def _analyze_chunk(self, label: str, code: str, file_data: dict, previous_findings: str = "") -> Optional[str]:
        context = ""
        if previous_findings:
            context = f"Hallazgos previos en este archivo (NO los repitas):\n{previous_findings}\n\n"
        
        papers_knowledge = self._get_papers_knowledge()
        if papers_knowledge:
            context += f"CONOCIMIENTO TÉCNICO DE TUS ESTUDIOS:\n{papers_knowledge}\n\n"
        
        dependencies = self._get_file_dependencies(label)
        if dependencies:
            context += f"DEPENDENCIAS (archivos que usan o son usados por este):\n{dependencies}\n\n"
        
        overview = self._generate_file_overview(file_data)
        
        prompt = f"""ESTRUCTURA COMPLETA DEL ARCHIVO:
{overview}

{context}Analiza este fragmento de código:

ARCHIVO: {label}
LÍNEAS TOTALES: {file_data.get('lines', '?')}

{code}

Identifica problemas REALES. NO repitas hallazgos previos.
Si una función está incompleta en este fragmento, NO la analices.
Si no ves problemas REALES, responde SIN_PROBLEMAS.
Es mejor decir SIN_PROBLEMAS que inventar un problema falso.

Para cada problema:
---
PROBLEMA: [breve]
FUNCIÓN: [nombre exacto]
SEVERIDAD: [baja/media/alta]
EXPLICACIÓN: [por qué es un problema]
SOLUCIÓN: [código Python ejecutable que resuelva el problema. Debe ser el MÍNIMO cambio necesario. Solo incluye la función o líneas modificadas, no el archivo completo. Si la solución no requiere código, escribe SIN_CODIGO.]
TRADE-OFF: [qué se pierde al aplicar el cambio]
---"""
        
        lines = file_data.get("lines", 0)
        has_cloud = CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid")

        if lines > 300 and has_cloud:
            max_tokens = 2000
            temperature = 0.15
            purpose = "analizar_imagen"
        else:
            max_tokens = 600
            temperature = 0.2
            purpose = "analisis_archivo_local"
        
        return self.llm.generate(prompt, temperature=temperature, max_tokens=max_tokens, purpose=purpose)
    
    def _split_into_chunks(self, content: str, chunk_size: int = 4000) -> list:
        lines = content.split('\n')
        chunks = []
        current = []
        current_len = 0

        for line in lines:
            current.append(line)
            current_len += len(line) + 1

            if current_len >= chunk_size and line.strip().startswith('def '):
                chunks.append('\n'.join(current))
                current = []
                current_len = 0

        if current:
            chunks.append('\n'.join(current))

        return chunks
    
    def _consolidate_analyses(self, file_path: str, analyses: list) -> str:
        combined = "\n\n".join(analyses)

        if len(combined) <= 800:
            return combined

        file_data = self.reader.get_file(file_path)
        lines = file_data.get("lines", 0)
        purpose = "analizar_imagen" if (lines > 300 and CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid")) else "evaluar"
        max_tokens = 1000 if purpose == "analizar_imagen" else 600

        prompt = f"""Consolida estos análisis del archivo {file_path}.
Elimina duplicados y falsos positivos obvios.
Mantén solo problemas reales.

{combined}

Análisis consolidado:"""

        return self.llm.generate(prompt, temperature=0.1, max_tokens=max_tokens, purpose=purpose)
    
    def _get_papers_knowledge(self) -> str:
        try:
            exploration_log = ENTITY_DATA_DIR / "memory" / "exploration_log.json"
            if not exploration_log.exists():
                return ""
            
            log = json.loads(exploration_log.read_text(encoding="utf-8"))
            
            knowledge = []
            for key, value in log.items():
                if any(kw in key for kw in ["python_performance", "llm_optimization", "cognitive_architectures", "sibelium_optimization", "sibelium_architecture"]):
                    desc = value.get("description", "")
                    if desc and len(desc) > 50:
                        knowledge.append(f"De '{key}': {desc[:400]}")
            
            return "\n".join(knowledge[-3:]) if knowledge else ""
        except:
            return ""
    
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
    
    def run_cycle(self):
        self.reader.index_codebase()
        files = list(self.reader.index.keys())
        if not files:
            return None
        
        if not hasattr(self, '_file_queue') or not self._file_queue:
            import random
            self._file_queue = files.copy()
            random.shuffle(self._file_queue)
        
        target = self._file_queue.pop(0)
        print(f"   [SelfEngineer] Analizando: {target}")
        return self.analyze_file(target)
    
    def get_proposals(self) -> list:
        return self.proposals