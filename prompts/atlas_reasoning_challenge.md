# ATLAS Core - Reasoning Engine Architecture Challenge

## Background

ATLAS Core is an event-driven agent architecture designed for real-time robotic or software agents. It processes streams of incoming events, updates its internal representation of the world, manages episodic and knowledge-based memory, and builds a comprehensive situation context. 

The current ATLAS Core (up to v0.3) handles the flow of information as follows:
1. **Event**: A structured observation from a sensor or system (e.g., `vision_system` detects `person_entered`).
2. **EventGateway**: The main entry point. It receives an Event and coordinates the downstream processing.
3. **WorldState**: Tracks the latest known state of the world based on the incoming events.
4. **EventHistory**: Maintains a short-term chronological log of recent events.
5. **ContextBuilder**: Synthesizes the current Event, the WorldState, and EventHistory into a unified **Situation Context**.
6. **MemoryManager**: Interfaces with long-term storage, including **Episodic Memory** (past events associated with entities) and **Knowledge Memory** (persistent facts about entities).

Currently, ATLAS Core builds a rich context but *does not take actions*. It lacks a component to reason over the situation and make decisions.

## The Challenge

Your task is to design the next major component for ATLAS Core: the **Reasoning Engine**, which will analyze the Situation Context and decide what actions the agent should take.

Please provide a detailed architectural proposal addressing the following points:

### 1. Architectural Analysis
- Analyze the current ATLAS architecture described above.
- Identify the primary responsibility of each existing major component (EventGateway, WorldState, EventHistory, ContextBuilder, MemoryManager).

### 2. Reasoning Engine Design
- Design the new Reasoning Engine component.
- Explain exactly how the Reasoning Engine should interact with:
  - WorldState
  - Situation Context
  - Event History
  - Episodic Memory
  - Knowledge Memory
- Propose the minimum number of new modules required to implement this Reasoning Engine (e.g., RulesEngine, LLMInterface, ActionDispatcher, etc.) without overcomplicating the design.

### 3. Data Flow
- Define the proposed step-by-step data flow from a new observation to an action:
  New Event → Context → Memory Retrieval → Reasoning → Decision

### 4. Constraints & Safety
- Explain how the Reasoning Engine can maintain read-only safety by avoiding direct modifications to the WorldState or Memory, ensuring that state changes only happen via standard Event processing.

### 5. Risk Assessment
- Identify potential architectural risks in your proposed design, specifically addressing:
  - Circular dependencies between the Reasoning Engine and existing modules
  - Duplicated state across components
  - Hallucinated decisions or actions
  - Uncontrolled memory growth
  - Tightly coupled modules

### 6. Implementation Plan
- Provide a step-by-step implementation plan for integrating the Reasoning Engine into the current ATLAS Core. 

**Rules:**
- **Do not write implementation code.** Focus on architecture, interfaces, and data flow.
- **Do not redesign the entire ATLAS system.** Your solution must preserve the current architecture and extend it cleanly.
