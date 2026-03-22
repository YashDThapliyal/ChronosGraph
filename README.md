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
- What was inside container Y at time T?
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

A baseline LLM asked "what is in the drawer?" will say "the keys" because they were placed there more recently in the action sequence. The knowledge graph answers correctly: only `card_001` is in the drawer. The keys are on the counter.

---

## Benchmark Results

The benchmark runs graded questions across three modes and scores each answer with an LLM judge against ground truth derived from live Cypher queries.

**Modes:**
- **Blind** — LLM receives only the question, no world data
- **Context** — LLM receives a full text dump of world state (current locations, containment history, event log) in the prompt
- **Graph** — LLM receives MCP tools backed by Neo4j and resolves answers via Cypher

### ComplexEpisode — 2 objects, 27 steps, 10 questions (gpt-4.1)

| ID  | Question | Blind | Context | Graph |
|-----|----------|-------|---------|-------|
| q01 | Where are the keys right now? | FAIL | PASS | PASS |
| q02 | What objects are currently inside drawer_01? | FAIL | PASS | PASS |
| q03 | Where is card_001 right now? | FAIL | PASS | PASS |
| q04 | Where were the keys at t=2.0? | PASS | PASS | PASS |
| q05 | Where were the keys at t=0.6? | FAIL | PASS | PASS |
| q06 | Which objects were inside drawer_01 at t=2.0? | PASS | PASS | FAIL |
| q07 | List every container the keys have been in | FAIL | PASS | PASS |
| q08 | List every container card_001 has been in | FAIL | PASS | PASS |
| q09 | Did keys end in same container as start? | FAIL | PASS | FAIL |
| q10 | Last container before drawer_01? | PASS | PASS | PASS |
| | **TOTAL** | **3/10** | **10/10** | **8/10** |
| | **Avg latency** | **632ms** | **566ms** | **1421ms** |

At small scale, context stuffing ties the graph at 10/10. The only information missing is "now" — the deceptive final state.

### MegaEpisode — 6 objects, 61 steps, 14 questions (gpt-4.1)

| ID  | Question | Category | Blind | Context | Graph |
|-----|----------|----------|-------|---------|-------|
| m01 | Where are keys_001 right now? | current_location | FAIL (955ms) | PASS (542ms) | PASS (5000ms) |
| m02 | Where is card_001 right now? | current_location | FAIL (575ms) | PASS (776ms) | PASS (1842ms) |
| m03 | What is currently in drawer_01? | container_contents | FAIL (437ms) | PASS (777ms) | PASS (4212ms) |
| m04 | What is currently in fridge_01? | container_contents | FAIL (542ms) | PASS (815ms) | PASS (6384ms) |
| m05 | What is on counter_01 right now? | container_contents | FAIL (552ms) | PASS (922ms) | PASS (7316ms) |
| m06 | Where was knife_001 at t=2.5? | historical_location | FAIL (655ms) | PASS (2024ms) | PASS (5569ms) |
| m07 | What was in drawer_01 at t=1.5? | historical_contents | PASS (596ms) | PASS (542ms) | PASS (6069ms) |
| m08 | What was in fridge_01 at t=3.5? | historical_contents | FAIL (721ms) | **FAIL (880ms)** | PASS (8892ms) |
| m09 | List every container keys_001 has been in | full_history | FAIL (547ms) | PASS (500ms) | PASS (8811ms) |
| m10 | List every container card_001 has been in | full_history | FAIL (417ms) | PASS (3657ms) | PASS (9557ms) |
| m11 | List every container knife_001 has been in | full_history | FAIL (559ms) | PASS (2322ms) | PASS (7559ms) |
| m12 | How many containers has keys_001 been in? | aggregation | FAIL (711ms) | PASS (5478ms) | PASS (7814ms) |
| m13 | Which containers were keys_001 and card_001 in together? | co_location | FAIL (492ms) | **FAIL (4670ms)** | **FAIL (8153ms)** |
| m14 | Which objects have ever been in fridge_01? | container_history | FAIL (541ms) | PASS (3824ms) | PASS (7862ms) |
| | **TOTAL** | | **1/14** avg 593ms | **12/14** avg 1981ms | **13/14** avg 6789ms |

**Key findings:**

**Blind collapses at scale (1/14).** With 6 objects and 61 steps of movement, the LLM answers almost nothing correctly. For objects it has no training data for (knife, mug, spatula) it says "I have no information." For everything else it hallucinates the most recently mentioned container. m07 is the only pass — a lucky guess that both keys and card were in the drawer at t=1.5.

**Context stuffing fails on temporal overlap (m08).** The context dump contains all the information needed to answer correctly, but the LLM fails when it must find all intervals that overlap a specific timestamp across multiple objects. For m08 (what was in fridge_01 at t=3.5?), the LLM found the egg (stationary, always in fridge) but missed that card's fridge window included t=3.5 — it can read the intervals as text but cannot reliably compute "which of these ranges overlap this point" when multiple objects are involved.

The graph agent passes m08 with a single Cypher query using exact range matching (`WHERE r.from_time <= $t AND (r.to_time IS NULL OR r.to_time > $t)`), which is unambiguous regardless of how many objects or events exist.

**m13 (co-location) fails all three modes.** "Which containers were keys_001 and card_001 in at the same time?" requires computing the intersection of two sets of time intervals and finding which containers appear in both. Blind guesses one container. Context finds only fridge_01 (a subset). Graph returns drawer_01, counter_01, fridge_01 — counter_01 is incorrect (a hallucinated superset). This is the hardest query class: join reasoning over temporal intervals across two entities. It is the remaining unsolved case.

