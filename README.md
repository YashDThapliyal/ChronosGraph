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

`to_time: null` means the entity is currently inside that container. When it moves, `to_time` is closed and a new `[:INSIDE]` is opened. This makes it possible to answer:

- Where is entity X right now?
- Where was entity X at time T?
- What is currently inside container Y?
- Every container entity X has ever been in, in order?

---

## The Demo Episode

The active episode is `ComplexEpisode` — a 27-step scripted scenario with two objects moving through multiple containers. The final state is intentionally deceptive.

**Keys journey** (4 containers):
```
t=0.1 -> 0.4   table_01
t=0.5 -> 1.4   counter_01
t=1.6 -> 2.3   drawer_01
t=2.5 -> NOW   counter_01   <-- ends back on the counter
```

**Card journey:**
```
t=0.1 -> 0.7   counter_01
t=0.9 -> NOW   drawer_01    <-- ends in the drawer
```

A baseline LLM asked "what is in the drawer?" will say "the keys" because they were placed there more recently in the sequence. The knowledge graph answers correctly: only `card_001` is in the drawer. The keys are on the counter.

**Questions the graph answers that the LLM gets wrong:**

| Question | LLM (baseline) | Graph |
|---|---|---|
| Where are the keys? | drawer (wrong) | counter_01 |
| What is in the drawer? | keys (wrong) | card_001 |
| Where were the keys at t=2.0? | no idea | drawer_01 |
| List every container the keys have been in | guesses | table, counter, drawer, counter |

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
| `episodes/` | HiddenObjectEpisode (simple) and ComplexEpisode (active demo) |
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

The last two tools require Neo4j and are only registered when `use_neo4j=True`.

---

## Quickstart (in-memory, no Neo4j)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Quickstart with Neo4j

### 1. Install and start Neo4j

**Via Homebrew (macOS):**
```bash
brew install neo4j
neo4j start
# On first run, change the default password at http://localhost:7474
```

**Via Docker:**
```bash
docker run -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/testpassword \
  neo4j:5
```

Neo4j Browser: http://localhost:7474

### 2. Run the bootstrap with Neo4j

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
print(api.whats_inside("drawer_01"))
```

### 3. Browse the graph

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

Set `use_neo4j=True` in `config/settings.py` before running to get the full 5-tool registry backed by Neo4j.

---

## Next Steps

### 1. Wire the Streamlit UI to Neo4j

The UI currently reads from `WorldStateEngine` (in-memory). Adding a toggle to switch its queries to `GraphQueryAPI` would let users see baseline vs graph-grounded answers side by side in the browser, with the graph visualization pulling live from Neo4j.

### 2. Build a temporal query benchmark

Write 10-20 ground-truth question-answer pairs derived from the episode's event log. Run both modes (baseline LLM and knowledge graph) against every question and score accuracy. This produces a concrete, reproducible number showing how much grounded memory improves factual recall.

### 3. Persist state across episodes

Neo4j is durable across restarts. Running multiple episodes accumulates knowledge. An agent in episode 5 can query what happened in episode 2. The storage layer interfaces are already defined — they just need to be called between runs rather than only during a single bootstrap.

### 4. Add more objects and longer episodes

The deceptive quality of the demo grows with episode length and number of objects. Adding 3-4 more pickupable objects each moving through 3+ containers over 50+ steps makes the baseline LLM's failure rate approach 100% while the graph stays correct.

### 5. Connect beliefs and LLM reasoning

The `BeliefManager` and `BeliefStore` interfaces are fully defined. Wiring an LLM to assert beliefs from observations ("the agent probably left the room") and storing them in Neo4j alongside events would add a higher-level reasoning layer on top of the raw event log.

---

## Requirements

- Python 3.10+
- ai2thor
- openai
- neo4j>=5.0
- Neo4j database (Homebrew or Docker)
