"""
Sibling Marker - Anki Addon
Mark any cards as siblings, even across different notes.
Cards marked as siblings will be buried when one is reviewed.

Version: 2.0.0

Storage: Uses Anki tags with prefix "sibling::" for native sync support.
"""

from aqt import mw, gui_hooks
from aqt.qt import QAction, QMenu, QInputDialog, QMessageBox
from aqt.browser import Browser
from aqt.utils import showInfo, tooltip
from anki.cards import Card
import os
import json
import re
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

def log(message: str, level: str = "INFO") -> None:
    """Log a message to console."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{ADDON_NAME}] [{level}] {timestamp}: {message}"
    print(full_msg)
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
# SYNC CHECK TIMESTAMP
# =============================================================================

def get_last_sync_check_time() -> int:
    """Get timestamp of last revlog check (milliseconds)."""
    if mw.col is None:
        return 0
    return mw.col.get_config("sibling_marker_last_check", 0)

def set_last_sync_check_time(timestamp: int) -> None:
    """Store timestamp of last revlog check."""
    if mw.col is not None:
        mw.col.set_config("sibling_marker_last_check", timestamp)

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
    note_ids = mw.col.find_notes(f"tag:{TAG_PREFIX}*")
    
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
    for nid in note_ids:
        try:
            note = mw.col.get_note(nid)
            sibling_tags = get_sibling_tags_for_note(note)
            if sibling_tags:
                for tag in sibling_tags:
                    note.tags.remove(tag)
                mw.col.update_note(note)
                removed_count += 1
        except Exception as e:
            log_error(f"Error removing tags from note {nid}", e)
    
    if removed_count > 0:
        tooltip(f"Removed {removed_count} note(s) from sibling groups")
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
# BURY LOGIC
# =============================================================================

def bury_custom_siblings(card: Card) -> int:
    """Bury custom siblings when a card is answered."""
    if not card or mw.col is None:
        return 0
    
    try:
        note = card.note()
        sibling_tags = get_sibling_tags_for_note(note)
        
        if not sibling_tags:
            return 0
        
        col = mw.col
        cards_to_bury: Set[int] = set()
        
        # Get all sibling cards from all groups this card belongs to
        for tag in sibling_tags:
            group_name = extract_group_name(tag)
            if not group_name:
                continue
            
            # Find all notes with this tag
            note_ids = col.find_notes(f"tag:{tag}")
            
            for nid in note_ids:
                if nid == card.nid:
                    continue  # Skip the current card's note
                
                try:
                    sibling_note = col.get_note(nid)
                    for sib_cid in sibling_note.card_ids():
                        if sib_cid == card.id:
                            continue
                        
                        sib_card = col.get_card(sib_cid)
                        
                        # Only bury if card is active (not already buried/suspended)
                        if sib_card.queue >= 0:
                            should_bury = False
                            
                            if sib_card.queue == 0:  # New
                                should_bury = True
                            elif sib_card.queue == 1:  # Learning
                                should_bury = True
                            elif sib_card.queue == 2:  # Review - due today
                                should_bury = sib_card.due <= col.sched.today
                            elif sib_card.queue == 3:  # Day learning
                                should_bury = sib_card.due <= col.sched.today
                            
                            if should_bury:
                                cards_to_bury.add(sib_cid)
                except Exception as e:
                    log(f"Error checking sibling card: {e}", "WARN")
        
        # Bury all at once
        if cards_to_bury:
            col.sched.bury_cards(list(cards_to_bury))
            log(f"Buried {len(cards_to_bury)} custom sibling(s)")
            return len(cards_to_bury)
        
        return 0
        
    except Exception as e:
        log_error("Error in bury_custom_siblings", e)
        return 0

def process_reviews_since_last_check() -> int:
    """Check revlog for reviews since last check and bury siblings.
    
    This handles reviews that happened on mobile or other devices.
    """
    if mw.col is None:
        return 0

    last_check = get_last_sync_check_time()

    # Query revlog for reviews since last check
    # revlog.id is the timestamp in milliseconds
    reviews = mw.col.db.list(
        "SELECT DISTINCT cid FROM revlog WHERE id > ?", last_check
    )

    if not reviews:
        # Update timestamp even if no reviews, so we don't re-check old ones
        import time
        set_last_sync_check_time(int(time.time() * 1000))
        return 0

    total_buried = 0
    for cid in reviews:
        try:
            card = mw.col.get_card(cid)
            buried = bury_custom_siblings(card)
            total_buried += buried
        except Exception:
            pass  # Card may have been deleted

    # Update last check time to now (in milliseconds)
    import time
    set_last_sync_check_time(int(time.time() * 1000))

    return total_buried

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


def check_and_unsuspend_siblings() -> int:
    """
    Unsuspend the NEXT sibling in each group if the previous one was reviewed.
    Called on profile load to release siblings sequentially.
    """
    if mw.col is None:
        return 0

    groups = get_all_sibling_groups()
    total_unsuspended = 0

    for group_name, note_ids in groups.items():
        # Get all cards in this group with their notes
        all_cards_with_notes = []
        for nid in note_ids:
            try:
                note = mw.col.get_note(nid)
                for card in note.cards():
                    all_cards_with_notes.append((card, note))
            except Exception:
                pass

        if not all_cards_with_notes:
            continue

        # Sort by card ID for stable ordering
        all_cards_with_notes.sort(key=lambda x: x[0].id)

        # Track: have all previous siblings been reviewed?
        previous_all_reviewed = True
        unsuspended_one = False

        for card, note in all_cards_with_notes:
            # Check if this card is a sibling-suspended card
            is_suspended_sibling = (
                card.queue == -1 and
                any(t.startswith(SUSPENDED_TAG_PREFIX) for t in note.tags)
            )

            if is_suspended_sibling:
                if previous_all_reviewed and not unsuspended_one:
                    # Unsuspend this one card
                    card.queue = 0  # Back to new
                    mw.col.update_card(card)
                    
                    # Remove the sibling-suspended tag from this note
                    note.tags = [t for t in note.tags if not t.startswith(SUSPENDED_TAG_PREFIX)]
                    mw.col.update_note(note)
                    
                    total_unsuspended += 1
                    unsuspended_one = True
                    log(f"Unsuspended sibling card {card.id} in group {group_name}")
                # Don't break - continue to check if there are more suspended siblings
            else:
                # This is an active (non-suspended) sibling
                # Check if it has been reviewed
                has_reviews = mw.col.db.scalar(
                    "SELECT COUNT() FROM revlog WHERE cid = ?", card.id
                )
                if has_reviews == 0 and card.type == 0:
                    # This card hasn't been reviewed yet - don't unsuspend the next one
                    previous_all_reviewed = False

    return total_unsuspended


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


def reschedule_review_siblings(card: Card, days_offset: int = 1) -> int:
    """
    Reschedule review siblings to tomorrow after a card is reviewed.
    This ensures the rescheduled due dates sync to mobile.
    """
    if not card or mw.col is None:
        return 0

    try:
        note = card.note()
        sibling_tags = get_sibling_tags_for_note(note)
        
        if not sibling_tags:
            return 0

        today = mw.col.sched.today
        target_due = today + days_offset
        rescheduled = 0

        for tag in sibling_tags:
            group_name = extract_group_name(tag)
            if not group_name:
                continue

            note_ids = mw.col.find_notes(f"tag:{tag}")
            
            for nid in note_ids:
                if nid == card.nid:
                    continue  # Skip the answered card's note

                try:
                    sibling_note = mw.col.get_note(nid)
                    for sib_card in sibling_note.cards():
                        # Only reschedule review cards due today or earlier
                        if sib_card.queue == 2 and sib_card.due <= today:
                            sib_card.due = target_due
                            mw.col.update_card(sib_card)
                            rescheduled += 1
                except Exception:
                    pass

        return rescheduled

    except Exception as e:
        log_error("Error in reschedule_review_siblings", e)
        return 0


def enforce_sibling_separation() -> int:
    """
    Scan all sibling groups and ensure proper separation.
    - For new cards: handled by suspend/unsuspend mechanism
    - For review cards: spread due dates
    """
    if mw.col is None:
        return 0

    groups = get_all_sibling_groups()
    total_rescheduled = 0

    for group_name in groups.keys():
        rescheduled = spread_review_card_due_dates(group_name)
        total_rescheduled += rescheduled

    return total_rescheduled


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

def on_reviewer_did_answer_card(reviewer, card, ease) -> None:
    """Hook called when a card is answered."""
    try:
        buried = bury_custom_siblings(card)
        if buried > 0:
            tooltip(f"Buried {buried} custom sibling(s)")
        
        # Also reschedule review siblings for cross-platform sync
        rescheduled = reschedule_review_siblings(card)
        if rescheduled > 0:
            log(f"Rescheduled {rescheduled} review sibling(s) for sync")
    except Exception as e:
        log_error("Error in reviewer hook", e)

def on_sync_did_finish() -> None:
    """Called after sync completes - check for mobile reviews."""
    try:
        buried = process_reviews_since_last_check()
        if buried > 0:
            tooltip(f"Buried {buried} sibling(s) from synced reviews")
            log(f"Post-sync: buried {buried} siblings")
    except Exception as e:
        log_error("Error in sync hook", e)

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

def show_all_groups() -> None:
    """Show all sibling groups in a dialog."""
    if mw.col is None:
        showInfo("Please open a collection first.")
        return
    
    groups = get_all_sibling_groups()
    
    if not groups:
        showInfo("No sibling groups defined yet.\n\n"
                "Use the Browser to select cards, then right-click -> "
                "Sibling Marker -> Mark as Siblings")
        return
    
    lines = ["Sibling Groups:\n"]
    total_notes = 0
    
    for group_name, note_ids in sorted(groups.items()):
        lines.append(f"  {TAG_PREFIX}{group_name}: {len(note_ids)} notes")
        total_notes += len(note_ids)
    
    lines.append(f"\nTotal: {len(groups)} groups, {total_notes} notes")
    lines.append("\nTip: Groups are stored as tags - view them in the tag sidebar!")
    
    showInfo("\n".join(lines), title="Sibling Marker - All Groups")

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
    """Called when a profile is loaded - run migration and check siblings."""
    migrate_from_json()
    
    # Initialize last check time if not set (so we don't process old reviews)
    if get_last_sync_check_time() == 0:
        import time
        set_last_sync_check_time(int(time.time() * 1000))
    
    # Check if any suspended siblings should be unsuspended
    unsuspended = check_and_unsuspend_siblings()
    if unsuspended > 0:
        tooltip(f"Unsuspended {unsuspended} sibling(s) ready for review")
        log(f"Profile load: unsuspended {unsuspended} siblings")
    
    # Enforce separation for review cards (spread due dates if needed)
    rescheduled = enforce_sibling_separation()
    if rescheduled > 0:
        tooltip(f"Rescheduled {rescheduled} sibling(s) to maintain separation")
        log(f"Profile load: rescheduled {rescheduled} review card siblings")

# =============================================================================
# REGISTER HOOKS
# =============================================================================

gui_hooks.browser_will_show_context_menu.append(on_browser_context_menu)
gui_hooks.reviewer_did_answer_card.append(on_reviewer_did_answer_card)
gui_hooks.main_window_did_init.append(setup_menu)
gui_hooks.profile_did_open.append(on_profile_loaded)
gui_hooks.sync_did_finish.append(on_sync_did_finish)

log("Sibling Marker addon loaded (v2.0 - tag-based sync)")
