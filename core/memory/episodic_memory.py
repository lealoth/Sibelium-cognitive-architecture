"""Memoria episódica con ChromaDB y Vector de Dirección Narrativa."""
import uuid
import math
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
        
        # 1. Memoria Episódica (Hipocampo) - Historial, interacciones, aprendizajes
        self.collection = self.client.get_or_create_collection(name="episodic_memory")
        
        # 2. Memoria Procedural (Ganglios Basales) - Código, APIs, comandos
        self.procedural_collection = self.client.get_or_create_collection(name="procedural_index")
        
        # 3. Memoria Semántica (Córtex Temporal) - Papers, teoría, documentación
        self.semantic_collection = self.client.get_or_create_collection(name="semantic_library")
        
        self._narrative_direction: Optional[np.ndarray] = None

    # ============================================
    # CRUD - MEMORIA EPISÓDICA
    # ============================================

    def store_interaction(self, user_message: str, assistant_response: str, user_id: str = "default", metadata: dict = None):
        from core.memory.chunking import SemanticChunker
        
        content = f"Usuario: {user_message}\nIA: {assistant_response}"
        
        # Si la interacción es corta, guardar completa
        if len(content) <= 2000:
            document_id = str(uuid.uuid4())
            base_metadata = {
                "source": "user_interaction",
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
        
        # Si es larga, fragmentar semánticamente
        chunker = SemanticChunker(target_chars=1500, overlap_chars=200)
        chunks = chunker.chunk_semantic(content, content_type="text")
        
        parent_id = str(uuid.uuid4())[:8]
        for chunk in chunks:
            base_metadata = {
                "source": "user_interaction",
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "fragment_id": chunk["fragment_id"],
                "fragment_index": chunk["fragment_index"],
                "total_fragments": chunk["total_fragments"],
                "prev_fragment_id": chunk.get("prev_fragment_id", ""),
                "next_fragment_id": chunk.get("next_fragment_id", ""),
                "parent_interaction": parent_id,
                "section": chunk.get("section", ""),
            }
            if metadata:
                base_metadata.update(metadata)
            self.collection.add(
                documents=[chunk["text"]],
                metadatas=[base_metadata],
                ids=[f"{parent_id}_{chunk['fragment_id']}"],
            )
        
        self._update_narrative_direction(content)
        return parent_id

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
                    n_results=min(limit * 3, count),
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

            scored = []
            now = datetime.now()

            for i, doc in enumerate(documents):
                similitud = 1.0 - distances[i] if i < len(distances) else 0.5

                recencia = 0.5
                meta = metadatas[i] if i < len(metadatas) else {}
                timestamp_str = meta.get("timestamp", "")
                hours_elapsed = 168.0
                if timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str)
                        hours_elapsed = (now - ts).total_seconds() / 3600.0
                        recencia = max(0.0, 1.0 - hours_elapsed / 168.0)
                    except Exception:
                        pass

                importancia = meta.get("importance", 0.5)
                temporal_focus = kwargs.get("temporal_focus", "recent")
                # Factor de decaimiento por último acceso
                last_accessed_str = meta.get("last_accessed", "")
                decay_factor = 1.0
                if last_accessed_str:
                    try:
                        last_accessed = datetime.fromisoformat(last_accessed_str)
                        days_since = (now - last_accessed).days
                        decay_factor = math.exp(-0.1 * max(0, days_since))
                    except Exception:
                        pass
                puntaje = calcular_score_trimetrico(
                    similitud=similitud,
                    hours_elapsed=hours_elapsed,
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

            if score_confianza < 0.55:
                return {"veredicto": "OK", "score_confianza": score_confianza}

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
                    return {
                        "veredicto": "ESCALAR_A_GEMINI",
                        "score_confianza": score_confianza,
                        "recuerdo": recuerdo,
                        "razon": veredicto_llm
                    }
                else:
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

    def active_forgetting(self, user_id: str = None):
        try:
            count = self.collection.count()
            if count == 0:
                return

            results = self.collection.get(include=["metadatas"])
            metadatas = results.get("metadatas", [])
            ids = results.get("ids", [])

            ids_to_delete = []
            for i, meta in enumerate(metadatas):
                if meta is None:
                    continue
                if meta.get("type") == "leccion_de_ingenieria":
                    continue
                    
                synaptic_strength = meta.get("synaptic_strength", 1.0)
                importance = meta.get("importance", 0.5)
                
                # Escudo absoluto
                if importance >= 0.8:
                    continue
                
                # Umbral dinámico
                threshold = 0.05 * (1.5 - importance)
                if synaptic_strength < threshold:
                    ids_to_delete.append(ids[i])

            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                print(f"   [Olvido] ChromaDB: {len(ids_to_delete)} vectores eliminados.")
        except Exception as e:
            print(f"   [!] Error en olvido activo ChromaDB: {e}")

    # ============================================
    # VECTOR DE DIRECCIÓN NARRATIVA
    # ============================================

    def _update_narrative_direction(self, content: str):
        emb = self._get_embedding(content)
        if emb is None:
            return

        emb_arr = np.array(emb)
        emb_arr = emb_arr / np.linalg.norm(emb_arr)

        alpha = min(0.25, max(0.15, len(content) / 2000.0))

        if self._narrative_direction is None:
            self._narrative_direction = emb_arr
        else:
            self._narrative_direction = (
                (1.0 - alpha) * self._narrative_direction + alpha * emb_arr
            )
            self._narrative_direction = self._narrative_direction / np.linalg.norm(self._narrative_direction)

    def _blend_query(self, query: str) -> str:
        if self._narrative_direction is None:
            return query
        try:
            query_emb = self._get_embedding(query)
            if query_emb is None:
                return query
            blended = np.array(query_emb) * 0.7 + self._narrative_direction * 0.3
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

    # ============================================
    # MEMORIA SEMÁNTICA (Papers, teoría)
    # ============================================

    def store_semantic(self, content: str, metadata: dict = None):
        document_id = str(uuid.uuid4())
        base_metadata = {
            "timestamp": datetime.now().isoformat(),
            "source": "nexus_world",
            "type": "empirical_fact",
            "confidence_score": 1.0,
            "importance": 0.7,
        }
        if metadata:
            base_metadata.update(metadata)
        self.semantic_collection.add(
            documents=[content],
            metadatas=[base_metadata],
            ids=[document_id],
        )
        return document_id

    def query_semantic(self, query: str, n_results: int = 5) -> list:
        try:
            results = self.semantic_collection.query(query_texts=[query], n_results=n_results)
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            return [{"content": d, "metadata": m} for d, m in zip(docs, metas)]
        except Exception:
            return []

    # ============================================
    # MEMORIA PROCEDURAL (Código, APIs, comandos)
    # ============================================

    def index_procedural(self, code_reader):
        code_reader.index_codebase()
        try:
            existing = self.procedural_collection.get(include=[])
            if existing.get("ids"):
                self.procedural_collection.delete(ids=existing["ids"])
        except Exception:
            pass
        
        indexed = 0
        for file_path, file_data in code_reader.index.items():
            content = file_data["content"]
            imports = file_data.get("imports", [])
            fragments = self._split_code_into_fragments(content)
            for frag in fragments:
                self.procedural_collection.add(
                    documents=[frag["code"]],
                    metadatas=[{
                        "file": file_path,
                        "class": frag.get("class", ""),
                        "function": frag.get("function", ""),
                        "line_start": frag["line_start"],
                        "line_end": frag["line_end"],
                        "dependencies": ", ".join(imports),
                        "type": "procedural_fragment",
                        "importance": 0.6,
                        "timestamp": datetime.now().isoformat(),
                    }],
                    ids=[f"{file_path}:{frag['line_start']}-{frag['line_end']}"],
                )
                indexed += 1
        print(f"   [ProceduralIndex] {indexed} fragmentos indexados.")
        return indexed

    def query_procedural(self, query: str, file_filter: str = None, function_filter: str = None, n_results: int = 5) -> list:
        where = {}
        if file_filter:
            where["file"] = file_filter
        if function_filter:
            where["function"] = function_filter
        try:
            if where:
                results = self.procedural_collection.query(
                    query_texts=[query], n_results=n_results, where=where
                )
            else:
                results = self.procedural_collection.query(
                    query_texts=[query], n_results=n_results
                )
            fragments = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            for doc, meta in zip(docs, metas):
                fragments.append({
                    "code": doc,
                    "file": meta.get("file", ""),
                    "class": meta.get("class", ""),
                    "function": meta.get("function", ""),
                    "line_range": f"{meta.get('line_start', '?')}-{meta.get('line_end', '?')}",
                })
            return fragments
        except Exception as e:
            print(f"   [!] Error en query_procedural: {e}")
            return []

    def _split_code_into_fragments(self, content: str) -> list:
        lines = content.split('\n')
        fragments = []
        current, current_start, current_class, current_function = [], 1, "", ""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('class '):
                if current and len('\n'.join(current)) > 500:
                    fragments.append({"code": '\n'.join(current), "line_start": current_start, "line_end": i-1, "class": current_class, "function": current_function})
                    current = []
                current_class = stripped.split('class ')[1].split('(')[0].split(':')[0].strip()
                current_function, current_start = "", i
                current.append(line)
            elif stripped.startswith('def '):
                if current and len('\n'.join(current)) > 500:
                    fragments.append({"code": '\n'.join(current), "line_start": current_start, "line_end": i-1, "class": current_class, "function": current_function})
                    current, current_start = [line], i
                else:
                    current.append(line)
                current_function = stripped.split('def ')[1].split('(')[0].strip()
            else:
                current.append(line)
                if len('\n'.join(current)) > 4000:
                    fragments.append({"code": '\n'.join(current), "line_start": current_start, "line_end": i, "class": current_class, "function": current_function})
                    current, current_start = [], i+1
        if current:
            fragments.append({"code": '\n'.join(current), "line_start": current_start, "line_end": len(lines), "class": current_class, "function": current_function})
        return fragments


# ============================================
# TEMPORAL FOCUS (Sistema de CPFdl Virtual)
# ============================================

TEMPORAL_ANCHORS = {
    "remote": "Pasado remoto. Archivo histórico profundo. Origen primigenio, inicios remotos, memorias antiguas, eventos consolidados en el tiempo lejano.",
    "recent": "Pasado inmediato. Memoria de trabajo reciente. Actualidad, sucesos de última hora, frescura temporal, recién ocurrido, contexto del ahora mismo.",
    "neutral": "Línea temporal indefinida. Conceptos abstractos, conocimiento general, datos atemporales, hechos permanentes sin coordenadas cronológicas.",
}

_temporal_anchor_embeddings = {}
_embedding_function = None


def _get_embedding_function():
    global _embedding_function
    if _embedding_function is None:
        from chromadb.utils import embedding_functions
        _embedding_function = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_function


def _get_temporal_anchor_embedding(focus: str):
    if focus not in _temporal_anchor_embeddings:
        ef = _get_embedding_function()
        emb = ef([TEMPORAL_ANCHORS[focus]])[0]
        _temporal_anchor_embeddings[focus] = np.array(emb) / np.linalg.norm(emb)
    return _temporal_anchor_embeddings[focus]


def determinar_temporal_focus(user_message: str) -> str:
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
        
        k = 4.0
        e_remote = math.exp(sim_remote * k)
        e_recent = math.exp(sim_recent * k)
        e_neutral = math.exp(sim_neutral * k)
        total = e_remote + e_recent + e_neutral
        
        p_remote = e_remote / total
        p_recent = e_recent / total
        p_neutral = e_neutral / total
        
        umbral_dinamico = 0.05 * (1.0 + sum(-p * math.log(p) for p in [p_remote, p_recent, p_neutral]))

        if p_remote - p_recent > umbral_dinamico and p_remote - p_neutral > umbral_dinamico:
            return "remote"
        elif p_recent - p_remote > umbral_dinamico and p_recent - p_neutral > umbral_dinamico:
            return "recent"
        else:
            return "neutral"
    except Exception:
        return "neutral"


def calcular_recencia_dinamica(hours_elapsed: float, focus: str) -> float:
    t = max(0.1, hours_elapsed)
    if focus == "recent":
        return math.exp(-t / 48.0)
    elif focus == "remote":
        return min(1.0, math.log10(t) / 4.0)
    else:
        return 0.0


def calcular_score_trimetrico(similitud: float, hours_elapsed: float, importancia: float, temporal_focus: str = "recent") -> float:
    w_sim = 0.5
    w_rec = 0.3
    w_imp = 0.2
    
    recencia_dinamica = calcular_recencia_dinamica(hours_elapsed, temporal_focus)
    
    if temporal_focus == "neutral":
        w_sim = 0.7
        w_rec = 0.0
    
    return (similitud * w_sim) + (recencia_dinamica * w_rec) + (importancia * w_imp)


# ============================================
# INTEGRACIÓN CON EPISODICMEMORY (Monkey Patch)
# ============================================

def patch_episodic_memory_get_relevant(episodic_memory_instance):
    original_get_relevant = episodic_memory_instance.get_relevant

    def extended_get_relevant(query, user_id=None, limit=5, include_ids=False, **kwargs):
        from datetime import datetime
        
        count = episodic_memory_instance.collection.count()
        if count == 0:
            return []

        search_query = episodic_memory_instance._blend_query(query)

        try:
            if user_id:
                results = episodic_memory_instance.collection.query(
                    query_texts=[search_query],
                    n_results=min(limit * 3, count),
                    where={"user_id": user_id},
                )
            else:
                results = episodic_memory_instance.collection.query(
                    query_texts=[search_query],
                    n_results=min(limit * 3, count),
                )

            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            ids = results.get("ids", [[]])[0]

            if not documents:
                return []

            scored = []
            now = datetime.now()

            for i, doc in enumerate(documents):
                similitud = 1.0 - distances[i] if i < len(distances) else 0.5
                meta = metadatas[i] if i < len(metadatas) else {}
                timestamp_str = meta.get("timestamp", "")
                hours_elapsed = 168.0
                if timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str)
                        hours_elapsed = (now - ts).total_seconds() / 3600.0
                    except Exception:
                        pass
                importancia = meta.get("importance", 0.5)
                temporal_focus = kwargs.get("temporal_focus", "recent")
                puntaje = calcular_score_trimetrico(similitud=similitud, hours_elapsed=hours_elapsed, importancia=importancia, temporal_focus=temporal_focus)
                doc_id = ids[i] if i < len(ids) else ""
                scored.append((puntaje, doc, doc_id, similitud, distances[i]))

            scored.sort(key=lambda x: x[0], reverse=True)

            if include_ids:
                return [(doc, doc_id, score, distance) for score, doc, doc_id, _, distance in scored[:limit]]
            else:
                return [doc for _, doc, _, _, _ in scored[:limit]]

        except Exception as e:
            print(f"❌ Error en get_relevant: {e}")
            import traceback
            traceback.print_exc()
            return []

    episodic_memory_instance.get_relevant = extended_get_relevant
    return episodic_memory_instance