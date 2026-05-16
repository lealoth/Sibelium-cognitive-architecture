"""Procesos cognitivos algorítmicos que no requieren LLM (Sistema 1)."""
from collections import Counter
from typing import List, Optional

import numpy as np


class FastCognitiveProcessors:
    """Sistema 1: rápido, algorítmico, sin LLM."""

    # Cache de embeddings compartido
    _embedding_cache = {}
    _max_cache_size = 100

    # ============================================
    # EMBEDDINGS
    # ============================================

    @classmethod
    def _get_cached_embedding(cls, text: str) -> Optional[list]:
        key = text[:100]
        if key in cls._embedding_cache:
            return cls._embedding_cache[key]
        try:
            from chromadb.utils import embedding_functions
            emb = embedding_functions.DefaultEmbeddingFunction()([text])[0]
            if len(cls._embedding_cache) >= cls._max_cache_size:
                cls._embedding_cache.pop(next(iter(cls._embedding_cache)))
            cls._embedding_cache[key] = emb
            return emb
        except Exception:
            return None

    @staticmethod
    def cosine_similarity(emb1: list, emb2: list) -> float:
        emb1_arr = np.array(emb1)
        emb2_arr = np.array(emb2)
        return float(np.dot(emb1_arr, emb2_arr) / (max(np.linalg.norm(emb1_arr), 1e-8) * max(np.linalg.norm(emb2_arr), 1e-8)))

    # ============================================
    # INHIBICIÓN LATERAL
    # ============================================

    @staticmethod
    def lateral_inhibition(thoughts: list, strength: float = 0.3) -> list:
        """Inhibición Lateral: reduce prioridad de pensamientos semánticamente similares (0.3-0.5)."""
        if len(thoughts) < 2:
            return thoughts

        embeddings = []
        for t in thoughts:
            emb = getattr(t, '_embedding', None) or FastCognitiveProcessors._get_cached_embedding(t.content)
            if emb is not None:
                t._embedding = emb
            embeddings.append(emb)

        inhibited = set()
        for i in range(len(thoughts)):
            if i in inhibited or embeddings[i] is None:
                continue
            for j in range(i + 1, len(thoughts)):
                if j in inhibited or embeddings[j] is None:
                    continue
                sim = FastCognitiveProcessors.cosine_similarity(embeddings[i], embeddings[j])
                if 0.3 < sim < 0.5:
                    if thoughts[i].priority >= thoughts[j].priority:
                        thoughts[j].priority *= (1.0 - strength)
                        inhibited.add(j)
                    else:
                        thoughts[i].priority *= (1.0 - strength)
                        inhibited.add(i)
        return thoughts

    # ============================================
    # DECAY Y CONEXIONES
    # ============================================

    @staticmethod
    def decay_priority(thought, minutes_elapsed: float) -> float:
        thought.priority *= (0.97 ** minutes_elapsed)
        thought.priority = max(0.0, thought.priority)
        return thought.priority

    @staticmethod
    def find_connections(thoughts: List, threshold: float = 0.25) -> list:
        """Encuentra pensamientos relacionados por similitud de embeddings cacheados."""
        if len(thoughts) < 2:
            return []

        embeddings = []
        for t in thoughts:
            emb = getattr(t, '_embedding', None) or FastCognitiveProcessors._get_cached_embedding(t.content)
            if emb is not None:
                t._embedding = emb
            embeddings.append(emb)

        connections = []
        for i in range(len(thoughts)):
            if embeddings[i] is None:
                continue
            for j in range(i + 1, len(thoughts)):
                if embeddings[j] is None:
                    continue
                sim = FastCognitiveProcessors.cosine_similarity(embeddings[i], embeddings[j])
                if sim > threshold:
                    connections.append((thoughts[i], thoughts[j], sim))

        return sorted(connections, key=lambda c: c[2], reverse=True)

    # ============================================
    # SIMILITUD LÉXICA
    # ============================================

    @staticmethod
    def is_related(text1: str, text2: str, threshold: int = 3) -> bool:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        return len(words1 & words2) >= threshold

    # ============================================
    # PALABRAS CLAVE
    # ============================================

    @staticmethod
    def extract_keywords(text: str, max_keywords: int = 5, use_llm: bool = False) -> List[str]:
        if use_llm:
            return FastCognitiveProcessors._extract_keywords_llm(text, max_keywords)
        return FastCognitiveProcessors._extract_keywords_fast(text, max_keywords)

    @staticmethod
    def _extract_keywords_fast(text: str, max_keywords: int = 5) -> List[str]:
        words = [w.strip('.,;:!?¿¡()[]{}""\'\'—…-') for w in text.lower().split()]
        words = [w for w in words if len(w) > 2]
        return [w for w, _ in Counter(words).most_common(max_keywords)]

    @staticmethod
    def _extract_keywords_llm(text: str, max_keywords: int = 5) -> List[str]:
        from core.llm import LLMModel
        prompt = f"""Extrae de 3 a {max_keywords} conceptos clave de este texto.
Devuelve SOLO los conceptos separados por comas, sin explicaciones.

Texto: "{text[:300]}"

Conceptos:"""
        try:
            result = LLMModel.get_instance().generate(prompt, temperature=0.2, max_tokens=50, purpose="extraer_keywords")
            return [kw.strip().lower() for kw in result.split(",") if kw.strip()][:max_keywords]
        except Exception:
            return FastCognitiveProcessors._extract_keywords_fast(text, max_keywords)

    # ============================================
    # UTILIDADES
    # ============================================

    @staticmethod
    def check_certainty_algorithmic(selected_info: str) -> str:
        if not selected_info or len(selected_info) < 20:
            return "BAJA"
        if len(selected_info) > 500:
            return "ALTA"
        if len(selected_info) > 150:
            return "MEDIA"
        return "BAJA"

    @staticmethod
    def should_use_llm_for_certainty(selected_info: str) -> bool:
        return 20 <= len(selected_info) <= 500 if selected_info else False