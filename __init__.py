"""
Sibling Marker - Anki Addon
Mark any cards as siblings, even across different notes.
Cards marked as siblings will be buried when one is reviewed.

Version: 2.0.0

Storage: Uses Anki tags with prefix "sibling::" for native sync support.
"""

from aqt import mw, gui_hooks
from aqt.qt import (QAction, QMenu, QInputDialog, QMessageBox,
                    QDialog, QListWidget, QListWidgetItem, QSplitter,
                    QScrollArea, QLabel, QPushButton, QHBoxLayout,
                    QVBoxLayout, QWidget, QFrame, Qt)
from aqt.browser import Browser
from aqt.utils import showInfo, tooltip
from anki.cards import Card
import os
import json
import re
import html
import traceback
from typing import Optional, List, Set
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

ADDON_NAME = "Sibling Marker"
TAG_PREFIX = "sibling::"
SUSPENDED_TAG_PREFIX = "sibling-suspended::"
DEBUG_MODE = False

# =============================================================================
# LOGGING
# =============================================================================

LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sibling_marker.log")

def log(message: str, level: str = "INFO") -> None:
    """Log a message to console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{ADDON_NAME}] [{level}] {timestamp}: {message}"
    print(full_msg)
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")
    except Exception:
        pass
    if DEBUG_MODE and level == "ERROR":
        tooltip(f"Sibling Marker Error: {message}")

def log_error(message: str, exc: Optional[Exception] = None) -> None:
    """Log an error with optional exception details."""
    if exc:
        log(f"{message}: {exc}\n{traceback.format_exc()}", "ERROR")
    else:
        log(message, "ERROR")

# =============================================================================
# TAG UTILITIES
# =============================================================================

def sanitize_group_name(name: str) -> str:
    """Sanitize a group name for use in tags. Preserves :: for hierarchy."""
    # Replace spaces and special chars with underscores, but keep : for hierarchy
    sanitized = re.sub(r'[^\w\-:]', '_', name)
    # Normalize multiple colons to exactly two (for hierarchy)
    sanitized = re.sub(r':+', '::', sanitized)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores and colons
    sanitized = sanitized.strip('_:')
    return sanitized.lower() if sanitized else None

def get_sibling_tag(group_name: str) -> str:
    """Create a sibling tag from a group name."""
    return f"{TAG_PREFIX}{group_name}"

def extract_group_name(tag: str) -> Optional[str]:
    """Extract group name from a sibling tag."""
    if tag.startswith(TAG_PREFIX):
        return tag[len(TAG_PREFIX):]
    return None

def get_sibling_tags_for_note(note) -> List[str]:
    """Get all sibling tags for a note."""
    return [t for t in note.tags if t.startswith(TAG_PREFIX)]

def generate_group_id() -> str:
    """Generate a unique group ID."""
    import uuid
    return str(uuid.uuid4())[:8]


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_all_sibling_groups() -> dict:
    """
    Get all sibling groups from the collection.
    Returns dict: {group_name: [note_id, ...]}
    """
    if mw.col is None:
        return {}

    groups = {}
    # Find all notes with sibling tags
    # Try multiple search approaches for compatibility
    search_queries = [
        f'"tag:{TAG_PREFIX}*"',  # Quoted with ::
        f"tag:sibling*",  # Simple prefix without ::
    ]

    note_ids = []
    for search_query in search_queries:
        try:
            found = mw.col.find_notes(search_query)
            log(f"get_all_sibling_groups: search '{search_query}' found {len(found)} notes")
            if found:
                note_ids = found
                break
        except Exception as e:
            log(f"get_all_sibling_groups: search '{search_query}' failed: {e}")

    if not note_ids:
        log("get_all_sibling_groups: no notes found with sibling tags")
        return {}

    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            for tag in get_sibling_tags_for_note(note):
                group_name = extract_group_name(tag)
                if group_name:
                    if group_name not in groups:
                        groups[group_name] = []
                    groups[group_name].append(nid)
        except Exception as e:
            log_error(f"Error reading note {nid}", e)

    log(f"get_all_sibling_groups: returning {len(groups)} groups")
    return groups

def get_cards_for_sibling_group(group_name: str) -> List[int]:
    """Get all card IDs in a sibling group."""
    if mw.col is None:
        return []
    
    tag = get_sibling_tag(group_name)
    note_ids = mw.col.find_notes(f"tag:{tag}")
    
    card_ids = []
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            card_ids.extend(note.card_ids())
        except Exception as e:
            log_error(f"Error getting cards for note {nid}", e)
    
    return card_ids

def get_sibling_groups_for_card(card_id: int) -> List[str]:
    """Get all sibling group names that a card belongs to."""
    if mw.col is None:
        return []
    
    try:
        card = mw.col.get_card(card_id)
        note = card.note()
        groups = []
        for tag in get_sibling_tags_for_note(note):
            group_name = extract_group_name(tag)
            if group_name:
                groups.append(group_name)
        return groups
    except Exception as e:
        log_error(f"Error getting groups for card {card_id}", e)
        return []

# =============================================================================
# USER ACTIONS
# =============================================================================

def mark_cards_as_siblings(card_ids: List[int], group_name: Optional[str] = None) -> bool:
    """Mark a list of cards as siblings by adding sibling tags to their notes."""
    if mw.col is None:
        showInfo("Please open a collection first.")
        return False
    
    if len(card_ids) < 2:
        showInfo("Please select at least 2 cards to mark as siblings.")
        return False
    
    # Get notes for selected cards (deduplicated)
    note_ids: Set[int] = set()
    for cid in card_ids:
        try:
            card = mw.col.get_card(cid)
            note_ids.add(card.nid)
        except Exception as e:
            log_error(f"Error getting note for card {cid}", e)
    
    if len(note_ids) < 2:
        showInfo("Selected cards belong to fewer than 2 notes. "
                "Cards from the same note are already native siblings.")
        return False
    
    # Check if any notes already have sibling tags
    existing_groups: Set[str] = set()
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            for group in [extract_group_name(t) for t in get_sibling_tags_for_note(note)]:
                if group:
                    existing_groups.add(group)
        except Exception:
            pass
    
    final_group_name: str
    
    if existing_groups and not group_name:
        # Ask user how to handle existing groups
        msg = f"Some selected notes are already in sibling group(s): {', '.join(existing_groups)}.\n\n"
        msg += "What would you like to do?"
        
        try:
            reply = QMessageBox.question(
                mw, "Existing Groups Found", 
                msg + "\n\nYes = Use existing group\nNo = Create new group",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            cancel_val = QMessageBox.StandardButton.Cancel
            yes_val = QMessageBox.StandardButton.Yes
        except AttributeError:
            reply = QMessageBox.question(
                mw, "Existing Groups Found",
                msg + "\n\nYes = Use existing group\nNo = Create new group",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            cancel_val = QMessageBox.Cancel
            yes_val = QMessageBox.Yes
        
        if reply == cancel_val:
            return False
        elif reply == yes_val:
            final_group_name = list(existing_groups)[0]
        else:
            final_group_name = generate_group_id()
    elif group_name:
        sanitized = sanitize_group_name(group_name)
        final_group_name = sanitized if sanitized else generate_group_id()
    else:
        final_group_name = generate_group_id()
    
    # Add tag to all notes
    tag = get_sibling_tag(final_group_name)
    modified_count = 0
    
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            if tag not in note.tags:
                note.tags.append(tag)
                mw.col.update_note(note)
                modified_count += 1
        except Exception as e:
            log_error(f"Error updating note {nid}", e)
    
    if modified_count > 0:
        tooltip(f"Marked {len(note_ids)} notes as siblings (group: {final_group_name})")
        log(f"Added sibling tag '{tag}' to {modified_count} notes")
        
        # Apply cross-platform sibling separation
        apply_sibling_separation(final_group_name, card_ids)
        
        return True
    else:
        tooltip("Notes were already in this sibling group")
        return True

def remove_from_sibling_group(card_ids: List[int]) -> bool:
    """Remove cards' notes from their sibling groups."""
    if mw.col is None:
        showInfo("Please open a collection first.")
        return False

    # Get unique notes
    note_ids: Set[int] = set()
    for cid in card_ids:
        try:
            card = mw.col.get_card(cid)
            note_ids.add(card.nid)
        except Exception:
            pass

    removed_count = 0
    unsuspended_count = 0
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            # Get both sibling:: and sibling-suspended:: tags
            sibling_tags = [t for t in note.tags if t.startswith(TAG_PREFIX)]
            suspended_tags = [t for t in note.tags if t.startswith(SUSPENDED_TAG_PREFIX)]

            if sibling_tags or suspended_tags:
                # Remove all sibling-related tags
                for tag in sibling_tags + suspended_tags:
                    note.tags.remove(tag)

                # If card was suspended by us, unsuspend it
                if suspended_tags:
                    for card in note.cards():
                        if card.queue == -1:  # Suspended
                            card.queue = 0  # Back to new
                            mw.col.update_card(card)
                            unsuspended_count += 1

                mw.col.update_note(note)
                removed_count += 1
        except Exception as e:
            log_error(f"Error removing tags from note {nid}", e)

    if removed_count > 0:
        msg = f"Removed {removed_count} note(s) from sibling groups"
        if unsuspended_count > 0:
            msg += f", unsuspended {unsuspended_count} card(s)"
        tooltip(msg)
    else:
        tooltip("Selected cards were not in any sibling groups")

    return True

