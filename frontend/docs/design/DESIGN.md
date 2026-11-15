---
version: alpha
name: Fatourati
description: A receipt-first expense tracker for Lebanon. Scan receipts, track spending in USD and LBP, ask questions in English or Arabizi.
# Tokens (colors, typography, rounded, spacing, components) are added here as each one is decided.
# Every token needs a matching entry in DECISIONS.md.
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
  screen-title:    # font and case still open
    fontFamily: DejaVu Sans Mono
    fontSize: 22px
    fontWeight: 700
    lineHeight: 26px
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
---

# Fatourati design system

Figma file (icons, wordmark, design work):
[Fatourati design system](https://www.figma.com/design/yH3BO0dprC2nmaKwBdbiDw/Fatourati-design-system).

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

Not decided yet.

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

**Case** (D012). Labels, shop names and the TOTAL line in capitals, applied as a style, never typed in capitals.
Receipt lines exactly as printed. Sentences in normal case.

**Printed look** (D011, within D009):
| Text | Look |
|---|---|
| Large Mono (24 px+, or 18.5 px+ bold) | G: rough edges ~3 px, bleed, patchy fading, streaks, specks; never below 52% opacity |
| Small Mono | E: rough edges under 1 px, slight bleed; never faded |
| Grey text | E's edges only, never faded (for now) |
| Sans sentences | clean |
| Wordmark | medium printed look, artwork (D010) |

## Layout

Not decided yet.

## Elevation & Depth

Not decided yet.

## Shapes

Not decided yet.

## Components

Not decided yet.

## Do's and Don'ts

Not decided yet.
