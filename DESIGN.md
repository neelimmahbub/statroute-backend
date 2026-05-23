# StatRoute — Design System

## Color Strategy
Restrained light mode. Warm slate canvas, one indigo accent carries primary actions, semantic colors for system states only.

## Palette (OKLCH)
- Canvas: oklch(97.5% 0.006 240) — soft warm slate, not pure white
- Surface: oklch(100% 0.003 240) — card white, faint blue tint
- Border: oklch(91% 0.008 240) — slate-200 equivalent
- Text primary: oklch(20% 0.015 240) — deep slate-900
- Text secondary: oklch(45% 0.010 240) — slate-500
- Text muted: oklch(65% 0.008 240) — slate-400

- Indigo (action/active path): oklch(50% 0.22 264) — indigo-600
- Indigo light: oklch(96% 0.04 264) — indigo-50
- Emerald (success/stock): oklch(52% 0.16 162) — emerald-600
- Emerald light: oklch(97% 0.03 162) — emerald-50
- Rose (emergency/alert): oklch(55% 0.20 15) — rose-600
- Rose light: oklch(97% 0.025 15) — rose-50
- Amber (warning/fallback): oklch(72% 0.16 75) — amber-500
- Amber light: oklch(97% 0.03 75) — amber-50

## Typography
- Font stack: system-ui, -apple-system, "Segoe UI", sans-serif
- Body: 13px / 1.5 — text-sm
- Label: 11px uppercase tracking-wider — text-[11px] tracking-widest
- Data: font-mono text-[12px] — numbers, coordinates, IDs
- Heading: font-semibold text-slate-900

## Elevation
- Level 0: canvas bg-slate-50
- Level 1: cards bg-white border border-slate-200 shadow-sm rounded-xl
- Level 2: focused/active cards ring-2 ring-indigo-500/20

## Components
- Button primary: bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2 text-sm font-medium
- Button danger: bg-rose-600 hover:bg-rose-700 text-white
- Badge success: bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full
- Badge error: bg-rose-50 text-rose-700 border border-rose-200 rounded-full
- Badge warning: bg-amber-50 text-amber-700 border border-amber-200 rounded-full
- Progress bar: bg-slate-100 rounded-full; fill emerald/amber/rose by stock level

## SVG Map
- Canvas: bg-white, light grid stroke-slate-100
- Static nodes: fill-slate-300 stroke-slate-400 r=6
- Static edges: stroke-slate-200 stroke-width=1.5
- Active path nodes: fill-indigo-500, glow filter
- Active path edges: stroke-indigo-500 stroke-width=2.5, animated dashoffset
- Transit dot: fill-indigo-600, animateMotion, dur=eta_seconds
- Emergency node (destination): fill-rose-500

## Motion
- Path draw: stroke-dashoffset ease-out 0.7s per hop
- Transit dot: animateMotion dur=eta_seconds (distance-proportional from backend)
- Card entry: opacity 0->1 + translateY -4px, 250ms ease-out
- Inventory flash: bg-emerald-50 pulse 600ms on update
