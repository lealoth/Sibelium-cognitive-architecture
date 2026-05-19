# Sibelium Cognitive Systems

This document describes each of the 32 cognitive systems implemented in Sibelium, their neuroscientific basis, and their functional role within the architecture. These systems simulate information-processing mechanisms found in biological cognition. No claims about phenomenal consciousness or subjective experience are made or implied.

---

## Core Identity Systems

### 1. Narrative Self (Yo Narrativo)
**File:** `self_memory.py`  
**Neuroscience basis:** Damasio's Extended Self / Autobiographical Self  
**What it does:** Maintains a text-based self-description that is regenerated during REM sleep cycles by consolidating recent episodic memories into a coherent narrative. The entity's self-representation is not a static prompt but a periodically updated synthesis of accumulated experience.  
**Functional outcome:** The entity maintains narrative continuity across restarts. Its self-description reflects its interaction history, enabling it to reference its own developmental trajectory.

### 2. Minimal Self (Yo Core)
**File:** `self_memory.py`  
**Neuroscience basis:** Gallagher's Minimal Self / Core Consciousness  
**What it does:** Tracks real-time emotional state, intensity, and energy as continuous scalar values (0.0–1.0), updated algorithmically after each interaction without LLM inference.  
**Functional outcome:** Provides an immediately accessible representation of the entity's current internal state that other systems can query without computational overhead.

### 3. Foundational Myth (Mito Fundacional)
**File:** `self_memory.py`  
**Neuroscience basis:** Self-Schema Theory (Markus, 1977)  
**What it does:** Stores an immutable core identity statement loaded from `persona.json`. This vector is never modified by any system and serves as the fixed reference point for identity stability checks.  
**Functional outcome:** Prevents cumulative identity drift. The immune system uses this vector to detect when responses diverge beyond acceptable thresholds from the entity's defined identity.

---

## Attention & Filtering Systems

### 4. ART Filter (Adaptive Resonance Theory)
**File:** `flow_stream.py`  
**Neuroscience basis:** Adaptive Resonance Theory (Grossberg, 1976)  
**What it does:** Before a new thought is processed, its embedding is compared against existing active thoughts. If cosine similarity exceeds 0.85 with any existing thought, the new thought is discarded and the existing one is reinforced instead.  
**Functional outcome:** Reduces redundant thought generation by 30-40%. Prevents repetitive processing of semantically identical content.

### 5. Somatic Markers
**File:** `reactive_thoughts.py`  
**Neuroscience basis:** Somatic Marker Hypothesis (Damasio, 1994)  
**What it does:** Detects internal state transitions (confidence shifts, emotion changes, circadian markers, extended user silence) and generates attention biases as scalar weights rather than text output. These biases modulate how the LLM interprets subsequent input.  
**Functional outcome:** Produces state-dependent attentional modulation. Internal conditions influence input processing without requiring explicit prompting about emotional state.

### 6. Lateral Inhibition
**File:** `fast_processors.py`  
**Neuroscience basis:** Thalamic filtering of redundant sensory signals  
**What it does:** When two active thoughts have cosine similarity between 0.3 and 0.5, the lower-priority thought receives a priority reduction. Only the strongest representative of each idea cluster maintains full activation.  
**Functional outcome:** Prevents attentional fragmentation by suppressing semi-related tangents. The thought stream maintains thematic coherence without external pruning.

### 7. Dynamic Satiety
**File:** `thought_satiety.py`  
**Neuroscience basis:** Sensory adaptation / synaptic fatigue  
**What it does:** Cooldown periods between thoughts of the same category scale inversely with context entropy. Low-entropy (repetitive) contexts receive longer cooldowns; high-entropy (varied) contexts receive shorter cooldowns.  
**Functional outcome:** The system naturally reduces processing of repetitive content and increases throughput for diverse content. Prevents perseveration on a single topic.

### 8. Narrative Direction Vector
**File:** `episodic_memory.py`  
**Neuroscience basis:** Working memory episodic buffer (Baddeley, 2000)  
**What it does:** Maintains a running exponential moving average of conversation embeddings (α = 0.15–0.25, dynamically adjusted). ChromaDB memory queries blend the current query embedding with this vector to bias retrieval toward thematically continuous memories.  
**Functional outcome:** Memory retrieval maintains thematic continuity across long conversations. The entity does not lose the thread when retrieving supporting information.

