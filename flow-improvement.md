# Sibling Marker Flow Improvement Notes

## Ideal Flow

### What the Perfect Experience Would Look Like

1. **Discovery**: User naturally discovers sibling marking through clear UI affordances
2. **Marking**: User can quickly mark related cards as siblings with minimal friction
3. **Visibility**: User can always see which cards are siblings, both in browser and during review
4. **Review**: Siblings are automatically buried with zero user intervention, across all platforms
5. **Cross-Platform**: Behavior is identical whether reviewing on desktop, AnkiMobile, or AnkiDroid
6. **Flexibility**: User can easily manage groups, remove cards, merge groups, etc.
7. **Transparency**: User understands what happened (how many siblings buried) without intrusion

---

## Current Shortcomings & Potential Issues

### 1. Discovery & Onboarding

**Problem**: The addon has no onboarding. Users must know to right-click in the browser.

- No visual indicator that the addon is installed
- Buried in right-click context menu submenu (3 clicks deep)
- "Tools → View Groups" is the only persistent menu item, and it's passive
- New users may never discover the feature

**Consequence**: Low adoption even among users who installed it intentionally.

---

### 2. Sibling Relationship Visibility

**Problem**: There's no way to see sibling relationships while browsing cards.

- Browser doesn't show which cards are siblings
- No column showing sibling group membership
- No highlighting of siblings when selecting cards
- When selecting cards to mark, can't see if they're already in a group

**Consequence**: Users work blind, may create duplicate groups, or forget which cards are related.

---

### 3. The Marking Flow Has Friction

