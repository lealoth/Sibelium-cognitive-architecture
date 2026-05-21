"""
Deep Reader — Saccadic Parallel Chunking para archivos extensos.
Sistema de Lectura Bifásica: Macro-Atención y Micro-Foco.
Homólogo a la Focalización Atencional Top-Down y Agrupamiento Jerárquico.

Fase 1: Esqueleto estructural (sin LLM, regex/ast)
Fase 2: Chunks paralelos con modelo local
Fase 3: Integración talámica con modelo cloud (si disponible)
"""

import re
import concurrent.futures
from pathlib import Path
from typing import Optional


class DeepReader:
    """Lector de archivos extensos con atención jerárquica."""

    def __init__(self, llm=None):
        self.llm = llm  # Se inyecta desde el flow_manager

    # ============================================
    # FASE 1: ESQUELETO ESTRUCTURAL (Sin LLM)
    # ============================================

    def extract_skeleton(self, content: str, file_type: str = "auto") -> str:
        """
        Extrae el esqueleto estructural sin usar LLM.
        Soporta: Python, Markdown, texto plano.
        """
        if file_type == "auto":
            file_type = self._detect_type(content)

        if file_type == "python":
            return self._skeleton_python(content)
        elif file_type == "markdown":
            return self._skeleton_markdown(content)
        else:
            return self._skeleton_text(content)

    def _detect_type(self, content: str) -> str:
        """Detecta el tipo de contenido."""
        if content.strip().startswith("import ") or content.strip().startswith("def ") or content.strip().startswith("class "):
            return "python"
        if content.strip().startswith("# ") or "```" in content:
            return "markdown"
        return "text"

    def _skeleton_python(self, content: str) -> str:
        """Esqueleto de archivo Python: imports, clases, métodos, docstrings."""
        lines = content.split('\n')
        skeleton = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ')):
                skeleton.append(f"L{i}: {stripped}")
            elif stripped.startswith('class '):
                skeleton.append(f"\nL{i}: {stripped}")
            elif stripped.startswith('def '):
                skeleton.append(f"L{i}: {stripped}")
            elif stripped.startswith('@'):
                skeleton.append(f"L{i}: {stripped}")
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                if len(stripped) > 3:
                    skeleton.append(f"L{i}: {stripped[:100]}")
        return '\n'.join(skeleton) if skeleton else "(Estructura no detectada)"

    def _skeleton_markdown(self, content: str) -> str:
        """Esqueleto de Markdown: encabezados y primeras líneas de secciones."""
        lines = content.split('\n')
        skeleton = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                skeleton.append(f"L{i}: {stripped}")
            elif stripped.startswith('|') and '|' in stripped[1:]:
                skeleton.append(f"L{i}: (tabla)")
        return '\n'.join(skeleton) if skeleton else "(Estructura no detectada)"

    def _skeleton_text(self, content: str) -> str:
        """Esqueleto de texto plano: primeras y últimas líneas de párrafos."""
        lines = content.split('\n')
        if len(lines) <= 50:
            return f"(Texto corto, {len(lines)} líneas)"
        skeleton = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped and (i <= 5 or i >= len(lines) - 5 or stripped[0].isupper()):
                skeleton.append(f"L{i}: {stripped[:100]}")
        return '\n'.join(skeleton[:30])

    # ============================================
    # FASE 2: CHUNKS PARALELOS
    # ============================================

    def split_into_chunks(self, content: str, num_chunks: int = 3) -> list:
        """Divide el contenido en N chunks respetando límites estructurales."""
        lines = content.split('\n')
        chunk_size = max(1, len(lines) // num_chunks)

        chunks = []
        current = []
        for i, line in enumerate(lines):
            current.append(line)
            if len(current) >= chunk_size and i < len(lines) - 1:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                # Cortar en límites naturales
                if (next_line.startswith(('def ', 'class ', '@', '# ', '## '))
                        or next_line == ''):
                    chunks.append('\n'.join(current))
                    current = []
        if current:
            chunks.append('\n'.join(current))
        return chunks

    def _process_chunk_local(self, chunk_text: str, chunk_idx: int, total_chunks: int,
                             skeleton: str, purpose: str = "analizar_archivo") -> str:
        """Procesa un chunk individual con el modelo local."""
        if self.llm is None:
            return f"[Chunk {chunk_idx+1}] LLM no disponible."

        prompt = f"""--- LECTURA PROFUNDA: FRAGMENTO {chunk_idx+1}/{total_chunks} ---
[MAPA ESTRUCTURAL DEL DOCUMENTO COMPLETO]:
{skeleton[:1500]}

[FRAGMENTO ACTUAL]:
{chunk_text[:2000]}

--- DIRECTIVA ---
Extrae información clave de este fragmento:
1. Conceptos principales y sus relaciones.
2. Datos, afirmaciones o lógica relevante.
3. Preguntas que este fragmento deja sin responder.

Responde de forma ultra-compacta (viñetas, máximo 200 tokens). Sin introducciones."""

        try:
            result = self.llm.generate(
                prompt, temperature=0.2, max_tokens=200,
                purpose="analisis_archivo_local"
            )
            return result or f"[Chunk {chunk_idx+1}] Sin información relevante."
        except Exception as e:
            return f"[Chunk {chunk_idx+1}] Error: {str(e)[:100]}"

    # ============================================
    # FASE 3: INTEGRACIÓN
    # ============================================

    def _integrate_chunks(self, chunk_outputs: list, skeleton: str,
                          file_name: str, total_lines: int,
                          integration_prompt: str = "") -> str:
        """
        Integra los outputs de los chunks en un análisis unificado.
        Usa el modelo cloud si está disponible (Thalamic Router).
        """
        if self.llm is None:
            return "\n\n".join(chunk_outputs)

        caracteristicas = "\n".join([
            f"- Bloque {i+1} (Líneas ~{i*len(chunk_outputs)//len(chunk_outputs)}-{(i+1)*len(chunk_outputs)//len(chunk_outputs)}): {output[:300]}"
            for i, output in enumerate(chunk_outputs)
        ])

        if not integration_prompt:
            integration_prompt = f"""--- SÍNTESIS GLOBAL ---
[MAPA ESTRUCTURAL DEL DOCUMENTO]:
{skeleton[:1500]}

[ANÁLISIS POR BLOQUES]:
{caracteristicas}

[ARCHIVO]: {file_name}
[LÍNEAS TOTALES]: {total_lines}

--- DIRECTIVA ---
Integra los análisis por bloques en una comprensión unificada del documento.
Identifica patrones globales, contradicciones entre secciones, y temas principales.
Responde en formato de análisis estructurado."""

        try:
            result = self.llm.generate(
                integration_prompt, temperature=0.3, max_tokens=800,
                purpose="respuesta_final"  # Activa Thalamic Router → cloud si disponible
            )
            return result or "\n\n".join(chunk_outputs)
        except Exception:
            return "\n\n".join(chunk_outputs)

    # ============================================
    # API PÚBLICA
    # ============================================

    def read(self, file_path: str, purpose: str = "analizar") -> str:
        """
        Lee un archivo extenso usando Saccadic Parallel Chunking.
        
        Args:
            file_path: Ruta al archivo.
            purpose: Propósito del análisis (para el prompt de integración).
        
        Returns:
            Análisis completo del archivo.
        """
        path = Path(file_path)
        if not path.exists():
            return f"[Error] Archivo no encontrado: {file_path}"

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return f"[Error] No se pudo leer el archivo: {e}"

        lines = len(content.split('\n'))

        # Si es corto, análisis directo
        if lines <= 250:
            return content

        # Fase 1: Esqueleto
        file_type = "python" if path.suffix == '.py' else "markdown" if path.suffix in ['.md', '.txt'] else "text"
        skeleton = self.extract_skeleton(content, file_type)

        # Fase 2: Chunks paralelos
        chunks = self.split_into_chunks(content, num_chunks=3)
        chunk_outputs = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self._process_chunk_local, chunk, i, len(chunks), skeleton, purpose
                ): i
                for i, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(futures):
                chunk_outputs.append(future.result())

        # Reordenar
        chunk_outputs.sort(
            key=lambda x: int(x.split('Chunk ')[1].split(']')[0]) if 'Chunk ' in str(x) else 0
        )

        # Fase 3: Integración
        return self._integrate_chunks(
            chunk_outputs, skeleton, path.name, lines,
            integration_prompt=f"Analiza el archivo {path.name} ({lines} líneas). Propósito: {purpose}."
        )

    def read_with_custom_prompt(self, file_path: str, integration_prompt: str) -> str:
        """Lee un archivo con un prompt de integración personalizado."""
        path = Path(file_path)
        if not path.exists():
            return f"[Error] Archivo no encontrado: {file_path}"

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return f"[Error] No se pudo leer el archivo: {e}"

        lines = len(content.split('\n'))

        if lines <= 250:
            return content

        skeleton = self.extract_skeleton(content)
        chunks = self.split_into_chunks(content, num_chunks=3)
        chunk_outputs = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self._process_chunk_local, chunk, i, len(chunks), skeleton, "analizar"
                ): i
                for i, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(futures):
                chunk_outputs.append(future.result())

        chunk_outputs.sort(
            key=lambda x: int(x.split('Chunk ')[1].split(']')[0]) if 'Chunk ' in str(x) else 0
        )

        return self._integrate_chunks(
            chunk_outputs, skeleton, path.name, lines,
            integration_prompt=integration_prompt
        )