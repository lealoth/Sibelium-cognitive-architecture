"""Análisis del usuario por resonancia estructural (sin palabras clave)."""
import numpy as np

from core.llm import LLMModel


# Mapa de referencia de estados afectivos (vectores inmutables)
_AFFECTIVE_MAP = None


def _get_affective_map():
    """Carga el mapa afectivo una sola vez."""
    global _AFFECTIVE_MAP
    if _AFFECTIVE_MAP is None:
        _AFFECTIVE_MAP = {
            "alegria": "feliz contento entusiasmado emocionado positivo agradecido",
            "tristeza": "triste deprimido melancolico desanimado apenado solo",
            "enojo": "enojado frustrado irritado molesto furioso indignado",
            "miedo": "asustado preocupado ansioso temeroso inseguro nervioso",
            "sorpresa": "sorprendido asombrado impresionado desconcertado",
            "neutral": "normal tranquilo calmado neutro objetivo",
            "curiosidad": "curioso interesado intrigado preguntando explorando",
            "confusion": "confundido dudoso inseguro perplejo desorientado",
        }
    return _AFFECTIVE_MAP


def _get_embedding(text: str) -> list:
    """Obtiene embedding de un texto."""
    try:
        from chromadb.utils import embedding_functions
        return embedding_functions.DefaultEmbeddingFunction()([text])[0]
    except Exception:
        return None


def analyze_user_message(message: str) -> dict:
    """
    Análisis por resonancia estructural:
    1. Genera embedding del mensaje
    2. Compara contra mapa afectivo de referencia (dot product)
    3. Extrae intención y temas con LLM (solo 1 llamada)
    """
    # 1. Resonancia afectiva (matemática, sin LLM)
    emotion = "neutral"
    emotion_intensity = 0.0

    msg_emb = _get_embedding(message)
    if msg_emb is not None:
        msg_arr = np.array(msg_emb)
        msg_norm = msg_arr / max(np.linalg.norm(msg_arr), 1e-8)

        best_emotion = "neutral"
        best_sim = -1

        for emotion_name, emotion_text in _get_affective_map().items():
            ref_emb = _get_embedding(emotion_text)
            if ref_emb is None:
                continue
            ref_arr = np.array(ref_emb)
            ref_norm = ref_arr / max(np.linalg.norm(ref_arr), 1e-8)
            sim = float(np.dot(msg_norm, ref_norm))

            if sim > best_sim:
                best_sim = sim
                best_emotion = emotion_name

        emotion = best_emotion
        emotion_intensity = min(1.0, max(0.0, (best_sim - 0.3) / 0.5))

    # 2. Intención y temas (1 llamada LLM)
    prompt = f"""Analiza este mensaje y extrae:
- intencion: pregunta, afirmacion, saludo, queja, sugerencia, correccion, o emocion
- temas: temas principales en 2-4 palabras

Mensaje: "{message[:300]}"

Responde SOLO JSON:
{{"intencion": "...", "temas": "..."}}"""

    try:
        llm = LLMModel.get_instance()
        result = llm.generate(prompt, temperature=0.2, max_tokens=60, purpose="analizar_usuario")

        import re
        import json
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return {
                "intention": data.get("intencion", ""),
                "emotion": emotion,
                "emotion_intensity": round(emotion_intensity, 2),
                "topics": data.get("temas", ""),
            }
    except Exception:
        pass

    return {
        "intention": "",
        "emotion": emotion,
        "emotion_intensity": round(emotion_intensity, 2),
        "topics": "",
    }