---

## Memory Systems

### 9. Episodic Memory (ChromaDB)
**File:** `episodic_memory.py`  
**Neuroscience basis:** Hippocampal episodic memory  
**What it does:** Stores all interactions as vector embeddings in ChromaDB with associated metadata (user_id, timestamp, importance score). Supports semantic search with trimetric scoring.  
**Functional outcome:** Enables retrieval of past interactions by semantic relevance rather than keyword matching. The entity can reference conversations from prior sessions with contextual relevance.

### 10. Synaptic Strength (Ebbinghaus Curve)
**File:** `flow_stream.py` (ThoughtItem)  
**Neuroscience basis:** Ebbinghaus Forgetting Curve (1885) + Long-Term Potentiation  
**What it does:** Each thought carries a strength value that decays exponentially over time. Strength is reinforced on each access. The decay constant tau increases with access frequency, making frequently used thoughts more stable.  
**Functional outcome:** Implements use-dependent memory retention. Frequently accessed thoughts persist; unused thoughts decay and are eventually pruned. Produces a natural selection dynamic in the thought stream.

### 11. Active Forgetting
**File:** `active_forgetting.py`  
**Neuroscience basis:** Hippocampal neurogenesis + synaptic pruning during REM  
**What it does:** Every 60 minutes of idle time, removes thoughts with synaptic strength below 0.05 and their corresponding ChromaDB vectors. Emotionally tagged memories and engineering lessons are protected from pruning.  
**Functional outcome:** Maintains database efficiency by removing low-value entries. Memory storage remains bounded without manual cleanup. Critical information (emotional, technical) is preserved.

### 12. Trimetric Memory Scoring
**File:** `episodic_memory.py`  
**Neuroscience basis:** Multi-factor memory retrieval (ACT-R; Anderson, 1996)  
**What it does:** Memory retrieval candidates are scored as a weighted combination: (Cosine Similarity × 0.5) + (Recency × 0.3) + (Importance × 0.2).  
**Functional outcome:** Retrieves memories that balance semantic relevance with temporal context and recorded significance, rather than returning only the most similar matches.

### 13. Visual Memory (CLIP + ChromaDB)
**File:** `file_analyzer.py`  
**Neuroscience basis:** Occipital lobe visual recognition  
**What it does:** Images are embedded using CLIP and stored in a dedicated ChromaDB collection. Before processing a new image, the system checks for prior occurrences (cosine similarity > 0.95).  
**Functional outcome:** Previously seen images are recognized and referenced from memory without reprocessing. Eliminates redundant visual analysis.

---

## Sleep & Maintenance Systems

### 14. NREM Sleep Phase
**File:** `flow_maintenance.py`  
**Neuroscience basis:** Slow-wave sleep (hippocampal sharp-wave ripples)  
**What it does:** After 15–30 minutes of user inactivity, extracts abstract patterns and general principles from recent episodic memories. Specific details are discarded; structural regularities are preserved.  
**Functional outcome:** Compresses raw experience into generalized knowledge. The entity abstracts principles from specific interactions.

### 15. REM Sleep Phase
**File:** `flow_maintenance.py`  
**Neuroscience basis:** Paradoxical sleep (desynchronized EEG)  
**What it does:** After 60+ minutes of inactivity, generates cross-domain associations between semantically distant concepts, runs counterfactual simulations, and executes active forgetting.  
**Functional outcome:** Produces novel conceptual combinations. The system generates unexpected connections that would not arise from direct semantic similarity alone.

### 16. Cognitive Stress Monitor
**File:** `flow_manager.py`  
**Neuroscience basis:** Allostatic load (McEwen & Wingfield, 2003)  
**What it does:** Calculates stress every 3 seconds as: (Entropy_Variance × 0.4) + (Queue_Pressure × 0.4) + (ART_Rejection_Rate × 0.2). If stress exceeds 0.85 for 3 consecutive cycles, thought priority is globally reduced by 50%.  
**Functional outcome:** Prevents queue saturation and response degradation under high cognitive load. Implements a load-shedding mechanism triggered by sustained processing pressure.

