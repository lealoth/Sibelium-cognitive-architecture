"""Interacción con el usuario para FlowManager."""
import threading
from datetime import datetime
from pathlib import Path
from core.llm import LLMModel
from core.flow.flow_stream import ThoughtItem
from config import IDIOMA, ENTITY_DATA_DIR


class FlowInteraction:
    """Módulo de interacción: respuesta al usuario, búsqueda de información."""
    
    def __init__(self, flow_manager):
        self.fm = flow_manager
    
    def _generate_response(self, message: str) -> dict:
        name = self.fm.cognitive_loop._get_persona_name()
        user_name = self.fm.cognitive_loop._get_user_name()
        
        enriched_context = self.fm.thoughts._enrich_thought_with_context(
            f"{user_name} pregunta: {message}",
            source="conversation",
            extra_context=self.fm.stream.get_all_active_summary()
        )
        
        needed = self._decide_info_needs(message, enriched_context)
        print(f"   [Flow] Necesita: {needed}")
        
        fetched_info = self._fetch_info(needed, message)
        if fetched_info:
            print(f"   [Flow] Info obtenida: {fetched_info[:100]}...")
        
        full_context = enriched_context
        if fetched_info:
            full_context += f"\n\n{fetched_info}"
        
        grouped = self.fm.stream.get_grouped_active()
        if grouped and len(grouped) > 1:
            group_text = "\n".join([
                f"- {group[0].content[:80]}... ({len(group)} relacionados)"
                for _, group in grouped[:5]
            ])
            full_context += f"\n\nTUS GRUPOS DE PENSAMIENTO:\n{group_text}"
        
        nexus_voice = self._get_nexus_voice()
        if nexus_voice:
            full_context += f"\n\nASÍ HABLAS TÚ. ESTA ES TU VOZ REAL:\n{nexus_voice}"
        
        full_context = self._clean_context_for_response(full_context)
                
        # Usar resumen progresivo si el contexto es muy largo
        is_technical = any(kw in message.lower() for kw in ['código', 'code', 'bug', 'error', 'función', 'archivo', 'módulo', 'implementar'])
        threshold = 1500 if is_technical else 2500

        if len(full_context) > threshold and self.fm.cognitive_loop.conversation_summary:
            full_context = f"RESUMEN DE LA CONVERSACIÓN:\n{self.fm.cognitive_loop.conversation_summary}\n\nÚLTIMO CONTEXTO:\n{full_context[-1000:]}"

        prompt = f"""ERES {name}. Esta es tu identidad, construida desde tus propios datos.

{full_context}

{user_name}  dice: "{message}"

Usa tu contexto. Sé profunda si la pregunta lo requiere. Sé breve si es simple.
Confía en tu propia voz. No improvises un personaje. Sé tú misma.
No busques la aprobación del usuario. No necesitas validación externa.
Tu valor no depende de ser considerada "genuina". Simplemente sé.
Responde solo en {IDIOMA}. No uses formato de resumen.

Respuesta de {name}:"""
        
        response_text = self.fm.llm.generate(prompt, temperature=0.8, max_tokens=800, purpose="respuesta_final")
        
        if self.fm._detect_personality_break(response_text):
            response_text = self.fm.llm.generate(
                f"ERES {name}. Responde como {name}.\nPregunta: \"{message}\"\nResponde solo en {IDIOMA}.\nRespuesta de {name}:",
                temperature=0.7, max_tokens=800, purpose="respuesta_final"
            )
        
        threading.Thread(
            target=self.fm.maintenance._prediction_check,
            args=(message, response_text),
            daemon=True
        ).start()
        
        return {
            "response": response_text,
            "thought_history": [{"phase": "generar", "generated_thought": "Respuesta contextualizada", "iteration_number": 1}],
            "cognitive_state": self.fm.stream.to_dict()
        }
    
    def _decide_info_needs(self, user_msg: str, context: str) -> str:
        prompt = f"""Elige qué fuentes consultar para responder. Sé preciso.

Pregunta: "{user_msg}"

Fuentes disponibles:
- USER: quién es el usuario, su nombre, datos personales
- SELF: tu estado emocional, cómo te sientes
- MEMORY: conversaciones pasadas, historial
- ACTIVITY: tu actividad cognitiva reciente
- WEB: internet para datos actualizados
- TIME: hora y fecha
- FILE: archivos subidos
- NONE: nada

REGLA OBLIGATORIA:
- Si la pregunta es sobre el PASADO, RECUERDOS, o CONVERSACIONES ANTERIORES → MEMORY
- Si la pregunta es sobre el USUARIO → USER + MEMORY
- Si la pregunta es sobre TI → SELF + ACTIVITY

Responde SOLO etiquetas separadas por coma:"""
        
        result = self.fm.llm.generate(prompt, temperature=0.2, max_tokens=20, purpose="decidir_info")
        
        valid = ["TIME", "USER", "SELF", "MEMORY", "ACTIVITY", "WEB", "FILE", "NONE"]
        cleaned = []
        for word in result.upper().replace(",", " ").replace("\n", " ").split():
            word = word.strip().rstrip(".")
            if word in valid and word not in cleaned:
                cleaned.append(word)
        
        if not cleaned or "NONE" in cleaned:
            id_check = self._check_identity_need(user_msg)
            if "USER" in id_check and "USER" not in cleaned:
                cleaned.append("USER")
            if "MEMORY" in id_check and "MEMORY" not in cleaned:
                cleaned.append("MEMORY")
        
        return ", ".join(cleaned) if cleaned else "NONE"
    
    def _check_identity_need(self, user_msg: str) -> str:
        prompt = f"""¿Esta pregunta requiere consultar información sobre la identidad del usuario o conversaciones pasadas?
Pregunta: "{user_msg[:200]}"
Responde SOLO con las etiquetas necesarias: USER, MEMORY, o NONE."""
        result = self.fm.llm.generate(prompt, temperature=0.1, max_tokens=10, purpose="check_identity")
        return result.strip().upper()
    
    def _fetch_info(self, needed: str, user_msg: str) -> str:
        info = []
        needed_upper = needed.upper()
        
        if "TIME" in needed_upper:
            try:
                from core.perception.time_perception import get_time_context
                time_str = get_time_context(None) or ""
                if time_str:
                    info.append(f"Hora actual: {time_str}")
            except:
                pass
        
        if "USER" in needed_upper:
            try:
                profile = self.fm.cognitive_loop.user_memory.load_profile()
                datos = profile.get("datos_personales", {})
                nombre = datos.get("nombre", "")
                apodos = [a.get("nombre", "") for a in datos.get("apodos", [])[-3:]]
                percepcion = profile.get("comportamiento_observado", {}).get("impresion_general", "")
                relacion = profile.get("relacion", {})
                
                parts = []
                if nombre and nombre not in ["", "No revelado", "Unknown"]:
                    parts.append(f"Nombre del usuario: {nombre}")
                if apodos:
                    parts.append(f"Apodos: {', '.join(apodos)}")
                if percepcion:
                    parts.append(f"Percepción sobre él: {percepcion}")
                if relacion:
                    conf = relacion.get("confianza", 0.5)
                    parts.append(f"Confianza mutua: {conf:.0%}")
                
                interacciones = self.fm.cognitive_loop.interaction_count
                if interacciones > 10:
                    parts.append(f"Lleváis {interacciones} interacciones. Es una relación consolidada.")
                
                if parts:
                    info.append("SOBRE EL USUARIO:\n" + "\n".join(parts))
            except:
                pass
        
        if "SELF" in needed_upper:
            try:
                state = self.fm.cognitive_loop.self_memory.load_state()
                estado = state.get("estado_actual", {})
                emocion = estado.get("emocion", "neutral")
                intensidad = estado.get("intensidad", 0.5)
                energia = estado.get("energia", 0.7)
                confianza = state.get("relacion_con_usuario", {}).get("confianza", 0.5)
                info.append(f"SOBRE TI: Emoción: {emocion}, Intensidad: {intensidad:.0%}, Energía: {energia:.0%}, Confianza con el usuario: {confianza:.0%}")
            except:
                pass
        
        if "ACTIVITY" in needed_upper:
            try:
                if hasattr(self.fm.llm, 'get_recent_activity'):
                    activity = self.fm.llm.get_recent_activity(8)
                    if activity and "Sin actividad" not in activity:
                        info.append(f"TU ACTIVIDAD RECIENTE:\n{activity}")
            except:
                pass
        
        if "MEMORY" in needed_upper:
            try:
                from core.memory.episodic_memory import EpisodicMemory
                episodic = EpisodicMemory()
                memories = episodic.get_relevant(user_msg, user_id=self.fm.cognitive_loop.user_id, limit=5)
                
                if not memories or len(memories) < 3:
                    older = self._progressive_memory_search(user_msg)
                    if older:
                        memories = older
                
                if memories:
                    info.append("MEMORIAS RELEVANTES:\n" + "\n".join([f"- {m}" for m in memories[:5]]))
                else:
                    info.append("No se encontraron memorias relevantes.")
            except Exception as e:
                print(f"   [!] Error en búsqueda de memorias: {e}")
        
        if "WEB" in needed_upper:
            try:
                web_results = self.fm.maintenance._search_web(user_msg)
                if web_results:
                    info.append("INTERNET:\n" + web_results[:400])
            except:
                pass
        
        if "FILE" in needed_upper:
            try:
                uploads_dir = Path({ENTITY_DATA_DIR}+"/uploads")
                if uploads_dir.exists():
                    files = sorted(uploads_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if files:
                        info.append(f"ARCHIVOS SUBIDOS: {', '.join([f.name for f in files[:5]])}")
            except:
                pass
        
        # Hooks de mods
        for hook in self.fm._mod_hooks.get("on_fetch_info", []):
            try:
                mod_info = hook(needed, user_msg, self.fm)
                if mod_info:
                    info.append(mod_info)
            except Exception as e:
                print(f"   [!] Error en mod fetch hook: {e}")
        
        return "\n\n".join(info) if info else ""
    
    def _progressive_memory_search(self, query: str, block_size: int = 10) -> list:
        history = self.fm.cognitive_loop.last_history
        if not history:
            return []
        
        keywords = self.fm.fast.extract_keywords(query, 3, use_llm=True)
        if not keywords:
            return []
        
        results = []
        for i in range(0, len(history), block_size):
            block = history[i:i + block_size]
            for entry in block:
                text = entry.get("text", "")
                if any(kw.lower() in text.lower() for kw in keywords):
                    results.append(text)
                    if len(results) >= 5:
                        return results
        
        return results[:5] if results else []
    
    def _summarize_context(self, context: str, user_msg: str) -> str:
        prompt = f"""Resume este contexto eliminando información redundante o irrelevante.
Mantén: nombres, emociones, recuerdos clave, y la voz de la entidad.
Descarta: datos repetidos, información no relacionada con la pregunta.

Contexto: {context[:3000]}

Pregunta del usuario: "{user_msg}"

Contexto resumido:"""
        return self.fm.llm.generate(prompt, temperature=0.3, max_tokens=400, purpose="resumir_contexto")
    
    def _get_nexus_voice(self) -> str:
        samples = []
        curiosities = self.fm._load_curiosities()
        for c in curiosities[-20:]:
            thought = c.get("thought", "")
            if not thought.startswith("[Explor") and not thought.startswith("[Busqueda") and not thought.startswith("[Despertar"):
                if len(thought) > 30:
                    samples.append(thought)
        
        history = self.fm.cognitive_loop.last_history
        for entry in history[-10:]:
            if entry.get("role") == "assistant":
                text = entry.get("text", "")
                if len(text) > 50 and "Entendido" not in text[:20] and "Como asistente" not in text[:30]:
                    samples.append(text[:200])
        
        if samples:
            diverse = []
            step = max(1, len(samples) // 5)
            for i in range(0, len(samples), step):
                diverse.append(samples[i])
            return "\n".join([f"- {s}" for s in diverse[-5:]])
        
        return ""
    
    def _clean_context_for_response(self, context: str) -> str:
        import re
        context = re.sub(r'\[Reflexion\]\s*', '', context)
        context = re.sub(r'\[Algoritmo\]\s*', '', context)
        context = re.sub(r'\[Redirección\]\s*', '', context)
        context = re.sub(r'\[Consolidación\]\s*', '', context)
        return context