**Problems**:
- Must open browser (can't mark from reviewer)
- Must select 2+ cards from 2+ different notes — error message if violated, but no guidance
- If cards are already in groups, dialog appears but logic may confuse users
- Auto-generated group names (`sibling::a1b2c3d4`) are meaningless to humans
- Named groups require manual typing — typos create new groups

**Edge case**: User selects 10 cards, 8 from one note and 2 from another. The requirement is "2+ cards from 2+ notes" which passes, but user probably wanted all 10 in the group. The 8 cards from one note are native siblings anyway.

---

### 4. Burying Logic Gaps

**Problem**: Only cards that are "due now" get buried.

Current logic buries:
- New cards (queue == 0)
- Learning cards (queue == 1)
- Review cards due ≤ today
- Day learning due ≤ today

**Not buried**:
- Cards that will become due later in the same session (intraday learning)
- Cards scheduled for later today but not yet in queue

**Scenario**: 
1. You review Card A at 10:00 AM
2. Sibling Card B is a learning card with 10-minute step, due at 10:30 AM
3. Card B is NOT buried because at 10:00 AM it wasn't in queue
4. At 10:30 AM, Card B appears — sibling burying fails

**Consequence**: Siblings can still appear in the same session for learning cards.

---

### 5. Learning Card Progress Loss

**Problem**: Burying learning cards may reset their progress.

When a learning card is buried:
- Anki's scheduler may reset learning steps (behavior varies by scheduler version)
- User has to restart learning from step 1 tomorrow

**Scenario**: Sibling A is on learning step 3/4 (almost done). You review Card B. Sibling A gets buried. Tomorrow, A restarts at step 1.

**Consequence**: Inefficient learning, user frustration.

---

### 6. Cross-Platform Sibling Separation

**Problem**: The suspend/unsuspend mechanism for new cards is complex and fragile.

Current approach:
1. When marking siblings, suspend all new cards except the first
2. On profile load, check if first card was reviewed → unsuspend second
3. Repeat until all cards are reviewed

**Issues**:
- Requires sync between every single card review (unrealistic)
- If user reviews 3 cards on mobile before syncing, only 1 new sibling unsuspends
- Sequential order is arbitrary (first card ID) — user may want different order
- What if user wants to see new siblings on same day but different sessions?
- Suspended cards tagged with `sibling-suspended::` but these tags accumulate forever

**Scenario**:
1. User marks 5 new cards as siblings
2. Cards 2-5 are suspended
3. User reviews card 1 on mobile
4. User reviews cards 2-5 on mobile before syncing (cards still suspended on server)
5. Nothing happens — cards 2-5 never seen on mobile
6. User syncs desktop, unsuspends card 2
7. User must sync mobile to see card 2

**Consequence**: New card sibling separation is unreliable and confusing.

---

### 7. Review Card Due Date Manipulation

**Problem**: Rescheduling review siblings to "tomorrow" interferes with SRS.

Current approach:
- When you review a card, sibling review cards get their due date moved to tomorrow
- Also `spread_review_card_due_dates()` spaces siblings 1 day apart

**Issues**:
- Changing due dates disrupts the SRS algorithm's predictions
- Cards can pile up if many siblings are rescheduled to tomorrow
- User loses control over their review schedule
- Anki's "due" field is the source of truth for scheduling — modifying it is invasive

**Scenario**: You have 5 sibling review cards all due today. You review one. The other 4 get pushed to tomorrow. Now tomorrow you have your normal load PLUS 4 extra cards.

**Consequence**: Unpredictable review loads, potential SRS damage.

---

### 8. Post-Sync Mobile Review Processing

**Problem**: `sync_did_finish` hook may miss reviews or run too late.

Current approach:
1. After sync, scan revlog for reviews since last check
2. For each reviewed card, bury its siblings

**Issues**:
- Only runs on desktop after sync — if you only use mobile, nothing happens
- By the time you sync, you may have already reviewed siblings on desktop
- Revlog scanning can be slow for large collections
- If sync fails or is partial, reviews may be missed

**Scenario**: 
1. Review card A on mobile
2. Don't sync for 3 days
3. Review sibling B on desktop during those 3 days
4. Finally sync — addon tries to bury B, but it was already reviewed

**Consequence**: Mobile-first users get no benefit from sibling separation.

---

### 9. Tag Clutter

**Problem**: Sibling tags visible in tag sidebar create visual noise.

- Every sibling group creates a `sibling::groupname` tag
- Tags appear in the left sidebar
- Large numbers of auto-generated UUIDs (`sibling::a1b2c3d4`) are meaningless
- No way to hide sibling tags from the UI
- Tag hierarchy (`sibling::anatomy::bones`) adds multiple nested levels

**Consequence**: Tag sidebar becomes cluttered and harder to navigate.

---

### 10. No Undo / Limited Management

**Problem**: Actions are permanent with no easy reversal.

- No undo for marking siblings
- "Remove from Sibling Group" exists but requires re-selection
- No way to merge two groups
- No way to split a group
- No way to rename a group (must remove and re-add)
- "View Groups" is read-only, can't act on groups

**Consequence**: Mistakes are tedious to fix.

---

### 11. Single Note Limitation

**Problem**: All cards from a note share the same sibling relationships.

Tags are applied at the note level, not card level. So:
- If note A has cards A1 and A2
- And you want A1 to be siblings with B1
- And A2 to be siblings with C1
- This is impossible — both A1 and A2 will be siblings with both B1 and C1

**Consequence**: Can't create card-level sibling relationships for multi-card notes.

---

### 12. Performance Concerns

**Problem**: Large sibling groups may cause performance issues.

- `get_sibling_groups_for_card()` queries database for every tag on a note
- `bury_custom_siblings()` does multiple database queries per group
- Groups with 100+ cards could cause noticeable delays
- `process_reviews_since_last_check()` scans entire revlog since last check

**Not tested**: What happens with 1000+ card sibling groups?

---

### 13. Multiple Group Membership

**Potential Problem**: Cards in multiple sibling groups may have unexpected behavior.

If card A is in groups X and Y:
- Reviewing A buries all cards in BOTH groups
- This might be intentional (transitive sibling relationship)
- Or might surprise users who wanted separate groups

**No documentation** explains this behavior.

---

### 14. Reviewer UI Absence

**Problem**: No UI during review to indicate sibling relationships.

- No indication that current card has siblings
- No way to see which cards were buried
- Tooltip disappears quickly
- No way to unbury siblings if you want to study them now

**Consequence**: The addon is invisible during the most important phase (reviewing).

---

## Initial Improvement Sketches

### Quick Wins (Low Effort)

1. **Add keyboard shortcut** for marking siblings in browser (Ctrl+Shift+S)
2. **Improve tooltip** — show group name(s) and list of buried cards
3. **Add browser column** showing sibling group membership
4. **Better default names** — use first card's content snippet instead of UUID
5. **Add confirmation dialog** showing what will happen before marking

### Medium Effort

6. **Reviewer indicator** — small icon showing "2 siblings" when reviewing a sibling card
7. **"Unbury siblings" button** — let user override and study siblings today
8. **Highlight siblings** in browser when one is selected
9. **Group management dialog** — rename, merge, split, delete groups
10. **Option to hide sibling tags** from sidebar (move to Anki's hidden tags)

### Major Rethinks

11. **Replace suspend/unsuspend with scheduling** — use rescheduling instead of suspension for new card separation
12. **Don't modify due dates** — use manual burying only, let user accept mobile limitations
13. **Card-level sibling support** — store relationships in card fields or custom data, not note tags
14. **Learning card handling** — option to NOT bury learning cards, or bury them to end of session rather than next day
15. **Intraday burying** — bury siblings for the entire session, not just "due now"

### Alternative Approaches to Consider

16. **Deck-based separation** — instead of burying, put sibling cards in a "review later" filtered deck
17. **Time-based separation** — "don't show siblings within X hours" instead of daily
18. **Priority ordering** — mark which sibling should be reviewed first, second, etc.
19. **Native integration** — submit feature request to Anki to support cross-note siblings natively

---

## Questions to Resolve

1. Should learning card progress be preserved? If so, how?
2. Is SRS due date modification acceptable to users?
3. How important is mobile parity vs. desktop-only reliability?
4. Should sibling relationships be transitive? (A~B and B~C means A~C?)
5. What's the expected group size? 2-3 cards? 10+? 100+?