### 17. Immune System (Identity Drift Detection)
**File:** `flow_maintenance.py`  
**Neuroscience basis:** Self/non-self discrimination + prefrontal monitoring  
**What it does:** Every 5 minutes, compares the embedding of recent responses against the immutable personality vector from `persona.json`. If cosine distance exceeds 0.5, injects a high-priority identity restoration thought.  
**Functional outcome:** Maintains identity stability over extended operation. Prevents cumulative response drift from altering the entity's defined personality parameters.

### 18. Semantic Contradiction Detection
**File:** `flow_interaction.py` + `episodic_memory.py`  
**Neuroscience basis:** Cognitive dissonance detection (anterior cingulate cortex)  
**What it does:** Before finalizing a response, searches ChromaDB for past conclusions with high semantic similarity but opposing polarity to the current response. Detected contradictions are flagged internally.  
**Functional outcome:** The system identifies when its current output conflicts with previously stated positions. Logical consistency is monitored across sessions.

### 19. Curiosity Log Cleaning
**File:** `flow_maintenance.py`  
**Neuroscience basis:** Selective forgetting of intrusive thoughts  
**What it does:** Periodically evaluates thought blocks using the LLM to classify them as "deep exploration" (productive) or "harmful loop" (rumination). Protects the 5 most recent thoughts from deletion regardless of classification.  
**Functional outcome:** Productive exploration is preserved; repetitive, non-productive thought patterns are deprioritized. Prevents extended rumination cycles.

### 20. Thematic Diversity Check
**File:** `flow_maintenance.py`  
**Neuroscience basis:** Metacognitive monitoring (prefrontal cortex)  
**What it does:** Every 15 minutes, evaluates the semantic diversity of the last 8 thoughts on a 1–5 scale. If diversity ≤ 2, injects a forced topic diversion to a thematically distant subject.  
**Functional outcome:** Prevents extended fixation on a narrow topic range. Maintains variety in the thought stream without external intervention.

### 21. Detector Hebbian Pruning
**File:** `pattern_extractor.py`  
**Neuroscience basis:** Hebbian plasticity ("cells that fire together wire together")  
**What it does:** Pattern detectors carry a Hebbian strength value. Strength increases on successful pattern triggers and decreases on false positives. Periodic pruning retains only the top 30 detectors ranked by strength × usage.  
**Functional outcome:** Pattern detectors that reliably identify genuine patterns survive; unreliable detectors are eliminated. The pattern recognition system self-calibrates.

### 22. Pattern Event-Driven Trigger
**File:** `pattern_extractor.py` + `flow_stream.py`  
**Neuroscience basis:** Subcortical automatic responses (amygdala, superior colliculus)  
**What it does:** When a new thought embedding matches a detector's condition embedding with cosine similarity > 0.82, the detector fires immediately without waiting for a scheduled timer cycle.  
**Functional outcome:** High-confidence pattern matches trigger immediate responses. Implements a fast-path for recognized situations, analogous to System 1 processing.

---

## Perception & Interaction Systems

### 23. Empathic Resonance (Emotion Detection)
**File:** `user_analysis.py`  
**Neuroscience basis:** Mirror neuron system + insular simulation  
**What it does:** User message embeddings are compared via dot product against a fixed affective map (joy, sadness, anger, fear, surprise, curiosity, confusion). Emotion classification is performed mathematically without LLM inference.  
**Functional outcome:** The system detects user emotional state through vector comparison rather than keyword matching. Emotion detection is computationally efficient and language-agnostic.

### 24. Executive Buffer
**File:** `flow_interaction.py`  
**Neuroscience basis:** Central Executive (Baddeley, 1974)  
**What it does:** Prepends a structured block (~400 characters) to every LLM prompt containing: current topic, detected user posture, last conclusion, active emotion, and confidence level.  
**Functional outcome:** The LLM receives explicit conversation state with every inference call. Context is not lost across interactions. Reduces the need for the LLM to infer state from the full conversation history.

