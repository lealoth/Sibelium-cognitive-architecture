"""
Fragmentación semántica inteligente para Sibelium.
Divide documentos en fragmentos con solapamiento y metadatos de navegación.
"""
import re
import uuid
from typing import List, Dict


class SemanticChunker:
    """Fragmenta documentos respetando límites lógicos (Markdown, código, texto)."""

    def __init__(self, target_chars: int = 1500, overlap_chars: int = 200):
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def chunk_semantic(self, content: str, content_type: str = "text") -> List[Dict]:
        """
        Fragmenta contenido en chunks semánticos con metadatos de navegación.
        
        Returns:
            Lista de dicts: {text, index, total, prev_id, next_id, section, content_type}
        """
        if content_type == "markdown":
            return self._chunk_markdown(content)
        elif content_type == "code":
            return self._chunk_code(content)
        else:
            return self._chunk_text(content)

    def _chunk_markdown(self, content: str) -> List[Dict]:
        """Fragmenta Markdown por encabezados y párrafos lógicos."""
        sections = re.split(r'\n(?=#{1,4}\s)', content)
        chunks = []
        current = ""
        current_section = ""

        for section in sections:
            header_match = re.match(r'(#{1,4})\s+(.+)', section)
            section_title = header_match.group(2) if header_match else current_section
            if header_match:
                current_section = section_title

            if len(current) + len(section) > self.target_chars and current:
                chunks.append({"text": current.strip(), "section": current_section})
                current = section[-self.overlap_chars:] + "\n\n" if len(section) > self.overlap_chars else section
            else:
                current += section

        if current.strip():
            chunks.append({"text": current.strip(), "section": current_section})

        return self._add_navigation(chunks)

    def _chunk_code(self, content: str) -> List[Dict]:
        """Fragmenta código por funciones/clases (AST simple)."""
        lines = content.split('\n')
        chunks = []
        current = []
        current_start = 1
        current_function = ""
        current_class = ""

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('class '):
                if current and len('\n'.join(current)) > 500:
                    chunks.append({
                        "text": '\n'.join(current),
                        "section": f"{current_class}.{current_function}" if current_class else current_function
                    })
                    current = []
                current_class = stripped.split('class ')[1].split('(')[0].split(':')[0].strip()
                current_function = ""
                current_start = i
                current.append(line)
            elif stripped.startswith('def '):
                if current and len('\n'.join(current)) > 500:
                    chunks.append({
                        "text": '\n'.join(current),
                        "section": f"{current_class}.{current_function}" if current_class else current_function
                    })
                    current = [line]
                    current_start = i
                else:
                    current.append(line)
                current_function = stripped.split('def ')[1].split('(')[0].strip()
            else:
                current.append(line)
                if len('\n'.join(current)) > self.target_chars:
                    chunks.append({
                        "text": '\n'.join(current),
                        "section": f"{current_class}.{current_function}" if current_class else current_function
                    })
                    current = current[-self.overlap_chars // 50:] if self.overlap_chars > 0 else []

        if current:
            chunks.append({
                "text": '\n'.join(current),
                "section": f"{current_class}.{current_function}" if current_class else current_function
            })

        return self._add_navigation(chunks)

    def _chunk_text(self, content: str) -> List[Dict]:
        """Fragmenta texto plano por párrafos con solapamiento."""
        paragraphs = content.split('\n\n')
        chunks = []
        current = ""
        current_section = ""

        for para in paragraphs:
            if len(current) + len(para) > self.target_chars and current:
                chunks.append({"text": current.strip(), "section": current_section or "general"})
                current = para[-self.overlap_chars:] + "\n\n" if len(para) > self.overlap_chars else para
            else:
                current += para + "\n\n"

        if current.strip():
            chunks.append({"text": current.strip(), "section": current_section or "general"})

        return self._add_navigation(chunks)

    def _add_navigation(self, chunks: List[Dict]) -> List[Dict]:
        """Añade metadatos de navegación bidireccional a cada chunk."""
        total = len(chunks)
        ids = [str(uuid.uuid4())[:8] for _ in range(total)]

        for i, chunk in enumerate(chunks):
            chunk["fragment_id"] = ids[i]
            chunk["fragment_index"] = i
            chunk["total_fragments"] = total
            chunk["prev_fragment_id"] = ids[i - 1] if i > 0 else None
            chunk["next_fragment_id"] = ids[i + 1] if i < total - 1 else None
            chunk["has_overlap"] = i > 0  # El overlap se aplicó al crear los chunks

        return chunks