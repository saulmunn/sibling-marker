# Sibling Marker - Anki Addon

_Written entirely by Claude, skim-reviewed by Saul Munn._

Mark any cards as siblings, even across different notes. When you review one card, its custom siblings get buried for the day.

## Version 2.0 - Now with Sync!

Sibling groups are now stored as Anki tags, which means they **sync automatically** across all your devices via AnkiWeb.

## Installation

1. Download `sibling_marker_v2.ankiaddon`
2. In Anki: Tools → Add-ons → Install from file...
3. Select the downloaded file
4. Restart Anki

## Usage

### Marking Cards as Siblings

1. Open the Browser (Browse)
2. Select 2 or more cards from different notes
3. Right-click → **Sibling Marker** → **Mark as Siblings**

The cards' notes will be tagged with a `sibling::` tag (e.g., `sibling::a1b2c3d4`).

### Named Groups

You can give your sibling groups meaningful names:

1. Right-click → **Sibling Marker** → **Mark as Siblings (with name)...**
2. Enter a name like `anatomy_bones` or use hierarchy: `anatomy::bones`

This creates tags like `sibling::anatomy_bones` or `sibling::anatomy::bones`.

### Viewing Groups

- **Tools → Sibling Marker: View Groups** - See all sibling groups
- **Tag sidebar** - Your sibling groups appear under the `sibling` tag hierarchy

### Removing Cards from Groups

1. Select cards in the Browser
2. Right-click → **Sibling Marker** → **Remove from Sibling Group**

Or simply remove the `sibling::*` tag from the note manually.

## How It Works

When you answer a card during review:
1. The addon checks if the card's note has any `sibling::*` tags
2. It finds all other notes with the same tag(s)
3. It buries all cards from those sibling notes that are due today

## Tag Hierarchy

Anki supports hierarchical tags using `::` as a separator. You can organize sibling groups like:

```
sibling::anatomy::bones
sibling::anatomy::muscles
sibling::languages::spanish
sibling::languages::french
```

These display as a collapsible tree in Anki's tag sidebar.

## Sync

Since v2.0, sibling relationships are stored as tags, which sync via AnkiWeb like any other tag. This means:

- Your sibling groups sync to all your devices automatically
- You can view and edit sibling groups on AnkiMobile/AnkiDroid by editing tags
- No separate data files to manage

## Migration from v1.x

If you're upgrading from v1.x (which used local JSON storage), the addon will automatically migrate your existing sibling groups to tags on first run. You'll see a notification when this happens.

Your old data file (`user_files/sibling_groups.json`) will be renamed to `.migrated` after successful migration.

## Notes

- **Per-note, not per-card**: Tags are applied to notes, so all cards from a note share the same sibling relationships
- **Native siblings still work**: Anki's built-in sibling burying for cards from the same note works as usual
- **Safe**: The addon only uses official Anki APIs and never modifies your collection directly

## Troubleshooting

**Cards aren't being buried:**
- Make sure both notes have the same `sibling::*` tag
- Check that the sibling cards are due today (or are new/learning)
- Cards that are already buried or suspended won't be buried again

**Migration didn't work:**
- Check if `user_files/sibling_groups.json.migrated` exists (means migration ran)
- If the original `.json` file still exists, migration may have failed - check Anki's debug console for errors
