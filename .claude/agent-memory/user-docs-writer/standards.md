---
name: IHP Documentation Standards
description: Established patterns, conventions, and naming for user-facing documentation
type: reference
---

## Documentation Structure

The project uses this established doc organization:

- `README.md` — Project hero, quick start (5 min), feature overview, doc navigation
- `CHANGELOG.md` — Keep a Changelog format, user-friendly language, semantic versioning
- `docs/INSTALLATION.md` — HACS + manual install methods, troubleshooting
- `docs/CONFIGURATION.md` — Setup flow, required vs optional fields, advanced settings, entities reference
- `docs/USER_GUIDE.md` — Common tasks, tips, best practices for end users
- `docs/HOW_IT_WORKS.md` — Technical explanation (but accessible), algorithms, cycle detection
- `docs/TROUBLESHOOTING.md` — Problem table, diagnostic steps, log analysis

## User-Facing Feature Names

- **Learned Heating Slope (LHS)** — the core metric, measured in °C/hour
- **Dead Time** — system lag before temperature rises (seconds)
- **Anticipation Time** — when IHP will trigger heating (calculated based on LHS + Dead Time)
- **Heating Cycle** — period of active heating from start to stop
- **Contextual LHS** — time-of-day specific heating slope (per hour)
- **IHP Preheating** — the main enable/disable switch entity
- **Vacation Mode** — automatic stop when scheduler disabled

## Sensor Naming Convention

Sensors follow the pattern: `sensor.intelligent_heating_pilot_<device_name>_<metric>`

Common sensors:
- `learned_heating_slope` — core LHS metric
- `dead_time` — learned dead time in seconds
- `anticipated_start_time` — calculated heating trigger time
- `next_schedule` — details of next scheduled event

## Badge & Version Patterns

- Version badge: `![Version](https://img.shields.io/badge/version-X.Y.Z-blue)`
- Status badge: `![Status](https://img.shields.io/badge/status-beta-yellow)` or green for stable
- HACS badge: `[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)`

## CHANGELOG Conventions

- **Keep a Changelog format** (Added, Changed, Fixed, Removed sections)
- **User language, not technical jargon** (e.g., "Fixed slow startup" not "Optimized recorder queries")
- **Link to GitHub issues** where applicable
- **No internal class names or module paths** in user-facing entries
- **Date format**: YYYY-MM-DD, use release date when known
- **Version format**: Semantic versioning (X.Y.Z)

## Writing Style for Users

- **Tone**: Friendly, confident, approachable
- **Audience**: Technically curious homeowners, not software engineers
- **Structure**: Short sentences, visual hierarchy, plenty of headings
- **Examples**: Always include concrete examples (e.g., "LHS = 2.0°C/hour" not just "slope value")
- **Avoid**: Walls of text, unexplained abbreviations, implementation details

## Common Abbreviations (all defined on first use)

- **IHP** — Intelligent Heating Pilot
- **LHS** — Learned Heating Slope
- **VTherm** — Versatile Thermostat
- **HACS** — Home Assistant Community Store
- **HA** — Home Assistant

## Cross-Reference Patterns

- Links between docs use relative paths: `[link text](file.md)` or `[link text](../path/file.md)`
- Footer navigation in guides: `📚 **See also:** [Guide 1](file1.md) · [Guide 2](file2.md) · [← Back to README](../../README.md)`
- README uses table for doc navigation (For | Start Here | columns)

## Visual Elements

- Emoji markers: 🚀 Quick Start, ⚙️ Configuration, 💡 Tips, ⚠️ Warnings, 🐛 Troubleshooting, 📖 Guides
- Tables for reference data (config options, sensors, comparisons)
- Code blocks with language tags: ```yaml, ```json, ```python
- Blockquotes for tips/warnings: `> 💡 **Tip:** ...`
- Numbered lists for sequential steps, bullet lists for non-sequential
