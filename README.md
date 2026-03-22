# ChronosGraph

ChronosGraph is an embodied memory system for AI agents. It watches a simulated world, detects when things change, records those changes as structured events, and builds a temporal knowledge graph that lets you ask questions like "where was the key before it was hidden?" or "what happened to the drawer between step 3 and step 7?"

The core idea is that a plain language model has no memory of what it observed. It can only answer questions based on what it was told in the prompt. ChronosGraph gives the agent a real memory layer: a queryable record of every state change, grounded in observations from the world.

---

## How It Works

A simulator (currently AI2-THOR) produces observations at each timestep. Each observation is a snapshot of every visible entity in the scene, including its position, visibility, and what container it is inside. ChronosGraph compares consecutive observations, detects meaningful changes (entity moved, became hidden, changed receptacle), and emits typed events. Those events are applied to the world state engine, which maintains a full history for every entity.

When an agent is asked a question about the world, it can call tools backed by this history rather than guessing from context alone.

```
simulator/ --> ingestion/ --> core/ --> world state engine
                                  |
                            event history
                                  |
                          query API / MCP tools
                                  |
                            OpenAI agent
```

---

## Architecture

| Layer | Responsibility |
|---|---|
| `simulator/` | World interface and raw observation models (Position, EntityObservation, Observation) |
| `ingestion/` | Bridge between simulator output and core system |
| `core/` | Change detection, event types, belief management |
| `world/` | In-memory temporal state engine (entity history, snapshot queries) |
| `storage/` | Abstract persistence interfaces for events, snapshots, beliefs |
| `graph/` | Abstract graph database interface (targeting Neo4j) |
| `queries/` | High-level query interface over the knowledge graph |
| `query_api/` | Concrete JSON-serializable adapter for world state queries |
| `mcp_server/` | JSON-RPC 2.0 MCP server exposing tools over stdio |
| `agent/` | OpenAI tool-calling agent with baseline vs grounded comparison modes |
| `episodes/` | Scripted simulation scenarios |
| `ui/` | Streamlit demo with frame playback, agent QA, and graph visualization |
| `config/` | System-wide configuration dataclass |

### Dependency Rules

- `core/` must not import from `simulator/`
- `storage/` must not import from `simulator/`
- `ingestion/` is the only module that bridges simulator and core
- All cross-module interaction goes through abstract interfaces

---

## Current Demo

The current episode (`HiddenObjectEpisode`) runs a short scripted sequence in an AI2-THOR kitchen scene. The agent picks up a set of keys, opens a drawer, places the keys inside, and closes the drawer. The episode is only a handful of steps long.

At the end, you can ask the agent "where are the keys?" in two modes:

- **Baseline**: the LLM answers from prompt context alone, with no memory tools
- **Knowledge Graph**: the LLM calls `get_current_parent`, `get_parent_at`, and `get_event_history` to retrieve grounded answers from the recorded world state

In the current short episode the difference is noticeable but not dramatic. The object goes in the drawer and stays there. The agent can usually guess right even without tools.

---

## Next Steps: Making the Knowledge Graph Shine

The demo becomes genuinely compelling when the episode is long and complex enough that no language model could track the state from context alone.

### 1. Extend the episode with multi-step object movement

The hidden object episode should move objects through multiple containers across many steps. For example: keys start on the counter, get moved to a bowl, then moved to a drawer, then the drawer is closed and a book is placed on top of it. After 20+ steps, "where are the keys?" becomes a hard question without memory. The answer requires tracing a chain of relationship changes across time.

### 2. Add distractor objects and events

Introduce several objects that move around the scene independently. The agent observing the scene has to track multiple entities simultaneously. A baseline LLM will confuse them or hallucinate positions. The knowledge graph retrieves the exact history for any entity by ID.

### 3. Add re-appearances and ambiguous visibility

Have objects disappear (move out of frame, get occluded) and reappear later. The `VisibilityChangedEvent` already tracks this. An episode that cycles objects in and out of visibility creates cases where the LLM confidently states an object is in a location it last saw it, while the knowledge graph correctly says it was moved after that last sighting.

### 4. Build a temporal query benchmark

Write 10-20 ground-truth question-answer pairs derived from the episode's event log. Run both modes (baseline and knowledge graph) against every question and score accuracy. This produces a concrete, reproducible demonstration that grounded memory improves factual recall.

### 5. Persist state across episodes

Right now the world state is rebuilt from scratch on every run. Wiring in the storage layer (EventStore, EntityStore) means the graph accumulates knowledge across multiple episodes. An agent running episode 5 can answer questions about what happened in episode 2.

### 6. Connect Neo4j

The `GraphInterface` is fully defined but has no concrete implementation. Connecting Neo4j turns the in-memory world state into a persistent, queryable graph database. This also enables Cypher queries for more expressive temporal reasoning (e.g. "find all objects that were in the drawer at any point between T=10 and T=30").

---

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Streamlit UI

```bash
pip install streamlit graphviz
streamlit run ui/app.py
```

### MCP Server

```bash
./run_mcp_server.sh
```

---

## Requirements

- Python 3.10+
- ai2thor
- openai
