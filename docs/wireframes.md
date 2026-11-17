# Implemented UI plan

This plan replaces the original static Gradio wireframes. The working voice interface is the visual and interaction baseline.

## Shared shell

Every view uses the same warm paper background, forest/olive palette, editorial typography, brand header, and persistent navigation:

```text
┌ Loose Ends ─────────── [ Talk ] [ Review 2 ] [ Board ] ── Listening ┐
│                                                                       │
│                         active view                                   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

On narrow screens, the navigation moves below the brand. No content is embedded from another page and no action opens a second local product.

## Talk

The voice orb remains the primary interaction. Live notes sit beside it on desktop and below it on mobile. A short journey guide makes completion explicit:

```text
Talk naturally → say “make a draft” → review and approve
```

When a persisted draft appears, Talk shows a high-visibility “Draft ready — Review draft” card and increments the Review badge. Ending a conversation opens Review if a draft exists. If none exists, a message explains exactly what to say next time.

Important Talk states:

| State | Behaviour |
|---|---|
| Offline | Orb says Start talking; typed input is disabled. |
| Connecting | Explain whether the room or companion is being awaited. |
| Listening | Animate the orb/wave; microphone remains interruptible. |
| Thinking | Preserve the transcript and show a distinct warm state. |
| Speaking | Speak final agent text and allow the user to interrupt. |
| Draft ready | Show Review badge and handoff card without ending the room. |
| Ended without draft | Stay on Talk and explain “say make a draft.” |

## Review

Review is a master-detail workspace. The left side lists pending drafts; the right side edits the selected draft.

Editable fields are title, description, due date, suggested work time, and one step per line. The source excerpt and unresolved detail stay visible. The two outcomes are Dismiss or Approve & add to board. Approval navigates directly to Board.

An empty Review view explains the complete path back to Talk instead of presenting a blank page.

## Board

The Board groups approved records into:

- In progress
- Ideas
- Finished & set aside

Task cards show date context, editable progress through checkboxes, and explicit Complete, Cancel, or Reopen actions. Completing a step does not silently complete its parent. A “Talk through another” action returns to the voice experience.

## Navigation acceptance criteria

- Talk, Review, and Board are reachable from every view in one click.
- The current view is visibly selected and exposed with `aria-current`.
- A reload preserves the selected hash route.
- Creating a draft updates the Review badge without a full reload.
- Ending a conversation with a draft opens Review.
- Approving a draft opens Board.
- Empty states always offer a useful next action.
- Mobile navigation and editors do not depend on hover or drag-and-drop.

The old SVG files in `docs/wireframes/` are historical exploration only and are not authoritative for implementation.
