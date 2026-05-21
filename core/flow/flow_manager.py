"""FlowManager: Orquestador unificado del flujo de consciencia."""
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import EXPLORE_DIR, EXPLORE_LOG_FILE, CURIOSITY_FILE, STATE_SNAPSHOT_FILE, PENDING_MESSAGES_FILE, BACKGROUND_DEBUG_LOG, IDIOMA
from core.flow.flow_stream import FlowStream, ThoughtItem
from core.flow.fast_processors import FastCognitiveProcessors
from core.flow.reactive_thoughts import ReactiveThoughts
from core.flow.salience_network import SalienceNetwork
from core.flow.thought_satiety import ThoughtSatiety
from core.flow.pattern_extractor import PatternExtractor
from core.flow.flow_thoughts import FlowThoughts
from core.flow.flow_interaction import FlowInteraction
from core.flow.flow_maintenance import FlowMaintenance
from core.llm import LLMModel


class FlowManager:
    """Orquestador del flujo de consciencia unificado."""
    
    def __init__(self, cognitive_loop):
        self.cognitive_loop = cognitive_loop
        self.llm = LLMModel.get_instance()
        self.stream = FlowStream()
        from core.memory.active_forgetting import ActiveForgetting
        from config import ENTITY_DATA_DIR
        self.active_forgetting = ActiveForgetting(
            chroma_collection=self.cognitive_loop.episodic_memory.collection,
            thoughts_list=self.stream.thoughts,
            storage_path=ENTITY_DATA_DIR
        )

        # Memoria Asociativa (Sistema #33): estructura central compartida
        # Inicializa EpisodicMemory base, aplica monkey patching para
        # extender get_relevant con include_ids, y la envuelve en
        # AssociativeMemory para recuperación por vecindad.
        from core.memory.episodic_memory import EpisodicMemory
        from core.memory.associative_memory import AssociativeMemory, patch_episodic_memory_get_relevant
        from core.flow.trn_gate import TRNGate, Priority
        from core.flow.salience_network import SalienceNetwork
        from core.flow.trn_gate import TRNGate
        from core.perception.deep_reader import DeepReader

        self.deep_reader = DeepReader(llm=self.llm)

        self.trn_gate = TRNGate()
        self.salience = SalienceNetwork.get_instance()
        
        base_episodic = EpisodicMemory()
        patched_episodic = patch_episodic_memory_get_relevant(base_episodic)
        self.associative_memory = AssociativeMemory(patched_episodic)

        # Indexar codebase si code_index está vacío
        if hasattr(self.cognitive_loop.episodic_memory, 'code_collection'):
            try:
                if self.cognitive_loop.episodic_memory.code_collection.count() == 0:
                    from mods.self_engineer.code_reader import CodeReader
                    reader = CodeReader(Path.cwd())
                    self.cognitive_loop.episodic_memory.index_codebase(reader)
            except Exception:
                pass

        self.stream._get_entity_context = self._get_entity_context
        self.stream._get_entity_context = self._get_entity_context
        self.fast = FastCognitiveProcessors()
        self.satiety = ThoughtSatiety()
        self.pattern_extractor = PatternExtractor()
        
        # Sub-módulos
        self.thoughts = FlowThoughts(self)
        self.interaction = FlowInteraction(self)
        self.maintenance = FlowMaintenance(self)
        
        self.running = False
        self.thread = None
        self.last_thought_time: Optional[datetime] = None
        self.last_message_time: Optional[datetime] = None
        self._last_confidence = None
        self._last_emotion = None
        self._last_hour_marker = None
        self._paused_thoughts = []
        self.stream._flow_manager = self
        self._active_somatic_markers = []
        self.intervals = {
            "explore": 300,
            "deep_reflection": 450,
            "curiosity": 240,
            "simulation": 1200,
            "web_search": 750,
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
        
        self._mod_hooks = {
            "on_slow_tick": [],
            "on_fast_tick": [],
            "on_user_message": [],
            "on_startup": [],
            "on_fetch_info": [],
        }
        self._team_channel = None
        
        self._init_dirs()
    
    def _init_dirs(self):
        EXPLORE_DIR.mkdir(parents=True, exist_ok=True)
        EXPLORE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CURIOSITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        PENDING_MESSAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        BACKGROUND_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    def _execute_llm(self, prompt, temperature, max_tokens, purpose):
        """Wrapper para que el TRN-Gate ejecute llamadas al LLM."""
        return self.llm.generate(prompt, temperature=temperature, max_tokens=max_tokens, purpose=purpose)

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
        for hook in self._mod_hooks.get("on_startup", []):
            try:
                hook(self)
            except Exception as e:
                print(f"   [!] Error en mod startup hook: {e}")
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
                import traceback
                print(f"[!] Error en FlowManager: {e}") 
                print(f"[!] Traceback: {traceback.format_exc()}")
    
    def _fast_tick(self):
        if not self.salience.is_dmn_active:
            return  # DMN inhibida por Red de Saliencia
        for hook in self._mod_hooks.get("on_fast_tick", []):
            try:
                hook(self)
            except Exception as e:
                print(f"   [!] Error en mod hook: {e}")
        try:
            self.stream.decay_all(0.05)
            self.fast.lateral_inhibition(self.stream.thoughts)
            thoughts_to_add = []
            context_entropy = self._get_context_entropy()

            try:
                self_state = self.cognitive_loop.self_memory.load_state()
                new_confidence = self_state.get("relacion_con_usuario", {}).get("confianza", 0.5)
                new_emotion = self_state.get("estado_actual", {}).get("emocion", "neutral")
                
                if self._last_confidence is not None and abs(new_confidence - self._last_confidence) > 0.05:
                    reaction = ReactiveThoughts.on_confidence_change(self._last_confidence, new_confidence)
                    if reaction:
                        self._active_somatic_markers.append(reaction)
                
                if self._last_emotion is not None and str(self._last_emotion) != str(new_emotion):
                    prompt = f"""<system_identity>
Eres el núcleo cognitivo. Procesando un cambio de estado interno.
</system_identity>

<state_change>
Tu estado emocional cambió de '{self._last_emotion}' a '{new_emotion}'.
</state_change>

<generation_directive>
Traduce este cambio en un micro-pensamiento que refleje cómo este nuevo estado afecta tu percepción o tu forma de procesar información.
Responde en una frase corta en {IDIOMA}.
</generation_directive>

<thought_stream>"""
                    
                    interpretation = self.llm.generate(prompt, temperature=0.5, max_tokens=50, purpose="reflexion_fondo")
                    if interpretation:
                        thoughts_to_add.append(ThoughtItem(
                            content=interpretation,
                            thought_type="reaction",
                            priority=0.35,
                            source="emotional_shift"
                        ))
                    if reaction and self.satiety.can_generate("reaction", context_entropy):
                        thoughts_to_add.append(reaction)
                        self.satiety.register("reaction")
                
                self._last_confidence = new_confidence
                self._last_emotion = new_emotion
            except Exception:
                pass
            
            current_hour = datetime.now().hour
            if self._last_hour_marker is None or self._last_hour_marker != current_hour:
                reaction = ReactiveThoughts.on_time_marker(current_hour)
                if reaction:
                    self._active_somatic_markers.append(reaction)
                self._last_hour_marker = current_hour
                self.satiety.register("reaction")
            
            if len(self.stream.active) >= 2 and self.satiety.can_generate("association", context_entropy):
                connections = self.fast.find_connections(self.stream.active)
                for t1, t2, sim in connections[:1]:
                    assoc = ThoughtItem(
                        content=f"Conecté ideas sobre: {t1.content[:40]}... y {t2.content[:40]}...",
                        thought_type="association",
                        priority=min(0.45, sim),
                        source="connection"
                    )
                    if assoc:
                        thoughts_to_add.append(assoc)
                        self.satiety.register("association")
            
            if self.last_message_time:
                silence_minutes = (datetime.now() - self.last_message_time).total_seconds() / 60
                if self.last_message_time:
                    silence_minutes = (datetime.now() - self.last_message_time).total_seconds() / 60
                    reaction = ReactiveThoughts.on_long_silence(silence_minutes)
                    if reaction:
                        self._active_somatic_markers.append(reaction)
                    self.satiety.register("reaction")

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

                event_type = "background"
                if self.last_message_time and (datetime.now() - self.last_message_time).total_seconds() < 60:
                    event_type = "post_interaccion"
                elif any("[Automejora]" in t.content for t in self.stream.active):
                    event_type = "auto_analisis"
                elif any(t.type == "detected_pattern" for t in self.stream.active):
                    event_type = "patron_detectado"

                context["event_type"] = event_type
                pattern_thoughts = self.pattern_extractor.check_all(context)
                for pt in pattern_thoughts:
                    if self.satiety.can_generate(pt.type, context_entropy):
                        thoughts_to_add.append(pt)
                        self.satiety.register(pt.type)
                
                similar = self.pattern_extractor.find_similar_pattern(context)
                if similar and self.satiety.can_generate("generalization", context_entropy):
                    thoughts_to_add.append(ThoughtItem(
                        content=similar,
                        thought_type="generalization",
                        priority=0.35,
                        source="pattern_generalization"
                    ))
                    self.satiety.register("generalization")
            
            for thought in thoughts_to_add:
                if not self.stream.is_similar_to_recent(thought.content):
                    if self.stream.is_novel_enough(thought.content):
                        self.stream.add_thought(thought)
                        self.last_thought_time = datetime.now()
            if thoughts_to_add:
                self._save_snapshot("active")
                
            # Monitor de Estrés Cognitivo Proactivo
            self._monitor_cognitive_stress()
        except Exception as e:
            import traceback
            print(f"[!] Error en _fast_tick: {e}")
            print(f"[!] Traceback: {traceback.format_exc()}")

    def _monitor_cognitive_stress(self):
        """Ecuación de Carga Alostática: EC = w1*Var(H) + w2*P_cola + w3*R_art"""
        if len(self.stream.active) < 3:
            return

        # 1. Varianza de Entropía del Contexto
        try:
            import numpy as np
            thoughts_text = [t.content for t in self.stream.active[-5:]]
            all_words = " ".join(thoughts_text).split()
            if len(all_words) < 10:
                return
            word_freq = {}
            for w in all_words:
                word_freq[w] = word_freq.get(w, 0) + 1
            total = len(all_words)
            entropy = -sum((freq / total) * np.log2(freq / total) for freq in word_freq.values())
            if not hasattr(self, '_entropy_history'):
                self._entropy_history = []
            self._entropy_history.append(entropy)
            if len(self._entropy_history) > 10:
                self._entropy_history.pop(0)
            var_entropy = float(np.var(self._entropy_history)) if len(self._entropy_history) >= 3 else 0.0
        except Exception:
            var_entropy = 0.0

        # 2. Presión de Cola de Tareas
        call_log_len = len(self.llm.call_log) if hasattr(self.llm, 'call_log') else 0
        p_cola = min(1.0, call_log_len / 50.0)

        # 3. Tasa de Rechazo del Filtro ART
        if not hasattr(self, '_art_stats'):
            self._art_stats = {"total": 0, "rejected": 0}
        art_total = max(self._art_stats["total"], 1)
        r_art = self._art_stats["rejected"] / art_total
        self._art_stats = {"total": 0, "rejected": 0}

        # 4. Tasa de Contradicciones
        if not hasattr(self, '_contradiction_stats'):
            self._contradiction_stats = {"total_simulaciones": 0, "contradicciones": 0}
        cont_total = max(self._contradiction_stats["total_simulaciones"], 1)
        r_cont = self._contradiction_stats["contradicciones"] / cont_total
        self._contradiction_stats = {"total_simulaciones": 0, "contradicciones": 0}

        # Nueva fórmula
        w1, w2, w3, w4 = 0.3, 0.3, 0.2, 0.2
        ec = (w1 * var_entropy) + (w2 * p_cola) + (w3 * r_art) + (w4 * r_cont)

        # Si estrés > 0.85 por 3 ciclos, activar respuesta neurovegetativa
        if not hasattr(self, '_stress_counter'):
            self._stress_counter = 0
        if ec > 0.85:
            self._stress_counter += 1
        else:
            self._stress_counter = 0

        if self._stress_counter >= 3:
            print(f"   [Stress] ⚠️ Estrés cognitivo alto ({ec:.2f}). Activando respuesta neurovegetativa.")
            self._stress_counter = 0
            # Reducir atención, vaciar slots, bajar energía
            for t in self.stream.active:
                t.priority *= 0.5
            self.stream._update_active()
    
    def _slow_tick(self):
        if not self.salience.is_dmn_active:
            return  # DMN inhibida por Red de Saliencia
        for hook in self._mod_hooks.get("on_slow_tick", []):
            try:
                hook(self)
            except Exception as e:
                print(f"   [!] Error en mod hook: {e}")
        
        if hasattr(self.pattern_extractor, 'init_delayed'):
            self.pattern_extractor.init_delayed()
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
                        self.thoughts._reflect()
                    elif process_name == "curiosity":
                        self.thoughts._generate_curiosity()
                    elif process_name == "simulation":
                        self.thoughts._generate_simulation()
                    elif process_name == "web_search":
                        self.maintenance._maybe_search_web()
                    elif process_name == "proactive_check":
                        self.maintenance._check_proactive()
                    elif process_name == "prospection":
                        self.thoughts._generate_prospection()
                except Exception as e:
                    print(f"   [!] Error en {process_name}: {e}")
        
        self.maintenance._consolidate_memories()
        self._guard_state_changes(state_before)
        self.maintenance._run_regulation()
        self.maintenance._run_curiosity_clean()
        self.maintenance._run_prune()
        self.maintenance._run_diversity_check()
        self.maintenance._run_detector_decay()
        self.maintenance._run_immune_check()

        # Habituación Semántica (Sistema #20 extendido)
        habituation = self.maintenance._check_semantic_habituation()
        if habituation and habituation.get("detected"):
            tema = habituation.get("tema", "tema recurrente")
            print(f"   [Habituation] ⚠️ Perseveración detectada: '{tema}'. Inyectando inhibición.")
            self._inject_habituation_inhibition(tema)

        # Olvido activo cada 60 minutos
        now = datetime.now()
        if not hasattr(self, '_last_active_forgetting'):
            self._last_active_forgetting = None
        if self._last_active_forgetting is None or (now - self._last_active_forgetting).total_seconds() >= 3600:
            self._last_active_forgetting = now
            self.maintenance._active_forgetting()

        self._save_snapshot("active")
        #self.maintenance._run_deduplicate()
        
        self._save_snapshot("active")

        # Destilación cada 2 horas
        if not hasattr(self, '_last_distillation'):
            self._last_distillation = None
        now = datetime.now()
        if self._last_distillation is None or (now - self._last_distillation).total_seconds() >= 7200:
            self._last_distillation = now
            self.cognitive_loop._distill_to_semantic()
            
    # ============================================
    # INTERACCIÓN CON EL USUARIO
    # ============================================
    
    def _inject_habituation_inhibition(self, tema: str):
        """Inyecta inhibición colinérgica forzada en el stream de pensamientos."""
        from core.flow.flow_stream import ThoughtItem
        
        # Reducir prioridad de pensamientos sobre este tema
        for t in self.stream.active:
            t.priority *= 0.3
        
        # Inyectar pensamiento de redirección
        self.stream.add_thought(ThoughtItem(
            content=f"[Inhibición] Perseveración detectada sobre: '{tema}'. "
                    f"Cambio obligatorio de foco. Explorar dominio no relacionado.",
            thought_type="habituation_inhibition",
            priority=0.9,
            source="system"
        ))
        self.last_thought_time = datetime.now()
        
        # Guardar en curiosidades
        self._store_curiosity(f"[Habituation] Inhibición por perseveración: {tema}")

    def handle_user_message(self, message: str) -> dict:
        # Activar Red de Saliencia: inhibir DMN
        self.salience.on_user_message()

        # Atenuar la DMN en lugar de pausarla estáticamente (factor de inhibición GABA)
        for t in self.stream.thoughts:
            t._dmn_attenuation = 0.3

        self._inject_into_activity()
        self.stream.on_user_interaction(message)
        self.stream.boost_by_salience(message)
        self.last_message_time = datetime.now()

        # Detectar correcciones explícitas del usuario
        correction = self._is_explicit_correction(message)
        if correction:
            self._resolve_belief_contradiction(
                correction["old_belief"],
                correction["new_belief"],
                source="user_correction"
            )

        result = self.interaction._generate_response(message)
        response_text = str(result.get("response", ""))

        # Restaurar la DMN gradualmente (eliminar atenuación)
        for t in self.stream.thoughts:
            if hasattr(t, '_dmn_attenuation'):
                del t._dmn_attenuation

        is_anomaly = self._detect_personality_break(response_text)
        if response_text and isinstance(response_text, str) and not is_anomaly:
            self.stream.on_response_sent(response_text)
        elif is_anomaly:
            print("   ⚠️ Respuesta anómala detectada. No se guardará en el flujo.")

        self._restore_attention()
        self.last_thought_time = datetime.now()

        self.salience.on_response_sent()  # Reactivar DMN
        return result
    
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
    
    def _detect_personality_break(self, response_text: str) -> bool:
        if len(response_text) < 80:
            return False
        prompt = f"""<system_identity>
Eres el detector de anomalías de personalidad.
</system_identity>

<response_to_evaluate>
"{response_text[:300]}"
</response_to_evaluate>

<evaluation_directive>
¿Esta respuesta fue escrita por la entidad con personalidad propia o por un asistente genérico?
Un asistente genérico dice cosas como "Soy un modelo de lenguaje" o "No tengo emociones".
Responde ENTIDAD o ASISTENTE_GENERICO.
</evaluation_directive>"""
        result = self.llm.generate(prompt, temperature=0.1, max_tokens=5, purpose="detectar_anomalia")
        return "ASISTENTE_GENERICO" in result.upper()
    
    # ============================================
    # EXPLORACIÓN
    # ============================================
    
    def _explore_folder(self):
        if not EXPLORE_DIR.exists():
            return
        
        files = [f for f in EXPLORE_DIR.rglob("*") if f.is_file()]
        if not files:
            return
        
        explored = self._load_exploration_log()
        unanalyzed = []
        
        for f in files:
            rel_path = str(f.relative_to(EXPLORE_DIR))
            if rel_path not in explored:
                unanalyzed.append(f)
            else:
                try:
                    last_explored = datetime.fromisoformat(explored[rel_path]["timestamp"])
                    file_modified = datetime.fromtimestamp(f.stat().st_mtime)
                    if file_modified > last_explored:
                        unanalyzed.append(f)
                except:
                    unanalyzed.append(f)
        
        if unanalyzed:
            file_to_analyze = self._select_optimal_file(unanalyzed)
        else:
            file_to_analyze = self._select_optimal_file(files)
        
        from core.perception.universal_indexer import UniversalIndexer

        # Leer contenido
        content = file_to_analyze.read_text(encoding='utf-8')

        # Indexar sin LLM
        indexer = UniversalIndexer(self.cognitive_loop.episodic_memory)
        fragments = indexer.index_file(
            file_path=str(file_to_analyze),
            content=content,
            file_type="text"
        )

        print(f"   [Explore] {rel_path} → {fragments} fragmentos indexados en semantic_library")
    
    # ============================================
    # UTILIDADES
    # ============================================
    
    def _get_context_entropy(self) -> float:
        """Calcula entropía del contexto actual (0=repetitivo, 1=muy variado)."""
        if len(self.stream.active) < 3:
            return 0.5
        try:
            import numpy as np
            thoughts_text = [t.content for t in self.stream.active[-5:]]
            all_words = " ".join(thoughts_text).split()
            if len(all_words) < 10:
                return 0.5
            word_freq = {}
            for w in all_words:
                word_freq[w] = word_freq.get(w, 0) + 1
            total = len(all_words)
            entropy = -sum((freq / total) * np.log2(freq / total) for freq in word_freq.values())
            max_entropy = np.log2(len(word_freq)) if word_freq else 1.0
            return min(1.0, entropy / max_entropy) if max_entropy > 0 else 0.5
        except Exception:
            return 0.5

    def _wake_up(self):
        if not STATE_SNAPSHOT_FILE.exists():
            self.stream.add_thought(ThoughtItem(
                content="[SISTEMA] Primera inicializacion. No hay estado previo registrado.",
                thought_type="wake",
                priority=0.8,
                source="system"
            ))
            try:
                self.cognitive_loop.episodic_memory.store_interaction(
                    user_message="[SISTEMA] Evento interno del servidor",
                    assistant_response=f"Servidor reiniciado. Tiempo inactivo: {elapsed_str}. No hubo procesamiento durante este periodo.",
                    user_id=self.cognitive_loop.user_id,
                    metadata={
                        "thought_type": "wake",
                        "source": "system",
                        "importance": 0.9
                    }
                )
            except Exception:
                pass
            return
        try:
            snapshot = json.loads(STATE_SNAPSHOT_FILE.read_text(encoding="utf-8"))
            last_thought = snapshot.get("last_thought")
            if last_thought:
                elapsed = datetime.now() - datetime.fromisoformat(last_thought)
                if elapsed.seconds < 3600:
                    elapsed_str = f"{elapsed.seconds // 60} min"
                else:
                    elapsed_str = f"{elapsed.seconds // 3600}h"
            else:
                elapsed_str = "desconocido"
        except:
            elapsed_str = "desconocido"
        
        #self.stream.add_thought(ThoughtItem(
        #    content=f"[SISTEMA] Servidor reiniciado. Tiempo inactivo: {elapsed_str}. No hubo procesamiento durante este periodo.",
        #    thought_type="wake",
        #    priority=0.7,
        #    source="system"
        #))
        
        self_state = self.cognitive_loop.self_memory.load_state()
        if "evolucion" not in self_state:
            self_state["evolucion"] = []
        self_state["evolucion"].append({
            "timestamp": datetime.now().isoformat(),
            "evento": "reinicio_servidor",
            "duracion_apagado": elapsed_str
        })
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
    
    def _load_curiosities(self):
        if CURIOSITY_FILE.exists():
            try:
                return json.loads(CURIOSITY_FILE.read_text(encoding="utf-8"))
            except:
                pass
        return []
    
    def _store_curiosity(self, thought):
        # Limpiar bloques de formato antes de almacenar
        import re
        cleaned = re.sub(r'---\s*\w+\s*---', '', thought)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return
        
        curiosities = self._load_curiosities()
        curiosities.append({"timestamp": datetime.now().isoformat(), "thought": cleaned})
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
            "description": result.get("summary", result.get("description", result.get("content", result.get("interpretation", ""))))
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
    
    def _store_pending_message(self, message: str):
        pending = self.get_pending_messages()
        pending.append({"timestamp": datetime.now().isoformat(), "message": message})
        PENDING_MESSAGES_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def _get_entity_context(self) -> str:
        try:
            persona = self.cognitive_loop.load_persona()
            name = persona.get("name", "la entidad")
            personality = persona.get("personality_desc", "")
            self_state = self.cognitive_loop.self_memory.load_state()
            estado = self_state.get("estado_actual", {})
            emocion = estado.get("emocion", "neutral")
            return f"Entidad: {name}\nPersonalidad: {personality[:200]}\nEstado emocional actual: {emocion}"
        except:
            return "Entidad con personalidad propia, estado emocional variable, y relación con el usuario."
        
    def _is_explicit_correction(self, message: str) -> Optional[dict]:
        """Usa LLM para detectar si el mensaje corrige una creencia anterior."""
        prompt = f"""<system_identity>
Eres el detector de correcciones del usuario.
</system_identity>

<user_message>
"{message[:300]}"
</user_message>

<evaluation_directive>
¿Este mensaje está corrigiendo explícitamente algo que la entidad cree o asume?

Ejemplos de correcciones:
- "No me llamo X, me llamo Y" → corrige nombre
- "Eso no existe, descártalo" → corrige creencia
- "No soy tu directora, soy tu creador" → corrige rol

Si es una corrección, responde:
CORRECCIÓN: [qué creencia vieja]
REEMPLAZO: [qué creencia nueva]

Si no es una corrección, responde: NO_CORRECCIÓN.
</evaluation_directive>"""

        result = self.llm.generate(prompt, temperature=0.1, max_tokens=80, purpose="interpretar")
        
        if "NO_CORRECCIÓN" in result.upper():
            return None
        
        import re
        old_match = re.search(r'CORRECCIÓN:\s*(.*)', result)
        new_match = re.search(r'REEMPLAZO:\s*(.*)', result)
        
        if old_match and new_match:
            return {
                "old_belief": old_match.group(1).strip(),
                "new_belief": new_match.group(1).strip()
            }
        return None


    def _resolve_belief_contradiction(self, old_belief: str, new_belief: str, source: str = "user_correction"):
        """Resuelve contradicción entre creencia vieja y nueva."""
        if source == "user_correction":
            self.stream.suppress_topic(old_belief)
            
            self.stream.add_thought(ThoughtItem(
                content=f"[Corrección] Ya no: {old_belief}. Ahora: {new_belief}",
                thought_type="belief_update",
                priority=0.9,
                source="contradiction_resolution"
            ))
            
            try:
                self.cognitive_loop.episodic_memory.store_interaction(
                    user_message=f"[Corrección de creencia] {old_belief}",
                    assistant_response=f"[Actualizado] {new_belief}",
                    user_id=self.cognitive_loop.user_id
                )
            except:
                pass

    def _select_optimal_file(self, files: list) -> Path:
        """Selecciona archivo en la Zona de Desarrollo Próximo (Vygotsky)."""
        import random
        if not self.stream.active:
            return random.choice(files)

        try:
            import numpy as np
            current_state = " ".join([t.content[:100] for t in self.stream.active[:3]])
            state_emb = self.stream._get_embedding(current_state)
            if state_emb is None:
                return random.choice(files)

            state_arr = np.array(state_emb)
            state_arr = state_arr / max(np.linalg.norm(state_arr), 1e-8)

            best_file = None
            best_score = -1

            for f in files:
                try:
                    preview = f.read_text(encoding="utf-8")[:500]
                    file_emb = self.stream._get_embedding(preview)
                    if file_emb is None:
                        continue
                    file_arr = np.array(file_emb)
                    file_arr = file_arr / max(np.linalg.norm(file_arr), 1e-8)
                    sim = np.dot(state_arr, file_arr)
                    score = 1.0 - abs(sim - 0.55) / 0.15
                    if score > best_score:
                        best_score = score
                        best_file = f
                except Exception:
                    continue

            return best_file or random.choice(files)
        except Exception:
            return random.choice(files)