# Photobooth Engine

Headless Ubuntu-based photobooth system with:

- Canon 5D Mark III tethered capture
- RAW processing
- Layout generation
- Print pipeline
- GUI/controller integration

## Structure

- `engine/` core Python modules
- `templates/` overlays and reusable assets
- `config/` default config templates
- `scripts/` helper launch scripts
- `jobs/` per-event data (ignored by Git)

## Current status

- Ubuntu installed
- Wi-Fi + SSH working
- Canon tethering working
- Timed 4-shot controller working
- RAW → JPG processing working
