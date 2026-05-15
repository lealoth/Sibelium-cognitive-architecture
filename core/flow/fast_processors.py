"""Procesos cognitivos algorítmicos que no requieren LLM."""
from typing import List


class FastCognitiveProcessors:
    """Sistema 1 de la Entidad: rápido, algorítmico, sin LLM."""
    
    @staticmethod
    def decay_priority(thought, minutes_elapsed: float) -> float:
        """Decaimiento exponencial. Matemática pura."""
        thought.priority *= (0.97 ** minutes_elapsed)
        thought.priority = max(0.0, thought.priority)
        return thought.priority
    
    @staticmethod
    def find_connections(thoughts: List, threshold: float = 0.25):
        """Encuentra pensamientos relacionados por similitud TF-IDF."""
        if len(thoughts) < 2:
            return []
        
        contents = [getattr(t, 'content', str(t)) for t in thoughts]
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf = vectorizer.fit_transform(contents)
            similarities = cosine_similarity(tfidf)
            
            connections = []
            for i in range(len(thoughts)):
                for j in range(i + 1, len(thoughts)):
                    if similarities[i][j] > threshold:
                        connections.append((thoughts[i], thoughts[j], float(similarities[i][j])))
            
            return sorted(connections, key=lambda c: c[2], reverse=True)
        except Exception:
            return []
    
    @staticmethod
    def check_certainty_algorithmic(selected_info: str) -> str:
        """Verificación de certeza basada en reglas."""
        if not selected_info or len(selected_info) < 20:
            return "BAJA"
        
        info_length = len(selected_info)
        
        if info_length > 500:
            return "ALTA"
        elif info_length > 150:
            return "MEDIA"
        else:
            return "BAJA"
    
    @staticmethod
    def should_use_llm_for_certainty(selected_info: str) -> bool:
        """Solo usar LLM para certeza en casos ambiguos."""
        if not selected_info:
            return False
        info_len = len(selected_info)
        return 20 <= info_len <= 500
    
    @staticmethod
    def clarify_memory_vs_activity_algorithmic(user_msg: str) -> str:
        """Heurística para diferenciar MEMORY de ACTIVITY."""
        self_indicators = [
            "funcionas", "piensas", "arquitectura", "procesas",
            "cognitivo", "mente", "razonas", "cerebro",
            "cambios en tu forma", "evolución", "aprendizaje",
            "subconsciente", "fondo", "internamente"
        ]
        
        msg_lower = user_msg.lower()
        
        for indicator in self_indicators:
            if indicator in msg_lower:
                return "ACTIVITY"
        
        return "MEMORY"
    
    @staticmethod
    def is_related(text1: str, text2: str, threshold: int = 3) -> bool:
        """Determina si dos textos están relacionados por palabras compartidas."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        overlap = words1 & words2
        return len(overlap) >= threshold
    
    @staticmethod
    def extract_keywords(text: str, max_keywords: int = 5, use_llm: bool = False) -> List[str]:
        """Extrae palabras clave de un texto.
        
        Args:
            text: Texto del que extraer palabras clave
            max_keywords: Número máximo de palabras clave
            use_llm: Si True, usa LLM para extraer conceptos semánticos en lugar de palabras sueltas.
                    Si False, usa el método rápido de frecuencia de palabras.
        """
        if use_llm:
            return FastCognitiveProcessors._extract_keywords_with_llm(text, max_keywords)
        else:
            return FastCognitiveProcessors._extract_keywords_fast(text, max_keywords)


    @staticmethod
    def _extract_keywords_fast(text: str, max_keywords: int = 5) -> List[str]:
        """Extrae palabras clave rápidamente (sin LLM). Para uso en _fast_tick."""
        stop_words = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del', 'que',
            'y', 'e', 'en', 'a', 'o', 'es', 'por', 'con', 'no', 'se', 'su', 'lo', 'para',
            'como', 'más', 'pero', 'si', 'ya', 'muy', 'todo', 'hay', 'le', 'esa', 'ese',
            'son', 'era', 'han', 'sus', 'entre', 'cuando', 'también', 'fue',
            'the', 'a', 'an', 'of', 'in', 'to', 'is', 'it', 'and', 'or', 'for', 'on', 'at',
            'me', 'mi', 'yo', 'tu', 'tus', 'él', 'ella', 'esto', 'eso', 'aquello',
            'ser', 'estar', 'tener', 'hacer', 'poder', 'decir', 'ir', 'ver',
            'este', 'esta', 'estos', 'estas', 'ese', 'esos', 'esa', 'esas'
        }
        
        words = text.lower().split()
        filtered = [w.strip('.,;:!?¿¡()[]{}""\'\'—…-') 
                    for w in words 
                    if w.strip('.,;:!?¿¡()[]{}""\'\'—…-') not in stop_words 
                    and len(w.strip('.,;:!?¿¡()[]{}""\'\'—…-')) > 2]
        
        from collections import Counter
        return [word for word, _ in Counter(filtered).most_common(max_keywords)]


    @staticmethod
    def _extract_keywords_with_llm(text: str, max_keywords: int = 5) -> List[str]:
        """Extrae conceptos clave usando LLM. Para búsquedas de memoria y enriquecimiento."""
        from core.llm import LLMModel
        
        prompt = f"""Extrae de 3 a {max_keywords} conceptos o temas clave de este texto.
    Devuelve SOLO los conceptos separados por comas, sin explicaciones.
    Cada concepto debe ser una palabra o frase corta que capture una idea.

    Texto: "{text[:300]}"

    Conceptos:"""
        
        try:
            llm = LLMModel.get_instance()
            result = llm.generate(prompt, temperature=0.2, max_tokens=50, purpose="extraer_keywords")
            
            # Limpiar resultado
            keywords = [kw.strip().lower() for kw in result.split(",") if kw.strip()]
            return keywords[:max_keywords]
        except:
            # Fallback: método rápido
            return FastCognitiveProcessors._extract_keywords_fast(text, max_keywords)