def show_sibling_info(card_ids: List[int]) -> None:
    """Show sibling group info for selected cards."""
    if mw.col is None:
        showInfo("Please open a collection first.")
        return
    
    info_lines = []
    seen_notes: Set[int] = set()
    
    for cid in card_ids:
        try:
            card = mw.col.get_card(cid)
            if card.nid in seen_notes:
                continue
            seen_notes.add(card.nid)
            
            note = card.note()
            groups = [extract_group_name(t) for t in get_sibling_tags_for_note(note)]
            groups = [g for g in groups if g]
            
            if groups:
                info_lines.append(f"Note {card.nid}: Groups: {', '.join(groups)}")
            else:
                info_lines.append(f"Note {card.nid}: Not in any sibling group")
        except Exception as e:
            info_lines.append(f"Card {cid}: Error - {e}")
    
    showInfo("\n".join(info_lines), title="Sibling Group Info")

def add_to_existing_group(card_ids: List[int], browser: Browser) -> bool:
    """Add cards to an existing sibling group."""
    if mw.col is None:
        showInfo("Please open a collection first.")
        return False
    
    groups = get_all_sibling_groups()
    
    if not groups:
        showInfo("No existing sibling groups. Use 'Mark as Siblings' first.")
        return False
    
    group_info = [f"{name} ({len(nids)} notes)" for name, nids in groups.items()]
    group_names = list(groups.keys())
    
    choice, ok = QInputDialog.getItem(
        browser, "Select Group", "Add to which sibling group?",
        group_info, 0, False
    )
    
    if not (ok and choice):
        return False
    
    group_name = group_names[group_info.index(choice)]
    tag = get_sibling_tag(group_name)
    
    # Get unique notes
    note_ids: Set[int] = set()
    for cid in card_ids:
        try:
            card = mw.col.get_card(cid)
            note_ids.add(card.nid)
        except Exception:
            pass
    
    # Add tag to notes
    added_count = 0
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            if tag not in note.tags:
                note.tags.append(tag)
                mw.col.update_note(note)
                added_count += 1
        except Exception as e:
            log_error(f"Error updating note {nid}", e)
    
    if added_count > 0:
        tooltip(f"Added {added_count} note(s) to group '{group_name}'")
    else:
        tooltip("Notes were already in this group")
    
    return True

