"""Sistema de Olvido Activo - Poda sináptica independiente."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


class ActiveForgetting:
    """
    Subsistema de Olvido Activo.
    Homólogo: neurogénesis hipocampal + poda sináptica durante el sueño REM.
    Elimina recuerdos con fuerza sináptica < umbral y protege recuerdos emocionales.
    """

    def __init__(self, chroma_collection, thoughts_list: list, storage_path: Path):
        self.collection = chroma_collection
        self.thoughts = thoughts_list
        self.storage = storage_path / "memory" / "forgetting_log.json"
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.stats = self._load_stats()

    def _load_stats(self) -> dict:
        if self.storage.exists():
            try:
                return json.loads(self.storage.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"total_forgotten": 0, "last_run": None, "history": []}

    def _save_stats(self):
        self.storage.write_text(json.dumps(self.stats, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_cycle(self, user_id: str = None):
        """
        Ejecuta un ciclo de olvido activo:
        1. Olvido de pensamientos (RAM)
        2. Olvido de vectores (ChromaDB)
        3. Protección de recuerdos emocionales
        """
        forgotten_thoughts = self._forget_thoughts()
        forgotten_vectors = self._forget_vectors(user_id)
        total = forgotten_thoughts + forgotten_vectors

        if total > 0:
            self.stats["total_forgotten"] += total
            self.stats["last_run"] = datetime.now().isoformat()
            self.stats["history"].append({
                "timestamp": datetime.now().isoformat(),
                "thoughts_forgotten": forgotten_thoughts,
                "vectors_forgotten": forgotten_vectors,
            })
            if len(self.stats["history"]) > 50:
                self.stats["history"] = self.stats["history"][-50:]
            self._save_stats()
            print(f"   [Olvido] {forgotten_thoughts} pensamientos + {forgotten_vectors} vectores eliminados.")

    def _forget_thoughts(self, threshold: float = 0.05) -> int:
        """Elimina pensamientos con fuerza sináptica < umbral.
        Protege pensamientos con carga emocional (tipo 'salience_alert', 'reaction')."""
        before = len(self.thoughts)
        protected_types = {"salience_alert", "reaction", "user_interaction", "learning"}

        self.thoughts[:] = [
            t for t in self.thoughts
            if getattr(t, '_synaptic_strength', 1.0) >= threshold
            or t.type in protected_types
        ]
        return before - len(self.thoughts)

    def _forget_vectors(self, user_id: str = None, threshold: float = 0.05) -> int:
        """Elimina vectores de ChromaDB con fuerza sináptica < umbral."""
        try:
            count = self.collection.count()
            if count == 0:
                return 0

            results = self.collection.get(include=["metadatas"])
            metadatas = results.get("metadatas", [])
            ids = results.get("ids", [])

            ids_to_delete = []
            for i, meta in enumerate(metadatas):
                if meta is None:
                    continue
                # Proteger recuerdos emocionales
                if meta.get("emotional_charge", 0) > 0.7:
                    continue
                # Proteger lecciones de ingeniería recientes (< 7 días)
                if meta.get("type") == "leccion_de_ingenieria":
                    continue
                # Eliminar si fuerza sináptica < umbral
                if meta.get("synaptic_strength", 1.0) < threshold:
                    ids_to_delete.append(ids[i])

            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                return len(ids_to_delete)
        except Exception as e:
            print(f"   [!] Error en olvido de vectores: {e}")
        return 0

    def get_stats(self) -> dict:
        """Devuelve estadísticas de olvido."""
        return self.stats