---
name: apple-calendar
description: Query and manage Apple Calendar on macOS via `icalBuddy` (read) and AppleScript (`osascript`) for event creation. Use when users ask about upcoming events or adding calendar events.
license: Proprietary. LICENSE.txt has complete terms
compatibility:
  os:
    - darwin
  deps:
    - icalBuddy
---

# Apple Calendar

Use this skill for Apple Calendar tasks on macOS.

## Prerequisites

- macOS
- Install `icalBuddy` for fast read-only queries:

```bash
brew install ical-buddy
```

- `osascript` is built in to macOS for event creation.

## Read events (icalBuddy)

Today's events:

```bash
icalBuddy eventsToday
```

Next 7 days:

```bash
icalBuddy eventsFrom:today to:7 days from now
```

Specific calendars only:

```bash
icalBuddy -ic 'Work,Personal' eventsFrom:today to:3 days from now
```

## Create events (AppleScript)

```bash
osascript -e 'tell application "Calendar" to tell calendar "Work" to make new event with properties {summary:"Team Sync", start date:date "Monday, February 10, 2026 10:00:00", end date:date "Monday, February 10, 2026 10:30:00"}'
```

## Usage guidance

- Always include absolute date/time in confirmations.
- Use read commands before mutating when user intent is ambiguous.
- If automation fails, user likely needs to allow Terminal automation permissions.
