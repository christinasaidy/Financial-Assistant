---
version: alpha
name: Fatourati
description: A receipt-first expense tracker for Lebanon. Scan receipts, track spending in USD and LBP, ask questions in English or Arabizi.
# Tokens (colors, typography, rounded, spacing, components) are added here as each one is decided.
# Every token needs a matching entry in DECISIONS.md.
# Colours (D022). The format has no themes, so each dark value is its own token with a -dark suffix.
colors:
  primary: "#2443a8"        # pen blue: main button, links, things the user can change
  primary-dark: "#9db0ff"
  paper: "#f3f4f1"          # thermal paper (background)
  paper-dark: "#17181b"
  ink: "#1c1d21"            # text and fine budgets
  ink-dark: "#e6e6e1"
  ink-2: "#575a60"          # grey text: dates, labels, captions
  ink-2-dark: "#a2a4a8"
  rule: "#c3c6c2"           # dividers
  rule-dark: "#3a3c40"
  track: "#dfe1dd"          # empty part of a budget bar
  track-dark: "#2a2c30"
  near-limit: "#8a5a00"     # budget at 80% or more
  near-limit-dark: "#e0a43a"
  limit-reached: "#b0241b"  # budget at 100% or more
  limit-reached-dark: "#e0524f"
typography:
  body:            # D006, D013: sentences
    fontFamily: DejaVu Sans
    fontSize: 15px
    fontWeight: 400
  body-mono:       # D006, D013: receipt text at the base size
    fontFamily: DejaVu Sans Mono
    fontSize: 15px
    fontWeight: 400
# Type scale "Balanced" (D014). Sizes in px; all follow the iPhone's text-size setting.
  total-hero:      # month total; printed look G
    fontFamily: DejaVu Sans Mono
    fontSize: 36px
    fontWeight: 700
    lineHeight: 38px
  screen-title:    # capitals (D015), no extra letter spacing (D028)
    fontFamily: DejaVu Sans Mono
    fontSize: 22px
    fontWeight: 700
    lineHeight: 26px
    letterSpacing: 0em
  shop-name:       # capitals; printed look E
    fontFamily: DejaVu Sans Mono
    fontSize: 16px
    fontWeight: 700
    lineHeight: 21px
  total-line:      # capitals; printed look E
    fontFamily: DejaVu Sans Mono
    fontSize: 16px
    fontWeight: 700
    lineHeight: 21px
  receipt-line:    # printed look E
    fontFamily: DejaVu Sans Mono
    fontSize: 15px
    fontWeight: 400
    lineHeight: 20px
  sentence:
    fontFamily: DejaVu Sans
    fontSize: 15px
    fontWeight: 400
    lineHeight: 22px
  meta:            # dates; grey
    fontFamily: DejaVu Sans Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 18px
  section-label:   # capitals; grey
    fontFamily: DejaVu Sans Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
    letterSpacing: 0.08em
  caption:         # "Looked at"; grey
    fontFamily: DejaVu Sans Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
# Shapes (D032): square corners everywhere.
rounded:
  none: 0px
# Spacing (D031): a 4 px scale; nothing in between.
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px
  screen-margin: 20px
---

# Fatourati design system