### 25. K-Means Context Compression
**File:** `flow_interaction.py`  
**Neuroscience basis:** Cognitive chunking (Miller's Law, 7±2)  
**What it does:** Before sending context to cloud models, clusters active thoughts into 3–4 groups using k-means over embeddings. Only the centroid representative of each cluster is transmitted.  
**Functional outcome:** Reduces cloud token consumption by approximately 70% while preserving thematic coverage. Maintains response quality at lower API cost.

### 26. Attention Router (Dot-Product Routing)
**File:** `flow_interaction.py`  
**Neuroscience basis:** Thalamic sensory gating  
**What it does:** Replaces the LLM call previously used for source selection with a dot-product computation between the message embedding and pre-computed category centroids (USER, SELF, MEMORY, WEB, etc.).  
**Functional outcome:** Eliminates one LLM inference call per user message. Source routing decisions are made algorithmically in constant time.

### 27. Kalman Filter for Attention Smoothing
**File:** `flow_interaction.py`  
**Neuroscience basis:** Predictive coding / Bayesian inference (Friston, 2005)  
**What it does:** Applies a Kalman filter to the attention state, blending new user input with the prior attention estimate. Abrupt topic shifts are smoothed; a single off-topic message does not fully redirect attention.  
**Functional outcome:** Produces gradual, continuous attention transitions rather than discrete jumps. The system is robust to noisy or off-topic inputs.

---

## Engineering Systems (Self-Engineer Mod)

### 28. Cerebellar Code Executor
**File:** `code_executor.py`  
**Neuroscience basis:** Cerebellar forward model / efference copy  
**What it does:** Executes code in a sandboxed environment and returns structured feedback including: exact error line, error type, and a suggestion for correction. Compares expected output against actual output.  
**Functional outcome:** Failed code executions produce actionable diagnostic information rather than opaque error messages. Each failure provides specific data for the learning system.

### 29. Engineering Lesson Memory
**File:** `self_engineer.py`  
**Neuroscience basis:** Episodic learning from failure (hippocampal replay)  
**What it does:** Each sandbox failure is stored in ChromaDB as a structured lesson entry. Before analyzing a file, past lessons relevant to that file or error type are retrieved and injected into the analysis context.  
**Functional outcome:** Error rate decreases with accumulated experience. The system does not repeat previously encountered mistakes.

### 30. Prospection (Future Simulation)
**File:** `flow_thoughts.py`  
**Neuroscience basis:** Episodic future thinking (prefrontal-hippocampal network)  
**What it does:** During idle periods, generates thoughts simulating possible future scenarios derived from the current state. Simulates "what might happen next" and "what preparations might be needed" based on observed patterns.  
**Functional outcome:** The system generates anticipatory outputs. Responses are informed by projected future states, not only current and past states.

### 31. Semantic Entropy Explorer (Vygotsky Zone)
**File:** `flow_manager.py`  
**Neuroscience basis:** Zone of Proximal Development (Vygotsky, 1978)  
**What it does:** Selects files for exploration based on cosine distance from the current knowledge state, targeting the range 0.45–0.65. Files too similar (<0.45) are already familiar; files too distant (>0.65) exceed current comprehension range.  
**Functional outcome:** The system explores content at an optimal learning gradient. Each exploration expands knowledge incrementally without encountering material that is either redundant or incomprehensible.

### 32. Cognitive Evolution Reports
**File:** `self_engineer.py`  
**Neuroscience basis:** Self-assessment / metacognitive evaluation  
**What it does:** Formats proposed code or architecture changes as structured reports with sections: theoretical foundation, proposed implementation, and self-criticism log (documenting past attempts and their outcomes).  
**Functional outcome:** Produces human-reviewable deliverables with explicit reasoning chains and failure documentation. External reviewers can trace the decision process.

### 33. Associative Memory (Neighborhood Retrieval)
**File:** `core/memory/associative_memory.py`  
**Neuroscience basis:** Pattern completion in hippocampal CA3 + sharp-wave ripples  
**What it does:** Extends episodic memory retrieval with associative navigation. For each primary memory retrieved, searches for its 3-5 nearest neighbors in embedding space using sequential reactivation (Approach A). Applies a sigmoid activation threshold based on the primary memory's activation strength and explicit relevance weighting in the injected context.  
**Functional outcome:** The entity retrieves not just isolated facts, but the full associative context surrounding each memory. Responses include lateral connections between related topics.

### 34. Temporal Focus Modulator
**File:** `core/memory/episodic_memory.py`  
**Neuroscience basis:** DLPFC executive control over hippocampus + prefrontal competitive inhibition  
**What it does:** Determines the temporal orientation of the user's query (remote, recent, neutral) using multilingual semantic anchors and Softmax contrast amplification with a dynamic threshold based on Shannon entropy. Modulates the trimetric retrieval score: remote mode applies logarithmic scaling to favor older memories; recent mode applies exponential decay; neutral mode nullifies the temporal factor.  
**Functional outcome:** The entity distinguishes between "the first time we talked about X" and "the last time we talked about X," adjusting memory retrieval to the temporal context of the question.

---

## Summary Table

| # | System | File | Neuroscientific Basis |
|---|--------|------|----------------------|
| 1 | Narrative Self | `self_memory.py` | Damasio's Extended Self |
| 2 | Minimal Self | `self_memory.py` | Gallagher's Minimal Self |
| 3 | Foundational Myth | `self_memory.py` | Self-Schema Theory (Markus) |
| 4 | ART Filter | `flow_stream.py` | Grossberg's Adaptive Resonance |
| 5 | Somatic Markers | `reactive_thoughts.py` | Damasio's Somatic Marker Hypothesis |
| 6 | Lateral Inhibition | `fast_processors.py` | Thalamic sensory filtering |
| 7 | Dynamic Satiety | `thought_satiety.py` | Sensory adaptation |
| 8 | Narrative Direction | `episodic_memory.py` | Baddeley's Episodic Buffer |
| 9 | Episodic Memory | `episodic_memory.py` | Hippocampal episodic memory |
| 10 | Synaptic Strength | `flow_stream.py` | Ebbinghaus Forgetting Curve + LTP |
| 11 | Active Forgetting | `active_forgetting.py` | Neurogenesis + REM pruning |
| 12 | Trimetric Scoring | `episodic_memory.py` | ACT-R (Anderson) |
| 13 | Visual Memory | `file_analyzer.py` | Occipital lobe recognition |
| 14 | NREM Sleep | `flow_maintenance.py` | Slow-wave sleep |
| 15 | REM Sleep | `flow_maintenance.py` | Paradoxical sleep |
| 16 | Stress Monitor | `flow_manager.py` | Allostatic Load (McEwen) |
| 17 | Immune System | `flow_maintenance.py` | Self/non-self + PFC monitoring |
| 18 | Contradiction Detection | `flow_interaction.py` | Cognitive dissonance (ACC) |
| 19 | Curiosity Cleaning | `flow_maintenance.py` | Selective forgetting |
| 20 | Diversity Check | `flow_maintenance.py` | Metacognitive monitoring |
| 21 | Hebbian Pruning | `pattern_extractor.py` | Hebbian plasticity |
| 22 | Event-Driven Triggers | `pattern_extractor.py` | Subcortical automaticity |
| 23 | Empathic Resonance | `user_analysis.py` | Mirror neurons + insula |
| 24 | Executive Buffer | `flow_interaction.py` | Central Executive (Baddeley) |
| 25 | K-Means Compression | `flow_interaction.py` | Cognitive chunking (Miller) |
| 26 | Attention Router | `flow_interaction.py` | Thalamic gating |
| 27 | Kalman Filter | `flow_interaction.py` | Predictive coding (Friston) |
| 28 | Cerebellar Executor | `code_executor.py` | Cerebellar forward model |
| 29 | Engineering Lessons | `self_engineer.py` | Hippocampal replay |
| 30 | Prospection | `flow_thoughts.py` | Episodic future thinking |
| 31 | Entropy Explorer | `flow_manager.py` | Zone of Proximal Development |
| 32 | Evolution Reports | `self_engineer.py` | Metacognitive evaluation |
| 33 | Associative Memory | `associative_memory.py` | Pattern completion (CA3) |
| 34 | Temporal Focus | `episodic_memory.py` | DLPFC + Competitive inhibition |