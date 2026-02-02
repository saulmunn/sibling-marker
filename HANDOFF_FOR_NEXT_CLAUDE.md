# Sibling Marker - Project Context

This document provides context for AI assistants working on this Anki addon.

## What This Addon Does

**Sibling Marker** lets users mark cards from different notes as "siblings." When you review one card, its custom siblings get buried (hidden) for the day—just like Anki's native sibling burying, but across notes.

**Use case:** Prevent seeing related cards too close together during review, even when they come from different notes.

## Current Implementation (v2.0)

### Storage: Anki Tags

Sibling groups are stored as tags with the prefix `sibling::`:
- `sibling::a1b2c3d4` (auto-generated)
- `sibling::anatomy::bones` (user-named with hierarchy)

**Why tags?**
- Native sync via AnkiWeb
- User-visible in tag sidebar
- Editable on mobile (AnkiMobile/AnkiDroid)
- Supports Anki's tag hierarchy (`::` separator)
- No external files to manage

**Limitation:** Tags are per-note, not per-card. All cards from a tagged note share the same sibling relationships.

### Core Flow

1. **Marking siblings:** User selects cards in Browser → right-click → "Mark as Siblings" → addon adds `sibling::groupname` tag to each card's note
2. **Burying:** When a card is answered, addon finds all notes with matching `sibling::*` tags and buries their due cards

### Key Functions

```python
# Find sibling groups for a card
def get_sibling_groups_for_card(card_id: int) -> List[str]

# Get all cards in a sibling group  
def get_cards_for_sibling_group(group_name: str) -> List[int]

# Bury siblings (called on card answer)
def bury_custom_siblings(card: Card) -> int
```

### Hooks Used

- `gui_hooks.browser_will_show_context_menu` - Add context menu
- `gui_hooks.reviewer_did_answer_card` - Trigger burying
- `gui_hooks.main_window_did_init` - Setup Tools menu
- `gui_hooks.profile_did_open` - Run migration

## Migration from v1.x

v1.x stored data in `user_files/sibling_groups.json`. v2.0 automatically migrates this to tags on first run:

1. Reads old JSON file
2. Converts each group to a `sibling::groupname` tag
3. Renames old file to `.migrated`

## Technical Reference

### Anki Card Queue Values
```
-3 = sched buried (manually)
-2 = user buried (sibling)  
-1 = suspended
 0 = new
 1 = learning
 2 = review
 3 = day learn
 4 = preview
```

### Tag Operations
```python
# Add tag to note
note.tags.append("sibling::my_group")
mw.col.update_note(note)

# Find notes with tag
note_ids = mw.col.find_notes('"tag:sibling::*"')
```

### Bury Cards
```python
mw.col.sched.bury_cards([card_id1, card_id2, ...])
```

## Alternative Approaches Considered

| Approach | Pros | Cons | Status |
|----------|------|------|--------|
| **Tags** | Syncs, visible, mobile-editable | Per-note only | **Implemented** |
| Media folder JSON | Syncs, per-card | Hidden, conflict risk, sync quirks | Rejected |
| Note field | Syncs | Requires modifying note types | Rejected |
| `card.custom_data` | Per-card, syncs | Hidden, newer Anki only | Rejected |

## File Structure

```
sibling-marker/
├── __init__.py           # Main addon code
├── manifest.json         # Anki addon metadata
├── README.md             # User documentation
├── sibling_marker_v2.ankiaddon  # Installable package
└── sibling-marker-addon/ # Old v1.x package (archived)
```

## Building the Addon

```bash
zip -r sibling_marker.ankiaddon __init__.py manifest.json README.md
```

Files must be at the root of the zip (not in a subfolder).
