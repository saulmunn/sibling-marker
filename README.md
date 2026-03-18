# Sibling Marker - Anki Addon

_Written entirely by Claude, skim-reviewed by Saul Munn._

Mark any cards as siblings, even across different notes. The addon enforces priority-based separation so you never see two siblings on the same day.

## How It Works

Sibling groups are stored as Anki tags with a `sibling::` prefix, so they **sync automatically** via AnkiWeb. The addon separates siblings using a three-tier priority system that runs at sync time (before and after) and on profile load:

**Priority: Learning > Review > New**

| Situation | New siblings | Review siblings | Learning siblings |
|---|---|---|---|
| Learning card active | Suspended | Buried for today | Only 1 kept; extras buried |
| Review card due (no learning) | Suspended | Only 1 kept; extras rescheduled to tomorrow | — |
| Only new cards | Only 1 active; extras suspended | — | — |

When you finish all active cards in a group, the addon automatically **unsuspends the next sibling** in the queue. This means siblings are introduced one at a time as you work through them.

Cards suspended by the addon are tracked with a `sibling-suspended::` tag so they can be distinguished from cards you suspended manually.

## Installation

1. Download `sibling_marker_v4.ankiaddon`
2. In Anki: Tools → Add-ons → Install from file...
3. Select the downloaded file
4. Restart Anki

## Usage

### Marking Cards as Siblings

1. Open the Browser (Browse)
2. Select 2 or more cards from different notes
3. Right-click → **Sibling Marker** → **Mark as Siblings**

The cards' notes will be tagged with a `sibling::` tag (e.g., `sibling::a1b2c3d4`). Separation is applied immediately: new cards beyond the first are suspended, and review cards due on the same day are spread across consecutive days.

### Named Groups

You can give your sibling groups meaningful names:

1. Right-click → **Sibling Marker** → **Mark as Siblings (with name)...**
2. Enter a name like `anatomy_bones` or use hierarchy: `anatomy::bones`

This creates tags like `sibling::anatomy_bones` or `sibling::anatomy::bones`.

### Adding to an Existing Group

1. Select cards in the Browser
2. Right-click → **Sibling Marker** → **Add to Existing Group...**
3. Pick from a list of your current groups

### Group Manager

**Tools → Sibling Marker: View Groups** opens a two-pane dialog:

- **Left pane**: All sibling groups with note counts
- **Right pane**: For the selected group, each note's first field and detailed card states (e.g., "new · active", "new · suspended (sibling)", "review · due today", "review · in 3 days")

From here you can **rename**, **delete**, or **browse** a group in the card browser. Deleting a group unsuspends any cards the addon had suspended.

### Removing Cards from Groups

1. Select cards in the Browser
2. Right-click → **Sibling Marker** → **Remove from Sibling Group**

This removes both the `sibling::` and `sibling-suspended::` tags and unsuspends any cards the addon had suspended.

### Reviewer Indicator

During review, a small indicator appears at the bottom of the screen showing how many siblings are waiting in each group (e.g., "anatomy · 2 siblings waiting").

## Sync and Mobile

Separation runs **before and after every sync**:

- **Before sync**: Ensures local state is correct before uploading
- **After sync**: Handles changes that arrived from mobile (e.g., a card reviewed on AnkiMobile triggers the next sibling to unsuspend)

Since suspension and rescheduling both sync via AnkiWeb, siblings stay separated even when reviewing on mobile. Burying does *not* sync, which is why the addon prefers suspension and rescheduling for durable separation.

## Tag Hierarchy

Anki supports hierarchical tags using `::` as a separator:

```
sibling::anatomy::bones
sibling::anatomy::muscles
sibling::languages::spanish
sibling::languages::french
```

These display as a collapsible tree in Anki's tag sidebar.

## Migration from v1.x

If you're upgrading from v1.x (which used local JSON storage), the addon will automatically migrate your existing sibling groups to tags on first run. You'll see a notification when this happens.

Your old data file (`user_files/sibling_groups.json`) will be renamed to `.migrated` after successful migration.

## Notes

- **Per-note, not per-card**: Tags are applied to notes, so all cards from a note share the same sibling relationships
- **Native siblings still work**: Anki's built-in sibling burying for cards from the same note works as usual
- **Safe**: The addon only uses official Anki APIs and never modifies your collection directly
- **Qt 5 and Qt 6**: The addon handles both Qt versions for cross-platform compatibility

## Troubleshooting

**Cards aren't being separated:**
- Make sure both notes have the same `sibling::*` tag
- Separation runs at sync time and profile load, not during review — try syncing
- Check `sibling_marker.log` in the addon folder for details

**A card is stuck suspended:**
- Open the Group Manager (Tools → Sibling Marker: View Groups) to see card states
- If a card shows "suspended (user)", the addon won't touch it — you suspended it manually
- If it shows "new · suspended (sibling)", it's waiting its turn in the queue

**Migration didn't work:**
- Check if `user_files/sibling_groups.json.migrated` exists (means migration ran)
- If the original `.json` file still exists, migration may have failed — check Anki's debug console for errors
