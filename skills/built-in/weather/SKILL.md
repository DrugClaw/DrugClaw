---
name: weather
description: Get current weather and short forecasts quickly using `wttr.in` (no API key required). Use when users ask for weather by city/region.
license: Proprietary. LICENSE.txt has complete terms
compatibility:
  deps:
    - curl
---

# Weather

Use this skill for quick weather lookups without API keys.

## Current weather

```bash
curl -s "wttr.in/San+Francisco?format=3"
```

## Compact format

```bash
curl -s "wttr.in/San+Francisco?format=%l:+%c+%t+%h+%w"
```

## Multi-day forecast

```bash
curl -s "wttr.in/San+Francisco?m"
```

## Usage guidance

- URL-encode spaces with `+`.
- Use `?m` for metric and `?u` for US units.
- For ambiguous place names, clarify state/country first.
