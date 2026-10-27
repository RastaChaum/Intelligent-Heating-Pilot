---
stage: specification
producer_agent: speckit.specify
critical_reviewer_agent: speckit.clarify
plan_reviewer_agent: speckit.checklist
tasks_reviewer_agent: speckit.analyze
implementation_reviewer_agent: speckit.review
review_status: pending
---

# Feature Specification: History Days Are Not Lost When the Recorder Fails or HA Shuts Down

**Feature Branch**: `fix/issue-187-recorder-extraction-retry`
**Created**: 2026-10-27
**Status**: Draft
**Input**: GitHub issue #187 — "Recorder extraction marks periods explored on errors and
cancellation; stale cycle cache"

## Context

IHP learns its heating slope (LHS) and dead time from heating cycles it extracts from the
Home Assistant Recorder history, one period (`task_range_days`, 7 days by default) at a time.
Every period it has looked at is remembered as *explored*, so it is never queried again. This
is what keeps the Recorder load low: a restart only extracts the days missing since the last
session, and a daily refresh extends the history backward by one period at a time.

Today, a period is also remembered as explored when its extraction **failed**:

- a Recorder timeout or database error while reading history (typically under load at
  startup) is swallowed, the extraction runs on an empty history, and the period is marked
  explored;
- a shutdown or a cancelled extraction (restart, unload, retention change) is turned into an
  ordinary error, and the interrupted period is marked explored too.

In both cases the heating cycles of those days are **never** learned: no later restart or
daily refresh looks at them again. On a common setup this silently removes up to a week of
learning data each time the Recorder is slow at startup.

The marking-on-failure exists for a valid reason: when the Recorder has purged a period
(older than its `purge_keep_days`), the history comes back empty and cycle extraction rejects
it. Without marking, the backfill would retry purged periods forever. That case must keep
working.

The third point of issue #187 (the in-memory cycles cache never being cleared after an
extraction) is already fixed on `integration` by commit `b2232f9` and covered by
`test_extracted_cycles_are_visible_to_anticipation_the_same_day`. It is out of scope here.

## Clarifications

### Session 2026-10-27

- Q: Which failures must leave a period unexplored (so it is retried), and which must still
  mark it explored? → A: Only a failure to **read** history (any adapter raising) leaves the
  period unexplored. A failure while extracting cycles from history that *was* read — which
  includes the purged-period case — still marks the period explored, because the same data
  would fail the same way on every retry.
- Q: When is an unexplored period retried? → A: At the next daily refresh, at most one
  `task_range_days` period per refresh, most recent first, in addition to the existing
  backfill step. Restarts keep retrying the startup window as they already do. No faster
  in-session retry: the learned slope and the cycles of previous sessions stay available in
  the meantime, so a day of delay costs little, while retrying a struggling Recorder sooner
  would add load at the worst moment.
- Q: The optional outdoor-temperature history already swallows its own read failures (a
  missing outdoor sensor must not block learning). Must a transient outdoor read failure
  also leave the period unexplored? → A: No, out of scope. Cycles are still learned; they
  only lack outdoor context for that period. Recorded as a known limitation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A slow Recorder at startup does not erase days of learning (Priority: P1)

Home Assistant restarts after a few days off. The Recorder is busy and times out when IHP
reads the history of the missing days. Those days must be extracted later instead of being
skipped forever.

**Why this priority**: This is the defect of issue #187: learning data is lost silently on a
common setup, which degrades the slope and dead time and therefore preheating accuracy.

**Independent Test**: Make the history read fail for a period, run the extraction, then run
a later refresh with a working Recorder and verify the cycles of that period are learned.

**Acceptance Scenarios**:

1. **Given** the history read of a period fails, **When** the extraction of that period
   ends, **Then** the period is not marked explored and no cycles are stored for it.
2. **Given** a period left unexplored by a failed read, **When** the next daily refresh
   runs, **Then** that period is extracted again and, on success, its cycles are stored and
   it is marked explored.
3. **Given** several periods failed, **When** a daily refresh runs, **Then** at most one
   `task_range_days` period is retried, the most recent one first.

### User Story 2 — A shutdown during extraction does not mark the interrupted period (Priority: P1)

Home Assistant stops, or the integration is reloaded, while IHP is reading history. The
interrupted period must stay unexplored, and the extraction must stop promptly instead of
running on as if the read had merely failed.

**Why this priority**: Same data loss as story 1, triggered by every restart that happens
during an extraction; it also delays shutdown.

