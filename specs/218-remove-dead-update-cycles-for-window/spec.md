---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: One Extraction Path and One Dead Time Writer for Heating Cycles

**Feature Branch**: `fix/issue-218-remove-dead-update-cycles-for-window`
**Created**: 2026-10-31
**Status**: Draft
**Input**: GitHub issue #218 — "Split cycles: first sub-cycle slope inflated by dead time;
remove dead update_cycles_for_window"

## Context

Issue #218 has two points.

**Point 1** (first split sub-cycle slope inflated by the dead time) is fixed on `integration`
by #245: the heating phase is split from the end of the dead time, and the BDD scenario
"Split cycles keep the heating slope of the heating phase"
(`tests/features/cycle_dead_time_and_slope.feature`) covers it.

**Point 2** is still open. `HeatingCycleLifecycleManager.update_cycles_for_window` has no
caller in `custom_components/`, only in tests. Its docstring claims it is called at startup,
on a retention change and by the 24-hour refresh, which is false: all three go through
`refresh_heating_cycle_cache` / `trigger_24h_refresh`, the `RecordingExtractionQueue` and
`_on_cycles_extracted`.

The method is not only unused, it is a second, divergent write path:

- It reads the Recorder directly through `_extract_cycles`, bypassing the extraction queue,
  its global semaphore (OOM guard) and the explored-dates tracking (#187).
- It stores the learned dead time from the extracted batch only, the pattern #185 removed
  from the live path, and it has none of the #224 safeguards (an unchanged value is not
  rewritten nor announced). It duplicates `_persist_learned_dead_time` line for line
  otherwise.

A future caller would silently bring these defects back. Seven tests and the cache
architecture document still present it as the way cycles are stored.

## Clarifications

### Session 2026-10-31

- Q: Remove the method, or route it through `_persist_learned_dead_time` as the issue also
  suggests? → A: Remove it. Nothing calls it, and routing only its dead time would still
  leave a Recorder read outside the extraction queue. The live path already covers every
  trigger the docstring lists.
- Q: What about `_extract_cycles`? → A: Removed too: `update_cycles_for_window` is its only
  caller. Its imports (`HistoricalDataKey`, `HistoricalDataSet`) go with it. The
  `historical_adapters` and `heating_cycle_service` constructor arguments stay: the
  extraction queues receive them.
- Q: What happens to the tests that call `update_cycles_for_window`? → A: They are removed.
  What they checked is kept on the live path: the averaging and the filtering of invalid dead
  times are covered by the domain tests of `DeadTimeCalculationService`; the two guards of the
  write itself (no cycle with a dead time, auto-learning disabled: nothing stored, nothing
  announced) are tested on `_persist_learned_dead_time`, which every live trigger calls.
- Q: `tests/unit/application/test_heating_cycle_lifecycle_manager.py.backup` also calls the
  method. Keep it? → A: Remove it. It is a tracked copy of an old version of the test file,
  never collected by pytest, and the last place presenting the method as tested.
- Q: Does #218 close with this change? → A: Yes. Point 1 was fixed by #245, point 2 is this
  change.
- Q: Is there a user-visible change? → A: No. The CHANGELOG gets a Maintenance entry only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A contributor finds a single way cycles are stored (Priority: P1)

A contributor looking for where heating cycles and the learned dead time are written finds
one path: extraction queue → `_on_cycles_extracted` (or pruning in
`refresh_heating_cycle_cache`) → `_trigger_lhs_cascade` and `_persist_learned_dead_time`.

**Why this priority**: The unused method is documented as the main write operation. Calling
it would reintroduce #185 and #224 and bypass the Recorder guards.

**Independent Test**: Search the code, the tests and the architecture documentation for
`update_cycles_for_window` and `_extract_cycles`.

**Acceptance Scenarios**:

1. **Given** the integration code, **When** it is searched for the removed methods, **Then**
   neither is defined nor called.
2. **Given** `docs/architecture/CACHE_SYSTEM.md`, **When** it describes how the cycle cache is
   populated, **Then** it names the extraction queue and `_on_cycles_extracted`.

### User Story 2 — Dead time learning keeps its guards (Priority: P1)

The learned dead time is stored only from cycles that carry a dead time, and only when
auto-learning is enabled, on the path the integration really uses.

**Independent Test**: Call `_persist_learned_dead_time` with cycles without a dead time, then
with auto-learning disabled.

**Acceptance Scenarios**:

1. **Given** cached cycles none of which has a positive dead time, **When** the dead time is
   learned, **Then** nothing is stored and no update is announced.
2. **Given** auto-learning disabled and cycles with a dead time, **When** the dead time is
   learned, **Then** nothing is stored and no update is announced.

### Edge Cases

- **Constructor arguments**: `historical_adapters` and `heating_cycle_service` are still
  passed on to every extraction queue; removing `_extract_cycles` must not drop them.
- **Comments in kept tests** that say "never calls `_extract_cycles()`" must not name a
  method that no longer exists.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `HeatingCycleLifecycleManager` MUST NOT define `update_cycles_for_window` nor
  `_extract_cycles`.
- **FR-002**: `_persist_learned_dead_time` MUST remain the only code storing a learned dead
  time computed from cycles (`reset_learning` still clears it).
- **FR-003**: The guards of FR-002 (no cycle with a dead time, auto-learning disabled) MUST be
  tested on `_persist_learned_dead_time`.
- **FR-004**: No test, docstring or document under `custom_components/`, `tests/` and `docs/`
  MAY name the removed methods.
- **FR-005**: `docs/architecture/CACHE_SYSTEM.md` MUST describe the real population of the
  cycle cache (extraction queue, `_on_cycles_extracted`, learning from all cached cycles) and
  the real read on a cache miss (an empty list, no Recorder query).

### Key Entities

- **Live write path**: `refresh_heating_cycle_cache`, `trigger_24h_refresh`,
  `on_demand_extraction` → `RecordingExtractionQueue` → `_on_cycles_extracted`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `grep -rn "update_cycles_for_window\|_extract_cycles(" custom_components tests docs`
  returns nothing.
- **SC-002**: The whole test suite passes; no behavior change.
- **SC-003**: One call site of `set_learned_dead_time` with a learned value in
  `custom_components/` (today: two).

## Assumptions

- No external code (other integrations, scripts) calls `HeatingCycleLifecycleManager`
  methods: it is an internal class of the integration.

## Out of Scope

- The other dead code listed in #200 (`view.py`, unused `HeatingApplication` members,
  constants…).
- The rest of `docs/architecture/CACHE_SYSTEM.md` (performance table, recommendations).
