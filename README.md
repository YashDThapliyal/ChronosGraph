# ChronosGraph

ChronosGraph is an embodied memory system for AI agents. It watches a simulated world, detects when things change, records those changes as structured events, and builds a temporal knowledge graph that lets you ask questions like "where was the key before it was hidden?" or "what happened to the drawer between step 3 and step 7?"

The core idea is that a plain language model has no memory of what it observed. It can only answer questions based on what it was told in the prompt. ChronosGraph gives the agent a real memory layer: a queryable record of every state change, grounded in observations from the world and persisted in a Neo4j property graph.

---

## How It Works

A simulator (currently AI2-THOR) produces observations at each timestep. Each observation is a snapshot of every visible entity in the scene, including its position, visibility, and what container it is inside. ChronosGraph compares consecutive observations, detects meaningful changes (entity moved, became hidden, changed receptacle), and emits typed events. Those events are written to Neo4j as nodes and relationships, and applied to the in-memory world state engine simultaneously.

When an agent is asked a question about the world, it calls tools backed by Cypher queries against the real graph rather than guessing from context alone.

```
AI2-THOR simulator
    |
    v
ChangeDetector --> [MovedEvent, VisibilityChangedEvent, RelationshipChangedEvent]
    |
    +---> WorldStateEngine (in-memory, drives Streamlit UI)
    |
    +---> Neo4j (Entity nodes, Event nodes, INSIDE relationships with timestamps)
                |
          GraphQueryAPI (Cypher)
                |
           MCP tools --> OpenAI agent
```

---

## Graph Schema

Every entity becomes a node. Containment is a relationship with timestamps:

```
(Entity {entity_id})-[:INSIDE {from_time, to_time}]->(Entity {entity_id})
(Entity {entity_id})-[:HAD_EVENT]->(Event {event_type, timestamp, ...})
```

`to_time: null` means the entity is currently inside that container. When it moves, `to_time` is closed and a new `[:INSIDE]` is opened. This lets you query:

- Where is entity X right now?
- Where was entity X at time T?
- What is currently inside container Y?
- Every container entity X has ever been in, in order?

---

## Architecture

| Layer | Responsibility |
|---|---|
| `simulator/` | World interface and raw observation models (Position, EntityObservation, Observation) |
| `ingestion/` | Bridge between simulator output and core system |
| `core/` | Change detection, event types, belief management |
| `world/` | In-memory temporal state engine (entity history, snapshot queries) |
| `storage/` | Persistence interfaces + Neo4j implementations (Neo4jEventStore, Neo4jEntityStore) |
| `graph/` | GraphInterface + Neo4jGraph implementation (driver wrapper + Cypher primitive) |
| `queries/` | High-level query interface |
| `query_api/` | WorldQueryAPI (in-memory) and GraphQueryAPI (Cypher-backed) |
| `mcp_server/` | JSON-RPC 2.0 MCP server with 5 tools (3 core + 2 graph-native) |
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

## MCP Tools

| Tool | Backend | Description |
|---|---|---|
| `get_current_parent` | Cypher / in-memory | Current container of an entity |
| `get_parent_at` | Cypher / in-memory | Container of an entity at a given timestamp |
| `get_event_history` | Cypher / in-memory | All events for an entity in order |
| `find_entities_in_container` | Cypher only | What is currently inside a given container |
| `get_containment_history` | Cypher only | Every container an entity has ever been in |

The last two tools require Neo4j. They are only registered when `use_neo4j=True`.

---

## Quickstart (in-memory mode)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Quickstart with Neo4j

### 1. Start Neo4j via Docker

```bash
docker run -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/testpassword \
  neo4j:5
```

Neo4j Browser is available at http://localhost:7474 once it starts.

### 2. Configure credentials

Edit `config/settings.py` or override when instantiating:

```python
from config.settings import ChronosGraphSettings

settings = ChronosGraphSettings(
    use_neo4j=True,
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="testpassword",
)
```

### 3. Run the bootstrap with Neo4j

```python
from graph.neo4j_graph import Neo4jGraph
from chronosgraph.bootstrap import bootstrap_world
from query_api.graph_query_api import GraphQueryAPI

graph = Neo4jGraph("bolt://localhost:7687", "neo4j", "testpassword")
graph.connect()

world = bootstrap_world(neo4j_graph=graph)
api = GraphQueryAPI(graph)

print(api.where_is("keys_001"))
print(api.get_containment_history("keys_001"))
```

### 4. Browse the graph

Open http://localhost:7474 and run:

```cypher
MATCH (e:Entity)-[r:INSIDE]->(c:Entity) RETURN e, r, c
```

---

## Streamlit UI

```bash
pip install streamlit graphviz
streamlit run ui/app.py
```

## MCP Server

```bash
./run_mcp_server.sh
```

Set `use_neo4j=True` in settings before running to get the full 5-tool registry backed by Neo4j.

---

## Next Steps: Making the Knowledge Graph Shine

The demo becomes genuinely compelling when the episode is long and complex enough that no language model could track the state from context alone.

### 1. Extend the episode with multi-step object movement

The hidden object episode should move objects through multiple containers across many steps. After 20+ steps, "where are the keys?" becomes a hard question without memory. The answer requires tracing a chain of `[:INSIDE]` relationships across time in the graph.

### 2. Add distractor objects and events

Introduce several objects that move independently. A baseline LLM will confuse them or hallucinate positions. The `find_entities_in_container` tool retrieves exact current contents from the graph by Cypher, which the LLM cannot fake.

### 3. Add re-appearances and ambiguous visibility

Cycle objects in and out of visibility. The LLM will confidently report last-known positions while the graph correctly tracks what actually changed after the last sighting.

### 4. Build a temporal query benchmark

Write 10-20 ground-truth question-answer pairs derived from the episode's event log. Score both modes against every question. This produces a concrete, reproducible demonstration that grounded graph memory improves factual recall.

### 5. Persist state across episodes

Neo4j is now connected and durable. Running multiple episodes accumulates knowledge across all of them. An agent in episode 5 can query what happened in episode 2.

---

## Requirements

- Python 3.10+
- ai2thor
- openai
- neo4j>=5.0 (optional, for graph persistence)
- Docker (optional, for running Neo4j locally)
