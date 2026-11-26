# Design decisions

One entry per design decision, numbered in the order made. Entries are not rewritten: if a decision changes, a new
entry replaces it and the old one is marked **Superseded by Dxxx**. The current values live in
[DESIGN.md](DESIGN.md).

Each entry follows Michael Nygard's decision record (status, context, decision, consequences), plus the options
considered, so the reasoning can be explained later.

---

## D001: The app is called Fatourati

- **Status:** Accepted, 2026-11-15
- **Context:** The app needs a name for the interface, the icon and the report.
- **Decision:** Fatourati (فاتورتي, "my receipt").
- **Consequences:** The name points the visual direction at receipts (D002).

## D002: The design feels like a receipt

- **Status:** Accepted, 2026-11-15
- **Context:** Scope v2 suggested a modern banking-app look (inspired by Revolut). The name is about receipts, and
  receipts are the app's core object.
- **Options considered:** banking-app look (scope v2); receipt look.
- **Decision:** The overall feel is a printed receipt. How far each element follows it is decided one element at a
  time (fonts first).
- **Consequences:** Replaces the banking-app direction of scope v2 as the main theme. Whether some of its layout
  patterns stay (one large number per screen, slide-up sheets, bottom tabs) is still open.

## D003: Light and dark themes

- **Status:** Accepted, 2026-11-15
- **Context:** Phones switch between light and dark.
- **Decision:** Both themes are designed. Every color is defined for both.
- **Consequences:** Each color decision needs a light and a dark value, checked for contrast on both. The DESIGN.md
  format has no built-in themes, so how dark values are written there is decided with the colors.

## D004: Designed and tested on an iPhone with Expo Go

- **Status:** Accepted, 2026-11-15
- **Context:** Scope v2 said Android first. The phone available for testing is an iPhone, and development is on
  Windows (no Mac).
- **Decision:** React Native with Expo, run on the iPhone through Expo Go.
- **Consequences:** Only libraries that work in Expo Go, unless agreed otherwise. Push notifications on iOS need a
  custom build and a paid Apple developer account, so they are optional. In-app notifications are not affected.
  The iPhone's system font (San Francisco) is the default unless a custom font is chosen.

## D005: How the design system is recorded

- **Status:** Proposed, 2026-11-15
- **Context:** Design decisions must be recorded in the codebase, in `frontend/docs/design/`, in a recognised
  structure.
- **Options considered:**
  1. One `DESIGN.md` in Google's format (YAML tokens + Markdown sections in a fixed order). Readable by people and
     coding tools, can be linted and exported to design-token JSON. Format is `alpha` and has no themes.
  2. Design tokens as JSON in the W3C Design Tokens format (stable since 2025.10, themes through its Resolver
     Module), with separate docs. A real standard, but JSON is hard to read and needs a build tool to reach React
     Native.
  3. A folder per topic (foundations, components, patterns), as large design systems do. Scales well, but many
     files for a one-person project.
- **Decision:** Option 1 for the current values, plus this file for the reasons. Option 2 stays reachable: the
  DESIGN.md tool can export to that format.
- **Consequences:** Two files to keep in step: a new token in DESIGN.md needs an entry here. The app's theme code
  must match DESIGN.md (how that is checked is decided when the code exists).

## D006: The font family is DejaVu

- **Status:** Accepted, 2026-11-15
- **Context:** The app should feel like a receipt (D002). Christina suggested DejaVu because it resembles receipt
  print.
- **Facts checked** (official release 2.37, July 2016, the latest; its `unicover.txt`, `langcover.txt` and
  `LICENSE`):
  - Members: DejaVu Sans (ExtraLight, Book, Bold, each with Oblique; plus Condensed), DejaVu Sans Mono (Book and
    Bold only, with Oblique), DejaVu Serif.
  - Arabic (receipt lines like Zaatar w Zeit's): Sans and Sans Mono have all 36 basic Arabic letters (Arabic block:
    Sans 165/255, Sans Mono 99/255); **Serif has no Arabic at all**.
  - License: Bitstream Vera license, DejaVu changes public domain. Free to bundle in an app; the license text must
    ship with the font; a modified font must be renamed (no "Bitstream" or "Vera" in the name); the font may not be
    sold on its own. A logo drawn from the letters is artwork, not a modified font.
  - Size: about 340 KB per file. Not on Google Fonts; the TTF files are bundled in the app and loaded with
    `expo-font`, which works in Expo Go.
- **Options considered:** DejaVu (Christina); real thermal-printer display fonts (Merchant Copy, Receiptional
  Receipt: very close to a printer, but display-only and poor for long text); the iPhone system font (proposed
  earlier, before the receipt direction).
- **Options for using it** (shown in the font specimen): A Sans Mono everywhere; B Sans Mono for the receipt
  parts, Sans for sentences; C Sans everywhere, Mono only for numbers.
- **Decision:** Option B.
  - **DejaVu Sans Mono** (Book, Bold): amounts, labels, receipt lines, shop names, totals, the "Looked at" line.
  - **DejaVu Sans** (Book, Bold): running text, such as assistant answers, explanations, questions typed by the user.
  - Not used: DejaVu Serif (no Arabic), ExtraLight, Condensed.
  - **Arabic** text uses DejaVu's own Arabic letters (Sans Mono in receipt lines, Sans in sentences), not the
    iPhone's Arabic font. Sans Mono forces every Arabic letter to the same width; Christina accepted that. To be
    confirmed on the iPhone, because the browser specimen draws Arabic differently.
- **Consequences:** Sans Mono has only two weights, so hierarchy comes from size, capitals (D012) and spacing. The
  TTF files and the DejaVu LICENSE ship inside the app.

## D007: No AI-default gradients

- **Status:** Accepted, 2026-11-15
- **Context:** Most AI-built apps default to blue-to-purple gradients; Christina does not want the app to look like
  them.
- **Decision:** No gradients unless one is explicitly decided later. Enforced by the project skill
  `.claude/skills/anti-ai-slop`.
- **Consequences:** Depth and emphasis come from type, rules, color blocks and spacing instead.

## D008: Our own icons, drawn in Figma; no icon library

- **Status:** Accepted, 2026-11-15
- **Context:** Library icons (Lucide in particular) are a common sign of a generated app.
- **Decision:** Christina draws the icons in Figma; 5-6 to start. They reach the code through the Figma MCP. No
  Lucide or other icon library, not even as placeholders.