# =============================================================================
# CROSS-PLATFORM SIBLING SEPARATION
# =============================================================================

def suspend_new_card_siblings(group_name: str, card_ids: List[int]) -> int:
    """
    Suspend all but the first new card in a sibling group.
    This enables cross-platform sibling separation since suspension syncs.
    """
    if mw.col is None:
        return 0

    # Get all cards and filter to new cards only
    new_cards = []
    for cid in card_ids:
        try:
            card = mw.col.get_card(cid)
            if card.queue == 0 and card.type == 0:  # New card
                new_cards.append(card)
        except Exception:
            pass

    if len(new_cards) < 2:
        return 0

    # Sort by card ID for stable ordering
    new_cards.sort(key=lambda c: c.id)

    # Keep the first one active, suspend the rest
    suspended_count = 0
    for card in new_cards[1:]:
        try:
            # Suspend the card
            card.queue = -1
            mw.col.update_card(card)
            
            # Add the sibling-suspended tag to track it
            note = card.note()
            suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"
            if suspended_tag not in note.tags:
                note.tags.append(suspended_tag)
                mw.col.update_note(note)
            
            suspended_count += 1
            log(f"Suspended new card {card.id} in group {group_name}")
        except Exception as e:
            log_error(f"Error suspending card {card.id}", e)

    return suspended_count


def spread_review_card_due_dates(group_name: str, min_gap_days: int = 1) -> int:
    """
    Spread review cards in a sibling group across consecutive days.
    This ensures review siblings are never due on the same day.
    """
    if mw.col is None:
        return 0

    tag = get_sibling_tag(group_name)
    note_ids = mw.col.find_notes(f"tag:{tag}")
    today = mw.col.sched.today

    # Collect all review cards due today or earlier
    review_cards_due = []
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            for card in note.cards():
                # Review cards due today or overdue
                if card.queue == 2 and card.due <= today:
                    review_cards_due.append(card)
        except Exception:
            pass

    if len(review_cards_due) < 2:
        return 0

    # Sort by due date, then by card ID for stability
    review_cards_due.sort(key=lambda c: (c.due, c.id))

    # Keep the first one as-is, spread the rest
    rescheduled = 0
    for i, card in enumerate(review_cards_due[1:], start=1):
        new_due = today + (i * min_gap_days)
        if card.due != new_due:
            card.due = new_due
            mw.col.update_card(card)
            rescheduled += 1
            log(f"Rescheduled review card {card.id} to day {new_due}")

    return rescheduled


