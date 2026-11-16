# RIKSORA design tokens (2026-11-06)

Founder remediation P1: one semantic vocabulary for product pages and the terminal, without losing terminal density. Visual source: design canvas `5AHxbsfoT3xdaxuMi4mJMb` (DesignSystem, Workspace, MobileTrading artboards).

## Layers

1. **Brand** (`src/tickAlpha/riksoraBrand.css`, `:root`): navy `#061A3C`, blue `#1378F5`, white, ice `#D9EAFE`, yellow `#FFCE55` (rare emphasis and focus), coral `#FF7373` (risk/error only), Inter + IBM Plex Mono, and AA helper shades.
2. **Semantic** (same file): names by role, used by product pages (`alphaProduct.css`).
3. **Terminal bridge** (`src/tickAlpha/tickAlpha.css`, `.tick-alpha` scope): the dense terminal styles keep their `--lab-*` names (shared with older surfaces in `src/workspace/designTokens.css`, which is unchanged), and inside RIKSORA those names resolve to the semantic layer.

## Semantic tokens

| Token | Value | Role |
|---|---|---|
| `--rk-ink` | navy | text on white/ice cards |
| `--rk-card` / `--rk-soft` / `--rk-ice-tint` | white / `#F3F8FF` / `#EAF2FD` | cards, fields on cards, quiet buttons and active rows |
| `--rk-panel` / `--rk-panel-raised` / `--rk-selected` | `#0C2655` / `#163566` / `#1B4A8C` | navy panels and terminal chrome, raised menus, selected rows |
| `--rk-line` / `--rk-line-strong` / `--rk-line-card` | `#1D3560` / `#2B4878` / ice | borders on navy, terminal control borders, borders on white |
| `--rk-text-on-navy` / `--rk-text-soft-on-navy` | white / `#E6EDF7` | primary text on navy |
| `--rk-muted-on-navy` / `--rk-subtle-on-navy` | `#C3D6F2` (10.9:1) / `#A9BDDB` (8.6:1) | secondary text on navy |
| `--rk-muted-on-white` | `#4A5B75` (6.9:1) | secondary text on white |
| `--rk-focus` | yellow | focus ring |
| `--rk-success` / `--rk-danger` / `--rk-danger-ink` / `--rk-danger-bg` / `--rk-warning-bg` | `#68D6BD` / coral / `#9E2B33` / `#FFE1E1` / `#FFF8E1` | state colours |
| `--rk-radius-pill` / `-card` / `-field` / `-dense` | 999 / 24 / 16 / 6 px | product pills, cards, fields; terminal density |
| `--rk-control` / `--rk-control-dense` | 44 / 32 px | touch-size product controls; terminal controls |
| `--rk-ease` / `--rk-fast` / `--rk-mid` | `cubic-bezier(.2,.8,.2,1)` / 160 ms / 220 ms | motion; every animation has a `prefers-reduced-motion` off switch |

## Terminal bridge

| `--lab-*` (terminal) | Resolves to |
|---|---|
| `--lab-font-ui` / `--lab-font-data` | `--rk-font-ui` / `--rk-font-data` |
| `--lab-surface-workspace` / `-secondary` / `-elevated` | `--rk-panel` / `#102D5E` / `--rk-panel-raised` |
| `--lab-text-primary` / `-secondary` / `-on-light` | `--rk-text-soft-on-navy` / `--rk-subtle-on-navy` / `--rk-ink` |
| `--lab-border` | `--rk-line-strong` |
| `--lab-accent` / `--lab-selected` | `--rk-blue-on-dark` / `--rk-selected` |
| `--lab-success` / `--lab-warning` / `--lab-error` | `--rk-success` / yellow / coral |
| `--lab-radius` | `--rk-radius-dense` |
| `--lab-surface-chart` | unchanged neutral dark (`#08090B`): the chart canvas colours live in `CandleChart.jsx` and stay the approved neutral set |

Sizes, spacing and type scale (`--lab-text-*`, `--lab-space-*`, `--lab-control*`) are untouched, so the terminal keeps its density.

## Evidence

Before/after screenshots at the same data: product pages are pixel-identical (the semantic values equal the old literals); terminal chrome moves from grey-black panels to the navy panel family. AccessLint 0 violations on replay and journal after the change.