Figma file (icons, wordmark, design work):
[Fatourati design system](https://www.figma.com/design/yH3BO0dprC2nmaKwBdbiDw/Fatourati-design-system).
Its "Color" variables mirror the colour tokens below one for one, `-dark` tokens included (Figma's free plan allows
a single mode, so there is no Light/Dark switch).
Its text styles carry the typography token names below (the nine roles of D014; colour is set on the text, not in
the style). DejaVu is uploaded to the Figma account so the file and Figma's tools can use it.

This file follows the [DESIGN.md format](https://github.com/google-labs-code/design.md) (Google Labs, version
`alpha`): exact values (tokens) go in the YAML front matter above, and the explanation of how to use them goes in the
sections below, in the format's fixed order. **Why** each choice was made, and what else was considered, is recorded
in [DECISIONS.md](DECISIONS.md). Sections not decided yet say so.

## Overview

**Name.** Fatourati (فاتورتي, "my receipt"). See D001.

**Feel: a receipt.** The app should look and feel like a printed receipt, because receipts are what it is about.
What that means in practice (paper texture or not, monospace or not, torn edges, dashed dividers, how far to take
it) is decided element by element below. See D002.

**Wordmark and launch screen.** "Fatourati" is drawn once in Figma with the medium printed look (ragged edges,
patchy fading) and shipped as an image labelled "Fatourati" for VoiceOver; it is the launch screen. A lighter
version is used where it is small. Logotypes are exempt from WCAG contrast; nothing else is. See D010.

**Accessibility.** All other text meets WCAG 2.2 AA contrast, including roughed-up text: grey text never fades,
fading has a floor, no dropouts. See D009.

**Themes.** Light and dark. See D003.

**Platform.** React Native with Expo, designed and tested on an iPhone with Expo Go. See D004.

## Colors

**Paper and ink** (D016, D017, D022). Light mode is thermal paper (#f3f4f1) with near-black ink (#1c1d21); dark
mode is dark paper (#17181b) with light ink (#e6e6e1). Grey ink is for secondary text only.

**Pen blue** (D018, D020) is the only accent: the main button (paper-coloured text on blue) and links, and things
the user can change.

**Budgets** (D021, D022). A fine budget is plain ink: colour appears only when something needs attention. Near the
limit (80% or more) is ochre-amber; at the limit (100% or more) is a calm red, in dark mode the same red brightened only as much as dark paper needs. The
state is always also written in words ("NEAR LIMIT · 88%", "LIMIT REACHED · 107%"), so colour is never the only
signal (WCAG 1.4.1). Bars are plain.

**Never** (D019, anti-AI-slop skill): gradients, the Claude look (warm charcoal, cream text, coral or terracotta),
blood-bright reds.

Every text colour passes WCAG 2.2 AA on its paper in both themes; bars pass 3:1 against their track. Values and
contrast ratios: front matter and D022.

## Typography

**Families** (D006). DejaVu 2.37, bundled with the app (with its LICENSE):
- **DejaVu Sans Mono**, Book and Bold: everything that belongs to a receipt: amounts, labels, receipt lines, shop
  names, totals, the "Looked at" line.
- **DejaVu Sans**, Book and Bold: sentences, such as assistant answers, explanations and the user's own questions.
- Arabic text uses DejaVu's own Arabic letters, in whichever of the two the text sits in.

**Size** (D013, D014). Base 15 px, scale "Balanced" (steps of x1.2): month total 36, screen title 22, shop name
and TOTAL line 16, receipt lines and sentences 15, dates 13, section labels and captions 12 (the smallest size).
Exact values in the front matter. All text follows the iPhone's text-size setting; layouts wrap instead of cutting
text (a receipt row wraps the item name and keeps the price on the right).

**Case** (D012, D015). Screen titles, labels, shop names and the TOTAL line in capitals, applied as a style, never typed in capitals.
Receipt lines exactly as printed. Sentences in normal case.

**Printed look** (D011, within D009):
| Text | Look |
|---|---|
| Large Mono (24 px+, or 18.5 px+ bold) | G: rough edges ~3 px, bleed, patchy fading, streaks, specks; never below 52% opacity |
| Small Mono | E: rough edges under 1 px, slight bleed; never faded |
| Grey text | E's edges only, never faded (for now) |
| Sans sentences | clean |
| Wordmark | medium printed look, artwork (D010) |

## Iconography

Our own icons, drawn in Figma (page "Icons"); no icon library (D008, D025). First six (D024): Home, Receipts, Scan,
Budgets, Assistant, Back; then (D030) Notifications, Close, Settings, Add, Flash, Gallery. SVGs in
`frontend/assets/icons/` (`name.svg` clean, `name-printed.svg` printed; both use `currentColor`).

- **Grid:** 24 px frame, 256-unit grid; 16-unit stroke (1.5 px at 24 px), round caps and joins; Phosphor-like.
- **Look:** two variants per icon: Clean (editable stroke) and Printed (a light thermal-print feel: slight edge
  wobble, soft fade never below 68% ink; D026), built as vector geometry so it exports as SVG.
- **Colour:** ink in light mode, ink-dark in dark mode. The fade is only transparency (in Figma an alpha mask
  named Fade; in code a gradient of opacity), so one drawing serves both themes. Faintest ink: about 5.5:1 on
  paper, 7:1 on dark paper.
- **Beside text** (D027): box = font size, centred on the line, gap 0.6 em. **Alone:** 24 px, 44 pt touch area. The app uses the Printed variant.

## Layout

**Spacing** (D031). Scale 4, 8, 12, 16, 24, 32, 48 px. Screen side margins 20 px, so a 15 px receipt line holds 39
Mono characters, the width of a real receipt. 8 px between a label and its content, 16 px between rows, 24 px
above and below a rule between sections.

**Home** (D035), top to bottom: header (small wordmark, bell); THIS MONTH label, month total, combined-currency
line; rule; BUDGETS (three closest to their limit) with "See all"; rule; RECENT (last three receipts); tab bar.

**Money** (D034). `$6.60`, `450,000 LBP`. A mixed total is shown in dollars and says how it was combined:
"$412.60 + 3,150,000 LBP at 89,500 LBP per $".

## Elevation & Depth

None (D032): no shadows, no cards. Everything sits flat on the paper, grouped by rules and space.

## Shapes

**Corners:** 0 everywhere (D032). **Rules:** dashed 1 px (4 on, 3 off) in `rule` between sections and receipt rows,
like a receipt's tear lines; solid 1 px only for the tab bar's top edge. **Budget bars:** 4 px, square ends, on
`track`.

## Components

**Tab bar** (D033). Home · Receipts · Scan · Budgets · Assistant; five equal tabs, 64 px plus the home indicator,
solid top rule. Each tab: printed icon (24 px) over a section-label caption. Selected: `ink` plus a 2 px ink bar at
the top; others `ink-2`. Scan is a 44 x 44 px `primary` square with a paper-coloured icon.

**Icon beside text** (D027). The icon box equals the font size and is centred on the line; the gap is one Mono
character (0.6 em). Icons on their own are 24 px with a 44 x 44 pt touch area.

**Wordmark** (D029). FATOURATI in capitals; large (48 px, launch screen) and small (20 px, Home header) versions in
`frontend/assets/wordmark/`, shipped as images labelled "Fatourati".

Other components (buttons, inputs, sheets) are sized when their screens are designed.

## Do's and Don'ts

Not decided yet.
