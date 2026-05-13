
# Architecture: The Sibelium Cognitive System

## Core Principle

Sibelium is built on a simple but powerful idea: consciousness is not a singular process but a continuous stream of competing, decaying, and reinforcing thoughts. By modeling this computationally, emergent behaviors appear — preferences, introspection, emotional regulation, and metacognition.

---

## Dual-Cycle Architecture

The system operates on two temporal cycles:

### Fast Cycle (every 3 seconds)
- Decay all active thoughts (latent inhibition)
- React to state changes (emotion, confidence)
- Generate associative connections between thoughts
- Evaluate pattern detectors (every 60 seconds)
- React to long silences

### Slow Cycle (every 15 seconds)
- Deep reflection using LLM
- Spontaneous curiosity generation
- Mental simulations (hypothetical scenarios)
- File exploration from `nexus_world/`
- Web searches triggered by curiosity
- Emotional regulation (every 10 minutes)
- Memory consolidation (every 60 minutes of idle time)

---

## The FlowStream

The `FlowStream` is the river of consciousness. It contains:

- **ThoughtItems**: Individual thoughts with ID, priority (0.0-1.0), decay rate, and metadata
- **Active thoughts**: Those with priority > 0.08, sorted by priority (max 15)
- **Current topic**: The highest priority thought

Each thought undergoes:
1. **Decay**: Priority decreases over time
2. **Reinforcement**: Relevance boosts priority
3. **Inhibition**: Similar recent thoughts are suppressed

---

## Memory Systems

### Episodic Memory (ChromaDB)
- Stores all user-entity interactions
- Semantic search for relevant past conversations
- Used to provide autobiographical continuity

### Self Memory (JSON)
- Emotional state (emotion, intensity, energy, disposition)
- User relationship (confidence, interest)
- Evolution log (emotional changes over time)
- Personal objectives

### User Memory (JSON)
- Personal data (name, age, location, occupation)
- Behavioral perceptions (style, attitude, general impression)
- Relationship metadata

### Scaffolding System
- Tracks exploration patterns
- Determines when the entity needs more or less critical thinking support
- Measures autonomy ratio