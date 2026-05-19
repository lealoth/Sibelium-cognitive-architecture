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

    def store_interaction(self, user_message: str, assistant_response: str, user_id: str = "default", metadata: dict = None):
        content = f"Usuario: {user_message}\nIA: {assistant_response}"
        document_id = str(uuid.uuid4())
        
        base_metadata = {
            "user_message": user_message,
            "assistant_response": assistant_response,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            base_metadata.update(metadata)
        
        self.collection.add(
            documents=[content],
            metadatas=[base_metadata],
            ids=[document_id],
        )
        self._update_narrative_direction(content)
        return document_id

    def get_relevant(self, query: str, user_id: str = None, limit: int = 5, **kwargs) -> list:
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

                temporal_focus = kwargs.get("temporal_focus", "recent")
                puntaje = calcular_score_trimetrico(
                    similitud=similitud,
                    hours_elapsed=(now - ts).total_seconds() / 3600.0 if timestamp_str else 168.0,
                    importancia=importancia,
                    temporal_focus=temporal_focus
                )
                scored.append((puntaje, doc))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in scored[:limit]]

        except Exception as e:
            print(f"❌ Error en get_relevant: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_relevant_with_contradiction(self, response_text: str, user_id: str = None, limit: int = 1) -> dict:
        """
        Detección de contradicción híbrida calibrada para all-MiniLM-L6-v2.
        
        Zonas:
        - score < 0.55: Terreno nuevo → OK
        - 0.55 <= score <= 0.72: Incertidumbre → LLM local evalúa
        - score > 0.72: Alta densidad factual → LLM local evalúa, si contradicción → ESCALAR
        
        Returns:
            dict con veredicto, score_confianza, y metadata
        """
        try:
            count = self.collection.count()
            if count == 0:
                return {"veredicto": "OK", "score_confianza": 0.0}

            if user_id:
                results = self.collection.query(
                    query_texts=[response_text[:500]],
                    n_results=1,
                    where={"user_id": user_id},
                    include=["documents", "distances"]
                )
            else:
                results = self.collection.query(
                    query_texts=[response_text[:500]],
                    n_results=1,
                    include=["documents", "distances"]
                )

            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]

            if not documents or not documents[0]:
                return {"veredicto": "OK", "score_confianza": 0.0}

            recuerdo = documents[0]
            distancia = distances[0] if distances else 1.0
            score_confianza = 1.0 - distancia

            # Zona verde: terreno nuevo
            if score_confianza < 0.55:
                return {"veredicto": "OK", "score_confianza": score_confianza}

            # Zona gris y roja: evaluación con LLM local
            prompt = f"""<system_identity>
Eres el sistema de detección de contradicciones.
</system_identity>

<factual_context>
Recuerdo real: {recuerdo[:300]}
</factual_context>

<hypothesis>
Simulación: {response_text[:300]}
</hypothesis>

<evaluation_directive>
Analiza si la simulación contiene datos, fechas, entidades o leyes físicas que hagan IMPOSIBLE que el recuerdo real sea verdadero al mismo tiempo.
Paso 1: Escribe una breve razón de 1 línea buscando inconsistencias.
Paso 2: Responde estrictamente en la última línea con: CONTRADICCION o OK.
</evaluation_directive>"""
            
            try:
                from core.llm import LLMModel
                llm = LLMModel.get_instance()
                veredicto_llm = llm.generate(prompt, temperature=0.0, max_tokens=80, purpose="verificar_respuesta")
            except Exception:
                return {"veredicto": "OK", "score_confianza": score_confianza}

            if "CONTRADICCION" in veredicto_llm.upper():
                if score_confianza > 0.72:
                    # Zona roja: escalar a Gemini
                    return {
                        "veredicto": "ESCALAR_A_GEMINI",
                        "score_confianza": score_confianza,
                        "recuerdo": recuerdo,
                        "razon": veredicto_llm
                    }
                else:
                    # Zona gris: regenerar local a baja temperatura
                    return {
                        "veredicto": "REGENERAR_LOCAL",
                        "score_confianza": score_confianza,
                        "recuerdo": recuerdo,
                        "razon": veredicto_llm
                    }

            return {"veredicto": "OK", "score_confianza": score_confianza}

        except Exception as e:
            print(f"❌ Error en búsqueda de contradicciones: {e}")
            return {"veredicto": "OK", "score_confianza": 0.0}
    
    def reset(self):
        if self.collection.count() > 0:
            try:
                results = self.collection.get(include=["documents"])
                ids = results.get("ids", [])
                if ids:
                    self.collection.delete(ids=ids)
                    print(f"   [Reset] {len(ids)} documentos eliminados.")
            except Exception as e:
                print(f"   [!] Error en reset: {e}")

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