**Graph is 11x slower at scale (6789ms vs 593ms for blind, 1981ms for context).** Multi-object questions require 2–4 tool call round-trips each adding LLM latency. The trade-off is worth it at scale: graph stays precise where context degrades. At 2 objects both methods score equally; at 6 objects with complex temporal queries, graph (13/14) > context (12/14) > blind (1/14).

**The inflection point:** At 2 objects, context = graph = 10/10. At 6 objects, graph outperforms context specifically on temporal overlap questions (m08) that require interval arithmetic the LLM cannot reliably perform over text. As object count grows, context accuracy will continue to degrade on these query types while graph stays exact.

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
| `mcp_server/` | JSON-RPC 2.0 MCP server with 6 tools (3 core + 3 graph-native) |
| `agent/` | OpenAI tool-calling agent with baseline vs grounded comparison modes |
| `episodes/` | HiddenObjectEpisode (simple) and ComplexEpisode (active demo) |
| `ui/` | Streamlit demo with frame playback, agent QA, and graph visualization |
| `config/` | System-wide configuration dataclass |
| `benchmark/` | Three-mode accuracy and latency benchmark with LLM judge scoring |

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
| `find_entities_in_container_at` | Cypher only | What was inside a container at a given timestamp |
| `find_entities_ever_in_container` | Cypher only | All entities that have ever been inside a container |
| `get_containment_history` | Cypher only | Every container an entity has ever been in |
| `find_co_located` | Cypher only | Other entities in the same container as X at time T |
| `list_entities` | Cypher only | Enumerate all tracked entities (discovery) |
| `list_containers` | Cypher only | Enumerate all containers that have ever held something |

The last seven tools require Neo4j and are only registered when `use_neo4j=True`.

**Tool design principle:** Tools are composable primitives, not answer machines. The agent reasons over tool results — tools just fetch. Discovery tools (`list_entities`, `list_containers`) are essential at scale so the agent does not need entity IDs hardcoded in the system prompt. Join tools (`find_co_located`, `find_entities_ever_in_container`) are added only when the composition pattern requires multiple round-trips for every question of that type.

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
print(api.whats_inside_at("drawer_01", 2.0))
```

### 3. Browse the graph

Open http://localhost:7474 and run:

```cypher
MATCH (e:Entity)-[r:INSIDE]->(c:Entity) RETURN e, r, c
```

---

## Run the Benchmark

```bash
source .venv/bin/activate
python -m benchmark.run --neo4j-password testpassword
```

Results are printed as a PASS/FAIL table with per-question latency and saved to `benchmark/results.json`.

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

Set `use_neo4j=True` in `config/settings.py` before running to get the full 6-tool registry backed by Neo4j.

---

## Next Steps

### 1. Re-run the mega benchmark with the patched tools

The benchmark has been re-run with the patched 8-tool set. Results: graph 13/14, context 12/14, blind 1/14.

- `find_entities_ever_in_container` (m14) is now answered correctly by all modes with tools
- m13 (co-location interval join) remains the one unsolved case across all three modes — see next step

### 2. Solve co-location interval joins (m13)

"Which containers were X and Y in at the same time?" requires computing the intersection of two entity's containment histories and finding containers where the intervals overlap. The current agent composes `get_containment_history` calls and reasons over the result, but adds a spurious container. Options:
- Add a dedicated `find_co_located_containers(entity_a, entity_b)` Cypher tool that does the interval join in the database
- Improve the system prompt to instruct the agent how to compute interval overlaps explicitly

### 3. Find the context-stuffing breakpoint

Context scored 12/14 at 6 objects but already fails on temporal overlap questions (m08) where the LLM must compute which time intervals are active at a given point across multiple objects. The next experiment is to increase to 10–15 objects and measure at what scale context accuracy drops below 50%, while graph stays above 90%.

### 3. Persist state across episodes

Neo4j is durable across restarts. Running multiple episodes accumulates knowledge. An agent in episode 5 can query what happened in episode 2. The storage layer interfaces are already defined — they just need to be called between runs rather than only during a single bootstrap.

### 4. Wire the Streamlit UI to Neo4j

The UI currently reads from `WorldStateEngine` (in-memory). Adding a toggle to switch its queries to `GraphQueryAPI` would let users see baseline vs graph-grounded answers side by side in the browser, with the graph visualization pulling live from Neo4j.

### 5. Reduce graph latency

The graph agent averages 6.8s per question versus 2.0s for context at MegaEpisode scale, primarily because multi-step questions require 2–4 tool call round-trips each involving an LLM call. Potential reductions:
- Parallel tool calls (batch multiple `get_parent_at` calls in one LLM turn)
- A `summarize_world_state()` tool that returns a compact snapshot for simple questions
- Pre-computing common query patterns as stored Cypher procedures

### 6. Connect beliefs and LLM reasoning

The `BeliefManager` and `BeliefStore` interfaces are fully defined. Wiring an LLM to assert beliefs from observations ("the agent probably left the room") and storing them in Neo4j alongside events would add a higher-level reasoning layer on top of the raw event log.

---

## Requirements

- Python 3.10+
- ai2thor
- openai
- neo4j>=5.0
- Neo4j database (Homebrew or Docker)
