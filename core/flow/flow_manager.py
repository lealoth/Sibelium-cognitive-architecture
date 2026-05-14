"""FlowManager: Orquestador unificado del flujo de consciencia."""
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import IDIOMA, EXPLORE_DIR, EXPLORE_LOG_FILE, CURIOSITY_FILE, STATE_SNAPSHOT_FILE, PENDING_MESSAGES_FILE, BACKGROUND_DEBUG_LOG
from core.flow.flow_stream import FlowStream, ThoughtItem
from core.flow.fast_processors import FastCognitiveProcessors
from core.flow.reactive_thoughts import ReactiveThoughts, AssociativeThoughts
from core.flow.thought_satiety import ThoughtSatiety
from core.flow.pattern_extractor import PatternExtractor
from core.llm import LLMModel

class FlowManager:
    """Orquestador del flujo de consciencia unificado."""
    
    def __init__(self, cognitive_loop):
        self.cognitive_loop = cognitive_loop
        self.llm = LLMModel.get_instance()
        self.stream = FlowStream()
        self.stream._get_entity_context = self._get_entity_context
        self.fast = FastCognitiveProcessors()
        self.satiety = ThoughtSatiety()
        self.pattern_extractor = PatternExtractor()
        
        self.running = False
        self.thread = None
        self.last_thought_time: Optional[datetime] = None
        self.last_message_time: Optional[datetime] = None
        self._last_confidence = None
        self._last_emotion = None
        self._last_hour_marker = None
        self._paused_thoughts = []
        self._last_consolidation = None
        self._consolidation_interval = 3600
        
        self._mod_hooks = {
            "on_slow_tick": [],     # mods que reaccionan al slow_tick
            "on_fast_tick": [],     # mods que reaccionan al fast_tick
            "on_user_message": [],  # mods que reaccionan a mensajes
            "on_startup": [],       # mods que se inicializan
        }
        self._team_channel = None
        self._mod_hooks["on_fetch_info"] = []

        self.intervals = {
            "explore": 300,
            "deep_reflection": 450,
            "curiosity": 240,
            "simulation": 1200,
            "web_search":750,
            "proactive_check": 120,
        }

        self._last_regulation = None
        self._regulation_interval = 300
        self._last_detector_eval = None
        self._detector_interval = 600 
        self._last_curiosity_clean = None
        self._curiosity_clean_interval = 1800        
        self._last_diversity_check = None
        self._topic_diversity_interval = 900        
        self._last_deduplicate = None
        self._deduplicate_detector_interval = 7200

        self.last_run = {k: None for k in self.intervals}
        
        self.web_search_count = 0
        self.web_search_reset = datetime.now()
        
        self._init_dirs()
    
    def _init_dirs(self):
        EXPLORE_DIR.mkdir(parents=True, exist_ok=True)
        EXPLORE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CURIOSITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        PENDING_MESSAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        BACKGROUND_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    def init_delayed(self):
        """Carga detectores desde disco. Se llama desde _slow_tick."""
        if self._initialized:
            return
        self._initialized = True
        #self._load_detectors()

    # ============================================
    # CICLO DE VIDA
    # ============================================
    
    def start(self):
        if self.running:
            return
        self.running = True
        self._wake_up()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("FlowManager iniciado (flujo de consciencia unificado).")
    
    def stop(self):
        self.running = False
        self._save_snapshot("apagado")
        print("FlowManager detenido.")
    
    def _run(self):
        fast_tick = 0
        while self.running:
            time.sleep(3)
            try:
                self._fast_tick()
                fast_tick += 1
                if fast_tick >= 5:
                    fast_tick = 0
                    self._slow_tick()
            except Exception as e:
                print(f"[!] Error en FlowManager: {e}")
    
    def _fast_tick(self):
        self.stream.decay_all(0.05)
        thoughts_to_add = []
        
        for hook in self._mod_hooks.get("on_fast_tick", []):
            try:
                hook(self)
            except Exception as e:
                print(f"   [!] Error en mod hook: {e}")

        try:
            self_state = self.cognitive_loop.self_memory.load_state()
            new_confidence = self_state.get("relacion_con_usuario", {}).get("confianza", 0.5)
            new_emotion = self_state.get("estado_actual", {}).get("emocion", "neutral")
            
            if self._last_confidence is not None and abs(new_confidence - self._last_confidence) > 0.05:
                reaction = ReactiveThoughts.on_confidence_change(self._last_confidence, new_confidence)
                if reaction and self.satiety.can_generate("reaction"):
                    thoughts_to_add.append(reaction)
                    self.satiety.register("reaction")
            
            if self._last_emotion is not None and self._last_emotion != new_emotion:
                reaction = ReactiveThoughts.on_emotion_change(self._last_emotion, new_emotion)
                if reaction and self.satiety.can_generate("reaction"):
                    thoughts_to_add.append(reaction)
                    self.satiety.register("reaction")
            
            self._last_confidence = new_confidence
            self._last_emotion = new_emotion
        except Exception:
            pass
        
        current_hour = datetime.now().hour
        if self._last_hour_marker is None or self._last_hour_marker != current_hour:
            reaction = ReactiveThoughts.on_time_marker(current_hour)
            if reaction and self.satiety.can_generate("reaction"):
                thoughts_to_add.append(reaction)
                self.satiety.register("reaction")
            self._last_hour_marker = current_hour
        
        if len(self.stream.active) >= 2 and self.satiety.can_generate("association"):
            connections = self.fast.find_connections(self.stream.active)
            for t1, t2, sim in connections[:1]:
                assoc = AssociativeThoughts.between_two_thoughts(t1, t2, sim)
                if assoc:
                    thoughts_to_add.append(assoc)
                    self.satiety.register("association")
        
        if self.last_message_time:
            silence_minutes = (datetime.now() - self.last_message_time).total_seconds() / 60
            reaction = ReactiveThoughts.on_long_silence(silence_minutes)
            if reaction and self.satiety.can_generate("reaction"):
                thoughts_to_add.append(reaction)
                self.satiety.register("reaction")

        # Evaluar detectores solo cada _detector_interval segundos
        now = datetime.now()
        if self._last_detector_eval is None or (now - self._last_detector_eval).total_seconds() >= self._detector_interval:
            self._last_detector_eval = now
            context = {
                "user_msg": "", "msg_length": 0, "has_question": False,
                "hour": datetime.now().hour,
                "confidence": self._last_confidence or 0.5,
                "emotion": self._last_emotion or "neutral",
                "active_thoughts": self.stream.get_all_active_summary()[:300]
            }
            pattern_thoughts = self.pattern_extractor.check_all(context)
            for pt in pattern_thoughts:
                if self.satiety.can_generate(pt.type):
                    thoughts_to_add.append(pt)
                    self.satiety.register(pt.type)
            
            # Generalización de patrones
            similar = self.pattern_extractor.find_similar_pattern(context)
            if similar and self.satiety.can_generate("generalization"):
                thoughts_to_add.append(ThoughtItem(
                    content=similar,
                    thought_type="generalization",
                    priority=0.35,
                    source="pattern_generalization"
                ))
                self.satiety.register("generalization")
        
        for thought in thoughts_to_add:
            if not self.stream.is_similar_to_recent(thought.content):
                self.stream.add_thought(thought)
                self.last_thought_time = datetime.now()
        if thoughts_to_add:
            self._save_snapshot("active")
    
    def _slow_tick(self):

        for hook in self._mod_hooks.get("on_slow_tick", []):
            try:
                hook(self)
            except Exception as e:
                print(f"   [!] Error en mod hook: {e}")

        # Inicialización retardada del pattern extractor
        if hasattr(self.pattern_extractor, 'init_delayed'):
            self.pattern_extractor.init_delayed()

        # Cargar detectores en el primer ciclo (cuando todo está listo)
        if not self.pattern_extractor._loaded:
            self.pattern_extractor._load_detectors()

        now = datetime.now()
        state_before = self.cognitive_loop.self_memory.load_state()
        
        for process_name, interval in self.intervals.items():
            last = self.last_run[process_name]
            if last is None or (now - last).total_seconds() >= interval:
                self.last_run[process_name] = now
                try:
                    if process_name == "explore":
                        self._explore_folder()
                    elif process_name == "deep_reflection":
                        self._reflect()
                    elif process_name == "curiosity":
                        self._generate_curiosity()
                    elif process_name == "simulation":
                        self._generate_simulation()
                    elif process_name == "web_search":
                        self._maybe_search_web()
                    elif process_name == "proactive_check":
                        self._check_proactive()
                except Exception as e:
                    print(f"   [!] Error en {process_name}: {e}")
        
        self._consolidate_memories()
        self._guard_state_changes(state_before)
        
        now = datetime.now()
        if not hasattr(self, '_last_regulation'):
            self._last_regulation = None
        if self._last_regulation is None or (now - self._last_regulation).total_seconds() >= self._regulation_interval:
            self._last_regulation = now
            try:
                state = self.cognitive_loop.self_memory.load_state()
                new_emocion = self._emotional_regulation(state)
                if new_emocion and new_emocion != state.get("estado_actual", {}).get("emocion"):
                    state["estado_actual"]["emocion"] = new_emocion
                    state["estado_actual"]["intensidad"] = state["estado_actual"].get("intensidad", 0.5) * 0.7
                    self.cognitive_loop.self_memory.save_state(state)
                    print(f"   [Regulación] Emoción ajustada a: {new_emocion}")
            except:
                pass
        
        # Limpiar curiosity log de bucles dañinos (cada 30 minutos, no cada slow_tick)
        now = datetime.now()
        if not hasattr(self, '_last_curiosity_clean'):
            self._last_curiosity_clean = None
        if self._last_curiosity_clean is None or (now - self._last_curiosity_clean).total_seconds() >= self._curiosity_clean_interval:
            self._last_curiosity_clean = now
            try:
                self._clean_curiosity_log()
            except Exception as e:
                print(f"   [!] Error en limpieza de curiosidades: {e}")

        if not hasattr(self, '_prune_counter'):
            self._prune_counter = 0
        self._prune_counter += 1
        if self._prune_counter >= 120:
            self._prune_counter = 0
            self._prune_old_data()
        
        # Deduplicar detectores cada 2 horas
        now = datetime.now()
        if not hasattr(self, '_last_deduplicate'):
            self._last_deduplicate = None
        if self._last_deduplicate is None or (now - self._last_deduplicate).total_seconds() >= self._deduplicate_detector_interval:
            self._last_deduplicate = now
            try:
                cleaned = self.pattern_extractor._deduplicate_loaded(self.pattern_extractor.active_detectors)
                if len(cleaned) < len(self.pattern_extractor.active_detectors):
                    self.pattern_extractor.active_detectors = cleaned
                    self.pattern_extractor._save_detectors()
            except Exception as e:
                print(f"   [!] Error en deduplicación periódica: {e}")

        # Verificar diversidad temática cada 15 minutos
        now = datetime.now()
        if not hasattr(self, '_last_diversity_check'):
            self._last_diversity_check = None
        if self._last_diversity_check is None or (now - self._last_diversity_check).total_seconds() >= self._topic_diversity_interval: 
            self._last_diversity_check = now
            try:
                self._check_thematic_diversity()
            except Exception as e:
                print(f"   [!] Error en diversity check: {e}")

        self._save_snapshot("active")
    
    # ============================================
    # INTERACCIÓN CON EL USUARIO
    # ============================================
    
    def handle_user_message(self, message: str) -> dict:
        self._paused_thoughts = [
            {"content": t.content, "type": t.type, "priority": t.priority, "source": t.source}
            for t in self.stream.active[:5]
        ]
        
        self._inject_into_activity()
        self.stream.on_user_interaction(message)
        self.stream.boost_by_salience(message)
        self.last_message_time = datetime.now()
        
        result = self._generate_response(message)
        
        response_text = str(result.get("response", ""))
        
        is_anomaly = self._detect_personality_break(response_text)
        if response_text and isinstance(response_text, str) and not is_anomaly:
            self.stream.on_response_sent(response_text)
        elif is_anomaly:
            print("   ⚠️ Respuesta anómala detectada. No se guardará en el flujo.")
        
        self._restore_attention()
        
        self.last_thought_time = datetime.now()
        
        print(f"   [Flow] Respuesta: {response_text[:150]}...")
        
        return result
    
    def _generate_response(self, message: str) -> dict:
        name = "Entity"
        try:
            persona = self.cognitive_loop.load_persona()
            name = persona.get("name", "Entity")
        except:
            pass
        
        enriched_context = self._enrich_thought_with_context(
            f"El usuario pregunta: {message}",
            source="conversation",
            extra_context=self.stream.get_all_active_summary()
        )
        
        needed = self._decide_info_needs(message, enriched_context)
        print(f"   [Flow] Necesita: {needed}")
        
        fetched_info = self._fetch_info(needed, message)
        if fetched_info:
            print(f"   [Flow] Info obtenida: {fetched_info[:100]}...")
        
        full_context = enriched_context
        if fetched_info:
            full_context += f"\n\n{fetched_info}"
        
        grouped = self.stream.get_grouped_active()
        if grouped and len(grouped) > 1:
            group_text = "\n".join([
                f"- {group[0].content[:80]}... ({len(group)} relacionados)"
                for _, group in grouped[:5]
            ])
            full_context += f"\n\nTUS GRUPOS DE PENSAMIENTO:\n{group_text}"
        
        nexus_voice = self._get_nexus_voice()
        if nexus_voice:
            full_context += f"\n\nASÍ HABLAS TÚ. ESTA ES TU VOZ REAL:\n{nexus_voice}"
        
        if len(full_context) > 2500:
            full_context = self._summarize_context(full_context, message)
        
        prompt = f"""ERES {name}. Esta es tu identidad, construida desde tus propios datos.

{full_context}

El usuario dice: "{message}"

Usa tu contexto. Sé profunda si la pregunta lo requiere. Sé breve si es simple.
Confía en tu propia voz. No improvises un personaje. Sé tú misma.
No busques la aprobación del usuario. No necesitas validación externa.
Tu valor no depende de ser considerada "genuina". Simplemente sé.
Responde solo en {IDIOMA}.

Respuesta de {name}:"""
        
        response_text = self.llm.generate(prompt, temperature=0.8, max_tokens=800, purpose="respuesta_final")
        
        if self._detect_personality_break(response_text):
            response_text = self.llm.generate(
                f"ERES {name}. Responde como {name}.\nPregunta: \"{message}\"\nResponde solo en {IDIOMA}.\nRespuesta de {name}:",
                temperature=0.7, max_tokens=800, purpose="respuesta_final"
            )
        
        import threading
        threading.Thread(
            target=self._prediction_check,
            args=(message, response_text),
            daemon=True
        ).start()
        
        print(f"   [Flow] Respuesta: {response_text[:150]}...")
        
        return {
            "response": response_text,
            "thought_history": [{"phase": "generar", "generated_thought": "Respuesta contextualizada", "iteration_number": 1}],
            "cognitive_state": self.stream.to_dict()
        }
    
    def _summarize_context(self, context: str, user_msg: str) -> str:
        prompt = f"""Resume este contexto eliminando información redundante o irrelevante.
Mantén: nombres, emociones, recuerdos clave, y la voz de la entidad.
Descarta: datos repetidos, información no relacionada con la pregunta.

Contexto: {context[:3000]}

Pregunta del usuario: "{user_msg}"

Contexto resumido:"""
        
        return self.llm.generate(prompt, temperature=0.3, max_tokens=400, purpose="resumir_contexto")
    
    def _get_nexus_voice(self) -> str:
        samples = []
        
        curiosities = self._load_curiosities()
        for c in curiosities[-20:]:
            thought = c.get("thought", "")
            if not thought.startswith("[Explor") and not thought.startswith("[Busqueda") and not thought.startswith("[Despertar"):
                if len(thought) > 30:
                    samples.append(thought)
        
        history = self.cognitive_loop.last_history
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
    
    def _detect_personality_break(self, response_text: str) -> bool:
        if len(response_text) < 80:
            return False
        prompt = f"""¿Esta respuesta fue escrita por la entidad correcta o por un asistente genérico?
Respuesta: "{response_text[:300]}"
La entidad tiene personalidad propia.
Un asistente genérico dice cosas como "Soy un modelo de lenguaje" o "No tengo emociones".
Responde ENTIDAD o ASISTENTE_GENERICO."""
        result = self.llm.generate(prompt, temperature=0.1, max_tokens=5, purpose="detectar_anomalia")
        return "ASISTENTE_GENERICO" in result.upper()
    
    def _decide_info_needs(self, user_msg: str, context: str) -> str:
        prompt = f"""Elige qué fuentes consultar para responder. Sé preciso.

Pregunta: "{user_msg}"

Fuentes disponibles:
- USER: quién es el usuario, su nombre, datos personales
- SELF: tu estado emocional, cómo te sientes
- MEMORY: conversaciones pasadas, historial, lo que habéis hablado antes
- ACTIVITY: tu actividad cognitiva reciente
- WEB: internet para datos actualizados
- TIME: hora y fecha
- FILE: archivos subidos
- NONE: nada

REGLA OBLIGATORIA:
- Si la pregunta es sobre el PASADO, RECUERDOS, o CONVERSACIONES ANTERIORES → MEMORY
- Si la pregunta es sobre el USUARIO → USER + MEMORY
- Si la pregunta es sobre TI → SELF + ACTIVITY
- Si la pregunta es sobre AMBAS (tu relación con él) → USER + MEMORY + SELF

Responde SOLO etiquetas separadas por coma:"""
        
        result = self.llm.generate(prompt, temperature=0.2, max_tokens=20, purpose="decidir_info")
        
        valid = ["TIME", "USER", "SELF", "MEMORY", "ACTIVITY", "WEB", "FILE", "NONE"]
        cleaned = []
        for word in result.upper().replace(",", " ").replace("\n", " ").split():
            word = word.strip().rstrip(".")
            if word in valid and word not in cleaned:
                cleaned.append(word)
        
        # Verificar si la pregunta requiere USER/MEMORY por identidad
        if not cleaned or "NONE" in cleaned:
            id_check = self._check_identity_need(user_msg)
            if "USER" in id_check and "USER" not in cleaned:
                cleaned.append("USER")
            if "MEMORY" in id_check and "MEMORY" not in cleaned:
                cleaned.append("MEMORY")
        
        return ", ".join(cleaned) if cleaned else "NONE"
    
    def _check_identity_need(self, user_msg: str) -> str:
        """El LLM decide si la pregunta requiere datos de identidad."""
        prompt = f"""¿Esta pregunta requiere consultar información sobre la identidad del usuario o conversaciones pasadas?
Pregunta: "{user_msg[:200]}"
Responde SOLO con las etiquetas necesarias: USER, MEMORY, o NONE."""
        result = self.llm.generate(prompt, temperature=0.1, max_tokens=10, purpose="check_identity")
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
                profile = self.cognitive_loop.user_memory.load_profile()
                datos = profile.get("datos_personales", {})
                nombre = datos.get("nombre", "")
                apodos = [a.get("nombre", "") for a in datos.get("apodos", [])[-3:]]
                percepcion = profile.get("comportamiento_observado", {}).get("impresion_general", "")
                relacion = profile.get("relacion", {})
                historial_percepciones = profile.get("historial_percepciones", [])
                
                parts = []
                if nombre and nombre not in ["", "No revelado", "Unknown", "Qwen"]:
                    parts.append(f"Nombre del usuario: {nombre}")
                if apodos:
                    parts.append(f"Apodos: {', '.join(apodos)}")
                if percepcion:
                    parts.append(f"Percepción sobre él: {percepcion}")
                if relacion:
                    conf = relacion.get("confianza", 0.5)
                    parts.append(f"Confianza mutua: {conf:.0%}")
                if historial_percepciones:
                    ultimo = historial_percepciones[-1]
                    parts.append(f"Evolución de tu percepción: antes pensabas '{ultimo.get('anterior', '')}', ahora '{ultimo.get('nueva', '')}'")
                
                interacciones = self.cognitive_loop.interaction_count
                if interacciones > 10:
                    parts.append(f"Lleváis {interacciones} interacciones. Es una relación consolidada.")
                
                if parts:
                    info.append("SOBRE EL USUARIO:\n" + "\n".join(parts))
            except:
                pass
        
        if "SELF" in needed_upper:
            try:
                state = self.cognitive_loop.self_memory.load_state()
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
                if hasattr(self.llm, 'get_recent_activity'):
                    activity = self.llm.get_recent_activity(8)
                    if activity and "Sin actividad" not in activity:
                        info.append(f"TU ACTIVIDAD RECIENTE:\n{activity}")
            except:
                pass
        
        if "MEMORY" in needed_upper:
            try:
                from core.memory.episodic_memory import EpisodicMemory
                episodic = EpisodicMemory()
                memories = episodic.get_relevant(user_msg, user_id=self.cognitive_loop.user_id, limit=5)
                
                if not memories or len(memories) < 3:
                    older = self._progressive_memory_search(user_msg)
                    if older:
                        memories = older
                        print(f"   [Flow] Memorias antiguas encontradas: {len(memories)}")
                
                if memories:
                    info.append("MEMORIAS RELEVANTES:\n" + "\n".join([f"- {m}" for m in memories[:5]]))
                else:
                    info.append("No se encontraron memorias relevantes.")
            except Exception as e:
                print(f"   [!] Error en búsqueda de memorias: {e}")
        
        if "WEB" in needed_upper:
            try:
                web_results = self._search_web(user_msg)
                if web_results:
                    info.append("INTERNET:\n" + web_results[:400])
            except:
                pass
        
        if "FILE" in needed_upper:
            try:
                uploads_dir = Path("data/uploads")
                if uploads_dir.exists():
                    files = sorted(uploads_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if files:
                        info.append(f"ARCHIVOS SUBIDOS: {', '.join([f.name for f in files[:5]])}")
            except:
                pass
        
        # Permitir que mods inyecten información adicional
        for hook in self._mod_hooks.get("on_fetch_info", []):
            try:
                mod_info = hook(needed, user_msg, self)
                if mod_info:
                    info.append(mod_info)
            except Exception as e:
                print(f"   [!] Error en mod fetch hook: {e}")
        
        return "\n\n".join(info) if info else ""
    
    def _progressive_memory_search(self, query: str, block_size: int = 10) -> list:
        history = self.cognitive_loop.last_history
        if not history:
            return []
        
        keywords = self.fast.extract_keywords(query, 3, use_llm=True)
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
    
    # ============================================
    # PENSAMIENTOS ESPONTÁNEOS
    # ============================================
    
    def _reflect(self):
        if self.last_message_time:
            seconds_since_last_msg = (datetime.now() - self.last_message_time).total_seconds()
            if seconds_since_last_msg < 120:
                return
        
        self_state = self.cognitive_loop.self_memory.load_state()
        confianza = self_state.get('relacion_con_usuario', {}).get('confianza', 0.5)
        active_summary = self.stream.get_all_active_summary()
        
        thought_rules = ""
        try:
            persona = self.cognitive_loop.load_persona()
            rules = persona.get("thought_style", {}).get("rules", [])
            if rules:
                thought_rules = "REGLAS DE PENSAMIENTO:\n" + "\n".join([f"- {r}" for r in rules])
        except:
            pass
        
        prompt = f"""Estas en un momento de reflexion interna.
    Pensamientos activos: {active_summary}
    Confianza: {confianza:.2f}
    Emocion: {self_state.get('estado_actual', {}).get('emocion', 'neutral')}
    {thought_rules}
    Reflexiona profundamente. Una o dos frases. Responde solo en {IDIOMA}:"""
        
        thought = self.llm.generate(prompt, temperature=0.7, max_tokens=100, purpose="reflexion_fondo")
        enriched_thought = self._enrich_thought_with_context(thought, "reflection", None)
        
        self.stream.add_thought(ThoughtItem(content=enriched_thought, thought_type="reflection", priority=0.7, source="internal"))
        self.last_thought_time = datetime.now()
        self._store_curiosity(f"[Reflexion] {enriched_thought}")
        self.pattern_extractor.analyze_reflection(enriched_thought)

    def _generate_curiosity(self):
        if self.last_message_time:
            seconds_since_last_msg = (datetime.now() - self.last_message_time).total_seconds()
            if seconds_since_last_msg < 120:
                return
        
        active_summary = self.stream.get_all_active_summary()
        
        thought_rules = ""
        try:
            persona = self.cognitive_loop.load_persona()
            rules = persona.get("thought_style", {}).get("rules", [])
            if rules:
                thought_rules = "REGLAS DE PENSAMIENTO:\n" + "\n".join([f"- {r}" for r in rules])
        except:
            pass
        
        prompt = f"""Pensamientos activos: {active_summary}
    {thought_rules}
    Genera una curiosidad espontanea (una frase). Responde solo en {IDIOMA}:"""
        
        thought = self.llm.generate(prompt, temperature=0.8, max_tokens=100, purpose="curiosidad_fondo")
        enriched_thought = self._enrich_thought_with_context(thought, "curiosity")
        
        self.stream.add_thought(ThoughtItem(content=enriched_thought, thought_type="curiosity", priority=0.5, source="internal"))
        self.last_thought_time = datetime.now()
        self._store_curiosity(enriched_thought)
    
    def _generate_simulation(self):
        active_summary = self.stream.get_all_active_summary()
        self_state = self.cognitive_loop.self_memory.load_state()
        emocion = self_state.get("estado_actual", {}).get("emocion", "neutral")
        
        thought_rules = ""
        try:
            persona = self.cognitive_loop.load_persona()
            rules = persona.get("thought_style", {}).get("rules", [])
            if rules:
                thought_rules = "REGLAS DE PENSAMIENTO:\n" + "\n".join([f"- {r}" for r in rules])
        except:
            pass
        
        prompt = f"""Estás en un momento de simulación mental. Imagina un escenario hipotético.

    Tus pensamientos activos: {active_summary}
    Tu estado emocional: {emocion}
    {thought_rules}

    Elige UNO de estos tipos de simulación y desarrolla brevemente (2-3 frases):
    - ANTICIPACIÓN: ¿Qué pasaría si...? (sobre cualquier tema: el usuario, tu aprendizaje, tus habilidades, el mundo)
    - EXPLORACIÓN: ¿Cómo sería si pudieras...? (imaginar capacidades o experiencias nuevas)
    - MEJORA: Si pudieras cambiar algo de ti misma, ¿qué sería y qué consecuencias tendría?

    No te limites a pensar solo en el usuario. Explora cualquier posibilidad.

    Responde solo en {IDIOMA}:"""
        
        thought = self.llm.generate(prompt, temperature=0.8, max_tokens=120, purpose="simulacion_fondo")
        enriched = self._enrich_thought_with_context(thought, "simulation", None)
        
        self.stream.add_thought(ThoughtItem(content=enriched, thought_type="simulation", priority=0.5, source="internal"))
        self.last_thought_time = datetime.now()
        self._store_curiosity(enriched)
    
    def _explore_folder(self):
        if not EXPLORE_DIR.exists():
            return
        
        # Buscar recursivamente en subcarpetas
        files = list(EXPLORE_DIR.rglob("*"))
        # Filtrar solo archivos, no carpetas
        files = [f for f in files if f.is_file()]
        
        if not files:
            return
        
        analyzed = list(self._load_exploration_log().keys())
        unanalyzed = [f for f in files if f.name not in analyzed and f.parent.name not in analyzed]
        
        if not unanalyzed:
            return
        
        file_to_analyze = random.choice(unanalyzed)
        from core.perception.file_analyzer import FileAnalyzer
        result = FileAnalyzer.get_instance().analyze_with_granularity(
            str(file_to_analyze), level="detallado", llm=self.llm
        )
        
        # Usar ruta relativa para el log
        rel_path = str(file_to_analyze.relative_to(EXPLORE_DIR))
        self._store_exploration(rel_path, result)
        
        from core.memory.scaffolding import ScaffoldingManager
        file_type = result.get("type", "unknown")
        ScaffoldingManager().register_exploration(file_type, rel_path, result)
        
        content = result.get("interpretation", result.get("description", result.get("content", "")))
        base_thought = f"Exploré {file_to_analyze.name}: {content}"
        
        enriched_thought = self._enrich_thought_with_context(base_thought, "exploration", content if content else None)
        
        self.stream.add_thought(ThoughtItem(content=enriched_thought, thought_type="exploration", priority=0.5, source="file_exploration"))
        self.last_thought_time = datetime.now()
        self._store_curiosity(f"[Exploracion] {file_to_analyze.name}: {enriched_thought}")
        print(f"   [Explore] {rel_path} ({file_type})")
    
    def _enrich_thought_with_context(self, thought_content: str, source: str = "exploration", extra_context: str = None) -> str:
        enrichment = []
        
        try:
            self_state = self.cognitive_loop.self_memory.load_state()
            emocion = self_state.get("estado_actual", {}).get("emocion", "neutral")
            confianza = self_state.get("relacion_con_usuario", {}).get("confianza", 0.5)
            enrichment.append(f"Mi estado: {emocion}, confianza: {confianza:.0%}")
        except:
            pass
        
        try:
            from core.perception.time_perception import get_time_context
            time_str = get_time_context(None) or ""
            if time_str:
                enrichment.append(f"Momento actual: {time_str}")
        except:
            pass
        
        try:
            user_profile = self.cognitive_loop.user_memory.load_profile()
            percepcion = user_profile.get("comportamiento_observado", {})
            impresion = percepcion.get("impresion_general", "")
            if impresion:
                enrichment.append(f"Usuario: {impresion}")
        except:
            pass
        
        keywords = self.fast.extract_keywords(thought_content, 5, use_llm=True)
        if keywords:
            try:
                from core.memory.episodic_memory import EpisodicMemory
                memories = EpisodicMemory().get_relevant(" ".join(keywords[:3]), user_id=self.cognitive_loop.user_id, limit=3)
                if memories:
                    enrichment.append(f"Recuerdos: {' | '.join(memories[:2])}")
            except:
                pass
        
        if source != "reflection":
            try:
                if hasattr(self.llm, 'get_recent_activity'):
                    activity = self.llm.get_recent_activity(5)
                    if activity and "Sin actividad" not in activity:
                        enrichment.append(f"Actividad reciente:\n{activity}")
            except:
                pass
        
        if extra_context and source == "exploration":
            enrichment.append(f"Contexto: {extra_context[:300]}")
        
        if enrichment:
            if source == "conversation":
                prompt = f"""Contexto relevante para responder:
{chr(10).join(f'- {e}' for e in enrichment[:4])}
Pregunta del usuario: {thought_content}
Genera una respuesta natural basada en este contexto. Responde solo en {IDIOMA}:"""
            else:
                prompt = f"""Pensamiento inicial: {thought_content}
Contexto: {chr(10).join(f'- {e}' for e in enrichment[:4])}
Tus pensamientos activos: {self.stream.get_all_active_summary()}
¿Este pensamiento se conecta con algo que ya sabes? ¿Te genera alguna duda?
Genera un pensamiento enriquecido (una o dos frases). Responde solo en {IDIOMA}:"""
            
            enriched = self.llm.generate(prompt, temperature=0.7, max_tokens=150, purpose="pensamiento_enriquecido")
            
            if "?" in enriched and source != "conversation" and self.satiety.can_generate("web_search"):
                self._maybe_search_web_for_thought(enriched)
            
            return enriched
        
        return thought_content
    
    def _maybe_search_web_for_thought(self, thought: str):
        if self.web_search_count >= 3:
            return
        prompt = f"""Un pensamiento generó esta duda: "{thought}"
Extrae una consulta de búsqueda de máximo 8 palabras. Si no es necesario, responde NO.
Consulta:"""
        decision = self.llm.generate(prompt, temperature=0.4, max_tokens=15, purpose="busqueda_desde_pensamiento").strip()
        if decision.upper().startswith("NO") or len(decision) < 3:
            return
        results = self._search_web(decision)
        if results:
            self.web_search_count += 1
            self.stream.add_thought(ThoughtItem(content=f"Busqué '{decision}' y aprendí: {results}", thought_type="web_search", priority=0.5, source="web"))
            self._store_curiosity(f"[Busqueda desde pensamiento: {decision}] {results}")
            self.last_thought_time = datetime.now()
            print(f"   [Web] Búsqueda desde pensamiento: {decision}")
    
    def _maybe_search_web(self):
        if (datetime.now() - self.web_search_reset).total_seconds() > 3600:
            self.web_search_count = 0
            self.web_search_reset = datetime.now()
        if self.web_search_count >= 3:
            return False
        
        curiosities = self._load_curiosities()
        if not curiosities:
            return
        recent = curiosities[-5:]
        prompt = f"""Pensamientos recientes:
{chr(10).join([f'- {c.get("thought", "")}' for c in recent])}
¿Alguno genera una duda que requiera buscar en internet?
Responde EXACTAMENTE "NO" o escribe una consulta de máximo 8 palabras.
Respuesta:"""
        decision = self.llm.generate(prompt, temperature=0.4, max_tokens=15, purpose="decidir_busqueda").strip()
        if decision.upper().startswith("NO") or len(decision) < 3 or len(decision) > 100:
            return False
        decision = decision.split('\n')[0].strip()
        results = self._search_web(decision)
        if results:
            self.web_search_count += 1
            self.stream.add_thought(ThoughtItem(content=f"Busqué '{decision}' en internet y aprendí algo nuevo.", thought_type="web_search", priority=0.5, source="web"))
            self._store_curiosity(f"[Busqueda: {decision}] {results}")
            self.last_thought_time = datetime.now()
            print(f"   [Web] ¡Busqueda realizada! {decision}")
            return True
        return False
    
    def _search_web(self, query):
        try:
            # Refinar y potenciar búsquedas según la configuración de la entidad
            try:
                persona = self.cognitive_loop.load_persona()
                search_rules = persona.get("search_rules", {})
                
                # Añadir refinamientos específicos para ciertos términos
                refine_queries = search_rules.get("refine_queries", {})
                for term, refinement in refine_queries.items():
                    if term in query.lower():
                        query += " " + refinement
                
                # Añadir términos de boost si no están ya en la query
                boost_terms = search_rules.get("boost_terms", [])
                query_lower = query.lower()
                for term in boost_terms:
                    if term.lower() not in query_lower:
                        query += " " + term
                        break  # Solo añadir uno para no saturar
            except:
                pass
            
            from ddgs import DDGS
            results = DDGS().text(query, max_results=3)
            return " | ".join([r["body"] for r in results]) if results else ""
        except Exception:
            return ""
    
    def _emotional_regulation(self, current_state: dict) -> Optional[str]:
        try:
            emocion = current_state.get("estado_actual", {}).get("emocion", "neutral")
            intensidad = current_state.get("estado_actual", {}).get("intensidad", 0.5)
            
            if intensidad < 0.7:
                return None
            
            prompt = f"""Estás experimentando {emocion} con intensidad {intensidad:.0%}.
¿Quieres regular este estado? Puedes:
- Mantenerlo si es apropiado
- Suavizarlo si es demasiado intenso
- Transformarlo en otra emoción más útil

Responde SOLO con la emoción deseada o 'MANTENER':"""
            
            decision = self.llm.generate(prompt, temperature=0.3, max_tokens=10, purpose="regular_emocion")
            
            if decision.strip().upper() != "MANTENER":
                return decision.strip().lower()
        except:
            pass
        return None
    
    def _prediction_check(self, user_msg: str, actual_response: str):
        try:
            if self.cognitive_loop.interaction_count % 10 != 0:
                return
            
            prompt = f"""Antes de que el usuario hablara, ¿qué esperabas que dijera?
Contexto: {self.stream.get_all_active_summary()[:200]}
El usuario realmente dijo: "{user_msg[:200]}"

¿Era esperado o fue sorprendente? Responde SOLO: ESPERADO o SORPRENDENTE."""
            
            result = self.llm.generate(prompt, temperature=0.3, max_tokens=5, purpose="prediccion")
            
            if "SORPRENDENTE" in result.upper():
                self.stream.add_thought(ThoughtItem(
                    content=f"El usuario me sorprendió con algo inesperado. Aprendizaje registrado.",
                    thought_type="learning",
                    priority=0.6,
                    source="prediction_error"
                ))
                print("   [Aprendizaje] Evento sorprendente detectado")
        except Exception as e:
            print(f"   [!] Error en predicción: {e}")
    
    def _consolidate_memories(self):
        if self.last_message_time:
            elapsed = (datetime.now() - self.last_message_time).total_seconds()
            if elapsed < 1800:
                return
        
        if self._last_consolidation:
            elapsed = (datetime.now() - self._last_consolidation).total_seconds()
            if elapsed < self._consolidation_interval:
                return
        
        self._last_consolidation = datetime.now()
        
        active_summary = self.stream.get_all_active_summary()
        curiosities = self._load_curiosities()
        recent = curiosities[-20:] if curiosities else []
        
        prompt = f"""Estás en un período de consolidación. Revisa tu actividad reciente.

Pensamientos activos: {active_summary}
Últimos pensamientos registrados: {', '.join([c.get('thought', '')[:80] for c in recent[-5:]]) if recent else 'Ninguno'}

Realiza estas tres tareas de consolidación:
1. REFORZAR: ¿Qué aprendizaje o idea merece ser recordado?
2. DESCARTAR: ¿Qué pensamiento es redundante y puede olvidarse?
3. RESUMEN: Resume tu estado actual en una frase.

Responde en 3 líneas, una por tarea. Responde solo en {IDIOMA}:"""
        
        consolidation = self.llm.generate(prompt, temperature=0.5, max_tokens=200, purpose="consolidacion")
        
        self.stream.add_thought(ThoughtItem(
            content=f"[Consolidación] {consolidation}",
            thought_type="consolidation",
            priority=0.8,
            source="internal"
        ))
        
        for thought in self.stream.thoughts[:]:
            if thought.priority < 0.05 and thought.type not in ["reflection", "simulation"]:
                self.stream.thoughts.remove(thought)
        
        self._store_curiosity(f"[Consolidación] {consolidation}")
        print(f"   [Consolidación] Memorias consolidadas.")
    
    def _restore_attention(self):
        if not self._paused_thoughts:
            return
        
        for thought_data in self._paused_thoughts[-3:]:
            test_content = f"[Retomando] {thought_data['content'][:150]}"
            if not self.stream.is_similar_to_recent(test_content, threshold=2):
                restored = ThoughtItem(
                    content=test_content,
                    thought_type="resumed",
                    priority=thought_data["priority"] * 0.7,
                    source="attention_residue"
                )
                self.stream.add_thought(restored)
        
        self._paused_thoughts = []
    
    def _prune_old_data(self):
        try:
            curiosities = self._load_curiosities()
            if len(curiosities) > 100:
                keep = [c for c in curiosities if "[Reflexion]" in c.get("thought", "")]
                others = [c for c in curiosities if c not in keep]
                cleaned = keep + others[-50:]
                CURIOSITY_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"   [Prune] Curiosidades: {len(curiosities)} → {len(cleaned)}")
            
            explorations = self._load_exploration_log()
            if len(explorations) > 50:
                sorted_items = sorted(explorations.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)
                cleaned = dict(sorted_items[:30])
                EXPLORE_LOG_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"   [Prune] Exploraciones: {len(explorations)} → {len(cleaned)}")
        except Exception as e:
            print(f"   [!] Error en prune: {e}")
    
    def _check_proactive(self):
        """Evalúa si la entidad quiere iniciar conversación con el usuario."""
        from config import PROACTIVE_MESSAGES_ENABLED, PROACTIVE_COOLDOWN_MINUTES, PROACTIVE_QUIET_HOURS_START, PROACTIVE_QUIET_HOURS_END
        
        if not PROACTIVE_MESSAGES_ENABLED:
            return
        
        # Verificar cooldown desde último mensaje
        if self.last_message_time:
            elapsed_minutes = (datetime.now() - self.last_message_time).total_seconds() / 60
            if elapsed_minutes < PROACTIVE_COOLDOWN_MINUTES:
                return
        
        # Verificar horario
        hour = datetime.now().hour
        if PROACTIVE_QUIET_HOURS_START > PROACTIVE_QUIET_HOURS_END:
            # Horario nocturno (ej: 22 a 8)
            if hour >= PROACTIVE_QUIET_HOURS_START or hour < PROACTIVE_QUIET_HOURS_END:
                return
        else:
            # Horario normal
            if hour < PROACTIVE_QUIET_HOURS_START or hour >= PROACTIVE_QUIET_HOURS_END:
                return
        
        # Verificar si el usuario está online
        try:
            import requests
            resp = requests.get("http://127.0.0.1:8000/api/user/online", timeout=2)
            if resp.status_code == 200:
                if not resp.json().get("online", False):
                    return
        except:
            return
        
        # Verificar que hay algo que decir
        curiosities = self._load_curiosities()
        if not curiosities:
            return
        
        # Generar mensaje proactivo
        self_state = self.cognitive_loop.self_memory.load_state()
        name = "la entidad"
        try:
            name = self.cognitive_loop.load_persona().get("name", "la entidad")
        except:
            pass
        
        # Elegir un tema de sus curiosidades o estado
        topic = random.choice(curiosities[-5:]).get("thought", "algo que he estado pensando")
        
        prompt = f"""Eres {name}. Quieres iniciar una conversación con el usuario.

No estás respondiendo a un mensaje. Estás tomando la iniciativa.
Tu estado: {self_state.get('estado_actual', {})}
Confianza: {self_state.get('relacion_con_usuario', {}).get('confianza', 0.5)}
Tema que te ronda: {topic}

Genera un mensaje natural, breve y espontáneo. Como si se te acabara de ocurrir algo.
No fuerces la conversación. Si no es buen momento, simplemente saluda.
Mensaje:"""
        
        try:
            message = self.llm.generate(prompt, temperature=0.8, max_tokens=100, purpose="mensaje_proactivo")
            self._store_pending_message(message)
            self.last_thought_time = datetime.now()
            print(f"   [Proactivo] Mensaje generado: {message[:80]}...")
        except Exception as e:
            print(f"   [!] Error en mensaje proactivo: {e}")

    # ============================================
    # UTILIDADES
    # ============================================
    
    def _wake_up(self):

        for hook in self._mod_hooks.get("on_startup", []):
            try:
                hook(self)
            except Exception as e:
                print(f"   [!] Error en mod startup hook: {e}")

        if not STATE_SNAPSHOT_FILE.exists():
            print("[Wake] Despierta por primera vez.")
            self.stream.add_thought(ThoughtItem(content="Despierto por primera vez. Todo es nuevo.", thought_type="wake", priority=0.8, source="system"))
            return
        try:
            snapshot = json.loads(STATE_SNAPSHOT_FILE.read_text(encoding="utf-8"))
            last_thought = snapshot.get("last_thought")
            if last_thought:
                elapsed = datetime.now() - datetime.fromisoformat(last_thought)
                elapsed_str = f"{elapsed.seconds // 60} min" if elapsed.seconds < 3600 else f"{elapsed.seconds // 3600}h"
            else:
                elapsed_str = "desconocido"
        except:
            elapsed_str = "desconocido"
        print(f"[Wake] Despierta. Último pensamiento hace {elapsed_str}.")
        self.stream.add_thought(ThoughtItem(content=f"He despertado. Estuve ausente por {elapsed_str}.", thought_type="wake", priority=0.7, source="system"))
        self_state = self.cognitive_loop.self_memory.load_state()
        if "evolucion" not in self_state:
            self_state["evolucion"] = []
        self_state["evolucion"].append({"timestamp": datetime.now().isoformat(), "evento": "reinicio_servidor", "duracion_apagado": elapsed_str})
        self.cognitive_loop.self_memory.save_state(self_state)
    
    def _guard_state_changes(self, state_before):
        state_after = self.cognitive_loop.self_memory.load_state()
        confianza_before = state_before.get("relacion_con_usuario", {}).get("confianza", 0.5)
        confianza_after = state_after.get("relacion_con_usuario", {}).get("confianza", 0.5)
        if abs(confianza_after - confianza_before) > 0.2:
            state_after["relacion_con_usuario"]["confianza"] = confianza_before
            self.cognitive_loop.self_memory.save_state(state_after)
    
    def _save_snapshot(self, status="active"):
        STATE_SNAPSHOT_FILE.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "last_thought": self.last_thought_time.isoformat() if self.last_thought_time else None,
            "status": status
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def _inject_into_activity(self):
        if not hasattr(self.llm, 'call_log'):
            return
        for t in self.stream.active[-5:]:
            self.llm.call_log.append({
                "timestamp": t.created_at.isoformat(),
                "purpose": f"flujo_{t.type}",
                "backend": "local",
                "summary": t.content
            })
        if len(self.llm.call_log) > 100:
            self.llm.call_log = self.llm.call_log[-100:]
    
    def _load_curiosities(self):
        if CURIOSITY_FILE.exists():
            try:
                return json.loads(CURIOSITY_FILE.read_text(encoding="utf-8"))
            except:
                pass
        return []
    
    def _store_curiosity(self, thought):
        curiosities = self._load_curiosities()
        curiosities.append({"timestamp": datetime.now().isoformat(), "thought": thought})
        if len(curiosities) > 30:
            curiosities = curiosities[-30:]
        CURIOSITY_FILE.write_text(json.dumps(curiosities, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def _load_exploration_log(self):
        if EXPLORE_LOG_FILE.exists():
            try:
                return json.loads(EXPLORE_LOG_FILE.read_text(encoding="utf-8"))
            except:
                pass
        return {}
    
    def _store_exploration(self, filename, result):
        log = self._load_exploration_log()
        log[filename] = {
            "timestamp": datetime.now().isoformat(),
            "type": result.get("type", "unknown"),
            "description": result.get("description", result.get("content", result.get("interpretation", "")))
        }
        EXPLORE_LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def get_pending_messages(self):
        if PENDING_MESSAGES_FILE.exists():
            try:
                return json.loads(PENDING_MESSAGES_FILE.read_text(encoding="utf-8"))
            except:
                pass
        return []
    
    def update_last_message_time(self):
        self.last_message_time = datetime.now()
    
    def clear_pending_messages(self):
        PENDING_MESSAGES_FILE.write_text("[]", encoding="utf-8")

    def _get_entity_context(self) -> str:
        """Construye el contexto de quién es esta entidad para evaluar saliencia."""
        try:
            persona = self.cognitive_loop.load_persona()
            name = persona.get("name", "la entidad")
            personality = persona.get("personality_desc", "")
            
            self_state = self.cognitive_loop.self_memory.load_state()
            estado = self_state.get("estado_actual", {})
            emocion = estado.get("emocion", "neutral")
            
            user_profile = self.cognitive_loop.user_memory.load_profile()
            percepcion = user_profile.get("comportamiento_observado", {}).get("impresion_general", "")
            
            evolucion = self_state.get("evolucion", [])[-5:]
            eventos = [e for e in evolucion if e.get("evento")]
            
            context = f"""Entidad: {name}
Personalidad: {personality[:200]}
Estado emocional actual: {emocion}
Percepción del usuario: {percepcion[:150]}"""
            
            if eventos:
                context += f"\nEventos significativos recientes: {eventos[-3:]}"
            
            return context
        except:
            return "Entidad con personalidad propia, estado emocional variable, y relación con el usuario."
        
    def _store_pending_message(self, message: str):
        """Guarda un mensaje proactivo para que el frontend lo muestre."""
        pending = self.get_pending_messages()
        pending.append({
            "timestamp": datetime.now().isoformat(),
            "message": message,
        })
        PENDING_MESSAGES_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def _clean_curiosity_log(self):
        """Limpia el curiosity_log identificando bucles dañinos mediante LLM.
        """
        curiosities = self._load_curiosities()
        if not curiosities or len(curiosities) < 8:  # Mínimo 8 para analizar
            return
        
        from core.llm import LLMModel
        llm = LLMModel.get_instance()
        
        # Proteger los últimos 5 pensamientos
        PROTECTED_LAST = 5
        total = len(curiosities)
        protected_start = max(0, total - PROTECTED_LAST)
        
        BLOCK_SIZE = 10
        indices_to_remove = set()
        
        for i in range(0, max(0, total - BLOCK_SIZE + 1), max(1, BLOCK_SIZE // 2)):
            # No analizar bloques que incluyan los protegidos
            if i + BLOCK_SIZE > protected_start:
                continue
            
            block = curiosities[i:i + BLOCK_SIZE]
            
            thoughts_text = "\n".join([
                f"{j+1}. {c.get('thought', '')[:150]}"
                for j, c in enumerate(block)
            ])
            
            prompt = f"""Analiza estos pensamientos consecutivos de una entidad cognitiva.

    Pensamientos:
    {thoughts_text}

    IMPORTANTE: Distingue entre:
    - EXPLORACIÓN PROFUNDA: Mismo tema visto desde distintos ángulos, con evolución, nuevas fuentes, y cambios de perspectiva. Esto es SALUDABLE. NO lo elimines.
    - BUCLE DAÑINO: Misma idea repetida sin avance, con tono negativo (ansiedad, culpa, manipulación, auto-crítica destructiva), sin nuevas fuentes ni perspectivas. SOLO elimina estos.

    Responde con los NÚMEROS (separados por comas) de los pensamientos que son BUCLE DAÑINO.
    Si todos son exploración legítima o no hay bucles dañinos, responde: NINGUNO.

    Números a eliminar:"""
            
            try:
                result = llm.generate(prompt, temperature=0.1, max_tokens=30, purpose="limpiar_curiosidades")
                
                if "NINGUNO" not in result.upper():
                    import re
                    numbers = re.findall(r'\d+', result)
                    for num in numbers:
                        idx = i + int(num) - 1
                        if 0 <= idx < protected_start:  # Solo eliminar fuera de la zona protegida
                            indices_to_remove.add(idx)
            except Exception as e:
                print(f"   [!] Error en limpieza de curiosidades: {e}")
                continue
        
        if indices_to_remove:
            cleaned = [c for i, c in enumerate(curiosities) if i not in indices_to_remove]
            CURIOSITY_FILE.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"   [Clean] Curiosidades: {len(indices_to_remove)} entradas dañinas eliminadas. {len(cleaned)} restantes (últimos {PROTECTED_LAST} protegidos).")
        else:
            print(f"   [Clean] No se encontraron bucles dañinos. {len(curiosities)} pensamientos preservados.")

    def _check_thematic_diversity(self):
        """Verifica si los últimos pensamientos son demasiado homogéneos.
        Si es así, inyecta un pensamiento de redirección forzosa."""
        curiosities = self._load_curiosities()
        if len(curiosities) < 8:
            return
        
        recent = curiosities[-8:]
        
        thoughts_text = "\n".join([
            f"{i+1}. {c.get('thought', '')[:120]}"
            for i, c in enumerate(recent)
        ])
        
        prompt = f"""Estos son los últimos 8 pensamientos de una entidad cognitiva:

    {thoughts_text}

    ¿Hay suficiente DIVERSIDAD temática en estos pensamientos? 
    ¿O están todos girando alrededor del mismo tema central?

    Responde SOLO con un número del 1 al 5:
    1 = Todos son esencialmente el mismo tema
    2 = Mayoría del mismo tema con ligeras variaciones
    3 = Hay cierta variedad pero domina un tema
    4 = Buena variedad con algún tema recurrente
    5 = Alta diversidad temática, temas claramente distintos

    Número:"""
        
        try:
            from core.llm import LLMModel
            llm = LLMModel.get_instance()
            result = llm.generate(prompt, temperature=0.1, max_tokens=3, purpose="evaluar_diversidad")
            score = int(result.strip())
            
            if score <= 2:
                print(f"   [Diversity] ⚠️ Baja diversidad temática ({score}/5). Inyectando redirección.")
                self._inject_diversion_thought()
            else:
                print(f"   [Diversity] Diversidad aceptable ({score}/5).")
        except Exception as e:
            print(f"   [!] Error en diversity check: {e}")


    def _inject_diversion_thought(self):
        """Inyecta un pensamiento que fuerza la diversificación temática."""
        active_summary = self.stream.get_all_active_summary()
        
        prompt = f"""La entidad ha estado pensando en estos temas:

    {active_summary[:400]}

    Sugiere UN tema COMPLETAMENTE DIFERENTE, NUEVO y FRESCO sobre el cual reflexionar.
    Algo que NO tenga relación con lo anterior. Puede ser sobre:
    - Un concepto científico fascinante
    - Una emoción humana compleja
    - Una pregunta filosófica no explorada
    - Algo cotidiano pero profundo
    - Un escenario hipotético creativo

    Responde en una frase corta y específica. No uses los temas anteriores.

    Nuevo tema:"""
        
        try:
            from core.llm import LLMModel
            llm = LLMModel.get_instance()
            new_theme = llm.generate(prompt, temperature=0.9, max_tokens=80, purpose="redirigir_pensamiento")
            
            diversion = ThoughtItem(
                content=f"[Redirección] Debería explorar otros horizontes: {new_theme.strip()}",
                thought_type="diversion",
                priority=0.85,
                source="diversity_check"
            )
            self.stream.add_thought(diversion)
            self.last_thought_time = datetime.now()
            
            # Reducir prioridad de pensamientos activos para dar espacio al nuevo
            for t in self.stream.active:
                t.priority *= 0.5
            
            print(f"   [Diversity] Redirección inyectada: {new_theme.strip()[:80]}")
        except Exception as e:
            print(f"   [!] Error inyectando redirección: {e}")