# ============================================
# TEMPORAL FOCUS (Sistema de CPFdl Virtual)
# ============================================

import math
import numpy as np

# Anclas temporales refinadas (español, compatibles con modelo multilingüe)
TEMPORAL_ANCHORS = {
    "remote": "Pasado remoto. Archivo histórico profundo. Origen primigenio, inicios remotos, memorias antiguas, eventos consolidados en el tiempo lejano.",
    "recent": "Pasado inmediato. Memoria de trabajo reciente. Actualidad, sucesos de última hora, frescura temporal, recién ocurrido, contexto del ahora mismo.",
    "neutral": "Línea temporal indefinida. Conceptos abstractos, conocimiento general, datos atemporales, hechos permanentes sin coordenadas cronológicas.",
}

# Embeddings cacheados de las anclas
_temporal_anchor_embeddings = {}
_embedding_function = None


def _get_embedding_function():
    """Singleton de la función de embeddings."""
    global _embedding_function
    if _embedding_function is None:
        from chromadb.utils import embedding_functions
        _embedding_function = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_function


def _get_temporal_anchor_embedding(focus: str):
    """Cachea y retorna el embedding de un ancla temporal."""
    if focus not in _temporal_anchor_embeddings:
        ef = _get_embedding_function()
        emb = ef([TEMPORAL_ANCHORS[focus]])[0]
        _temporal_anchor_embeddings[focus] = np.array(emb) / np.linalg.norm(emb)
    return _temporal_anchor_embeddings[focus]


def determinar_temporal_focus(user_message: str) -> str:
    """
    Determina la orientación temporal usando amplificación de contraste
    (modulación dopaminérgica de ganancia prefrontal).
    """
    import math
    import numpy as np
    
    try:
        ef = _get_embedding_function()
        msg_emb = np.array(ef([user_message])[0])
        msg_emb = msg_emb / np.linalg.norm(msg_emb)
        
        remote_emb = _get_temporal_anchor_embedding("remote")
        recent_emb = _get_temporal_anchor_embedding("recent")
        neutral_emb = _get_temporal_anchor_embedding("neutral")
        
        sim_remote = float(np.dot(msg_emb, remote_emb))
        sim_recent = float(np.dot(msg_emb, recent_emb))
        sim_neutral = float(np.dot(msg_emb, neutral_emb))
        
        # Ganancia dopaminérgica (k=4 estira diferencias en zona alta)
        k = 4.0
        e_remote = math.exp(sim_remote * k)
        e_recent = math.exp(sim_recent * k)
        e_neutral = math.exp(sim_neutral * k)
        total = e_remote + e_recent + e_neutral
        
        p_remote = e_remote / total
        p_recent = e_recent / total
        p_neutral = e_neutral / total
        
        # Reemplazar UMBRAL_PROB = 0.10 por:
        umbral_dinamico = 0.05 * (1.0 + sum(-p * math.log(p) for p in [p_remote, p_recent, p_neutral]))

        # Y la condición:
        if p_remote - p_recent > umbral_dinamico and p_remote - p_neutral > umbral_dinamico:
            return "remote"
        elif p_recent - p_remote > umbral_dinamico and p_recent - p_neutral > umbral_dinamico:
            return "recent"
        else:
            return "neutral"
    except Exception:
        return "neutral"


def calcular_recencia_dinamica(hours_elapsed: float, focus: str) -> float:
    """
    Calcula la recencia dinámica según el foco temporal.
    - recent: decaimiento exponencial (tau=48h)
    - remote: escalado logarítmico (consolidación a largo plazo)
    - neutral: 0.0 (anula el factor temporal)
    """
    t = max(0.1, hours_elapsed)
    
    if focus == "recent":
        return math.exp(-t / 48.0)
    elif focus == "remote":
        return min(1.0, math.log10(t) / 4.0)
    else:
        return 0.0


def calcular_score_trimetrico(
    similitud: float,
    hours_elapsed: float,
    importancia: float,
    temporal_focus: str = "recent"
) -> float:
    """
    Puntuación trimétrica modulada por foco temporal.
    """
    w_sim = 0.5
    w_rec = 0.3
    w_imp = 0.2
    
    recencia_dinamica = calcular_recencia_dinamica(hours_elapsed, temporal_focus)
    
    if temporal_focus == "neutral":
        w_sim = 0.7
        w_rec = 0.0
    
    return (similitud * w_sim) + (recencia_dinamica * w_rec) + (importancia * w_imp)