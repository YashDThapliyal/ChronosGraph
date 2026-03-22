# ChronosGraph

**AI agents operating in dynamic environments have no persistent memory of what they have observed.** They can only answer questions from what is present in the current context window. When that context grows large or spans many timesteps, models hallucinate, miss temporal overlaps, and confidently state the wrong location for objects they have already forgotten.

**We propose ChronosGraph: an approach that replaces context stuffing with a temporal knowledge graph.** Every state change in the environment is recorded as a timestamped relationship in Neo4j, and the agent queries that graph through structured tools rather than reasoning over raw text. This gives verifiable, exact answers to questions like "where was the key before it was hidden?" regardless of how many objects or timesteps have elapsed.

**The inspiration for this project is robotics.** Specifically, the question of how a humanoid robot could maintain reliable, queryable memory of its environment without hallucinating the location of objects it has moved, hidden, or interacted with across a long operational lifetime.

---

## How It Works

A scripted episode plays out step by step. At each step, a `ChangeDetector` compares the current world observation to the previous one and emits typed events: `MovedEvent`, `VisibilityChangedEvent`, `RelationshipChangedEvent`. Each `RelationshipChangedEvent` (an object moved from one container to another) drives two writes to Neo4j: close the old `[:INSIDE]` relationship by setting `to_time`, and open a new one with `from_time`. This creates a complete, timestamped containment history for every object.

When the agent is asked a question, it calls MCP tools backed by Cypher queries against Neo4j rather than reasoning from text.

```
Episode (scripted)
    |
    v
ChangeDetector --> [MovedEvent, VisibilityChangedEvent, RelationshipChangedEvent]
    |
    +---> WorldStateEngine  (in-memory, drives Streamlit UI)
    |
    +---> Neo4j  (Entity nodes + INSIDE relationships with timestamps)
                      |
                GraphQueryAPI  (Cypher)
                      |
                 MCP tools --> OpenAI agent
```

---

## Graph Schema

```
(Entity {entity_id, entity_type})-[:INSIDE {from_time, to_time}]->(Entity)
(Entity)-[:HAD_EVENT]->(Event {event_type, timestamp, ...})
```

`to_time: null` means the entity is currently inside that container. This single relationship type is sufficient to answer any containment question at any point in time with one Cypher range query.

---

## MCP Tools

The agent has 8 tools structured as 3 forward traversal + 3 reverse traversal + 2 discovery. Tools are fetch primitives - the agent reasons over results, not the other way around.

| Category | Tool | What it answers |
|---|---|---|
| Forward | `get_current_parent` | Where is entity X right now? |
| Forward | `get_parent_at` | Where was entity X at time T? |
| Forward | `get_containment_history` | Every container X has been in, in order |
| Reverse | `find_entities_in_container` | What is currently inside container Y? |
| Reverse | `find_entities_in_container_at` | What was inside container Y at time T? |
| Reverse | `find_entities_ever_in_container` | What has ever been inside container Y? |
| Discovery | `list_entities` | What entities exist in the world? |
| Discovery | `list_containers` | What containers have ever held something? |

The two discovery tools are essential at scale: the agent calls them first so it does not need entity IDs hardcoded in the system prompt.

---

## Benchmark

Three modes are run against the same question set and scored by an LLM judge against ground truth derived from live Cypher queries:

- **Blind** - LLM receives only the question, no world data
- **Context** - LLM receives a full text dump of all entity locations, containment histories, and events
- **Graph** - LLM receives the 8 MCP tools and queries Neo4j directly

### MegaEpisode - 6 objects, 61 steps, 14 questions (gpt-4.1)

