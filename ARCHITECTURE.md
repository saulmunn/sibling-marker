# Sibling Marker - Architecture & Logic

## Overview

Sibling Marker is an Anki addon that allows marking cards from **different notes** as "siblings" so they won't appear on the same day. This extends Anki's native sibling burying (which only works for cards from the same note) to work across notes.

## Design Goals

1. **Cross-platform sync**: Sibling relationships and separation must work on mobile (AnkiMobile/AnkiDroid) without the addon installed
2. **No same-day siblings**: At most one sibling per group should appear on any given day
3. **Priority ordering**: Learning > Review > New (higher priority cards take precedence)
4. **Minimal intervention**: Only modify card state at sync time, not during reviews

---

## Data Model

### Storage: Tags

All sibling relationships are stored as **Anki tags** on notes. This enables native sync support.

| Tag Pattern | Purpose |
|-------------|---------|
| `sibling::<group_name>` | Marks a note as belonging to a sibling group |
| `sibling-suspended::<group_name>` | Tracks cards we suspended (to distinguish from user-suspended cards) |

**Examples:**
- `sibling::a1b2c3d4` - Auto-generated group ID
- `sibling::bayes-thm` - Named group
- `sibling::probability::monotonicity` - Hierarchical group name

### Why Tags?

1. **Tags sync natively** - No custom sync logic needed
2. **Tags are note-level** - All cards from a note share sibling relationships (intentional)
3. **User-visible** - Users can see/edit relationships via tag sidebar
4. **Searchable** - Can find all cards in a group with `tag:sibling::groupname`

---

## Card States & Queues

Understanding Anki's card queues is essential:

| Queue | Meaning | Our Handling |
|-------|---------|--------------|
| 0 | New | Suspend extras (keeps 1 active) |
| 1 | Learning (intraday) | Bury extras (keeps 1 active) |
| 2 | Review | Reschedule extras to tomorrow |
| 3 | Day-learning | Bury if due today |
| -1 | Suspended | Check if ours via tag |
| -2 | Buried (user) | Don't touch |
| -3 | Buried (scheduler) | Don't touch |

### Why Suspend vs Bury?

- **Suspension syncs** to mobile - use for new cards
- **Burying doesn't sync** - use for same-day desktop separation only
- **Rescheduling syncs** - use for review cards (changes `due` field)

---

## Core Logic: Priority-Based Separation

All separation logic runs at **sync time** via `apply_priority_based_separation()`.

### Priority Rules

For each sibling group, we check what card types exist and apply rules:

```
IF any LEARNING cards exist:
    → Suspend all NEW siblings (syncs to mobile)
    → Bury all REVIEW siblings due today (desktop only)
    → Bury extra LEARNING siblings (keep first one)

ELSE IF any REVIEW cards due today:
    → Suspend all NEW siblings
    → Reschedule extra REVIEW cards to tomorrow (syncs)

ELSE (only new cards or suspended-new):
    → Ensure only 1 NEW card is active
    → If none active but suspended exist → unsuspend 1
```

### Why This Priority?

- **Learning cards are "in progress"** - they'll appear multiple times today, so protect siblings
- **Review cards are one-time today** - after reviewing one, others can wait until tomorrow
- **New cards are lowest priority** - they can wait indefinitely

---

## Sync Hooks

### `on_sync_will_start`

Runs **before** sync uploads local changes.

1. Calls `apply_priority_based_separation()`
2. Ensures local state is correct before syncing
3. Suspended cards and rescheduled due dates will sync to server

### `on_sync_did_finish`

Runs **after** sync downloads remote changes.

1. Calls `apply_priority_based_separation()` again
2. Handles cards reviewed on mobile:
   - Mobile review changed card from new → learning/review
   - Our suspended siblings need state updated
3. Unsuspends next sibling if previous one was reviewed

---

## Key Functions

### `get_all_sibling_groups() → dict`

Returns `{group_name: [note_id, ...]}`

- Searches for notes with `tag:sibling::*`
- Groups notes by their sibling group tags
- A note can be in multiple groups

### `apply_priority_based_separation() → dict`

Main separation logic. For each group:

1. Categorize all cards: learning, review_due, new, suspended_new
2. Apply priority rules (see above)
3. Return counts of actions taken

### `suspend_new_card_siblings(group_name, card_ids) → int`

Used when **marking new siblings**:

- Suspends all but the first new card
- Adds `sibling-suspended::` tracking tag

### `spread_review_card_due_dates(group_name) → int`

Used when **marking new siblings**:

- Spreads review cards across consecutive days
- Card 1: today, Card 2: tomorrow, Card 3: day after, etc.

### `remove_from_sibling_group(card_ids) → bool`

- Removes both `sibling::` and `sibling-suspended::` tags
- Unsuspends any cards we had suspended

---

## User Workflows

### Marking Cards as Siblings

1. User selects 2+ cards in Browser (from different notes)
2. Right-click → Sibling Marker → Mark as Siblings
3. Addon adds `sibling::<group>` tag to all notes
4. Addon immediately applies separation:
   - Suspends extra new cards
   - Spreads review card due dates

### Daily Flow (Desktop + Mobile)

1. **Morning**: User opens Anki on desktop
2. **Auto-sync triggers** → `on_sync_will_start`
   - Separation logic runs
   - Only 1 sibling per group is "active" for today
3. **User reviews on mobile** (no addon)
   - Suspended cards remain suspended
   - Active card gets reviewed, transitions to learning/review
4. **Evening**: User syncs desktop
   - `on_sync_did_finish` runs
   - Detects the reviewed card changed state
   - Unsuspends next sibling in sequence

### Mobile-Only Users

The addon only runs on desktop, but mobile users still benefit:

- New card siblings are **suspended** (syncs to mobile)
- Review card siblings are **rescheduled** (due date syncs)
- Learning/review burying is desktop-only (acceptable limitation)

---

## Edge Cases Handled

| Scenario | Behavior |
|----------|----------|
| Card in multiple groups | Processed for each group independently |
| User manually unsuspends our card | Re-suspended at next sync (2 active new cards detected) |
| All siblings reviewed | Group becomes inactive, no actions taken |
| Empty group (cards deleted) | Gracefully ignored |
| Sync fails | Local changes persist, reconciled on next successful sync |
| Native siblings (same note) | Anki handles these; we handle cross-note |

---

## File Structure

```
sibling-marker/
├── __init__.py          # Main addon code
├── manifest.json        # Addon metadata
├── sibling_marker.log   # Debug log (created at runtime)
└── sibling_marker_v4.ankiaddon  # Packaged addon
```

---

## Configuration

Currently hardcoded in `__init__.py`:

```python
TAG_PREFIX = "sibling::"
SUSPENDED_TAG_PREFIX = "sibling-suspended::"
DEBUG_MODE = False
```

---

## Limitations

1. **Tags are note-level**: Can't have different sibling relationships for different cards of the same note
2. **Learning card burying doesn't sync**: Mobile won't see buried learning siblings
3. **No undo**: Removing from group is manual
4. **Log file grows forever**: No rotation implemented

---

## Version History

- **v1.0**: JSON-based storage (local only)
- **v2.0**: Tag-based storage (syncs), priority-based separation, sync-time-only logic