**Independent Test**: Cancel the extraction while a history read is in progress and verify
the cancellation propagates and the period is not marked explored.

**Acceptance Scenarios**:

1. **Given** a history read is in progress, **When** the extraction is cancelled, **Then**
   the cancellation propagates out of the extraction (it is not converted into an ordinary
   error) and the period is not marked explored.
2. **Given** the extraction was cancelled, **When** the integration is cancelling its
   extractions, **Then** it completes without error as it does today.

### User Story 3 — Purged history still ends the backfill (Priority: P1)

The backfill reaches periods the Recorder has already purged. They must still be marked
explored so the backfill stops there, exactly as today.

**Why this priority**: Regression guard. Without it, every daily refresh would query purged
periods forever.

**Independent Test**: Run an extraction where the history read succeeds but returns nothing,
and verify the period is marked explored.

**Acceptance Scenarios**:

1. **Given** the history read succeeds but returns no data, **When** the extraction of that
   period ends, **Then** the period is marked explored.
2. **Given** the history read succeeds but cycle extraction fails on the data, **When** the
   extraction of that period ends, **Then** the period is marked explored and the failure is
   logged.

### Edge Cases

- **Mixed periods in one queue**: a failed read on one period does not prevent the following
  periods of the same queue from being extracted (current behavior, kept).
- **Fresh installation whose very first extraction fails**: nothing is explored yet; the
  daily refresh explores yesterday and today, and the existing backfill then walks back over
  the failed window. No special handling is needed.
- **VTherm entity unavailable at startup** (mapper cannot be selected): treated as a read
  failure, so the period is retried later instead of being lost.
- **Retry of a period that keeps failing to read**: retried once per daily refresh, one
  Recorder query per device per day at most; it never blocks the existing backfill step.
- **On-demand extraction** (`on_demand_extraction`): still raises when any period failed, as
  today; a failed read there no longer marks the period explored either.
- **Today and yesterday** are re-extracted by every daily refresh regardless of exploration
  (unchanged); the retry search therefore ends the day before yesterday.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A cancellation of a history read MUST propagate out of the history adapters
  unchanged; it MUST NOT be converted into an ordinary error.
- **FR-002**: When any history adapter fails while reading a period, the extraction of that
  period MUST fail as a whole: no cycles are extracted or stored for it.
- **FR-003**: A period whose history read failed MUST NOT be marked explored.
- **FR-004**: A period whose history read succeeded MUST be marked explored once its
  extraction ends, whether cycle extraction succeeded, found nothing, or failed.
- **FR-005**: A cancelled extraction MUST NOT mark the interrupted period explored.
- **FR-006**: Each daily refresh MUST retry the most recent unexplored period lying between
  the oldest explored day and the day before yesterday, limited to one `task_range_days`
  period, within the retention window.
- **FR-007**: The retry of FR-006 MUST run alongside the existing backfill step, without
  cancelling the recent-days refresh or the backfill.
- **FR-008**: A failed read MUST be logged at warning level with the period and the fact that
  it will be retried; this replaces the current log line that does not say so.

### Key Entities

- **Explored period**: a date range whose history was read successfully, whatever its
  outcome in cycles. It is the single source of truth for "never query this again".
- **Unexplored gap**: a date range inside the explored span, or inside the retention window,
  that is not explored. A gap left by a failed read is retried by the daily refresh.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a failed history read, 100% of the affected days are extracted again by
  a later refresh once the Recorder answers, with no restart needed.
- **SC-002**: A period that was being read during a shutdown is never marked explored.
- **SC-003**: Purged periods are queried at most once, as today: the backfill still ends at
  the Recorder retention boundary.
- **SC-004**: Without failures, the number of Recorder queries per device per day is
  unchanged; with failures, it grows by at most one per device per day.

## Assumptions

- Historical periods are immutable: reading the same period again returns the same data, so a
  cycle-extraction failure on successfully read data is deterministic and not worth retrying.
- The cache-invalidation part of issue #187 (point 3) is already fixed on `integration`.

## Known Limitations

- A transient failure of the optional outdoor-temperature read still yields cycles without
  outdoor context for that period (the period is explored). Distinguishing "outdoor sensor
  missing" from "Recorder timeout" is left for a follow-up.
- A storage failure while persisting extracted cycles is logged and swallowed by the cycle
  manager, so the period is still marked explored (pre-existing, unchanged).