def apply_priority_based_separation() -> dict:
    """
    Apply priority-based sibling separation at sync time.

    Priority: Learning > Review > New

    Rules:
    - If any LEARNING cards in group → suspend new siblings, bury review siblings
    - Else if any REVIEW cards due in group → suspend new siblings, reschedule extra reviews to tomorrow
    - Else → ensure only 1 new card active

    Returns dict with counts of actions taken.
    """
    if mw.col is None:
        log("apply_priority_based_separation: no collection open")
        return {"suspended_new": 0, "buried_learning": 0, "buried_review": 0, "rescheduled_review": 0, "unsuspended": 0}

    groups = get_all_sibling_groups()
    today = mw.col.sched.today

    log(f"apply_priority_based_separation: found {len(groups)} sibling group(s), today={today}")

    total_suspended_new = 0
    total_buried_learning = 0
    total_buried_review = 0
    total_rescheduled_review = 0
    total_unsuspended = 0

    for group_name, note_ids in groups.items():
        # Categorize all cards in this group
        learning_cards = []  # Cards in learning (queue 1 or queue 3 due today)
        review_cards_due = []  # Review cards due today (queue 2, due <= today)
        new_cards = []  # New cards (queue 0)
        suspended_new_cards = []  # Suspended new cards (queue -1 with our tag)

        for nid in note_ids:
            try:
                note = mw.col.get_note(nid)
                has_suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}" in note.tags

                for card in note.cards():
                    if card.queue == 0:  # New
                        new_cards.append((card, note))
                    elif card.queue == 1:  # Intraday learning
                        learning_cards.append((card, note))
                    elif card.queue == 3 and card.due <= today:  # Day learning due today
                        learning_cards.append((card, note))
                    elif card.queue == 2 and card.due <= today:  # Review due today
                        review_cards_due.append((card, note))
                    elif card.queue == -1 and has_suspended_tag:  # Our suspended new cards
                        suspended_new_cards.append((card, note))
            except Exception as e:
                log_error(f"Error categorizing cards for note {nid}", e)

        # Apply priority rules
        has_learning = len(learning_cards) > 0
        has_review_due = len(review_cards_due) > 0

        # Debug logging
        log(f"Group {group_name}: {len(learning_cards)} learning, {len(review_cards_due)} review due, {len(new_cards)} new, {len(suspended_new_cards)} suspended-new")

        if has_learning:
            # Learning cards exist: suspend new siblings, bury review siblings, bury extra learning siblings

            # Suspend new cards
            for card, note in new_cards:
                try:
                    card.queue = -1
                    mw.col.update_card(card)

                    suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"
                    if suspended_tag not in note.tags:
                        note.tags.append(suspended_tag)
                        mw.col.update_note(note)

                    total_suspended_new += 1
                    log(f"Suspended new card {card.id} (learning sibling exists)")
                except Exception as e:
                    log_error(f"Error suspending card {card.id}", e)

            # Bury review cards due today
            review_card_ids = [card.id for card, note in review_cards_due]
            if review_card_ids:
                try:
                    mw.col.sched.bury_cards(review_card_ids)
                    total_buried_review += len(review_card_ids)
                    log(f"Buried {len(review_card_ids)} review card(s) (learning sibling exists)")
                except Exception as e:
                    log_error(f"Error burying review cards", e)

            # Bury extra learning cards (keep only the first one)
            if len(learning_cards) > 1:
                learning_sorted = sorted(learning_cards, key=lambda x: x[0].id)
                extra_learning_ids = [card.id for card, note in learning_sorted[1:]]
                try:
                    mw.col.sched.bury_cards(extra_learning_ids)
                    total_buried_learning += len(extra_learning_ids)
                    log(f"Buried {len(extra_learning_ids)} extra learning card(s)")
                except Exception as e:
                    log_error(f"Error burying learning cards", e)

        elif has_review_due:
            # Review cards due but no learning: suspend new siblings, reschedule extra reviews

            # Suspend new cards
            for card, note in new_cards:
                try:
                    card.queue = -1
                    mw.col.update_card(card)

                    suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"
                    if suspended_tag not in note.tags:
                        note.tags.append(suspended_tag)
                        mw.col.update_note(note)

                    total_suspended_new += 1
                    log(f"Suspended new card {card.id} (review sibling due)")
                except Exception as e:
                    log_error(f"Error suspending card {card.id}", e)

            # Reschedule extra review cards to tomorrow (keep only first one due today)
            if len(review_cards_due) > 1:
                # Sort by due date, then card ID for stability
                review_cards_sorted = sorted(review_cards_due, key=lambda x: (x[0].due, x[0].id))
                for card, note in review_cards_sorted[1:]:
                    try:
                        card.due = today + 1
                        mw.col.update_card(card)
                        total_rescheduled_review += 1
                        log(f"Rescheduled review card {card.id} to tomorrow (sibling due today)")
                    except Exception as e:
                        log_error(f"Error rescheduling card {card.id}", e)

        else:
            # No learning or review due
            # Ensure only ONE new card is active at a time

            if len(new_cards) > 1:
                # Multiple active new cards - suspend all but the first one
                new_cards_sorted = sorted(new_cards, key=lambda x: x[0].id)
                for card, note in new_cards_sorted[1:]:
                    try:
                        card.queue = -1
                        mw.col.update_card(card)

                        suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"
                        if suspended_tag not in note.tags:
                            note.tags.append(suspended_tag)
                            mw.col.update_note(note)

                        total_suspended_new += 1
                        log(f"Suspended new card {card.id} (only one new sibling at a time)")
                    except Exception as e:
                        log_error(f"Error suspending card {card.id}", e)

            elif len(new_cards) == 0 and len(suspended_new_cards) > 0:
                # No active new cards, but we have suspended ones - unsuspend the next note.
                # We pick by lowest card ID, then unsuspend ALL cards from that note.
                # Unsuspending only one card-per-note would leave sibling cards from the same
                # note in a zombie state: still suspended (queue=-1) but with no tracking tag
                # after the tag is removed from the note, making them permanently invisible.
                suspended_sorted = sorted(suspended_new_cards, key=lambda x: x[0].id)
                _, next_note = suspended_sorted[0]
                try:
                    unsuspended_this_note = 0
                    for c in next_note.cards():
                        if c.queue == -1:
                            c.queue = 0  # Back to new
                            mw.col.update_card(c)
                            unsuspended_this_note += 1
                            log(f"Unsuspended new card {c.id} (next in sequence)")

                    # Safe to remove this group's tag now: all suspended cards from this note are active.
                    # Only remove the current group's tag so other groups' suspension tracking is preserved.
                    suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"
                    next_note.tags = [t for t in next_note.tags if t != suspended_tag]
                    mw.col.update_note(next_note)

                    total_unsuspended += unsuspended_this_note
                except Exception as e:
                    log_error(f"Error unsuspending cards for note {next_note.id}", e)

            # If len(new_cards) == 1 and suspended_new_cards exist, do nothing
            # The one active new card is correct, others wait their turn

    return {
        "suspended_new": total_suspended_new,
        "buried_learning": total_buried_learning,
        "buried_review": total_buried_review,
        "rescheduled_review": total_rescheduled_review,
        "unsuspended": total_unsuspended
    }


