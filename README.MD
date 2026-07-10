# What is is this?
This is a TCL/TK Python simulation showing  [likely] a triumph of genetic algorithms over overthinking and deep analysis. You can have multiple Civilizations (think "players") competing with different strategies having access to the same data & tools to manage the game.

---

# Install & Run

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.14 tested; use Homebrew `python@3.14` on macOS |
| Tcl/Tk | bundled | macOS: `brew install python-tk@3.14` (or matching version) |
| OLLAMA | latest | Required only for the LLM strategy — [ollama.com](https://ollama.com) |
| Qwen model | `qwen3:14b` | `ollama pull qwen3:14b` — skip if not using the LLM strategy |

## Setup

```bash
# 1. Clone
git clone https://github.com/yourname/labyrinth.git
cd labyrinth

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install runtime dependencies
pip install -r requirements.txt

# 4. Install the package in editable mode (enables `from labyrinth…` imports)
pip install -e .
```

### macOS — Tk support

Homebrew Python ships without Tk bindings by default. Install the matching formula once:

```bash
brew install python-tk@3.14   # replace 3.14 with your Python minor version
```

Verify with:

```bash
python -c "import tkinter; print('Tk', tkinter.TclVersion)"
```

## Run

```bash
python main.py
```

Games are auto-recorded to `saves/game_YYYYMMDD_HHMMSS.db` when a simulation starts. Use **Save Game** on the Commentary tab to export a copy elsewhere.

## Run tests

```bash
# Unit tests only
pytest

# Include integration tests (requires OLLAMA running with qwen3:14b)
pytest -m integration

# E2E GUI tests (programmatic Tk control; requires display)
pytest -m gui

# Skip GUI tests (CI-friendly)
pytest -m "not gui"
```

---

# Target State

This section documents the **intended** GUI, persistence, and testing contract. Load/replay from saved games is planned but not yet implemented.

## GUI workflow

| Step | Behavior |
|---|---|
| Start screen | Set number of turns, click **Start Simulation** |
| Plot tab | God-view labyrinth (left) + combined civ overlay map (right) |
| Turn execution | Background worker thread; UI stays responsive during turns |
| Controls | **Next Turn** / **Stop** / **Reset** / **Auto-advance** on Plot tab |
| Auto-save | Every game auto-records to `saves/game_YYYYMMDD_HHMMSS.db` on start |
| Save Game | Commentary tab exports the auto-save DB via Save As dialog |
| Load/replay | *Out of scope for current milestone* |

## Persistence

- Engine writes one SQLite row per turn when `db_path` is set.
- Auto-save path is created under `saves/` at simulation start (no path picker).
- **Save Game** copies the auto-save file to a user-chosen location.

## Testing strategy

| Layer | Command | Notes |
|---|---|---|
| Unit | `pytest -m "not gui"` | Domain, engine, strategies (no Tk) |
| Integration | `pytest -m integration` | Full turns; OLLAMA optional |
| E2E GUI | `pytest -m gui` | `LabyrinthApp(test_mode=True)` + `GuiHarness` |

### `test_mode`

When `LabyrinthApp(test_mode=True)`:

- GenAlg-only civilizations (no OLLAMA)
- `thinking_seconds=0.1` (fast turns)
- Window withdrawn (headless-friendly)
- Auto-advance delay 100 ms
- No modal dialogs on invalid input

### E2E flow under test

1. Start simulation with N turns
2. Run one turn manually
3. Enable auto-advance and wait for turn 3
4. Assert SQLite turn count matches
5. Export save file (filedialog mocked in tests)

---

# Flow of the game

1. The goal of the game is to have most Soma in the end of the Game (predefined number of turns). You start with `INITIAL_RAKSHAS × turns_total` Soma (e.g. 2 000 for a default 20-turn game).
2. Soma is gathered in the center of 100 square x 100 squares Labyrinth. When you Raksha arrives to the center of Labyrinth he gets 1 to 10 Soma, random.
3. Civilization consists of Rakshas (you start with 100 with different gene types of equal number to adapt to any Epoch). To sustain 1 Raksha for 1 turn you need 1 Soma - if you dont have enough you have to indicate who has to die. You can decide who dies even if you have enough Soma - "weed the field", so to say. If you have enough Soma to sustain those Rakshas you selected - Rakhash is available for tasking and can be sent into Labyrinth. For killing/sustaining Rakshas en masse you can issue a command like "sustain only those who are Resistant to fire" or "sustain 100 of each Resistant to Fire, Earth, Water, Air." or "Sustain Rakshas who ventured into Labyrinth successfully at least once".
4. Labyrinth is a blackbox for the Civilization - we dont know whats inside. Labyrinth has Traps of different types - Earth, Fire, Air, Water scattered across the map. **10% of squares are traps**; **75% of those traps** belong to the current epoch type (Epoch of Water, Fire, etc.). The remaining 90% of squares are free passage. Epoch has lenghth between 5 to 10 turns (random). (The idea of the epoch is that we want to punish for hyper-optimization - in the epoch of fire those who wiped out all Rakshas of other dominant Genes will suffer when Epoch changes.)
5. Takes a Trip into a Labyrinth. Trip may have Path defined (as X1, Y1  > ... -> Xn, Yn). Rakshas steps into a Square with a Trap of Type he is not Resistant to - Rakshas has 50% chance to die. If Resistant - no harm if he has dominant Resistance gene, 25% chance to die if has secondary Resistance Gene. Rakshas who went in all the way to the center gets random 1-10 Soma and immediately teleports home, bringing back his Travelog - record of the path travelled, which steps X1, Y1  -> Xn, Yn he took and what was there: free, Trap of Type<t>, Soma.
6. Each Rakshas has DNA - 3 genes defining his Resistance, 1 Dominant and 1 Secondary and 1 Recessive (random gene from the parental tree, but not one he already has). He gets them from Parents - which one is dominant and which is secondary decided at random, Recessive is random from non-dominant of his Parents but available in the "family tree". 
3. In the end of the turn Civilization decides who will reproduce. Again, we shall be able to issue en masse command  "those who are Resistant to fire and water" or "those who ventured into Labyrinth successfully at least once reproduce".

# Civilization decisions
Game is a predefined set of Turns + Civilizations(Strategy).
Each Timed Turn (3 mins):
1. Strategize - process results from those who returned, update whatever data massives they have to base their decisions upon, issue/update StandingOrders set in Strategy which game uses to un the Turn loop. (game to call services to weed(Criteria), send_to_labyrinth(List<Raksha>), reproduce(Criteria) when player signals "make turn" or 3-mins expire), describe strategy for the current turn an set Strategy.current_strategy_sumup.
2. Send Raksha's to the Labyrinth - Time Raksha's spend in Labyrinth does not count toward Turn time - only thinking counts. After they returned you see stats: died/returned/update of the Labyrinth uncovered by your Rakshas who returned.
5. Decide who dies [mandatory if not enough Soma]; can be empty if you sustain all. Likely set on the Strategy during Strategy.decide() 
5. Turn summarized: Soma start, Soma end, Soma expended, Population start, Population end, Strategy decicions done, whatnot -> recorded as Turn to be analyzed. You cannot think for more than 3 mins - every Turn is timed. 

# GUI
The spectator interface:
Main form with stat tabs showing current turn [can be switched to any turn already completed], updated in real-time:
1. Tab "Plot": 
- overall labirinth in the left (transparent for the spectator) & Epoch (Water, Fire etc.) with remaining turns for the epoch/game, 
- and Labirinths as uncovered by every Civilization + Underneath Civilization stats with Rakshas and Soma count + outcomes of their Rakshas venturing into Labirinth in real-time, together with Labyrinth mapped by survived Rakshas: survived + Soma gathered/died.
- "Next turn" button with auto-advance checkbox.
2. Tab "Civilizations": with stats & diagrams on their population as charts updated in real time: count, genes breakdown, soma.
3. Tab "Commentary": Decision making log from their Strategy - who dies and why, who sent and why, who breeds and why; turn over turn.
4. Save game (in the end), load game (can be "replayed" turn by turn)

# Players and strategies

### 1. GenAlg — black-box genetic algorithm (no epoch oracle)

**Objective:** maximize population **survival** (and indirectly soma runway). Fitness is inferred only from trip outcomes — the strategy never sees the current epoch.

**Genome:** a Raksha’s DNA triple (dominant / secondary / recessive). **Phenotype** in the labyrinth = returns alive (optionally with soma).

1. **Initialize a diverse population** — 96 cohort + 4 strays ≈ broad initial search space across dom×sec families, not a single hyper-fit clone.
2. **Fitness = empirical survival rate** — per archetype and per dominant gene, updated from travelogs. Not *analytic* fitness function; only observed labyrinth performance.
3. **Exploration: scout phase** — send one representative per **64 archetypes** (4×4×4 grid). Uniform exploration of genotype space to estimate which regions survive under current trap pressure.
4. **Exploitation: harvest phase** — once a fitness signal exists, send mostly Rakshas with the **currently fittest dominant gene**. Selection pressure toward what worked last turn.
5. **Selection for breeding** — trip **survivors** reproduce. Survival selection: only phenotypes that passed the environment propagate.
6. **Crossover analogue: similarity mating** — survivors pair with the **most genetically similar** partner. Assortative mating reinforces promising lineages without immediate collapse to one clone.
7. **Diversity pressure (anti-hyperoptimization)** — keep ≥1 reserve per archetype when culling excess clones; protect soma-bringing and current-best dominants; the 64-grid scout pool acts as a **diversity archive**. Soma budget caps how much diversity can be maintained.
8. **Population size = constraint, not objective** — growth limited by soma runway (1 soma/Raksha/turn). The GA maximizes survivors under resource constraints, not headcount.
9. **Epoch change = fitness landscape shift** — when the environment changes, old fitness estimates go stale. The strategy does **not** model the new epoch.
10. **Re-scout on collapse** — if last expedition survival **<25%**, treat as landscape shock → partial/full re-exploration (scout cohort) to rediscover which gene dominates now.
11. **Culling = prune redundant genotypes** — when clone copies of the same DNA pile up, kill excess low-fitness copies. Reduce redundant search; keep archive + winners.
12. **Loop:** `explore (scout) → estimate fitness → exploit (harvest) → select survivors → mate similar → prune clones → re-explore on shock`.

*One-liner: a black-box GA where fitness is survival, scouting estimates the landscape, harvesting amplifies the current elite, similarity mating propagates winners, and reserved archetypes + re-scouting prevent premature convergence when epochs shift.*

### 2. LLM (Qwen via OLLAMA) — reasoning strategy

LLM-based strategy using local OLLAMA Qwen, aware of game rules and the 3-minute per-turn thinking limit. Each turn it receives the same **classes of empirical data** as GenBot (gene counts, 64-archetype survival, clone counts, compact travelogs, soma bearers) plus a **blackboard** — structured self-notes from the prior turn (phase, hypothesized trap, plan, next intent). No epoch oracle; the model infers trap dominance from data and writes letters to its future self.


# Technicalities
1. Python.
2. Completed games can be saved into SQLite db containing all Turns and whatnot for every saved Game. We can analyze these files later on to define better Strategies.
3. Real-time GUI updates as Raksha's return/die etc.

---

# Technologies

| Layer | Library / Tool | Notes |
|---|---|---|
| Language | Python 3.11+ | dataclasses, `match/case`, `UUID`, type aliases |
| GUI | `tkinter` + `ttk` (stdlib) | `Canvas` for grids; `ttk.Notebook` for tabs |
| Charts | `matplotlib` via `FigureCanvasTkAgg` | Gene breakdown bars + soma history lines |
| Concurrency | `threading` (stdlib) | `Strategy.decide()` runs in a daemon thread; GUI on main thread |
| Persistence | `sqlite3` (stdlib) | One `.db` file per saved game |
| LLM inference | `ollama` Python client + Qwen2.5 local | No cloud dependency; streams with deadline awareness |
| Serialization | `json` (stdlib) | Travelog paths, map knowledge snapshots stored as JSON blobs |
| Logging | `structlog` | Structured decision logs feed the Commentary tab |
| Testing | `pytest` + `pytest-mock` | Domain logic only; no GUI tests |

---

# Wireframes (Tkinter / ttk)

## Tab: Plot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Labyrinth Simulation                             Turn 4 / 20   ⏱  02:43    │
├─────────────────────────────────────────────────────────────────────────────┤
│  [Plot]   [Civilizations]   [Commentary]                                    │
├────────────────────────────────────────┬────────────────────────────────────┤
│ ACTUAL LABYRINTH  (tk.Canvas 400×400)  │ CIV: AlgoBot  [GenAlg]             │
│ Epoch: ██ FIRE   ░░░░░░░  3 turns left │   Soma  1 243    Rakshas  88 alive │
│                                        │  ┌──────────────────────────────┐  │
│  · · · F · · W · · · · E · · · · · ·  │  │ Uncovered map  (tk.Canvas)   │  │
│  · W · · · · · · A · · · · · · · · ·  │  │  ·  known free               │  │
│  · · · · W · · · · · · · · · A · · ·  │  │  F/W/E/A  trap type found    │  │
│  · · F · · · · · · · · · · · · · · ·  │  │  ●  soma collected           │  │
│  · · · · · · · · · ● · · · · · · · ·  │  │  ✝  raksha died here         │  │
│         [center square = ●]            │  └──────────────────────────────┘  │
│                                        │   Turn: 12 sent · 9 back · 3 ✝     │
│  F=Fire  W=Water  E=Earth  A=Air       ├────────────────────────────────────┤
│  (spectator sees all traps & soma)     │ CIV: Qwen-7B  [LLM]                │
│                                        │   Soma    987    Rakshas  95 alive │
│                                        │  ┌──────────────────────────────┐  │
│                                        │  │ Uncovered map  (tk.Canvas)   │  │
│                                        │  └──────────────────────────────┘  │
│                                        │   Turn:  8 sent ·  7 back · 1 ✝    │
├────────────────────────────────────────┴────────────────────────────────────┤
│  [ Next Turn ]   [x] Auto-advance                   Game: 16 turns remain   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Tab: Civilizations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [Plot]   [Civilizations]   [Commentary]                                    │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ AlgoBot  (GenAlg)                    │ Qwen-7B  (LLM)                       │
│                                      │                                      │
│  Soma over turns                     │  Soma over turns                     │
│  1400 ╮                              │  1400                                │
│  1200  ╲__                           │  1200 ╮╭─╮                           │
│  1000     ╰──╮                       │  1000  ╰─╯ ╰──                       │
│       T1  T2  T3  T4                 │       T1  T2  T3  T4                 │
│                                      │                                      │
│  Gene breakdown — turn 4             │  Gene breakdown — turn 4             │
│  FIRE  ████████████ 42%              │  FIRE  ████████ 32%                  │
│  WATER ████████     28%              │  WATER █████████ 35%                 │
│  EARTH █████        18%              │  EARTH █████     20%                 │
│  AIR   ████         12%              │  AIR   ████      13%                 │
│                                      │                                      │
│  Population: 88    Soma: 1 243       │  Population: 95    Soma: 987         │
├──────────────────────────────────────┴──────────────────────────────────────┤
│  [ Turn: ←  1  2  3 [4]  5  6 ... → ]                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Tab: Commentary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [Plot]   [Civilizations]   [Commentary]                                    │
├──────────────────────────────────────────────────────────┬──────────────────┤
│  [ Turn: ←  1  2  3 [4]  5  6 ... → ]                   │  [Save Game]     │
├──────────────────────────────────────────────────────────┴──────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ [T4] AlgoBot (GenAlg) ─────────────────────────────────────────── ▲ │    │
│  │   Strategy: "Epoch FIRE turn 2/7. Harvesting aggressively. Weeding │    │
│  │   low-survival non-FIRE below diversity floor."                    │    │
│  │   Weed:      "EARTH-dominant, <2 trips survived (5 Rakshas)"       │    │
│  │   Sent:      65 Rakshas  (FIRE-dominant priority)                  │    │
│  │   Reproduce: "FIRE×WATER pairs; maintain 15% floor each gene"      │    │
│  │                                                                    │    │
│  │ [T4] Qwen-7B (LLM) ───────────────────────────────────────────── │    │
│  │   Strategy: "Soma comfortable. Dispatching scouts to uncharted     │    │
│  │   north-east quadrant. No weed needed."                            │    │
│  │   Weed:      "None — sustain all"                                  │    │
│  │   Sent:      40 Rakshas  (top trip-success-rate)                   │    │
│  │   Reproduce: "Those who reached center at least once"              │    │
│  │                                                                    │    │
│  │ [T3] AlgoBot (GenAlg) ─────────────────────────────────────────── ▼ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Domain Model

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from uuid import UUID

class GeneType(Enum):
    FIRE  = auto()
    WATER = auto()
    EARTH = auto()
    AIR   = auto()

class CivilizationStatus(Enum):
    ACTIVE  = auto()
    EXTINCT = auto()

@dataclass
class DNA:
    dominant:  GeneType
    secondary: GeneType
    recessive: GeneType  # random from non-dominant ancestors; not one he already has

@dataclass
class Raksha:
    id:              UUID
    civilization_id: str
    dna:             DNA
    alive:           bool      = True
    trips_completed: int       = 0
    trips_survived:  int       = 0
    parent_a_id:     UUID | None = None
    parent_b_id:     UUID | None = None

@dataclass
class SquareRecord:
    """What a Civilization knows about one labyrinth square."""
    x:          int
    y:          int
    trap_type:  GeneType | None  # None = free passage
    is_center:  bool = False

TRIP_MAX_STEPS: int = 50  # hard cap for naive random walk on 100×100 grid

@dataclass
class Travelog:
    """Produced by every trip; accumulated into civilization's known_map."""
    raksha_id:      UUID
    path:           list[tuple[int, int]]
    squares:        dict[tuple[int, int], SquareRecord]
    soma_gathered:  int
    survived:       bool
    hit_step_limit: bool = False  # True when returned due to TRIP_MAX_STEPS

@dataclass
class Epoch:
    dominant_type:   GeneType
    turns_remaining: int   # 5–10 on creation
    length:          int

class CriteriaField(Enum):
    """Raksha attribute that a Criterion can filter on."""
    GENE_DOMINANT   = "gene_dominant"
    GENE_SECONDARY  = "gene_secondary"
    GENE_RECESSIVE  = "gene_recessive"
    TRIPS_COMPLETED = "trips_completed"
    TRIPS_SURVIVED  = "trips_survived"
    ALIVE           = "alive"

class CriteriaOp(Enum):
    EQ  = "eq"
    NEQ = "neq"
    GT  = "gt"
    GTE = "gte"
    LT  = "lt"
    LTE = "lte"

@dataclass
class Criterion:
    """
    A single filter rule. Multiple Criteria in a list are AND-ed.

    Examples:
      Criterion(CriteriaField.GENE_DOMINANT, CriteriaOp.EQ,  GeneType.EARTH)
      Criterion(CriteriaField.TRIPS_SURVIVED, CriteriaOp.LTE, 1)
    """
    field:    CriteriaField
    op:       CriteriaOp
    value:    GeneType | int | bool   # type depends on field

# CriteriaResolver(criteria: list[Criterion], rakshas: list[Raksha]) -> list[Raksha]
# Lives in engine/criteria.py; used by Game to resolve all three StandingOrders fields.

@dataclass
class TurnContext:
    """Read-only snapshot passed to Strategy.decide() each turn."""
    turn_number:      int
    soma:             int
    rakshas:          list[Raksha]
    recent_travelogs: list[Travelog]
    known_map:        dict[tuple[int, int], SquareRecord]
    turns_remaining:  int  # turns left in game
    # Strategies do NOT receive current_epoch — infer trap dominance from scouts.

@dataclass
class Civilization:
    id:           str
    name:         str
    soma:         int
    status:       CivilizationStatus = CivilizationStatus.ACTIVE
    extinct_turn: int | None         = None

@dataclass
class TurnSummary:
    turn_number:     int
    civilization_id: str
    soma_start:      int
    soma_end:        int
    pop_start:       int
    pop_end:         int
    deaths:          int
    trips_sent:      int
    trips_survived:  int
    soma_gathered:   int
    strategy_sumup:  str
    went_extinct:    bool = False
```

### Relationships

```
Game ──── 1 Labyrinth
     ──── N Civilization
               ├── 1 Strategy  (owns StandingOrders)
               └── M Raksha    (each has DNA)

Labyrinth ──── 100×100 Square grid
          ──── 1 current Epoch

Trip ──── 1 Raksha  ──→  produces  ──── 1 Travelog
Travelog accumulated per Civilization → TurnContext.known_map
```

**Center zone**: 4 squares — `(49,49)`, `(49,50)`, `(50,49)`, `(50,50)`. Stepping into any of them triggers the soma reward + teleport home.

**Path**: optional per trip. If omitted, Game generates a naive random walk (uniform random choice among the 4 cardinal neighbours at each step).

---

# Storage Model (SQLite)

```sql
CREATE TABLE games (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    turns_total  INTEGER NOT NULL,
    winner_civ   TEXT,
    played_at    TEXT    NOT NULL   -- ISO-8601
);

CREATE TABLE civilizations (
    id            INTEGER PRIMARY KEY,
    game_id       INTEGER NOT NULL REFERENCES games(id),
    name          TEXT    NOT NULL,
    strategy_type TEXT    NOT NULL,  -- 'GenAlg' | 'LLM'
    status        TEXT    NOT NULL DEFAULT 'active',  -- 'active' | 'extinct'
    extinct_turn  INTEGER           -- NULL while alive
);

CREATE TABLE epochs (
    id            INTEGER PRIMARY KEY,
    game_id       INTEGER NOT NULL REFERENCES games(id),
    dominant_type TEXT    NOT NULL,
    start_turn    INTEGER NOT NULL,
    end_turn      INTEGER          -- NULL while active
);

CREATE TABLE turns (
    id          INTEGER PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    turn_number INTEGER NOT NULL,
    epoch_id    INTEGER NOT NULL REFERENCES epochs(id)
);

CREATE TABLE turn_summaries (
    id             INTEGER PRIMARY KEY,
    turn_id        INTEGER NOT NULL REFERENCES turns(id),
    civ_id         INTEGER NOT NULL REFERENCES civilizations(id),
    soma_start     INTEGER NOT NULL,
    soma_end       INTEGER NOT NULL,
    pop_start      INTEGER NOT NULL,
    pop_end        INTEGER NOT NULL,
    deaths         INTEGER NOT NULL DEFAULT 0,
    trips_sent     INTEGER NOT NULL,
    trips_survived INTEGER NOT NULL,
    soma_gathered  INTEGER NOT NULL,
    strategy_sumup TEXT,
    went_extinct   INTEGER NOT NULL DEFAULT 0  -- 1 when this turn caused extinction
);

CREATE TABLE rakshas (
    id             TEXT    PRIMARY KEY,  -- UUID
    civ_id         INTEGER NOT NULL REFERENCES civilizations(id),
    dominant_gene  TEXT    NOT NULL,
    secondary_gene TEXT    NOT NULL,
    recessive_gene TEXT    NOT NULL,
    alive          INTEGER NOT NULL DEFAULT 1,
    parent_a_id    TEXT,
    parent_b_id    TEXT
);

CREATE TABLE trips (
    id            INTEGER PRIMARY KEY,
    turn_id       INTEGER NOT NULL REFERENCES turns(id),
    raksha_id     TEXT    NOT NULL REFERENCES rakshas(id),
    path_json     TEXT,              -- JSON [[x,y], ...]
    survived      INTEGER NOT NULL,
    soma_gathered INTEGER NOT NULL DEFAULT 0
);

-- Full accumulated map knowledge per civ per turn (enables replay)
CREATE TABLE map_snapshots (
    id             INTEGER PRIMARY KEY,
    turn_id        INTEGER NOT NULL REFERENCES turns(id),
    civ_id         INTEGER NOT NULL REFERENCES civilizations(id),
    knowledge_json TEXT    NOT NULL  -- JSON {"x,y": {trap, is_center}}
);
```

---

# Strategy Design

## StandingOrders

```python
@dataclass
class StandingOrders:
    """
    Orders the game engine executes at the turn boundary.

    Strategy.decide() writes to this object incrementally during its
    thinking window. Game reads it when the 3-min timer fires OR when
    decide() returns — whichever comes first.

    Safe fallback: if decide() never updates last_updated_turn for the
    current turn, Game re-uses the previous turn's orders verbatim and
    logs a warning. This prevents a hung or slow strategy from causing
    a null-action turn.
    """
    weed_criteria:          list[Criterion] = field(default_factory=list)
    send_criteria:          list[Criterion] = field(default_factory=list)
    reproduce_criteria:     list[Criterion] = field(default_factory=list)
    current_strategy_sumup: str             = ""
    last_updated_turn:      int             = -1   # -1 = never written
```

## Strategy (ABC)

```python
import time
from abc import ABC, abstractmethod

class Strategy(ABC):
    """
    Abstract base for all Civilization strategies.

    Lifecycle per turn:
      1. Game calls set_deadline(now + 180).
      2. Game launches decide(context) in a daemon thread.
      3. decide() writes to self.standing_orders at any point.
      4. When the thread joins (or the deadline fires), Game reads
         self.standing_orders and executes the engine turn loop.

    Subclasses MUST check should_stop() in any inner loop and return
    early — Game will not forcibly kill the thread.
    """

    def __init__(self) -> None:
        self.standing_orders: StandingOrders = StandingOrders()
        self._deadline: float = float("inf")

    # --- called by Game ---------------------------------------------------

    def set_deadline(self, deadline: float) -> None:
        """Unix timestamp after which the engine reads standing_orders as-is."""
        self._deadline = deadline

    @abstractmethod
    def decide(self, context: TurnContext) -> None:
        """
        Analyze context; update self.standing_orders before returning.
        Must respect should_stop() — return early when it is True.
        """
        ...

    # --- helpers for subclasses -------------------------------------------

    def time_remaining(self) -> float:
        return max(0.0, self._deadline - time.time())

    def should_stop(self) -> bool:
        """True when fewer than 1 second remain — use as loop guard."""
        return self.time_remaining() < 1.0

    def select_send_pool(self, candidates: list[Raksha], context: TurnContext) -> list[Raksha]:
        """Narrow send candidates after criteria resolve (default: all)."""
        return candidates
```

---

# GenAlgStrategy

```python
class GenAlgStrategy(Strategy):
    """
    Survival-of-the-fittest with genetic diversity floors.

    Core rules (no epoch oracle — learns from scout travelogs):
    - Track per-gene trip-survival rate from recent travelogs.
    - Maintain DIVERSITY_FLOOR (15%) for every gene type.
    - Weed: remove Rakshas whose dominant gene has the worst learned
      survival rate, but only down to the floor for that gene.
    - Scout phase (no travelogs yet): send one alive Raksha per dominant
      gene (up to 4) via select_send_pool().
    - Harvest phase: sort alive Rakshas by learned survival_rate DESC;
      send top ceil(HARVEST_RATIO × alive) via select_send_pool().
    - Reproduce: pair survivors biased toward best-inferred gene while
      preserving diversity floor fractions.
    """

    DIVERSITY_FLOOR: float = 0.15
    HARVEST_RATIO:   float = 0.70

    def decide(self, context: TurnContext) -> None:
        self._update_survival_rates(context.recent_travelogs, context.rakshas)
        counts = self._count_by_gene(context.rakshas)
        total  = len([r for r in context.rakshas if r.alive])

        weed  = self._build_weed_criteria(counts, total)
        send  = self._build_send_criteria()
        repro = self._build_repro_criteria()

        self.standing_orders = StandingOrders(
            weed_criteria          = weed,
            send_criteria          = send,
            reproduce_criteria     = repro,
            current_strategy_sumup = self._summarize(context, counts),  # inferred gene, not epoch
            last_updated_turn      = context.turn_number,
        )

    def select_send_pool(self, candidates, context) -> list[Raksha]:
        """Scout (one/gene) or harvest (top HARVEST_RATIO by learned rate)."""
        ...
```

---

# LLMStrategy

```python
class LLMStrategy(Strategy):
    """
    OLLAMA + Qwen strategy.

    Approach:
    - build_strategy_snapshot() serializes TurnContext + cumulative archetype
      survival + prior_blackboard (no epoch oracle).
    - Stream response; parse JSON once after stream completes.
    - Sliding HISTORY_TURNS chat window + durable blackboard for multi-turn intent.
    - LLM outputs criteria DSL; CriteriaResolver maps to Raksha lists (no UUIDs).

    Input snapshot (user JSON) includes:
      turn, soma, alive_count, turns_remaining,
      gene_counts, archetype_survival (64 triples),
      clone_counts, last_travelogs, soma_bearers,
      gene_survival_rates, known_trap_counts, recent_trips_summary,
      prior_blackboard (optional)

    Output JSON:
      {
        "reasoning": "...",
        "blackboard": {
          "phase": "scout|harvest|conserve",
          "hypothesized_trap": "FIRE|...|unknown",
          "current_plan": "...",
          "last_actions": "...",
          "next_intent": "..."
        },
        "weed_criteria": [...],
        "send_criteria": [...],
        "reproduce_criteria": [...],
        "strategy_sumup": "..."
      }
    """

    DEFAULT_MODEL  = "qwen3:14b"
    HISTORY_TURNS  = 3
    # Prompt in labyrinth/strategy/llm_prompt.py — field guide + workflow + blackboard
```

Key design decisions:
- **Empirical parity with GenBot sensing** — shared helpers in `empirical.py`; cumulative archetype survival on both strategies.
- **Blackboard** — LLM writes structured notes each turn; injected as `prior_blackboard` next turn (~500 char cap).
- **Structured `Criterion` DSL, not UUIDs** — same resolver as GenAlgStrategy.
- **Sliding history** — 3-turn window supplements blackboard; does not replace it.

---

# Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor UI as Tkinter UI (Spectator)
    participant G as Game
    participant C as Civilization
    participant S as Strategy
    participant L as Labyrinth
    participant DB as SQLite

    UI->>G: start_game(civs, turns_total)
    G->>L: __init__(100x100, seed_epoch)
    loop for each Civilization
        G->>C: __init__(name, strategy, soma=initial_soma(turns_total), rakshas=100)
    end
    G->>UI: render(turn=0, labyrinth)

    loop Turn 1 .. turns_total

        G->>UI: start_turn(n, epoch) [spectator sees epoch + full map]
        G->>S: set_deadline(now + 180s)

        loop each Civilization C

            alt C.status == EXTINCT
                G->>G: noop TurnSummary
            else ACTIVE
                G->>S: decide(TurnContext without epoch) [daemon thread]

                alt decide() joins before deadline
                    S-->>G: standing_orders fresh
                else deadline fires first
                    G->>S: read standing_orders as-is (last known)
                end

                G->>C: weed(standing_orders.weed_criteria)
                alt alive == 0 after weed
                    G->>C: mark_extinct(turn_number)
                else
                    G->>S: select_send_pool(candidates, context)
                    loop for each Raksha in send pool [parallel]
                        G->>L: run_trip(raksha, path or naive_random_walk)
                        loop each step (x,y) up to TRIP_MAX_STEPS=50
                            L->>L: resolve_trap(square, raksha.dna)
                            alt trap death
                                L-->>G: TripResult(died, partial_travelog)
                            else center zone reached
                                L-->>G: TripResult(survived, travelog, soma 1..10)
                            else TRIP_MAX_STEPS reached
                                L-->>G: TripResult(survived=True, hit_step_limit=True)
                            end
                        end
                    end
                    alt alive == 0 after trips
                        G->>C: mark_extinct(turn_number)
                    else
                        G->>C: reproduce(standing_orders.reproduce_criteria)
                    end
                end
                G->>C: deduct_soma(alive_count)
            end
        end

        G->>L: maybe_advance_epoch()
        G->>DB: insert(TurnSummary, trips, map_snapshot)
        G->>UI: render_turn(summary)

        alt all civs status == EXTINCT
            G->>DB: finalize_game(winner = null)
            note over G: Early game end
        end
    end

    G->>DB: finalize_game(winner = max soma among ACTIVE civs; null if none)
    G->>UI: show_final_scores()
```

---

# Game Loop & Tk Event Bridge

Two runtime mechanisms keep the simulation alive: the **game loop** that advances turns, and the **event bridge** that pushes engine state into the Tk GUI without freezing it.

---

## 1. Game Loop

### Big Idea

The game loop is the heartbeat of the simulation. Each call to `Game.next_turn()` runs one complete turn for every civilization in sequence:

1. **Strategy thinks** — `Strategy.decide()` runs in a daemon thread with a time budget (default 180 s). The engine waits for it, or reads whatever `StandingOrders` exist when the deadline fires.
2. **Weed** — Rakshas matching `weed_criteria` (plus any forced by Soma deficit) are killed.
3. **Trips** — Surviving Rakshas from `send_criteria` venture into the Labyrinth one by one; each result is merged back into the civilization's `known_map`.
4. **Reproduce** — `reproduce_criteria` pairs survivors; children are ready next turn.
5. **Sustenance** — 1 Soma per alive Raksha is deducted at turn end.
6. **Epoch tick** — Labyrinth checks whether the epoch should rotate.
7. **Persist** — `TurnSummary` + trip records are written to SQLite (if `db_path` is set).
8. **Notify GUI** — `events.on_turn_end(summaries)` fires; the Tk bridge delivers it to widgets on the main thread.

The loop is a plain `while current_turn < turns_total`. There is no hidden scheduler or coroutine — one blocking call = one turn.

### Diagram: How It Works in the App

```
LabyrinthApp._advance_turn()
        │
        └─► daemon thread: _run_turn_worker()
                    │
                    └─► Game.next_turn()
                              │
                    ┌─────────▼──────────────────────────────────────────┐
                    │  for each CivilizationState                        │
                    │                                                    │
                    │  ① strategy thread                                 │
                    │       set_deadline(now + 180 s)                    │
                    │       thread.start()  ← decide() writes orders     │
                    │       thread.join(timeout=180 s)                   │
                    │       read standing_orders (fresh or fallback)     │
                    │                                                    │
                    │  ② apply_weed(criteria) + mandatory_kill()         │
                    │       if alive == 0 → mark_extinct                 │
                    │                                                    │
                    │  ③ for each raksha in send_pool:                   │
                    │       labyrinth.run_trip(raksha)                   │
                    │       events.on_trip_result(civ_id, result) ──────►│──► queue
                    │       merge travelog → known_map                   │
                    │                                                    │
                    │  ④ apply_reproduce(criteria)                       │
                    │                                                    │
                    │  ⑤ deduct_sustenance()                             │
                    └────────────────────────────────────────────────────┘
                              │
                    labyrinth.tick_epoch()
                    repo.save_turn(...)
                    events.on_turn_end(summaries) ──────────────────────► queue
```

### Detailed Example from Code

`Game.next_turn()` is the single entry point — it increments the counter, fires the start event, and delegates per-civilization work:

```130:185:labyrinth/game.py
def next_turn(self) -> list[TurnSummary]:
    ...
    self.current_turn += 1
    ...
    for state in self.civilizations:
        summary = run_turn_for_civilization(
            state, self.labyrinth, self.current_turn, ...
        )
```

Inside `run_turn_for_civilization`, the strategy thread + deadline contract enforces the 3-minute thinking budget:

```261:272:labyrinth/engine/turn.py
    deadline = time.time() + thinking_seconds
    civ_state.strategy.set_deadline(deadline)

    thread = threading.Thread(
        target=_run_strategy_decide,
        args=(civ_state, context),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=thinking_seconds)

    orders, used_fallback = _get_orders(civ_state, turn_number)
```

The **fallback rule** — if `decide()` never wrote `last_updated_turn` for this turn, the previous turn's orders are reused and a warning is logged:

```142:153:labyrinth/engine/turn.py
def _get_orders(state: CivilizationState, turn_number: int) -> tuple[StandingOrders, bool]:
    """Return standing orders and whether fallback was used."""
    orders = state.strategy.standing_orders
    used_fallback = orders.last_updated_turn != turn_number
    if used_fallback:
        log.warning(
            "strategy.deadline_used",
            civilization=state.civilization.id,
            turn=turn_number,
            last_updated=orders.last_updated_turn,
        )
    return orders, used_fallback
```

---

## 2. Tk Event Bridge

### Big Idea

Tkinter is fundamentally single-threaded: **only the main thread may touch widgets**. The game engine runs on a daemon thread. If it tried to update a `Canvas` directly it would crash or corrupt the display.

The solution is a **thread-safe queue** (`queue.Queue`) paired with a **recurring Tk timer**:

- The engine fires `GameEvents` callbacks from the worker thread.
- Each callback calls `_dispatch(fn, *args)`, which puts `(fn, args)` into `_pending_main`.
- Every 50 ms, `self.after(50, _pump_main_queue)` drains the queue on the **main thread** and calls the actual widget-update methods.

`GameEvents` is a plain dataclass of callable fields — all no-op lambdas by default. This decouples the engine entirely from Tkinter; it works identically in tests with no GUI wired.

### Diagram: How It Works in the App

```
Worker thread                           Queue (_pending_main)    Tk main thread
──────────────────────────────────────  ──────────────────────   ─────────────────────────────────
game.next_turn()                                                 mainloop() running
  └─ events.on_trip_result(cid, r)  ──► put(_apply_trip_result)
  └─ events.on_turn_end(summaries)  ──► put(_apply_turn_end)
  └─ events.on_chapter(text)        ──► put(_apply_chapter)
                                                                 after(50) fires → _pump_main_queue()
                                                                   process_pending():
                                                                     → _apply_trip_result(cid, r)
                                                                         plot_tab.on_trip_result()
                                                                     → _apply_turn_end(summaries)
                                                                         plot_tab.on_turn_end()
                                                                         civs_tab.on_turn_end()
                                                                         commentary_tab.on_turn_end()
                                                                     → _apply_chapter(text)
                                                                         commentary_tab.on_chapter()
                                                                 after(50) re-arms → loops forever
```

### Detailed Example from Code

**Queue setup and the pump** — wired at app startup, before any game starts:

```55:66:labyrinth/gui/app.py
        self._pending_main: queue.Queue[tuple[object, tuple]] = queue.Queue()
        ...
        self.after(50, self._pump_main_queue)

    def _pump_main_queue(self) -> None:
        """Drain worker-thread callbacks on the Tk main thread."""
        self.process_pending()
        self.after(50, self._pump_main_queue)
```

`process_pending` drains the entire queue in one shot on each tick. `get_nowait()` is non-blocking; the `Empty` exception breaks the loop cleanly:

```165:172:labyrinth/gui/app.py
    def process_pending(self) -> None:
        """Run callbacks queued from background worker threads."""
        while True:
            try:
                fn, args = self._pending_main.get_nowait()
            except queue.Empty:
                break
            fn(*args)
```

**The dispatch helper** — the thin write-side of the bridge, callable from any thread:

```174:176:labyrinth/gui/app.py
    def _dispatch(self, fn, *args) -> None:
        """Queue a main-thread GUI update from a worker thread."""
        self._pending_main.put((fn, args))
```

**Event wiring** — connects `GameEvents` callbacks (fired by the engine) to `_dispatch`:

```178:185:labyrinth/gui/app.py
    def _wire_events(self) -> None:
        if self._events is None:
            return
        self._events.on_turn_start = lambda t, e: self._dispatch(self._apply_turn_start, t, e)
        self._events.on_trip_result = lambda c, r: self._dispatch(self._apply_trip_result, c, r)
        self._events.on_turn_end = lambda s: self._dispatch(self._apply_turn_end, s)
        self._events.on_game_end = lambda s: self._dispatch(self._apply_game_end, s)
        self._events.on_chapter = lambda t: self._dispatch(self._apply_chapter, t)
```

**`GameEvents`** — the decoupling contract that keeps the engine GUI-agnostic. All fields are callables, defaulting to no-op lambdas so the engine runs identically headless (in tests) or wired to a full GUI:

```151:173:labyrinth/domain/entities.py
@dataclass
class GameEvents:
    """Callback hooks decoupling engine from GUI."""

    on_turn_start: object = None
    on_trip_result: object = None
    on_turn_end: object = None
    on_game_end: object = None
    on_chapter: object = None
    on_civilization_extinct: object = None

    def __post_init__(self) -> None:
        if self.on_turn_start is None:
            self.on_turn_start = lambda *_: None
        if self.on_trip_result is None:
            self.on_trip_result = lambda *_: None
        if self.on_turn_end is None:
            self.on_turn_end = lambda *_: None
        if self.on_game_end is None:
            self.on_game_end = lambda *_: None
        if self.on_chapter is None:
            self.on_chapter = lambda *_: None
        if self.on_civilization_extinct is None:
            self.on_civilization_extinct = lambda *_: None
```

The engine fires `events.on_trip_result(civ_id, result)` from `_execute_trips()` in `turn.py` as **each Raksha returns** — so the GUI map updates live, trip by trip, rather than only at turn end:

```192:200:labyrinth/engine/turn.py
    for raksha in to_send:
        result = labyrinth.run_trip(raksha, rng)
        results.append(result)
        _merge_travelog(civ_state.civilization, result)
        events.on_trip_result(civ_state.civilization.id, result)
        if result.travelog.survived:
            survived_count += 1
        soma_gathered += result.travelog.soma_gathered
        civ_state.civilization.soma += result.travelog.soma_gathered
```

---

# Design Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Trap distribution | **Fixed at epoch start.** 10% of squares are traps; 75% of traps match the epoch dominant type, remainder split among other types. Center squares always free. Layout re-rolled on epoch change. |
| 2 | Trip length limit | **`TRIP_MAX_STEPS = 50`** (hard cap). If reached without trap death, Raksha **returns home alive** with partial `Travelog`, `hit_step_limit=True`, `survived=True`, and zero Soma. |
| 3 | Trip parallelism | **All civilizations' trips run simultaneously** in parallel thread pools. GUI updates fire as individual trip results arrive from any civilization. |
| 4 | DNA inheritance | Child draws one gene from `{parent_a.dominant, parent_a.secondary}` and one from `{parent_b.dominant, parent_b.secondary}`; assignment to child's dominant/secondary is random. Recessive drawn randomly from the union of both parents' three genes, excluding the two already assigned. |
| 5 | Mandatory weed enforcement | If `weed_criteria` leaves a Soma deficit after the strategy's orders are applied, Game auto-kills additional Rakshas in ascending order of `(trips_survived, trips_completed)` until the deficit is covered. |
| 6 | Reproduce pairing | `reproduce_criteria` selects an eligible **pool**; Game randomly pairs them. Odd one out is skipped. New Rakshas are available the **following** turn. |
| 7 | Replay semantics | Loading a saved game displays stored `TurnSummary` data turn-by-turn. No re-simulation. Individual trips are reconstructed from `path_json` + outcome stored in the `trips` table. |
| 8 | Start Soma | `INITIAL_SOMA = INITIAL_RAKSHAS × turns_total` (100 × 20 = 2000). Full-game sustenance runway at max population with zero labyrinth income. |
| 9 | Extinction | `alive == 0` → civilization extinct permanently. Skips strategy + turn actions thereafter. Game ends early if all civs extinct (`winner = null`). Only non-extinct civs with living Rakshas may win. |
| 10 | Weed timing | Strategic weed + mandatory deficit kill remain **at turn start** (before labyrinth). Sustenance deduction at turn end unchanged. |
| 11 | Send volume | Strategy decision only — no engine cap. `select_send_pool()` narrows criteria-matched candidates before trips. |
| 12 | Strategy epistemics | **Strategies never receive `current_epoch`.** They infer trap dominance from scout travelogs and `known_map`. The **spectator** (GUI, narrative) sees full state including epoch name and god-view labyrinth. |





