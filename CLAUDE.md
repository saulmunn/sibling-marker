# Sibling Marker — Anki Addon

## Build

```bash
zip -r sibling_marker_v4.ankiaddon __init__.py manifest.json
```

Only `__init__.py` and `manifest.json` go in the package. Install via Anki → Tools → Add-ons → Install from file.

## Architecture

**Single-file addon** — all logic lives in `__init__.py` (~1,340 lines). No external dependencies beyond Anki's own libraries (`aqt`, `anki`).

**Tag-based storage (v2.0):** Sibling relationships are stored as native Anki tags so they sync via AnkiWeb:
- `sibling::groupname` — marks membership in a sibling group
- `sibling-suspended::groupname` — tracks addon-suspended cards (vs user-suspended)

**Priority-based separation** runs at sync time and profile load:
1. If any **learning** cards exist → suspend new siblings, bury review siblings due today, bury extra learning siblings
2. Else if any **review** cards are due today → suspend new siblings, reschedule extra reviews to tomorrow
3. Else (only new/suspended) → keep 1 new card active, suspend the rest

**Hooks registered** (end of file):
- `sync_will_start` / `sync_did_finish` — enforce separation before upload & after download
- `profile_did_open` — migration + initial enforcement
- `browser_will_show_context_menu` — right-click menu for marking/managing siblings
- `reviewer_did_show_question` — JS-injected sibling indicator during review
- `main_window_did_init` — Tools menu entry for group manager

## Key constants

```python
TAG_PREFIX = "sibling::"
SUSPENDED_TAG_PREFIX = "sibling-suspended::"
```

## Anki card queue values

```
-3  Buried (scheduler)   — don't touch
-2  Buried (user)        — don't touch
-1  Suspended            — used for new sibling separation & tracking
 0  New                  — suspend extras, unsuspend when next in queue
 1  Learning (intraday)  — bury extras via sched.bury_cards()
 2  Review               — reschedule extras to future dates
 3  Day learning         — bury if due today
```

Card type: `0` = new, `1` = learning, `2` = review.

## Qt5 / Qt6 compatibility

All Qt enum access uses try/except fallback:

```python
try:
    val = QMessageBox.StandardButton.Yes   # Qt6
except AttributeError:
    val = QMessageBox.Yes                  # Qt5
```

Same pattern for `Qt.Orientation`, `Qt.ItemDataRole`, `Qt.AlignmentFlag`, `QFrame.Shape`, etc.

## Key code sections

| Lines | Section |
|-------|---------|
| 27-34 | Configuration constants |
| 62-96 | Tag utilities |
| 98-183 | Core functions (get groups, find cards) |
| 184-419 | User actions (mark, remove, add) |
| 420-746 | Separation logic |
| 748-829 | v1.x → v2.0 migration |
| 831-883 | Sync hooks |
| 885-1220 | UI (browser menu, group manager dialog) |
| 1257-1329 | Reviewer indicator (JS injection) |
| 1332-1343 | Hook registration |