- **Consequences:** Each screen waits for its icons or uses a marked placeholder box. Which 5-6 icons come first,
  their grid size, stroke and export format (SVG through `react-native-svg`, which works in Expo Go) are to be
  decided.

## D009: All text meets WCAG 2.2 AA, including the printed look

- **Status:** Accepted, 2026-11-15
- **Context:** In the first roughed-up variants the medium fade made the grey date "12/11/2026" hard to read.
  Christina wants the receipt feel without excluding people with weaker sight.
- **Decision:** Every piece of text passes WCAG 2.2 AA contrast (1.4.3): 4.5:1 for normal text, 3:1 for large
  text (24 px, or about 18.5 px bold). For roughed-up text the test is the faintest ink inside a letter (anti-aliased
  edges ignored, as WCAG says). Consequences for the printed look:
  - grey (secondary) text is never faded: at 6.6:1 it fails once it fades below 85% opacity;
  - fading, if used, has a floor: 75% opacity for small text, 62% for large (worst case 7.4:1 / 4.8:1 in light and
    8.2:1 / 6.1:1 in dark on the placeholder colours);
  - no dropouts (specks that cut letters);
  - edge roughness stays under about 1 px at small sizes so 1/7, 3/8, 0/6 stay distinct (judged by eye; WCAG has
    no number for letter shape).
- **Options considered:** printed strengths light / medium / heavy (medium and heavy fail); E "solid ink" (rough,
  bled edges, no fading: same contrast as clean text); F "fade with a floor"; G "rougher" (asked for after F:
  streaks and specks that fade only down to the floor, floors 64% small / 52% large, worst case 5.1:1 / 3.5:1 light
  and 6.4:1 / 4.7:1 dark; the 52% floor is allowed only for large text).
- **Consequences:** Every color decision is checked for contrast in both themes, including faded ink at its floor.
  The floors are recomputed when real colours are chosen. Which of E or F is used is still open.

## D010: The wordmark and the launch screen use the medium printed look

- **Status:** Accepted, 2026-11-15
- **Context:** The medium printed look (ragged edges + patchy fading with no floor) fails D009 for ordinary text,
  but it carries the receipt feel best. WCAG 2.2 (Understanding 1.4.3) exempts logotypes: "Text that is part of a
  logo or brand name has no contrast requirement."
- **Options considered:** medium on the wordmark only; medium also on in-app waiting states (receipt being read,
  assistant thinking). In-app waiting states show status text that must pass AA, so they were left out.
- **Decision:** The "Fatourati" wordmark uses the medium printed look, and it is what the iOS launch screen shows.
  Conditions:
  1. the exception covers the wordmark only: any other text near it follows D009;
  2. it is fixed artwork made once in Figma (the same fade every time), shipped as an image (SVG or PNG); the launch
     screen is a static image in Expo anyway;
  3. the image carries the accessible label "Fatourati" so VoiceOver reads the name;
  4. two versions: medium for large placements (launch screen, onboarding) and a lighter one for small placements
     (about 18-20 px, e.g. a header), so the name stays recognisable.
- **Consequences:** Christina draws the wordmark in Figma (with the icons). The launch screen's background colour
  is decided with the colours. Which typeface the wordmark is drawn from (DejaVu Sans Mono Bold in the specimen) is
  part of that artwork.

## D011: The printed look by text size

- **Status:** Accepted, 2026-11-15 (grey text: "for now")
- **Context:** D009 allows roughed-up text only within AA. The specimen offered E (solid ink), F (fade with a
  floor) and G (rougher).
