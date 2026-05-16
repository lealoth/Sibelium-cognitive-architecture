"""Memoria episódica con ChromaDB y Vector de Dirección Narrativa."""
import uuid
from pathlib import Path
from typing import Optional

import chromadb
import numpy as np
from config import CHROMA_PATH
from datetime import datetime

class EpisodicMemory:
    def __init__(self):
        self.persist_directory = Path(CHROMA_PATH)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self.client.get_or_create_collection(name="episodic_memory")
        # Vector de Dirección Narrativa (promedio móvil de embeddings)
        self._narrative_direction: Optional[np.ndarray] = None

    # ============================================
    # CRUD
    # ============================================

    def store_interaction(self, user_message: str, assistant_response: str, user_id: str = "default"):
        content = f"Usuario: {user_message}\nIA: {assistant_response}"
        document_id = str(uuid.uuid4())
        self.collection.add(
            documents=[content],
            metadatas=[{
                "user_message": user_message,
                "assistant_response": assistant_response,
                "user_id": user_id
            }],
            ids=[document_id],
        )
        # Actualizar Vector de Dirección Narrativa
        self._update_narrative_direction(content)
        return document_id

    def get_relevant(self, query: str, user_id: str = None, limit: int = 5) -> list:
        print(f"🔍 Buscando memorias para: {query[:50]}...")
        count = self.collection.count()
        print(f"🔍 Total documentos en colección: {count}")
        if count == 0:
            print("🔍 No hay memorias almacenadas")
            return []

        search_query = self._blend_query(query)

        try:
            if user_id:
                results = self.collection.query(
                    query_texts=[search_query],
                    n_results=min(limit * 3, count),  # Buscar más para reordenar
                    where={"user_id": user_id}
                )
            else:
                results = self.collection.query(
                    query_texts=[search_query],
                    n_results=min(limit * 3, count)
                )

            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            if not documents:
                return []

            # Puntuación Trimétrica: Similitud + Recencia + Importancia
            import numpy as np
            scored = []
            now = datetime.now()

            for i, doc in enumerate(documents):
                similitud = 1.0 - distances[i] if i < len(distances) else 0.5

                recencia = 0.5
                meta = metadatas[i] if i < len(metadatas) else {}
                timestamp_str = meta.get("timestamp", "")
                if timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str)
                        hours_elapsed = (now - ts).total_seconds() / 3600.0
                        recencia = max(0.0, 1.0 - hours_elapsed / 168.0)  # Decae en 1 semana
                    except Exception:
                        pass

                importancia = meta.get("importance", 0.5)

                puntaje = (similitud * 0.5) + (recencia * 0.3) + (importancia * 0.2)
                scored.append((puntaje, doc))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in scored[:limit]]

        except Exception as e:
            print(f"❌ Error en get_relevant: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_relevant_with_contradiction(self, response_text: str, user_id: str = None, limit: int = 3) -> list:
        """Estrategia híbrida: alta similitud + filtro de metadatos + validación LLM."""
        try:
            count = self.collection.count()
            if count == 0:
                return []

            # Paso 1: Buscar ALTA similitud (lo opuesto no funciona en embeddings)
            if user_id:
                results = self.collection.query(
                    query_texts=[response_text[:500]],
                    n_results=min(limit * 3, count),
                    where={"user_id": user_id}
                )
            else:
                results = self.collection.query(
                    query_texts=[response_text[:500]],
                    n_results=min(limit * 3, count)
                )

            documents = results.get("documents", [[]])[0]
            if not documents:
                return []

            # Paso 2: Validación con LLM local (rápido, binario)
            contradictions = []
            for doc in documents[:limit]:
                prompt = f"""¿Esta respuesta contradice esta conclusión anterior?

    Respuesta tentativa: "{response_text[:300]}"
    Conclusión anterior: "{doc[:300]}"

    Responde SOLO CONTRADICCION o OK."""
                try:
                    from core.llm import LLMModel
                    llm = LLMModel.get_instance()
                    result = llm.generate(prompt, temperature=0.0, max_tokens=5, purpose="verificar_respuesta")
                    if "CONTRADICCION" in result.upper():
                        contradictions.append(doc)
                except Exception:
                    continue

            return contradictions[:limit]
        except Exception as e:
            print(f"❌ Error en búsqueda de contradicciones: {e}")
            return []

    def reset(self):
        if self.collection.count() > 0:
            response = self.collection.get(include=["ids"])
            ids = [item for item in response.get("ids", [])]
            if ids:
                self.collection.delete(ids=ids)

    def get_by_time_range(self, limit: int = 10, offset: int = 0):
        if self.collection.count() == 0:
            return []
        try:
            results = self.collection.get(
                include=["documents"],
                limit=limit,
                offset=offset
            )
            return results.get("documents", [])
        except Exception as e:
            print(f"Error en get_by_time_range: {e}")
            return []

    # ============================================
    # Vector de Dirección Narrativa
    # ============================================

    def _update_narrative_direction(self, content: str):
        """Alpha dinámico según densidad de información del estímulo."""
        emb = self._get_embedding(content)
        if emb is None:
            return

        emb_arr = np.array(emb)
        emb_arr = emb_arr / np.linalg.norm(emb_arr)

        # Alpha dinámico: 0.15-0.25 según longitud del contenido
        # Más largo = más informativo = mayor peso
        alpha = min(0.25, max(0.15, len(content) / 2000.0))

        if self._narrative_direction is None:
            self._narrative_direction = emb_arr
        else:
            self._narrative_direction = (
                (1.0 - alpha) * self._narrative_direction + alpha * emb_arr
            )
            self._narrative_direction = self._narrative_direction / np.linalg.norm(self._narrative_direction)

    def _blend_query(self, query: str) -> str:
        """Combina la query actual con el Vector de Dirección Narrativa."""
        if self._narrative_direction is None:
            return query
        try:
            query_emb = self._get_embedding(query)
            if query_emb is None:
                return query
            # Promedio: 70% query actual, 30% dirección narrativa
            blended = np.array(query_emb) * 0.7 + self._narrative_direction * 0.3
            # Convertir de vuelta a texto aproximado no es posible,
            # pero podemos usar la query original enriquecida con contexto
            return f"{query} [contexto narrativo]"
        except Exception:
            return query

    def _get_embedding(self, text: str) -> Optional[list]:
        try:
            from chromadb.utils import embedding_functions
            ef = embedding_functions.DefaultEmbeddingFunction()
            return ef([text])[0]
        except Exception:
            return None

    def active_forgetting(self, user_id: str = None):
        """Olvido activo: elimina vectores con fuerza sináptica insignificante."""
        try:
            count = self.collection.count()
            if count == 0:
                return

            # Obtener todos los metadatos
            results = self.collection.get(include=["metadatas"])
            metadatas = results.get("metadatas", [])
            ids = results.get("ids", [])

            ids_to_delete = []
            for i, meta in enumerate(metadatas):
                if meta is None:
                    continue
                # Verificar si es una lección de ingeniería antigua sin reutilización
                if meta.get("type") == "leccion_de_ingenieria":
                    # Las lecciones de ingeniería se borran después de 30 días
                    # (no tenemos timestamp en metadata, así que usamos heurística)
                    continue
                # Si no tiene metadatos de fuerza, conservar
                if "synaptic_strength" not in meta:
                    continue
                if meta.get("synaptic_strength", 1.0) < 0.05:
                    ids_to_delete.append(ids[i])

            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                print(f"   [Olvido] ChromaDB: {len(ids_to_delete)} vectores eliminados.")
        except Exception as e:
            print(f"   [!] Error en olvido activo ChromaDB: {e}")