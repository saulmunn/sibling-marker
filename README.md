# Sibling Marker - Anki Addon

_Written entirely by Claude, skim-reviewed by Saul Munn._

Mark any cards as siblings, even if they're from different notes. When you review one card, its custom siblings are automatically buried for the day.

## Installation

### Option 1: Using Anki's installer (easiest)

1. In Anki, go to **Tools → Add-ons → Install from file...**
2. Select the `sibling_marker.ankiaddon` file
3. Restart Anki

### Option 2: Manual installation

1. Find your Anki addons folder:
   - **Windows:** `%APPDATA%\Anki2\addons21\`
   - **Mac:** `~/Library/Application Support/Anki2/addons21/`
   - **Linux:** `~/.local/share/Anki2/addons21/`

2. Extract `sibling_marker.ankiaddon` (it's a zip file)

3. Copy the extracted `anki_sibling_marker` folder into your `addons21/` folder

4. Restart Anki

## Usage

### Mark Cards as Siblings

1. Open the **Browser** (Browse button or Ctrl+B)
2. Select 2 or more cards you want to mark as siblings
3. Right-click → **Sibling Marker** → **Mark as Siblings**

You can also give the group a custom name using "Mark as Siblings (with name)..."

### Add Cards to Existing Group

1. Select cards in the Browser
2. Right-click → **Sibling Marker** → **Add to Existing Group...**
3. Choose which group to add them to

### Remove Cards from Sibling Groups

1. Select cards in the Browser  
2. Right-click → **Sibling Marker** → **Remove from Sibling Group**

### View Sibling Info

- **For specific cards:** Select cards → Right-click → **Sibling Marker** → **Show Sibling Info**
- **For all groups:** Tools menu → **Sibling Marker: View Groups**

### Cleanup Deleted Cards

If you delete cards that were in sibling groups:
- Tools menu → **Sibling Marker: Cleanup Deleted Cards**

This removes stale references to cards that no longer exist.

## How It Works

- Sibling relationships are stored in a JSON file inside the addon folder
- When you review a card, the addon checks if it belongs to a custom sibling group
- If so, all other cards in that group that are due today (or are new/learning cards) get buried
- Buried cards will appear again tomorrow (or you can unbury manually)

## Safety Features (v1.1.0)

This addon includes several safeguards:

- **Atomic file writes**: Data is written to a temp file first, then renamed. This prevents corruption if Anki crashes mid-save.
- **Automatic backups**: Before each save, the previous data is backed up. If the main file becomes corrupted, it auto-recovers from backup.
- **Data validation**: On every load, the data structure is validated and repaired if needed.
- **Type consistency**: Card IDs are normalized to prevent lookup failures.
- **Stale reference cleanup**: Deleted cards can be cleaned up via the Tools menu.
- **Error logging**: All errors are logged to the console for debugging.
- **Qt compatibility**: Works with both older PyQt5 and newer PyQt6.

## Debug Mode & Tests

To enable debug mode and run the built-in tests:

1. Edit `__init__.py`
2. Change `DEBUG_MODE = False` to `DEBUG_MODE = True`
3. Restart Anki
4. Tools menu → **Sibling Marker: Run Tests**

Tests verify:
- Data structure validity
- Data validation and repair
- Orphan cleanup
- Save/load roundtrip integrity
- Type consistency

## Data Storage

Data is stored in:
```
<addon_folder>/user_files/sibling_groups.json
```

Format:
```json
{
  "version": 1,
  "groups": {
    "group_name": [card_id1, card_id2, ...],
    "another_group": [card_id3, card_id4, ...]
  },
  "card_to_group": {
    "card_id1": "group_name",
    "card_id2": "group_name",
    ...
  }
}
```

## Notes

- This works alongside Anki's built-in sibling burying (doesn't interfere)
- Sibling data is stored locally and won't sync between devices
- If a group is reduced to 1 card (by removing cards), it's automatically deleted
- Groups are buried on answer, not on card display

## Compatibility

- Requires Anki 2.1.50 or newer
- Works with V2 and V3 schedulers
- Works with FSRS
- Works with PyQt5 and PyQt6

## Troubleshooting

**Cards aren't being buried:**
- Make sure both cards are in the same group (use "Show Sibling Info")
- The sibling must be due today or be a new/learning card
- Check the Anki console (Help → Debug Console) for error messages

**Data seems corrupted:**
- The addon auto-repairs most issues on load
- Try: Tools → Sibling Marker: Cleanup Deleted Cards
- As a last resort, delete `user_files/sibling_groups.json` and start fresh

**Addon not loading:**
- Check the Anki console for error messages
- Ensure you're running Anki 2.1.50+