def enforce_sibling_separation() -> dict:
    """
    Scan all sibling groups and ensure proper separation.

    Uses priority-based separation:
    - Learning > Review > New
    - Learning cards cause new siblings to be suspended, review siblings to be buried
    - Review cards cause new siblings to be suspended, extra reviews rescheduled

    Returns dict with counts of actions taken.
    """
    if mw.col is None:
        return {"suspended_new": 0, "buried_learning": 0, "buried_review": 0, "rescheduled_review": 0, "unsuspended": 0}

    result = apply_priority_based_separation()
    total = result["suspended_new"] + result["buried_learning"] + result["buried_review"] + result["rescheduled_review"] + result["unsuspended"]

    if total > 0:
        log(f"Priority separation: {result['suspended_new']} new suspended, {result['buried_review']} review buried, {result['rescheduled_review']} review rescheduled, {result['unsuspended']} unsuspended")

    return result


def apply_sibling_separation(group_name: str, card_ids: List[int]) -> None:
    """
    Apply sibling separation for a newly marked group.
    - Suspends new card siblings (all but first)
    - Spreads review card due dates
    """
    # Handle new cards: suspend all but the first
    suspended = suspend_new_card_siblings(group_name, card_ids)
    if suspended > 0:
        log(f"Suspended {suspended} new card siblings in group {group_name}")

    # Handle review cards: spread due dates
    spread = spread_review_card_due_dates(group_name)
    if spread > 0:
        log(f"Spread {spread} review card due dates in group {group_name}")


# =============================================================================
# MIGRATION FROM V1 (JSON storage)
# =============================================================================

def get_legacy_config_path() -> str:
    """Get the old JSON config file path."""
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(addon_dir, "user_files", "sibling_groups.json")