- **Decision:**
  - **Large Mono text** (24 px and up, or 18.5 px and up in bold; e.g. the month's total): **G**, ragged edges
    (~3 px), slight bleed, patchy fading, print-head streaks and specks, never below 52% opacity.
  - **Small Mono text** (receipt lines, shop names, amounts in lists): **E**, ragged edges under ~1 px and a slight
    bleed; the ink never fades.
  - **Grey text** (dates, labels, the "Looked at" line): E's edges only, never faded. Kept "for now"; may become clean.
  - **Sans text** (sentences): clean, no printed look.
  - The wordmark is separate (D010).
- **Options considered:** strengths light / medium / heavy (fail AA), E, F, G, and a mix by size.
- **Consequences:** G runs close to the AA line (3.5:1 light, 4.7:1 dark on the placeholder colours), so it is only
  allowed on text styles big enough to count as large, and its floor is recomputed when the colours are chosen. How
  the look is built in React Native (no filters there) is still open: a roughed copy of the font renamed e.g.
  "Fatourati Print", Figma artwork for fixed text, or a texture over the text. Live numbers like the total change, so
  they cannot be artwork.

## D012: Receipt-style capitals

- **Status:** Accepted, 2026-11-15
- **Decision:** Labels (e.g. THIS MONTH), shop names and the TOTAL line are shown in capitals, as receipts print
  them. Receipt lines keep the text exactly as printed on the receipt. Sentences keep normal case.
- **Consequences:** Capitals are applied with `textTransform: 'uppercase'`, never by storing or typing capitalised
  text, so VoiceOver reads normal words instead of spelling out letters.

## D013: Base text size 15 px, following the iPhone's text-size setting

- **Status:** Accepted, 2026-11-15
- **Options considered:** 15 px (39 Mono characters per line on an iPhone) or 14 px (42, closer to an 80 mm
  receipt). iOS's own body text is 17.
- **Decision:** Base size 15 px. Text grows and shrinks with the iPhone's text-size setting (Dynamic Type).
- **Consequences:** With larger text settings a line holds fewer Mono characters, so receipt rows must wrap: the item
  name wraps, the price stays on the right. The full type scale (sizes for each text role) is the next decision.

## D014: Type scale "Balanced" (steps of x1.2 from 15 px)

- **Status:** Accepted, 2026-11-15
- **Options considered** (font specimen): Compact x1.125 (total 30, title 19); Balanced x1.2 (total 36, title
  22); Strong x1.333 (total 48, title 27). Small text has a 12 px floor in all three (iOS's smallest is 11).
- **Decision:** Balanced, in px (size / line height):

  | Role | Font | Size |
  |---|---|---|
  | Month total | Mono Bold, printed look G | 36 / 38 |
  | Screen title | Mono Bold (font and case still open) | 22 / 26 |
  | Shop name | Mono Bold, caps, E | 16 / 21 |
  | TOTAL line | Mono Bold, caps, E | 16 / 21 |
  | Receipt line | Mono, E | 15 / 20 |
  | Sentence | Sans | 15 / 22 |
  | Date, meta | Mono, grey | 13 / 18 |
  | Section label | Mono, caps, grey, letter spacing +8% | 12 / 16 |
  | Caption ("Looked at") | Mono, grey | 12 / 16 |

- **Consequences:** All sizes grow with the iPhone's text-size setting (D013). The 36 px total is large text, so
  G's 52% floor applies (D011). Roles not listed (buttons, inputs, tab bar, badges) are sized with their components.

## D015: Screen titles in Mono capitals; section labels stay at 12 px

- **Status:** Accepted, 2026-11-15
- **Context:** Left open by D014.
- **Options considered:** screen titles in Mono or Sans, capitals or normal case; section labels at 12 or 13 px.
- **Decision:** Screen titles ("HOME", "RECEIPTS") are DejaVu Sans Mono Bold in capitals, 22 / 26 px, letter
  spacing as the labels' (to be confirmed with the first screen). Section labels stay at 12 px.
- **Consequences:** Adds screen titles to the capitals of D012 (applied as a style). Every receipt-like heading is
  now Mono capitals; only sentences are Sans.

## D016: The light theme looks like real thermal paper

- **Status:** Accepted, 2026-11-15
- **Options considered:** real thermal paper (a slightly cool, greyish white); plain neutral white; warm cream
  (rejected up front: one of the most common AI-generated looks).
- **Decision:** The light background imitates real thermal paper; ink is a near-black like thermal print. Exact
  values are chosen in the colour study and must pass D009.

## D017: The dark theme is dark paper with light ink

- **Status:** Accepted, 2026-11-15
- **Options considered:** dark paper with light ink (the receipt inverted); a dark table with receipts kept as light
  paper slips on it.
- **Decision:** Dark paper with light ink, the same layout and roles as the light theme.
- **Consequences:** Every colour has a light and a dark value; the printed look's fade floors (D011) are checked in
  both.

## D018: The accent is pen blue

- **Status:** Accepted, 2026-11-15 (light #2443a8, dark #9db0ff). Briefly marked superseded by D019 through a
  misreading; reinstated by D020.
- **Context:** Real receipts are almost all black ink. The colour study showed three receipt-world accents in both
  themes.
- **Options considered:** ink only with reverse print (no colour); thermal red (two-colour thermal paper); pen blue
  (ballpoint, like writing on a receipt by hand).
- **Decision:** Pen blue, for the main button and for things the user can change.
- **Consequences:** Budget states keep their own colours (amber near the limit, red at the limit, proposed); how they
  look, including a roughed-up treatment, is being explored. Contrast on the proposed values: 7.8:1 light, 8.5:1 dark.

## D019: Pen blue dropped; dark mode must not look like Claude; near-limit is orange

- **Status:** Accepted, 2026-11-15. Supersedes D018.
- **Context:** On the first colour study Christina found the light mode good, but the dark mode "all looks like
  Claude colors": warm charcoal paper, cream-white ink, a coral/salmon red and a golden amber. She also dropped pen
  blue after seeing it on the budget variations.
- **Decision:**
  - The light mode values stay as proposed (paper #f3f4f1, ink #1c1d21, grey #575a60).
  - The dark mode has **no warm tint**: a cool neutral or blue-black paper, cool white ink, a true red (hue 0), not
    salmon or coral.
  - "Near the limit" is a pure, saturated **orange** (light #b84300, hue 22; dark #ff8a1f, hue 29), kept clearly
    away from Claude's coral (hue 15, softer). "At the limit" is red (light #b0241b, dark #ff4f4f).
  - The accent is reopened.
- **Options for the accent** (colour study round 2): ink only with reverse print; cash-register green (the customer
  display on a till; light #00715d, dark #3ee6c1); thermal red (shares red with the limit warning). Dark paper:
  neutral black #111213 or blue-black #0e1116.
- **Consequences:** The anti-AI-slop skill now bans the Claude look. All proposed values pass AA in all three
  themes (computed).

## D020: Pen blue stays; budget colours and the dark paper change; no roughed-up budgets

- **Status:** Accepted, 2026-11-15. Corrects D019.
- **Context:** D019 recorded "pen blue dropped". That was a misreading: Christina meant to go back to pen blue
  ("now pen blue again"). She also rejected the roughed-up budget variations.
- **Decision:**
  - The accent is pen blue, exactly as in D018 (light #2443a8, 7.8:1; dark #9db0ff, 9.0:1 on the new dark papers).
  - Budget states: orange near the limit, red at the limit (values as in D019); plain bars, not roughed up.
  - Dark mode: cool, no warm tint (D019 stands on this); paper still to choose, neutral black #111213 or
    blue-black #0e1116.
  - The four roughed-up budget variations (printed bars, stamps, pen marks, character bars) are dropped.
- **Consequences:** The roughed-up type of D011 is not affected by this entry; only the budgets' treatment is.

## D021: Budget colours and the dark mode, chosen by feel

- **Status:** Accepted, 2026-11-15 (direction; exact values chosen next from the colour study)
- **Context:** Christina found the red "too bloody": for someone who is broke it would make them feel guilty. She
  found the cool dark mode ugly and asked to decide the colours together.
- **Options asked:** over the limit: calm and serious / a different hue (plum) / no colour / same as near-limit.
  Near the limit: pure orange / softer ochre / yellow. Fine budgets: ink / pen blue / green. Dark mode: graphite /
  night ink / carbon paper / true black.
- **Decision:**
  - **Over the limit:** calm and serious, a muted brick, no alarm. Supersedes D019's red.
  - **Near the limit:** a softer ochre. Supersedes D019's orange.
  - **Fine budgets:** plain ink, no colour; colour appears only when something needs attention.
  - **Dark mode:** carbon paper: a dark blue-grey background with soft grey-white text (not bright white).
    Supersedes the neutral-black / blue-black papers of D019 and D020.
  - Pen blue unchanged (D018, D020).
- **Consequences:** Candidates must stay clear of Claude's coral (dark-mode brick is kept redder and greyer, hue
  about 6-9) and of golden amber (dark-mode ochre kept at hue 40-41 and greyer). Every candidate passes AA.

## D022: Final colours: the first pen blue palette, with a calm rose-red for "limit reached" in dark mode

- **Status:** Accepted, 2026-11-15; dark "limit reached" superseded by D023. Supersedes the colour values of D019, D020 and D021 (their exploration is kept
  above as history).
- **Context:** After three rounds Christina chose ("khalas") the very first pen blue screen (colour study round 1,
  option 3), changing only "limit reached" in dark mode: its salmon (#ff8a7a, hue 7) was close to Claude's coral.
- **Decision:** (contrast against the paper of the same theme; bars against their track)

  | Token | Light | Dark | Contrast light / dark |
  |---|---|---|---|
  | paper | #f3f4f1 | #17181b | |
  | ink | #1c1d21 | #e6e6e1 | 15.3 / 14.2 |
  | ink-2 (grey text) | #575a60 | #a2a4a8 | 6.3 / 7.1 |
  | rule | #c3c6c2 | #3a3c40 | |
  | track (bar background) | #dfe1dd | #2a2c30 | |
  | pen blue (accent) | #2443a8 | #9db0ff | 7.8 / 8.5; button text 7.8 / 8.5 |
  | near limit | #8a5a00 | #e0a43a | 5.4 / 8.1; bar 4.5 / 6.4 |
  | limit reached | #b0241b | #d9737b | 6.1 / 5.7; bar 5.1 / 4.5 |

  Dark "limit reached" #d9737b is a muted rose-red (hue 355), on the other side of red from coral (hue 15).
  Fine budgets are ink (D021). Budget bars are plain, not roughed up (D020).
- **Consequences:** D011's printed-look floor rechecked on these colours: large ink at 52% gives 3.4:1 light and
  4.7:1 dark (needs 3:1). Small text never fades. Amber "near limit" text in light mode cannot fade at all (D009).

## D023: Dark-mode "limit reached" is the light-mode red, brightened only as needed

- **Status:** Accepted "for now", 2026-11-15. Supersedes D022's dark "limit reached" (#d9737b, which Christina
  hated). May be revisited once seen in the real app.
- **Options considered** (all pass AA on #17181b): deep red #e0524f (4.6:1); clear red #e85c5c (5.2:1); bright red
  #ff7070 (6.6:1); no colour. A deeper red fails on dark paper (#c94f4f: 4.0:1).
- **Decision:** #e0524f (hue 1): the light-mode red (#b0241b) brightened only as much as dark paper needs. Text
  4.6:1, bar 3.7:1 against the track.
- **Consequences:** It is the deepest red that passes, so it cannot get darker without failing AA; its margin is
  small (4.6 vs 4.5), so the dark paper must not get lighter without rechecking it.

## D024: The first six icons

- **Status:** Accepted, 2026-11-15
- **Context:** D008 left open which 5-6 icons come first.
- **Options considered:** the five proposed tabs plus Notifications, Settings, or Back/Close.
- **Decision:** Home, Receipts, Scan, Budgets, Assistant, Back. Back comes before Notifications because every screen
  opened from a list needs it, while notifications only matter once budget alerts exist. Next in line:
  Notifications, Close, Settings, Add, Camera flash, Gallery.
- **Consequences:** Icons 1-5 assume the proposed tab bar (Home · Receipts · Scan · Budgets · Assistant), which is
  still marked proposed.

## D025: Icons are Phosphor-like line icons with the medium printed look

- **Status:** Accepted, 2026-11-15; printed-look values superseded by D026. Changes D008 on who draws the first set: Christina asked for these to be drawn
  for her in Figma; no icon library is used or copied.
- **Context:** Christina asked for the six icons "similar to Phosphor icons" and roughed up like option D of the
  font specimen ("D · B, printed": the medium thermal-print look).
- **Decision:**
  - **Drawing:** Phosphor's grammar (Regular weight), drawn as our own shapes: 24 px frame on a 256-unit grid,
    16-unit stroke (1.5 px at 24 px, the same as DejaVu Sans Mono Book's stem at 15 px), round caps and joins.
    Metaphors: house with door; receipt slip with a torn bottom edge and an item-left / price-right line; four
    viewfinder corners with a scan line; a gauge with its needle near the limit; a speech bubble with two lines
    (no sparkles, no robot); an arrow.
  - **Printed look:** the specimen's medium filter rebuilt as vector geometry, so it exports as plain SVG:
    ragged edges (edge displaced along its normal by noise, scale 1.8 px, grain frequency 0.9 per px) and patchy
    fading (soft horizontal bands, frequency 0.012 x 0.18 per px, ink alpha = 2.4n - 0.35) as a vertical gradient
    of ink. Each icon samples a different spot on the "paper"; spots were picked where the faintest band stays
    between 40% and 60% ink, so no part of an icon disappears.
  - **In Figma:** page "Icons", one component set per icon with variants Look=Clean (editable stroke) and
    Look=Printed (roughed outline), plus a 96 px preview row.
- **Consequences:**
  - The medium look has no fade floor. Icons that carry meaning need 3:1 against paper (WCAG 1.4.11); ink at
    42% on light paper is about 2.6:1, so the faintest bands fail. To decide: a fade floor for icons (as F/G do
    for text) or accept it.
  - Colour is plain ink #1c1d21 for now; dark mode and binding to colour variables come with the Figma
    foundations.
  - Alignment with text, gap, and sizes other than 24 px are still open.

## D026: A lighter printed look for icons

- **Status:** Accepted, 2026-11-15. Supersedes D025's printed-look values (the drawings stay).
- **Context:** On seeing D025's icons Christina found them "not good": too squiggly and too noisy. She asked to
  keep the fade-away feel but tone it down.
- **Decision:**
  - **Edges:** a slight ink wobble instead of ragged squiggles: edge displaced along its normal by smoother noise
    (scale 0.55 px instead of 1.8, grain frequency 0.45 per px instead of 0.9), outline lightly simplified.
  - **Fade:** same soft horizontal bands, toned down so ink never drops below 68% (in these six the faintest band
    is 81-85%).
- **Consequences:** Ink at 68% on light paper is about 5.5:1, so icons now pass WCAG 1.4.11 (3:1) at their
  faintest; the "icon fade floor" question from D025 is settled. Figma's Printed variants were updated in place
  (same components).

## D027: Icons line up with text by size: icon box = font size, centred on the line

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it.
- **Context:** Her reference is Revolut, where the icon matches the height of the first character beside it.
- **Options considered:** drawn glyph = cap height on the baseline; icon box = line height; glyph = font ascent.
- **Decision:**
  - The icon's 24 px box is scaled to the **font size** of the text beside it (15 px beside receipt lines, 22 px
    beside a screen title) and **centred on the line** (`alignItems: 'center'`). Our drawings fill 75% of their
    box, and DejaVu's capitals are 72.9% of the font size, so the drawn icon is as tall as a capital letter: the
    Revolut rule, with no per-size maths. Measured error: under 0.5 px at every size in the type scale.
  - **Gap:** one Mono character, 0.6 em (9 px at 15 px), so the icon sits on the receipt's character grid and grows
    with the iPhone's text size.
  - **Icons on their own** (tab bar, Back, Close, the bell) are 24 px, with a 44 x 44 pt touch area (Apple's
    minimum).
  - **Variant:** the app uses the Printed variant everywhere; Clean is the editable master in Figma.
- **Consequences:** Icon size is never a separate token: it follows the text style it sits with.

## D028: Screen titles have no extra letter spacing

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it. Settles D015's open point.
- **Options considered:** +8% like the section labels; none.
- **Decision:** 0. Section labels get +8% because 12 px capitals need air to stay readable; at 22 px Bold, Mono's
  fixed character width already spaces capitals evenly, and more spacing makes HOME read as H O M E.

## D029: The wordmark is FATOURATI in capitals, in two printed strengths

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it. Builds on D010.
- **Decision:**
  - **Capitals**, set in DejaVu Sans Mono Bold: the app's name is printed like the shop name at the top of a
    receipt (D012). VoiceOver still reads "Fatourati" (the image's label).
  - **Large** (48 px, launch screen and onboarding): edges displaced up to about 1 px with smooth noise, fade
    floor 45% (logotypes are exempt from contrast, D010).
  - **Small** (20 px, the Home header): lighter, edges 0.35 px, fade floor 75%, so it reads cleanly at header size.
  - Files: `frontend/assets/wordmark/fatourati-large.svg` and `-small.svg`, coloured by `currentColor`.
- **Consequences:** Each letter is its own shape with its own fade, so the fade varies across the word as well as
  down it.

## D030: The next six icons

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it. Extends D024.
- **Decision:** Notifications (bell), Close (X), Settings (gear), Add (plus), Flash (lightning bolt, for the scan
  screen), Gallery (picture frame, to pick a receipt photo). Same grid, stroke and printed look (D025, D026).
  All twelve are in `frontend/assets/icons/` (`name.svg` clean, `name-printed.svg` printed).

## D031: Spacing: a 4 px scale and 20 px screen margins

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it.
- **Decision:**
  - **Scale:** 4, 8, 12, 16, 24, 32, 48 px. Nothing in between.
  - **Screen side margins:** 20 px. On a 393 pt iPhone that leaves 353 px, which holds 39 Mono characters at 15 px:
    the width of a real 80 mm receipt line.
  - **Inside a section:** 8 px between a label and its content, 16 px between rows. **Between sections:** 24 px
    above and below a rule.
- **Consequences:** Settles "Layout" in DESIGN.md for phones; tablets are out of scope.

## D032: Shapes: square corners, dashed rules, no shadows

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it.
- **Decision:**
  - **Corners:** 0 everywhere. Receipt paper is cut square, and it keeps the app away from the
    rounded-card look of generated apps.
  - **Rules:** sections and receipt rows are separated by a **dashed** rule (1 px, 4 on / 3 off, colour `rule`), like
    the tear lines on a receipt. The tab bar's top edge is a **solid** 1 px rule, because it is the app's edge, not
    part of a receipt.
  - **Elevation:** none. No shadows, no cards; everything sits flat on the paper and is grouped by rules and space.
  - **Budget bars:** 4 px tall, square ends, on `track`.

## D033: The tab bar

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it. Confirms the proposed tabs: Home · Receipts · Scan · Budgets · Assistant.
- **Decision:**
  - Five equal tabs, 64 px tall plus the home-indicator area, on paper with a solid top rule.
  - Each tab: Printed icon (24 px) over its label in the section-label style (12 px Mono capitals, +8%).
  - **Selected:** icon and label in `ink`, with a 2 px ink bar at the top of the tab; the others in `ink-2`. The bar
    means the state is not shown by colour alone (WCAG 1.4.1).
  - **Scan** is the main action: a 44 x 44 px pen-blue square with the icon in paper colour (D018: pen blue is the
    main button), its label below in `ink`.

## D034: Money on screen

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it. Adopts the earlier proposal.
- **Decision:** dollars as `$6.60`, pounds as `450,000 LBP` (comma thousands, no decimals). A total that mixes
  both is shown in dollars and always says how: "$412.60 + 3,150,000 LBP at 89,500 LBP per $".

## D035: The Home screen

- **Status:** Accepted, 2026-11-19. Decided by Claude at Christina's request ("u decide all of these"); open to change once she sees it.
- **Decision:** top to bottom, inside the 20 px margins:
  1. **Header:** the small wordmark on the left, the bell on the right.
  2. **THIS MONTH · NOVEMBER** (section label), the month total in total-hero, the combined-currency line (caption).
  3. Dashed rule.
  4. **BUDGETS** with "See all" (pen blue, a link): the three budgets closest to their limit. Each row: name and
     "$spent / $limit" (receipt-line), a 4 px bar, and the state in words when it needs attention ("NEAR LIMIT ·
     89%", "LIMIT REACHED · 105%") in its colour.
  5. Dashed rule.
  6. **RECENT**: the last three receipts. Each row: shop name (shop-name style) and total, then date, time and item
     count (meta), with dashed rules between rows.
  7. Tab bar, Home selected.
- **Consequences:** The first screen to build in the app; Figma copy follows when Figma calls are available again.

## D036: Home greets the user by first name

- **Status:** Accepted, 2026-11-19. Asked for by Christina ("add a Hello, Name"); style decided by Claude at her
  request.
- **Decision:** "Hello, Christina" (the account's first name) is Home's screen title: screen-title style
  (DejaVu Sans Mono Bold, 22 / 26, capitals as a style, D015, D028), under the header with the wordmark. Home has no
  other title. To make room, Recent shows the two newest receipts in the first view; the rest scroll. This changes
  D035's "last three".

## D037: Home before any receipts, and the main button

- **Status:** Accepted, 2026-11-19. Asked for by Christina (versions "without entered data"); design decided by
  Claude at her request.
- **Decision:**
  - **Empty Home:** same layout as D035. The total reads $0.00 with "No receipts yet this month". Below it, one
    sentence on what scanning does ("Take a photo of a receipt. Fatourati reads the shop, the items and the total,
    in dollars or pounds.") and the main button, **Scan a receipt**. Budgets: a grey sentence ("Set a monthly
    limit for groceries, fuel or eating out, and see how close you are.") and a **Set a budget** link. Recent: "Receipts you scan show up here, newest first."
    No illustrations.
  - **Main button:** full width inside the margins, 48 px tall, square corners, `primary` fill, label in paper
    colour, total-line style (Mono Bold 16, capitals), with the 16 px Scan icon one character before the text
    (D027). Contrast 7.8 : 1 light, 8.5 : 1 dark. One main button per screen.
  - Helper sentences are DejaVu Sans (they are sentences, D006), grey (`ink-2`) where they only explain.

## D038: The brand colour is highlighter yellow, on the wordmark

- **Status:** Accepted, 2026-11-23. Chosen by Christina from the Home canvas ("Yellow A, highlighted wordmark").
- **Context:** Christina found the screens dull and wanted a pop of colour tied to Fatourati itself, not to the data.
- **Options considered:** highlighter yellow on the total; an end-of-roll pink stripe; yellow on the wordmark
  (A); a yellow top band (B).
- **Decision:** Highlighter yellow, `highlight` #f5e54a (light) / `highlight-dark` #e8d84a (dark), drawn as a
  flat swipe with slightly uneven edges **behind the wordmark**, and behind the selected tab's label (it replaces
  D033's 2 px ink bar). Text on yellow is always ink #1c1d21, in both themes (13.0 : 1 and 11.5 : 1). Nowhere else.
- **Consequences:** Pen blue keeps meaning "you can tap this" (D018); yellow means "Fatourati". The app icon
  should use the same yellow (not designed yet).

## D039: Paper by screen: yellow launch, lightly creased everywhere else

- **Status:** Accepted, 2026-11-23; the creased paper is replaced by D042 (plain white). Chosen by Christina from the canvas (launch "Yellow", sign in and Home "Lightly
  creased"). She rejected the heavily crumpled experiment for every screen.
- **Decision:**
  - **Launch screen:** a full page of yellow paper (`highlight` #f5e54a with the fine grain) and the large wordmark
    in ink, centred. Same in dark mode (no dark version).
  - **Sign in, create account, Home:** "lightly creased" paper: the light paper becomes milky **#f7f8f6** (was
    #f3f4f1), with a fine grain (`assets/paper/grain-light.png`, 256 px tile) and soft crease shading
    (`assets/paper/wrinkle-light.png`, stretched once over the screen). Dark mode keeps paper-dark **#17181b**
    with `grain-dark.png` and `wrinkle-dark.png`.
  - The textures are images, not gradients (D007 stands).
- **Consequences:** Contrast on #f7f8f6 is slightly higher than before (ink 15.8, ink-2 6.5, pen blue 8.1,
  near-limit 5.6, limit-reached 6.3). Dark paper stays #17181b because the dark "limit reached" red (#e0524f) has no
  margin (4.6 : 1; on a lighter #1a1b1e it would be 4.5). The crease shadows are faint (at most 7% ink) and only
  darken the paper, so light-mode contrast does not drop.

## D040: Sign in and create account

- **Status:** Accepted, 2026-11-23 (design from the canvas; Apple and password reset left out by Christina).
- **Decision:**
  - Layout from the mockups: large highlighted wordmark, the screen title (SIGN IN / CREATE ACCOUNT), one grey
    sentence, the fields, the main button (D037), a link to the other screen at the bottom.
  - **Fields are fill-in lines**, like "Signature: ____" on a receipt: a section-label caption above, a single 1 px
    ink line under the value, no box, square everything. Value text in receipt-line style. Password has a
    pen-blue SHOW / HIDE.
  - **Not built yet:** "Continue with Apple" and "Forgot password?" (the backend supports neither). They come back
    as their own features.
- **Consequences:** The "or" divider and the outlined secondary button wait for Apple sign-in.

## D041: Accounts have a first name and a gender

- **Status:** Accepted, 2026-11-23. Asked for by Christina.
- **Decision:**
  - Sign-up asks for **first name** (required; Home greets with it, D036) and **gender**: Female, Male, or Prefer
    not to say (required choice; "Prefer not to say" is a real answer).
  - Gender control: three equal square options in one row under a GENDER caption, 48 px tall, 1 px `rule` border,
    labels in section-label style (capitals, may wrap to two lines); the chosen one has a 2 px pen-blue border and
    pen-blue label (it is something the user changes, D018).
  - Backend: `users` gain `first_name` and `gender` (`female` | `male` | `prefer_not_to_say`); register takes them,
    `/auth/me` and login return them.
- **Consequences:** Existing accounts have no name or gender until they set them (no profile screen yet). The
  assistant could use gender to address the user correctly in Arabizi; that is a separate change.

---

## D042: Plain white paper, no crease

- **Status:** Accepted, 2026-11-25; replaced by D044 (the invoice design). Asked for by Christina after trying the app on her iPhone ("remove the creasing
  and make it just white, all pages"). Replaces the lightly creased paper of D039.
- **Decision:**
  - Sign in, create account, Home and every other app screen sit on flat paper: **#ffffff** in light mode, the
    same **#17181b** in dark mode. No grain, no crease shading. `wrinkle-light.png`, `wrinkle-dark.png` and
    `grain-dark.png` are deleted; `grain-light.png` stays for the yellow launch.
  - The launch screen stays yellow with its grain (D039); it never had a crease.
- **Consequences:** Contrast on white is a little higher than on #f7f8f6 (ink 16.8, ink-2 6.9, pen blue 8.6,
  near-limit 5.9, limit-reached 6.7). The main button's label uses the `paper` token, so it is now white on pen
  blue. Dark mode keeps its colour, only its textures go.

## D043: Settings: appearance and sign out, from a gear on Home

- **Status:** Accepted, 2026-11-25; replaced by D044 (light only, settings from the wordmark). Christina chose where settings open from and what the appearance setting
  offers, after finding no way to leave dark mode or to sign out on her iPhone. The rest are my calls, on her
  standing instruction to decide small details myself.
- **Options considered:** the gear in Home's header (chosen), a SETTINGS link at the bottom of Home, or tapping the
  wordmark. For appearance: Phone / Light / Dark (chosen), Light / Dark only, or dropping dark mode.
- **Decision:**
  - **Home's header:** the gear (D030) to the left of the bell. Their 44 pt touch areas sit side by side, so the
    two 24 px icons are 20 px apart. The gear opens Settings, pushed over the tabs (iOS slide), with Back.
  - **Settings screen**, laid out like Home on plain paper (D042): a 44 px header with Back (left, 12 px padding),
    the SETTINGS screen title, then sections 24 px apart with a dashed rule between them:
    - **APPEARANCE:** Phone, Light, Dark, as three equal square options (the gender control of D041, now the
      shared `OptionRow`). Phone is the default and follows the iPhone (D003). The choice applies at once to the
      whole app, status bar included, and is kept on the phone (it survives signing out).
    - **ACCOUNT:** the email in `meta` style, then SIGN OUT as a pen-blue link (section-label style). Signing out
      needs no confirmation and goes straight to sign in.
  - The temporary SIGN OUT link at the bottom of Home is removed.
- **Consequences:** D003 ("follow the phone") stays the default, with an override. The bell still does nothing.

## D044: The invoice design replaces the first design

- **Status:** Accepted, 2026-11-26. Christina brought a new design (`frontend/design/`, from her design handoff)
  and asked to follow it absolutely, keeping only her five tab icons from the first design.
- **Decision:**
  - `frontend/design/` is the source of truth: `DESIGN.md` (the spec), `theme.ts` (the tokens, re-exported by
    `src/shared/theme/tokens.ts` untouched), `screens/` and `reference/` (exact values). Colours the reference
    screens use that `theme.ts` does not name are added in `tokens.ts`, each with its screen; a test checks
    each one appears in `reference/`.
  - Kept from the first design: the printed icons for Home, Receipts, Scan, Budgets and Assistant (tab bar,
    and the empty Recent box). Everything else (DejaVu, pen blue, yellow, the wordmark artwork, plain paper,
    the yellow launch, D002-D043's looks) gives way to the invoice design.
  - Christina's answers (2026-11-26):
    - This round rebuilds the screens that exist: launch, sign in, create account, Home and empty Home, the tab
      bar, settings. Receipt detail, Budgets and the two Assistant screens come next, as their own features.
    - **Light only.** The design has no dark colours, so dark mode and the Phone / Light / Dark setting of D043
      are removed; the status bar is always dark.
    - **Forgot? and Continue with Apple** are left out until the backend supports them.
    - **Create account and Settings** are built from the design's parts. Create account is the sign-in frame
      with the four fields; gender uses the Assistant's segmented switch. Settings opens from the Fatourati
      wordmark on Home (the design's header has only the bell; D045 moves it to an account button): the receipt screen's top bar, an ACCOUNT sheet
      (name, email) and an outlined Sign out.
  - My calls, on her standing instruction to decide small details:
    - **Invoice number:** one invoice a month, counted from the month of the first receipt (Nº 0001 is that
      month, and a new user's).
    - **The table** lists the three budgets closest to their limit (every budget since D048), then "Everything else" = the dollar total
      minus those categories, so the rows add up to TOTAL. A budget is red once spent passes its limit.
    - **The older months** behind the invoice are the two months before this one, shown once the user has a
      receipt from before this month. They are not tappable yet (switching months is not designed).
    - **The note** says "Set your first monthly budget" (opens Budgets) until there is a budget, then
      "Ask me — “adey sarafet 3al akel?”" (opens the Assistant; the design's "addeh sraft 3al akl" is
      wrong Arabizi, corrected by Christina on 2026-11-26, as is the Beta placeholder: "S2al bel arabizi… e.g.
      adey dafa3et?").
    - Create account's heading: "Start a fresh invoice."; field errors are 13 px `redText` under the line;
      the button shows a spinner while busy and turns `cobaltPressed` while pressed.
    - The torn teeth are part of the creased sheet (the gaps are painted in the colour behind), as the
      design's CSS mask does; slips lying on other slips keep plain teeth under them.
- **Consequences:** The fonts are Geist, Geist Mono and Noto Naskh Arabic (only the weights used are
  bundled). The crease needs `mixBlendMode`, which Expo SDK 58's New Architecture has. Loading and error looks
  are still not designed (a spinner, and a sentence with Try again).

## D045: An account button by the bell opens Settings

- **Status:** Accepted, 2026-11-26. Christina found Sign out hidden behind the wordmark (D044) and chose an
  account icon by the bell (over a gear, or a Settings link at the bottom of Home).
- **Decision:** Home's header has a person icon left of the bell, drawn in the design's line style (24 view
  box, 1.7 stroke, 20 px in a 44 px button), labelled "Account and settings" for VoiceOver. It opens
  Settings. The wordmark is no longer a button.
- **Consequences:** One icon the design does not have; it follows the bell's style exactly.

## D046: Budgets, and the budget form as a sheet

- **Status:** Accepted, 2026-11-26. Built from design/screens/06-budgets.png. Christina chose the form as a
  sheet from the bottom and a blank budget sheet for no budgets; the rest are my calls.
- **Decision:**
  - **Budgets** follows screen 06: title, ‹ month ›, the black +; the budget sheet; one creased slip per budget
    (over-budget first, then by % used); the dashed Everything else box. Next is disabled on the current month;
    earlier months can be browsed.
  - **The sheet** adds the budgets up in dollars, pound budgets at today's rate. "N days left" counts the days
    after today; on the last day "Last day"; earlier months say "Month ended" and show no pace.
  - **Pace** ("$2.13 a day") = left ÷ days left (DESIGN.md §5), "$0.00 a day" when over; on the last day, all
    that is left.
  - **Everything else** = the month's dollar spending outside every budget. Shown when above zero, and always
    while there are no budgets.
  - **No budgets:** a blank sheet, $0.00 in grey and "No budgets yet. Set a monthly limit for a category."
  - **The form** is an iOS sheet on the sign-in form's clean paper. New (from + or Set budget): NEW BUDGET and the
    month, "Set a monthly limit.", "It applies from November 2026 onwards." (the backend sets a limit from a
    month onwards), CATEGORY as the Assistant's chips (only categories without a budget; the chosen chip is ink
    with light text, like the user's chat bubble), MONTHLY LIMIT, CURRENCY (USD / LBP, the segmented switch),
    Save budget. Edit (tap a slip): EDIT BUDGET, the category as the heading, the same fields filled in, and an
    outlined Remove budget, which asks first (iOS alert) because it removes the budget for every month.
  - Limits: positive, dollars with at most two decimals, pounds whole; commas are fine.
- **Consequences:** New icons in the design's line style: the month chevrons and the + (copied from reference 06).
  Creating a category from the form is not designed yet.

## D047: The Assistant, with text answer cards for now

- **Status:** Accepted, 2026-11-26. Built from design/screens/07 and 08 on the two assistant modes merged from main
  (Standard with Claude Sonnet, Beta with the fine-tuned Qwen). Christina chose text cards for now; the rest are
  my calls.
- **Decision:**
  - The screen follows 07 / 08: title and + (new conversation), the two-line segmented switch (Assistant ·
    Claude Sonnet / Arabizi BETA · Fine-tuned Qwen), day separators ("Today · 26 Nov"), ink question bubbles
    (Arabizi questions in Geist Mono), creased answer cards with ASSISTANT or ARABIZI · BETA, and the message
    field with the cobalt send button and each mode's placeholder.
  - **Answer cards are text for now:** the answer's sentence with amounts in bold Geist Mono (Markdown **bold**
    kept as bold), or its table when the backend sends one. The design's budget bar and Beta's category header
    with a big amount wait until the backend sends what an answer is about.
  - **Beta:** the dashed BETA note; Show / Hide query on answers with SQL; "Was this right?" ✓ / ✗ on the
    latest data answer, stored as the answer's rating (training data); a chosen button turns ink with a white
    mark; choosing it again clears it.
  - Each mode opens its newest conversation and keeps it while switching; + starts an empty one (created by its
    first question).
  - **Asking:** the question shows at once, then a card with a spinner ("Thinking…", Beta "Reading your
    receipts…"). If the backend refuses (today's Standard limit, still answering), its sentence shows above the
    field and the question goes back into the field. Answers may take up to 90 s.
  - **Suggestions** in Standard only, under the conversation: "Where can I cut back?" and "Compare to <last
    month>", asked with one tap.
  - When a mode cannot answer (not set up, today's limit, the monthly cap), a sentence says so and Send is off.
- **Consequences:** New line icons from the reference: send, the query chevron, ✓, ✗, and + for a new
  conversation. Conversation history (older conversations) is not designed yet.

## D048: Home's invoice lists every budget

- **Status:** Accepted, 2026-11-26. Christina's fourth budget (Transport, set through the assistant) was missing
  from Home: the invoice listed only the three budgets closest to their limit, and unused budgets tied at 0% were
  cut by name.
- **Decision:** The invoice table lists every budget of the month, closest to its limit first (then by name),
  then Everything else, which is now only spending with no budget. More budgets make a longer invoice.
- **Consequences:** Replaces D044's "three closest" rule. Everything else no longer includes budgeted categories.

## D049: Pound budgets in the invoice table: short amounts with LBP under the limit

- **Status:** Accepted, 2026-11-26. Christina's Shopping budget of 150,000,000 LBP barely fit the invoice's fixed
  LIMIT (60 px) and SPENT (84 px) columns. She chose short amounts and asked for the currency to show.
- **Decision:** In Home's invoice table, pound amounts from a million up are short: "150M", "1.25M" (two decimals
  at most), "2.5B" from a billion; below a million they stay exact ("450,000"). The same goes for "148.75M left"
  and "+600,000 over". Every pound budget shows a small LBP cap label under its limit; dollar budgets show none
  (the invoice is in dollars). Budgets and the budget form keep the full numbers.
- **Consequences:** Only the invoice table shortens amounts; totals and receipts are exact everywhere.

## D050: The Receipts tab and a receipt's page

- **Status:** Accepted, 2026-11-26. Built from design/screens/13-receipts.png and 05-receipt-detail.png (the new
  handoff in frontend/design). Christina asked for simple versions of the parts with no screen yet (search, the
  month picker, Split items); the details are my calls.
- **Decision:**
  - **Receipts tab** (screen 13): the month and its total ("Total $447.80"; "N receipts shown" while narrowed),
    the filter chips (All, the month's categories by number of receipts, Other for receipts with no category),
    and one long creased roll grouped "This week" (since Monday) and "Earlier in November" ("In October" for a
    month with nothing this week), ending with the month before and "Older receipts →". Only confirmed
    receipts. Rows are the same as Home's (now one shared ReceiptRow), and open the receipt.
  - **Search** (simple): the search button opens a field over the list, matching shops and categories.
  - **Month** (simple): the calendar button opens the Budgets-style ‹ November 2026 › switcher.
  - **A receipt's page** (screen 05): Back, RECEIPT, share (the receipt as text); the creased receipt with its
    category and "18 Nov · 18:42" (the printed date, the time it was added), the shop and total, ITEM / QTY /
    AMOUNT (QTY is the size when known, "1 kg", else the count), TOTAL · N ITEMS (the payment method is not
    read, so "card" is left out), and "Groceries after this" when the category has a budget that month.
  - **Change category** (a sheet): category chips; every item follows the new category.
  - **Split items** (simple, a sheet): each item with a row of category chips; an item in the receipt's own
    category is saved as following it. On the page, an item in another category shows that category in small
    cobalt capitals under its name.
  - Both save through the backend's confirm, which corrects a confirmed receipt; every value is kept.
- **Consequences:** The list opens each receipt of the month to count its items (the list endpoint leaves items
  out). Dashed lines are now drawn at 100% width, never from a measured width.

## Open (not decided)

From Christina, to discuss later:
- **Printed look for the rest of the app** (the wordmark is settled by D010). Christina asked to see the type itself roughed up like receipt print (specimen option D and three
  strengths: light = ragged edges, medium = + patchy fading, heavy = + dropouts). To decide: which strength, on
  what (wordmark only, big numbers, all Mono text), and how it is built in React Native, which has no filters
  (a roughed copy of the font renamed e.g. "Fatourati Print", Figma artwork, or a grain texture over text).

- **Arabic on the iPhone:** confirm DejaVu's Arabic looks acceptable on the phone (D006).

Proposed earlier, still to discuss:
- Interface language: English screens, Arabizi in the assistant only (proposed).
