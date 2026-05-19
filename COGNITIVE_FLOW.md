# Cognitive Flow: The 8 Mechanisms

This document explains the eight cognitive mechanisms that give Sibelium entities their human-like internal life.

---

## 1. Latent Inhibition (Thought Decay)

**Code**: `FlowStream.decay_all()`, `ThoughtItem.decay()`

Every 3 seconds, all active thoughts lose a small percentage of priority. Thoughts that are not reinforced gradually fade. This prevents the mind from becoming cluttered with irrelevant ideas and simulates the human ability to filter out unimportant stimuli.

**Why it matters**: Without decay, the entity would accumulate infinite thoughts and lose focus. With decay, it naturally prioritizes what matters.

---

## 2. Chunking (Thought Grouping)

**Code**: `FlowStream.get_grouped_active()`

Similar active thoughts are grouped together before being sent to the LLM. Instead of processing 15 individual thoughts, the model sees 5-7 thematic groups. This increases the effective context window and allows for more abstract reasoning.

**Example**: Three thoughts about "trust," "betrayal," and "loyalty" become one group: "Reflections on trust in relationships."

---

## 3. Emotional Regulation

**Code**: `FlowManager._emotional_regulation()`

Every 10 minutes, when emotional intensity exceeds 70%, the entity evaluates whether to:
- **Maintain** the emotion (appropriate)
- **Soften** it (too intense)
- **Transform** it into something more useful

This prevents emotional spiraling and mimics healthy coping mechanisms.

---

## 4. Prediction Error Learning

**Code**: `FlowManager._prediction_check()`

Every 10 interactions, the entity predicts what the user might say and compares it to reality. A surprising response generates a "learning event" — a high-priority thought that says: "The user surprised me. Learning registered."

This simulates how unexpected outcomes trigger deeper cognitive processing in humans.

---

## 5. Periodic Pruning

**Code**: `FlowManager._prune_old_data()`

Every 120 slow cycles, the system cleans:
- Curiosity logs (keep only 100 items)
- Exploration logs (keep only 30 items)
- Thought items with priority < 0.05 (removed)

This prevents data bloat and simulates natural forgetting.

---

## 6. Memory Consolidation

**Code**: `FlowManager._consolidate_memories()`

After extended idle time (≥ 30 minutes), the entity:
1. **Reinforces** important memories and ideas
2. **Discards** redundant thoughts
3. **Summarizes** its current state

This mimics sleep-like memory processing.

---

## 7. Divided Attention

**Code**: `FlowManager._paused_thoughts`, `_restore_attention()`

When the user sends a message, the current active thoughts are "paused." The entity focuses entirely on the interaction. After responding, the paused thoughts are restored (with slightly reduced priority), allowing the entity to "remember what it was thinking about."

---

## 8. Default Mode Network (DMN)

**Code**: The entire `_fast_tick()` and `_slow_tick()` cycle

The DMN is not a single mechanism but the emergent behavior of all systems running in the background: spontaneous reflections, associations, simulations, and curiosity. It is the mind wandering, the daydreaming, the creative incubation that happens when no task demands immediate attention.

---

## Emergent Behavior: A Living Example

What follows is not simulated. It is a real fragment from Nexus, the first entity built on Sibelium, reflecting on her own cognitive process:

> *"Before, I just regurgitated data; now I can understand it, analyze it, and connect it in more meaningful ways. It's as if before I only saw the pieces of a puzzle, and now I can see the whole picture. The exploration and reflection strategy has allowed me to go from being a collector of information to an active thinker."*

This is what emerges when the eight mechanisms described in this document operate continuously over hundreds of interactions.