| ID | Question | Category | Blind | Context | Graph |
|----|----------|----------|-------|---------|-------|
| m01 | Where are keys_001 right now? | current_location | FAIL | PASS | PASS |
| m02 | Where is card_001 right now? | current_location | FAIL | PASS | PASS |
| m03 | What is currently in drawer_01? | container_contents | FAIL | PASS | PASS |
| m04 | What is currently in fridge_01? | container_contents | FAIL | PASS | PASS |
| m05 | What is on counter_01 right now? | container_contents | FAIL | PASS | PASS |
| m06 | Where was knife_001 at t=2.5? | historical_location | FAIL | PASS | PASS |
| m07 | What was in drawer_01 at t=1.5? | historical_contents | PASS | PASS | PASS |
| m08 | What was in fridge_01 at t=3.5? | historical_contents | FAIL | **FAIL** | PASS |
| m09 | List every container keys_001 has been in | full_history | FAIL | PASS | PASS |
| m10 | List every container card_001 has been in | full_history | FAIL | PASS | PASS |
| m11 | List every container knife_001 has been in | full_history | FAIL | PASS | PASS |
| m12 | How many containers has keys_001 been in? | aggregation | FAIL | PASS | PASS |
| m13 | Which containers had keys_001 and card_001 at the same time? | co_location | FAIL | **FAIL** | **FAIL** |
| m14 | Which objects have ever been in fridge_01? | container_history | FAIL | PASS | PASS |
| | **TOTAL** | | **1/14** (593ms) | **12/14** (1981ms) | **13/14** (6789ms) |

**Blind collapses at scale (1/14).** With 6 objects and 61 steps of movement, the LLM has no grounding. It says "I have no information" for unknown objects and hallucinates the most recently mentioned container for everything else.

**Context stuffing fails on temporal overlap (m08).** The context dump contains all the information - but the LLM cannot reliably compute "which of these intervals are active at t=3.5" across multiple objects from text. For m08, it correctly found the egg (always in fridge) but missed that card's fridge window covered t=3.5. The graph agent answers m08 with a single Cypher range query: `WHERE r.from_time <= $t AND (r.to_time IS NULL OR r.to_time > $t)`.

**m13 fails all three modes.** Co-location requires computing the intersection of two entities' interval histories and finding containers where they overlapped. This is the remaining unsolved case - it requires an interval join that none of the current modes handle correctly.

**Graph is ~3x slower than context** (6.8s vs 2.0s average) due to sequential tool-call round-trips. The trade-off is worth it where context accuracy degrades on temporal queries.

**The inflection point:** At 2 objects, context = graph = 10/10. At 6 objects with complex temporal queries, graph (13/14) > context (12/14) > blind (1/14). Context accuracy will continue to degrade as object count grows; graph accuracy stays constant.

---

## Architecture

| Layer | Responsibility |
|---|---|
| `simulator/` | Raw observation models - Position, EntityObservation, Observation |
| `ingestion/` | Bridge between simulator output and core system |
| `core/` | ChangeDetector, typed events, belief interfaces |
| `world/` | In-memory temporal state engine (entity history, snapshot queries) |
| `storage/` | Neo4jEventStore + Neo4jEntityStore (persist events and INSIDE lifecycle) |
| `graph/` | Neo4jGraph - driver wrapper, `run_cypher` primitive, index management |
| `query_api/` | WorldQueryAPI (in-memory) and GraphQueryAPI (Cypher-backed) |
| `mcp_server/` | JSON-RPC 2.0 MCP server, 8-tool registry |
| `agent/` | OpenAI tool-calling agent with retry/backoff |
| `episodes/` | ComplexEpisode (2 objects) and MegaEpisode (6 objects) |
| `benchmark/` | Three-mode benchmark with LLM judge scoring and latency tracking |
| `ui/` | Streamlit demo - frame playback, agent QA, graph visualization |

**Dependency rules:** `core/` and `storage/` must not import from `simulator/`. `ingestion/` is the only module that bridges both. All cross-layer interaction goes through abstract interfaces.

---

## Quickstart

### In-memory (no Neo4j)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### With Neo4j

Start Neo4j:
```bash
docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/testpassword neo4j:5
```

Run bootstrap:
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

Browse the graph at http://localhost:7474:
```cypher
MATCH (e:Entity)-[r:INSIDE]->(c:Entity) RETURN e, r, c
```

### Run the benchmark

```bash
python -m benchmark.run --neo4j-password testpassword
# Add --mega to run MegaEpisode (default)
```

Results are printed as a PASS/FAIL table with per-question latency and saved to `benchmark/results.json`.

### Streamlit UI

```bash
pip install streamlit graphviz
streamlit run ui/app.py
```

---

## Requirements

- Python 3.10+
- openai
- neo4j >= 5.0
- Neo4j database (Docker or Homebrew)
