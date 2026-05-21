"""
Indexador Universal — Fragmenta y almacena cualquier contenido en las colecciones correspondientes.
Usado por: SelfEngineer, ExploreFolder, FileAnalyzer.
"""
from pathlib import Path
from typing import Optional
from core.memory.chunking import SemanticChunker


class UniversalIndexer:
    """Indexa contenido en procedural_index o semantic_library según tipo."""

    def __init__(self, episodic_memory):
        self.em = episodic_memory
        self.chunker = SemanticChunker(target_chars=1500, overlap_chars=200)

    def index_file(self, file_path: str, content: str, file_type: str = "auto") -> int:
        """
        Indexa un archivo en la colección adecuada.
        
        - Código (Python, JS, etc.) → procedural_index
        - Documentación (Markdown, texto) → semantic_library
        
        Returns: número de fragmentos indexados.
        """
        if file_type == "auto":
            ext = Path(file_path).suffix.lower()
            if ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.css', '.html']:
                file_type = "code"
            else:
                file_type = "text"

        if file_type == "code":
            return self._index_code(file_path, content)
        else:
            return self._index_document(file_path, content)

    def _index_code(self, file_path: str, content: str) -> int:
        """Indexa código en procedural_index."""
        # Borrar fragmentos existentes de este archivo antes de re-indexar
        try:
            existing = self.em.procedural_collection.get(
                where={"file": file_path},
                include=["ids"]
            )
            if existing.get("ids"):
                self.em.procedural_collection.delete(ids=existing["ids"])
        except Exception:
            pass

        chunks = self.chunker.chunk_semantic(content, content_type="code")
        base_id = Path(file_path).stem
        
        count = 0
        for chunk in chunks:
            clean_meta = self._sanitize_metadata({
                "file": file_path,
                "section": chunk.get("section", ""),
                "fragment_id": chunk.get("fragment_id", ""),
                "fragment_index": chunk.get("fragment_index", 0),
                "total_fragments": chunk.get("total_fragments", 0),
                "prev_fragment_id": chunk.get("prev_fragment_id", ""),
                "next_fragment_id": chunk.get("next_fragment_id", ""),
                "type": "code_fragment",
                "importance": 0.6,
            })
            self.em.procedural_collection.add(
                documents=[chunk["text"]],
                metadatas=[clean_meta],
                ids=[f"{base_id}_{chunk.get('fragment_id', count)}"],
            )
            count += 1
        
        return count

    def _index_document(self, file_path: str, content: str) -> int:
        """Indexa documento en semantic_library."""
        # Borrar fragmentos existentes de este archivo antes de re-indexar
        try:
            existing = self.em.semantic_collection.get(
                where={"filename": file_path},
                include=["ids"]
            )
            if existing.get("ids"):
                self.em.semantic_collection.delete(ids=existing["ids"])
        except Exception:
            pass

        chunks = self.chunker.chunk_semantic(content, content_type="markdown")
        base_id = Path(file_path).stem
        
        count = 0
        for chunk in chunks:
            clean_meta = self._sanitize_metadata({
                "source": "nexus_world",
                "filename": file_path,
                "section": chunk.get("section", ""),
                "fragment_id": chunk.get("fragment_id", ""),
                "fragment_index": chunk.get("fragment_index", 0),
                "total_fragments": chunk.get("total_fragments", 0),
                "prev_fragment_id": chunk.get("prev_fragment_id", ""),
                "next_fragment_id": chunk.get("next_fragment_id", ""),
                "type": "empirical_fact",
                "confidence_score": 1.0,
                "importance": 0.7,
            })
            self.em.semantic_collection.add(
                documents=[chunk["text"]],
                metadatas=[clean_meta],
                ids=[f"{base_id}_{chunk.get('fragment_id', count)}"],
            )
            count += 1
        
        return count

    def _sanitize_metadata(self, meta: dict) -> dict:
        """Asegura que todos los valores sean strings, números o booleanos para ChromaDB."""
        clean = {}
        for key, value in meta.items():
            if value is None:
                clean[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                clean[key] = value
            else:
                clean[key] = str(value)
        return clean

    def index_all_in_folder(self, folder_path: str, file_type: str = "auto") -> dict:
        """Indexa todos los archivos de una carpeta."""
        folder = Path(folder_path)
        results = {"indexed": 0, "errors": 0, "files": []}
        
        for file in folder.rglob("*"):
            if file.is_file() and file.suffix in ['.py', '.md', '.txt', '.js', '.html', '.css', '.json']:
                try:
                    content = file.read_text(encoding='utf-8')
                    fragments = self.index_file(str(file), content, file_type)
                    results["indexed"] += fragments
                    results["files"].append(str(file))
                except Exception as e:
                    print(f"   [!] Error indexando {file}: {e}")
                    results["errors"] += 1
        
        return results