def migrate_from_json() -> bool:
    """
    Migrate sibling groups from old JSON storage to tags.
    Returns True if migration was performed.
    """
    if mw.col is None:
        return False
    
    legacy_path = get_legacy_config_path()
    
    if not os.path.exists(legacy_path):
        return False
    
    try:
        with open(legacy_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        groups = data.get("groups", {})
        
        if not groups:
            log("No groups to migrate from JSON")
            # Rename the file to mark as processed
            os.rename(legacy_path, legacy_path + ".migrated")
            return True
        
        migrated_groups = 0
        migrated_notes = 0
        
        for group_id, card_ids in groups.items():
            # Sanitize group name for tag
            tag_group_name = sanitize_group_name(group_id) or generate_group_id()
            tag = get_sibling_tag(tag_group_name)
            
            # Find notes for these cards and add tag
            note_ids_for_group: Set[int] = set()
            
            for cid in card_ids:
                try:
                    card = mw.col.get_card(cid)
                    note_ids_for_group.add(card.nid)
                except Exception:
                    # Card might have been deleted
                    pass
            
            # Add tag to each note
            for nid in note_ids_for_group:
                try:
                    note = mw.col.get_note(nid)
                    if tag not in note.tags:
                        note.tags.append(tag)
                        mw.col.update_note(note)
                        migrated_notes += 1
                except Exception as e:
                    log_error(f"Error migrating note {nid}", e)
            
            if note_ids_for_group:
                migrated_groups += 1
        
        # Rename the old file to mark as migrated
        os.rename(legacy_path, legacy_path + ".migrated")
        
        log(f"Migration complete: {migrated_groups} groups, {migrated_notes} notes")
        showInfo(f"Sibling Marker: Migrated {migrated_groups} groups ({migrated_notes} notes) "
                f"from local storage to synced tags.\n\n"
                f"Your sibling groups will now sync across devices!")
        
        return True
        
    except Exception as e:
        log_error("Migration failed", e)
        showInfo(f"Sibling Marker: Migration from old format failed: {e}\n\n"
                f"Your old data is still at: {legacy_path}")
        return False

# =============================================================================
# HOOKS
# =============================================================================

def on_sync_will_start() -> None:
    """Called before sync starts - enforce sibling separation."""
    log("Sync starting - running priority separation")
    try:
        result = enforce_sibling_separation()
        total = result["suspended_new"] + result["buried_learning"] + result["buried_review"] + result["rescheduled_review"] + result["unsuspended"]

        if total > 0:
            parts = []
            if result["suspended_new"] > 0:
                parts.append(f"{result['suspended_new']} new suspended")
            if result["buried_learning"] > 0:
                parts.append(f"{result['buried_learning']} learning buried")
            if result["buried_review"] > 0:
                parts.append(f"{result['buried_review']} review buried")
            if result["rescheduled_review"] > 0:
                parts.append(f"{result['rescheduled_review']} review rescheduled")
            if result["unsuspended"] > 0:
                parts.append(f"{result['unsuspended']} unsuspended")
            tooltip(f"Sibling Marker: {', '.join(parts)}")

        log(f"Pre-sync: priority separation affected {total} card(s)")
    except Exception as e:
        log_error("Error in sync_will_start hook", e)

def on_sync_did_finish() -> None:
    """Called after sync completes - re-run separation to handle mobile reviews."""
    log("Sync finished - running priority separation for incoming changes")
    try:
        result = enforce_sibling_separation()
        total = result["suspended_new"] + result["buried_learning"] + result["buried_review"] + result["rescheduled_review"] + result["unsuspended"]

        if total > 0:
            parts = []
            if result["suspended_new"] > 0:
                parts.append(f"{result['suspended_new']} new suspended")
            if result["buried_learning"] > 0:
                parts.append(f"{result['buried_learning']} learning buried")
            if result["buried_review"] > 0:
                parts.append(f"{result['buried_review']} review buried")
            if result["rescheduled_review"] > 0:
                parts.append(f"{result['rescheduled_review']} review rescheduled")
            if result["unsuspended"] > 0:
                parts.append(f"{result['unsuspended']} unsuspended")
            tooltip(f"Sibling Marker (post-sync): {', '.join(parts)}")

        log(f"Post-sync: priority separation affected {total} card(s)")
    except Exception as e:
        log_error("Error in sync_did_finish hook", e)

def on_browser_context_menu(browser: Browser, menu: QMenu) -> None:
    """Add sibling marker options to browser context menu."""
    try:
        selected = browser.selectedCards()
        if not selected:
            return
        
        selected_list = list(selected)
        
        sibling_menu = menu.addMenu("Sibling Marker")
        
        # Mark as siblings
        action_mark = sibling_menu.addAction(f"Mark {len(selected_list)} cards as Siblings")
        action_mark.triggered.connect(lambda: mark_cards_as_siblings(selected_list))
        
        # Mark with custom name
        action_mark_named = sibling_menu.addAction("Mark as Siblings (with name)...")
        def mark_with_name():
            name, ok = QInputDialog.getText(browser, "Group Name", 
                                           "Enter a name for this sibling group:\n"
                                           "(supports hierarchy, e.g., anatomy::bones)")
            if ok and name:
                mark_cards_as_siblings(selected_list, name)
        action_mark_named.triggered.connect(mark_with_name)
        
        # Add to existing group
        action_add = sibling_menu.addAction("Add to Existing Group...")
        action_add.triggered.connect(lambda: add_to_existing_group(selected_list, browser))
        
        sibling_menu.addSeparator()
        
        # Remove from group
        action_remove = sibling_menu.addAction("Remove from Sibling Group")
        action_remove.triggered.connect(lambda: remove_from_sibling_group(selected_list))
        
        # Show info
        action_info = sibling_menu.addAction("Show Sibling Info")
        action_info.triggered.connect(lambda: show_sibling_info(selected_list))
        
    except Exception as e:
        log_error("Error creating context menu", e)

class SiblingGroupManagerDialog(QDialog):
    """Two-pane dialog for viewing and managing sibling groups."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sibling Marker — Groups")
        self.setMinimumSize(720, 480)
        self._current_group = None
        self._groups = {}
        self._setup_ui()
        self._load_groups()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter()
        try:
            splitter.setOrientation(Qt.Orientation.Horizontal)
        except AttributeError:
            splitter.setOrientation(Qt.Horizontal)

        # --- Left panel ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        self._group_count_label = QLabel("0 groups")
        left_layout.addWidget(self._group_count_label)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_group_selected)
        left_layout.addWidget(self._list)

        splitter.addWidget(left_widget)

        # --- Right panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)

        header_row = QHBoxLayout()
        self._group_name_label = QLabel("")
        self._group_name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        header_row.addWidget(self._group_name_label)
        header_row.addStretch()

        self._rename_btn = QPushButton("Rename")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._on_rename)
        header_row.addWidget(self._rename_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        header_row.addWidget(self._delete_btn)

        right_layout.addLayout(header_row)

        line = QFrame()
        try:
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
        except AttributeError:
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(line)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        try:
            self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        except AttributeError:
            self._scroll_area.setFrameShape(QFrame.NoFrame)
        right_layout.addWidget(self._scroll_area, 1)

        self._browse_btn = QPushButton("Browse Group in Browser")
        self._browse_btn.setEnabled(False)
        self._browse_btn.clicked.connect(self._on_browse)
        right_layout.addWidget(self._browse_btn)

        splitter.addWidget(right_widget)
        splitter.setSizes([220, 500])

        main_layout.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        main_layout.addLayout(footer)

    def _load_groups(self):
        self._groups = get_all_sibling_groups()
        prev_group = self._current_group
        self._list.blockSignals(True)
        self._list.clear()
        try:
            user_role = Qt.ItemDataRole.UserRole
        except AttributeError:
            user_role = Qt.UserRole
        for group_name in sorted(self._groups.keys()):
            note_ids = self._groups[group_name]
            item = QListWidgetItem(f"{group_name} ({len(note_ids)} notes)")
            item.setData(user_role, group_name)
            self._list.addItem(item)
        count = len(self._groups)
        self._group_count_label.setText(f"{count} group{'s' if count != 1 else ''}")
        self._list.blockSignals(False)
        # Restore selection
        restored = False
        if prev_group:
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item.data(user_role) == prev_group:
                    self._list.setCurrentRow(i)
                    restored = True
                    break
        if not restored and self._list.count() > 0:
            self._list.setCurrentRow(0)
        elif not restored:
            self._on_group_selected(-1)

    def _on_group_selected(self, row):
        try:
            user_role = Qt.ItemDataRole.UserRole
        except AttributeError:
            user_role = Qt.UserRole
        if row < 0:
            self._current_group = None
            self._group_name_label.setText("")
            self._rename_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            self._browse_btn.setEnabled(False)
            self._scroll_area.setWidget(QWidget())
            return
        item = self._list.item(row)
        group_name = item.data(user_role)
        self._current_group = group_name
        self._group_name_label.setText(group_name)
        self._rename_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        self._browse_btn.setEnabled(True)
        self._populate_right_panel(group_name)

    def _card_state(self, card, note, group_name):
        today = mw.col.sched.today
        q = card.queue
        if q == 0:
            return "new · active"
        elif q == -1:
            if f"{SUSPENDED_TAG_PREFIX}{group_name}" in note.tags and card.type == 0:
                return "new · suspended (sibling)"
            return "suspended (user)"
        elif q == 1:
            return "learning"
        elif q == 3:
            return "relearning"
        elif q == 2:
            if card.due <= today:
                return "review · due today"
            days = card.due - today
            return f"review · in {days} day{'s' if days != 1 else ''}"
        elif q == -2:
            return "buried (user)"
        elif q == -3:
            return "buried (scheduler)"
        return f"queue {q}"

    def _populate_right_panel(self, group_name):
        if mw.col is None:
            return
        note_ids = self._groups.get(group_name, [])
        container = QWidget()
        layout = QVBoxLayout(container)
        try:
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        except AttributeError:
            layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        for nid in sorted(note_ids):
            try:
                note = mw.col.get_note(nid)
                first_field = note.fields[0] if note.fields else "(empty)"
                first_field = re.sub(r'<[^>]+>', '', first_field).strip()
                if len(first_field) > 60:
                    first_field = first_field[:57] + "..."
                note_label = QLabel(f"<b>{html.escape(first_field)}</b>")
                note_label.setWordWrap(True)
                layout.addWidget(note_label)
                for i, card in enumerate(note.cards(), start=1):
                    state = self._card_state(card, note, group_name)
                    card_label = QLabel(f"  Card {i} — {state}")
                    card_label.setStyleSheet("color: #666; font-size: 11px; margin-left: 12px;")
                    layout.addWidget(card_label)
                spacer = QLabel("")
                spacer.setFixedHeight(6)
                layout.addWidget(spacer)
            except Exception as e:
                log_error(f"Error displaying note {nid} in group manager", e)

        layout.addStretch()
        self._scroll_area.setWidget(container)

    def _on_rename(self):
        if not self._current_group or mw.col is None:
            return
        old_name = self._current_group
        new_name_raw, ok = QInputDialog.getText(
            self, "Rename Group", "New group name:", text=old_name
        )
        if not ok or not new_name_raw.strip():
            return
        new_name = sanitize_group_name(new_name_raw.strip())
        if not new_name:
            tooltip("Invalid group name.")
            return
        if new_name == old_name:
            return
        if new_name in self._groups:
            tooltip(f"A group named '{new_name}' already exists.")
            return
        old_tag = f"{TAG_PREFIX}{old_name}"
        new_tag = f"{TAG_PREFIX}{new_name}"
        old_sus = f"{SUSPENDED_TAG_PREFIX}{old_name}"
        new_sus = f"{SUSPENDED_TAG_PREFIX}{new_name}"
        for nid in self._groups.get(old_name, []):
            try:
                note = mw.col.get_note(nid)
                note.tags = [new_tag if t == old_tag else
                             new_sus if t == old_sus else t
                             for t in note.tags]
                mw.col.update_note(note)
            except Exception as e:
                log_error(f"Error renaming note {nid}", e)
        log(f"Renamed sibling group '{old_name}' → '{new_name}'")
        mw.reset()
        self._current_group = new_name
        self._load_groups()

    def _on_delete(self):
        if not self._current_group or mw.col is None:
            return
        group_name = self._current_group
        try:
            reply = QMessageBox.question(
                self, "Delete Group",
                f"Delete group '{group_name}'?\n\nThis will unsuspend any siblings we suspended.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            yes_val = QMessageBox.StandardButton.Yes
        except AttributeError:
            reply = QMessageBox.question(
                self, "Delete Group",
                f"Delete group '{group_name}'?\n\nThis will unsuspend any siblings we suspended.",
                QMessageBox.Yes | QMessageBox.No
            )
            yes_val = QMessageBox.Yes
        if reply != yes_val:
            return
        sibling_tag = f"{TAG_PREFIX}{group_name}"
        suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"
        for nid in self._groups.get(group_name, []):
            try:
                note = mw.col.get_note(nid)
                had_suspended = suspended_tag in note.tags
                note.tags = [t for t in note.tags if t != sibling_tag and t != suspended_tag]
                if had_suspended:
                    for card in note.cards():
                        # Only unsuspend cards we suspended (new cards); leave user-suspended
                        # review/learning cards alone. card.type == 0 means "new" type.
                        if card.queue == -1 and card.type == 0:
                            card.queue = 0
                            mw.col.update_card(card)
                mw.col.update_note(note)
            except Exception as e:
                log_error(f"Error deleting group tag from note {nid}", e)
        log(f"Deleted sibling group '{group_name}'")
        mw.reset()
        self._current_group = None
        self._load_groups()

    def _on_browse(self):
        if not self._current_group:
            return
        try:
            from aqt import dialogs
            browser = dialogs.open("Browser", mw)
            browser.search_for(f"tag:{TAG_PREFIX}{self._current_group}")
        except Exception as e:
            log_error("Error opening browser from group manager", e)


def show_all_groups() -> None:
    """Show all sibling groups in a dialog."""
    if mw.col is None:
        showInfo("Please open a collection first.")
        return
    dlg = SiblingGroupManagerDialog(mw)
    dlg.exec()

def setup_menu() -> None:
    """Set up Tools menu entries."""
    try:
        # View groups
        action_view = QAction("Sibling Marker: View Groups", mw)
        action_view.triggered.connect(show_all_groups)
        mw.form.menuTools.addAction(action_view)
        
        log("Menu setup complete")
    except Exception as e:
        log_error("Failed to setup menu", e)

def on_profile_loaded() -> None:
    """Called when a profile is loaded - run migration and initial enforcement."""
    migrate_from_json()
    # Run enforcement at profile load so state changes are pending BEFORE auto-sync
    # computes its change set. This prevents the 'always blue' sync button issue
    # that occurs when sync_will_start makes changes not included in the current sync.
    try:
        result = enforce_sibling_separation()
        total = result["suspended_new"] + result["buried_learning"] + result["buried_review"] + result["rescheduled_review"] + result["unsuspended"]
        if total > 0:
            log(f"Profile load: enforcement affected {total} card(s)")
    except Exception as e:
        log_error("Error in profile_loaded enforcement", e)

def on_reviewer_did_show_question(card) -> None:
    """Inject a sibling indicator below the card during review."""
    try:
        if mw.col is None:
            return

        note = card.note()

        # Find all sibling groups this card's note belongs to
        sibling_tags = [t for t in note.tags if t.startswith(TAG_PREFIX)]
        if not sibling_tags:
            if mw.reviewer:
                mw.reviewer.web.eval(
                    "(function(){var e=document.getElementById('sibling-indicator');if(e)e.remove();})();"
                )
            return

        parts = []
        for tag in sibling_tags:
            group_name = tag[len(TAG_PREFIX):]
            suspended_tag = f"{SUSPENDED_TAG_PREFIX}{group_name}"

            # Count siblings waiting (suspended by us, not this card's note)
            try:
                group_note_ids = mw.col.find_notes(f"tag:{TAG_PREFIX}{group_name}")
            except Exception:
                continue

            waiting = 0
            for nid in group_note_ids:
                if nid == card.nid:
                    continue
                try:
                    sibling_note = mw.col.get_note(nid)
                    if suspended_tag not in sibling_note.tags:
                        continue
                    for c in sibling_note.cards():
                        if c.queue == -1:
                            waiting += 1
                except Exception:
                    pass

            if waiting > 0:
                sibling_word = "sibling" if waiting == 1 else "siblings"
                parts.append(f"{group_name} · {waiting} {sibling_word} waiting")

        if not parts:
            if mw.reviewer:
                mw.reviewer.web.eval(
                    "(function(){var e=document.getElementById('sibling-indicator');if(e)e.remove();})();"
                )
            return

        if not mw.reviewer:
            return

        text = "  \u2502  ".join(parts)
        text_escaped = text.replace("\\", "\\\\").replace("'", "\\'")
        js = f"""
(function() {{
    var existing = document.getElementById('sibling-indicator');
    if (existing) existing.remove();
    var div = document.createElement('div');
    div.id = 'sibling-indicator';
    div.style.cssText = 'position:fixed;bottom:10px;left:0;right:0;text-align:center;font-size:0.72em;color:#999;pointer-events:none;z-index:100;letter-spacing:0.02em;';
    div.textContent = '\u26d3 {text_escaped}';
    document.body.appendChild(div);
}})();
"""
        mw.reviewer.web.eval(js)

    except Exception as e:
        log_error("Error in reviewer_did_show_question hook", e)


# =============================================================================
# REGISTER HOOKS
# =============================================================================

gui_hooks.browser_will_show_context_menu.append(on_browser_context_menu)
gui_hooks.main_window_did_init.append(setup_menu)
gui_hooks.profile_did_open.append(on_profile_loaded)
gui_hooks.sync_will_start.append(on_sync_will_start)
gui_hooks.sync_did_finish.append(on_sync_did_finish)
gui_hooks.reviewer_did_show_question.append(on_reviewer_did_show_question)

log("Sibling Marker addon loaded (v2.0 - tag-based sync)")
