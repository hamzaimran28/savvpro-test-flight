# AI usage — FlightHub

Short disclosure of how **AI coding assistants** were used and how output was **validated**, for assessment transparency.

---

## Tools

Development was done in **Cursor** using built-in AI features (composer / agent-style chat with models routed by Cursor). No separate standalone API billing beyond the Cursor product.

---

## How AI helped

AI sped up **UI iteration** (layout, dark theme, seat map styling, confirmation overlays), **initial test and doc scaffolding**, and **cross-cutting explanations** (e.g. mapping **409** responses to clearer staff messaging). The heavy lifting was still **review, correction, and verification** on my side.

---

## Mistakes from AI output (and how they were fixed)

**Backend / data**

- **Inventory counter vs real occupancy under concurrency** — After parallel booking attempts, the stored `seats_available` column could disagree with what the seat map and derivation logic implied. The fix was to **reconcile** the stored value from confirmed bookings **inside the booking transaction**, right before commit, so stress scripts and inventory invariants agree. Confirmed with pytest and the concurrent booking verification script.

- **Tests talking to the wrong database** — Early tests imported the database session factory at **module load time**, so seed data landed in one SQLite file while `TestClient` used another after the test harness rewired `DATABASE_URL`. Fixed by obtaining the session factory **only inside tests**, after fixtures run, so seeds and HTTP share one database.

**Frontend**

- **Invalid CSS** — A block was accidentally nested inside `:root`, which breaks the stylesheet. Removed the nesting and restored valid rules.

- **Noisy UX** — Some flows showed both a banner and a modal for the same event. Reduced to **one** clear pattern per outcome.

These issues were caught by **running the app**, **running automated tests**, and **reading diffs** — not by trusting first-pass AI output.

---

## Prompting style

Work was **iterative**: broad goals first (e.g. “polish UI without frameworks”, “add pytest with isolated DB”, “handle already-cancelled cancel”), then tighten based on failing tests or manual checks. No single “magic prompt” replaced engineering judgment.

---

## Validation

All behavior that matters for assessment was checked with:

- **Manual exercise** of the UI against a live API
- **`python -m pytest`** (backend)
- **Optional** `scripts/verify_*.py` runs for booking and concurrency

**Takeaway:** AI accelerated drafting and exploration; **correctness, boundaries, and design trade-offs** remained **human-owned** and test-backed.
