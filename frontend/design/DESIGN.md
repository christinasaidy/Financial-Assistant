# Fatourati — Design spec (invoice direction)

This folder is the source of truth for the app's look. Build the React Native screens to match `screens/*.png`. Use `reference/*.html` for exact values (each file is the real markup of that screen, open it in a browser to inspect). Tokens are in `theme.ts`.

**Fatourati** (فاتورتي, "my invoice") turns crumpled receipts into a clean monthly invoice. Every screen borrows from a Lebanese shop's invoice book: a numbered invoice, ruled columns, a double rule above the total, a torn bottom edge, a perforated line. The paper is lightly **crumpled** (a crease texture over the content). The app is calm and mostly monochrome, with one cobalt accent.

---

## 1. Decisions already made (do not undo)

| Decision | Why |
|---|---|
| **Light grey background `#E3E4E6` on every screen** (Launch is the one exception, see §6) | User chose it over white and beige |
| Paper is **`#EFEEEB`**, crease texture at **~0.6 opacity, overlay**, drawn **on top of** text | The crease must run through the ink, like a real creased sheet |
| **No yellow, no beige, no handwriting fonts, no red margin / blue ruled lines** | Tried and rejected as "ugly / too much" |
| **No rubber stamp** (the round blue "4 days left" stamp) | Rejected |
| Torn zigzag edges: **only at the bottom of invoice-like sheets and slips**. Never between sections of a screen | "We don't need it everywhere" |
| Creasing must stay **subtle** on main screens. Heavier crease is used only on the Sign-in receipt slips and the Launch sheet | "Overdone creasing" was rejected twice |
| **No animation** on Launch. It is a static screen | Rejected the "flattening" animation |
| Arabic wordmark is **فاتورتي** (with ي after ت) | Spelling correction from the user |
| One accent: **cobalt `#2340C8`**. Red **`#B3261E`** only for over-budget | Keeps it calm |

---

## 2. Tokens

### Colour
| Token | Hex | Use |
|---|---|---|
| `bg` | `#E3E4E6` | Screen background |
| `paper` | `#EFEEEB` | Invoice sheets, slips, assistant answer cards |
| `paperClean` | `#FCFBF8` | The Sign-in form sheet (the "flattened" sheet), input field background |
| `tabBar` | `#F6F6F5` | Bottom tab bar background |
| `ink` | `#1A1A1A` | Primary text, rules, active tab, user chat bubbles |
| `inkSoft` | `#46453F` | Secondary text **on paper** |
| `inkMuted` | `#55544F` | Secondary text **on bg**, inactive tabs |
| `capLabel` | `#4A4944` | Small uppercase mono labels |
| `cobalt` | `#2340C8` | Scan button, Sign-in button, links, invoice number, "Note" label, send button |
| `cobaltPressed` | `#182E96` | Pressed/hover |
| `red` | `#B3261E` | Over-budget amount and bar; text variant `#A3231B` |
| `ruleSoft` | `rgba(0,0,0,0.13)` | Row dividers and column rules **on paper** |
| `barTrack` | `rgba(0,0,0,0.12)` | Progress bar track |
| `dashed` | `rgba(0,0,0,0.28)` | Dashed dividers on paper |
| `dashedBg` | `#B3B5BA` | Dashed outlines on bg (empty states) |
| `perfDot` | `#C9CBCF` | Perforation dots above the tab bar |
| `sheetBehind1` | `#D2D4D8` | "September" sheet peeking behind the home invoice |
| `sheetBehind2` | `#F4F4F3` / `#F5F5F4` | "October" sheet peeking behind the home invoice |
| `launchPaper` | `#C9C9C6` | The Launch screen sheet only |

### Type
- **Geist** (400 / 500 / 600) for UI text and headings.
- **Geist Mono** (400 / 500 / 600) for **all numbers** (tabular), dates, and small labels.
- **Noto Naskh Arabic** (600 / 700) for فاتورتي.

| Style | Font | Size / weight | Notes |
|---|---|---|---|
| `cap` label | Geist Mono 500 | 10.5, letter-spacing 0.08em, UPPERCASE | e.g. "INVOICE Nº 0447", "BUDGET", "RECENT RECEIPTS" |
| Big total | Geist Mono 500 | 50–52, letter-spacing −0.04em | `$447.80` |
| Screen title | Geist 600 | 20 | "Budgets", "Assistant" |
| Wordmark | Geist 600 | 18 + فاتورتي Naskh 600 15 in `inkMuted` | Header on home |
| Row label | Geist 500 | 15 | Budget/receipt names |
| Row number | Geist Mono 400–500 | 14–15 | Amounts |
| Sub-number | Geist Mono 400 | 11–11.5 | "8.50 left", "≈ $5.03" |
| Body | Geist 400 | 14–15, line-height 1.4–1.45 | |

### Spacing / shape
- Screen side padding: **14px** for sheets, **20px** for text rows on the background.
- Touch targets **≥ 44px**.
- Sheets have **no border radius** (they are paper). Buttons radius **12**, Scan button **16**, chips **20**, input **14**.
- Sheet shadow: `0 10px 14px rgba(40,35,25,0.14)` + `0 1px 1px rgba(40,35,25,0.10)`.

---

## 3. The paper + crease recipe (most important)

`assets/crease.jpg` is a grayscale crumpled-paper texture **centred on 50% grey**. With blend mode **overlay**, mid-grey is invisible, so only the folds show.

Rules:
1. Draw the texture **after** (on top of) the sheet's content, so the folds run through the ink.
2. `mixBlendMode: 'overlay'`, opacity **0.6** on main screens (home, receipt, budgets, assistant cards). Use **0.69** on Sign-in slips and the Launch sheet.
3. Tile it at about **300px wide** (`resizeMode="repeat"`). Bigger tiles look blurry, smaller tiles look busy.
4. Overlay needs paper that is **not near-white**. That is why paper is `#EFEEEB`, not white. On `#FFFFFF` the creases disappear.
5. `pointerEvents="none"` so it never blocks taps.
6. Wrap each sheet so the blend only affects that sheet (`isolation: 'isolate'` on the sheet's container in RN 0.77+).

`mixBlendMode` needs the **New Architecture** (RN 0.77+), and on Android, **Android 10+**. Fallback for older setups: render the same stack in `@shopify/react-native-skia` with `blendMode="overlay"`, or skip the crease (the design still works flat).

```tsx
// CreasedPaper.tsx
import { View, Image, StyleSheet, ViewProps } from 'react-native';
import { colors } from './theme';

export function CreasedPaper({ children, style, crease = 0.6, ...rest }: ViewProps & { crease?: number }) {
  return (
    <View style={[{ backgroundColor: colors.paper, isolation: 'isolate', overflow: 'hidden' }, style]} {...rest}>
      {children}
      <Image
        source={require('./assets/crease.jpg')}
        resizeMode="repeat"
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { mixBlendMode: 'overlay', opacity: crease }]}
      />
    </View>
  );
}
```

### Torn bottom edge
A zigzag along the bottom of invoice sheets and slips: teeth **12px wide, 6px tall** (slips on Sign-in: 10 × 5; Launch: 14 × 7). In RN, draw it with `react-native-svg` as a `Path` in the paper colour under the sheet, or mask the sheet. Keep the drop shadow on the outer wrapper so it follows the zigzag.

```tsx
// TornEdge.tsx: place directly under a sheet, same width
import Svg, { Path } from 'react-native-svg';
export function TornEdge({ width, color, tooth = 12, height = 6 }: { width: number; color: string; tooth?: number; height?: number }) {
  let d = `M0 0 H${width} V0`;
  for (let x = width; x > 0; x -= tooth) d += ` L${x - tooth / 2} ${height} L${Math.max(x - tooth, 0)} 0`;
  return <Svg width={width} height={height}><Path d={d + ' Z'} fill={color} /></Svg>;
}
```
If the crease overlay must cover the teeth too, put the TornEdge inside `CreasedPaper` (before the crease Image) and extend the paper.

### Perforation line
A row of dots above the tab bar: dot radius 2.5px, every 12px, colour `perfDot`.

---

## 4. Components

- **Header (home, empty home):** "Fatourati" Geist 600 18 + فاتورتي, bell icon button (44×44) on the right.
- **Invoice sheet (home):** `CreasedPaper` + TornEdge, padding 16/18/22.
  - Top row: `cap` "INVOICE Nº 0447" in cobalt (left), `cap` "NOV 2026" (right).
  - "Billed to Christina" 14 `inkSoft`.
  - Big total `$447.80` + line `$412.60 + 3,150,000 LBP · 89,500` (mono 12 `inkSoft`).
  - **Ruled table**: 1px ink rule on top, header row of `cap` labels (BUDGET / LIMIT / SPENT), rows ~46px with `ruleSoft` dividers, column widths `1fr / 60 / 84`, vertical `ruleSoft` rules between columns, numbers right-aligned.
  - Under each budget name: 3px progress bar (track `barTrack`, fill `ink`; fill `red` when over).
  - Under the spent value: `8.50 left` (mono 11 `inkSoft`), or `+3.00 over` in red.
  - "Everything else" row has no bar and limit "—".
  - **Total row**: 3px **double** ink rule on top, `cap` "TOTAL" left, mono 17/600 right.
  - **Note row**: dashed divider, `cap` "NOTE" in cobalt, text, cobalt arrow. Opens the assistant.
- **Older months behind the invoice:** two sheets peeking ~30px above the invoice, slightly rotated (−1.6° and +1°), labelled `SEP` / `OCT` (cap, right). They are the month switcher.
- **Recent receipts list (on bg):** `cap` heading with a 1px ink rule below. Rows ≥58px: date block (day in mono 18 over `NOV` cap), name (Geist 500 15) over "Groceries · 9 items" (13 `inkMuted`), amount right (mono 15). LBP rows show `≈ $5.03` under the amount. Dashed dividers between rows.
- **Tab bar:** bg `tabBar`, perforation line on top, 5 slots: Home, Receipts, **Scan** (cobalt 56×56 radius 16, white scan icon), Budgets, Assistant. Active tab = ink + weight 600; inactive = `inkMuted`. Icons: 22px, 1.7 stroke, line style.
- **Buttons:** primary = cobalt fill, white Geist 600 15–16, height 52, radius 12. Secondary = 1px ink outline, same size.
- **Chat (assistant):** user message = ink bubble, radius `14 14 4 14`, text `#F6F6F5` 15. Assistant answer = small `CreasedPaper` + TornEdge card, max-width ~88%, `cap` "ASSISTANT" in cobalt at top.
- **Segmented switch (assistant):** track `rgba(0,0,0,0.06)` radius 12, active segment `paperClean` with a 1px shadow. Each segment has two lines: name + mono 10.5 model label.

---

## 5. Data formatting rules
- Base currency **USD**. LBP amounts keep LBP but show `≈ $x.xx` underneath, using the month's rate (sample: **89,500 LBP/USD**).
- All numbers in **Geist Mono**, tabular, right-aligned in tables.
- Totals: two decimals with `$`. Table cells: no `$`, two decimals (limits may be whole numbers).
- Per-day pace on Budgets = `left ÷ days remaining`. Over-budget shows `$0.00 a day`.
- Sample data used everywhere (keep consistent while building): Transport 63.00 / 60 (over by 3.00), Eating out 71.50 / 80, Groceries 186.40 / 250, Everything else 126.90 (no budget). Total 447.80. Recent: Spinneys Achrafieh $38.40 (18 Nov, 9 items, Groceries), Zaatar w Zeit 450,000 LBP (17 Nov, 2 items, Eating out).

---

## 6. Screens (see `screens/` and `reference/`)

| # | Screen | Key points |
|---|---|---|
| 01 | **Launch** | Static. White background, one full-screen sheet `#C9C9C6` with crease 0.69 and a torn bottom edge (14×7). Top: `INVOICE Nº 0001` (cobalt) / `USD · LBP`, a 1px rule. Bottom: huge **فاتورتي** (Naskh 700, ~108px, right-aligned), double rule, "Fatourati" 30/600 left, `TOTAL · $0.00` right, tagline "Every crumpled receipt, flattened out and accounted for." (mono 13). Open question: the user may move this to the grey bg too; if so, lighten the sheet so it still stands out. |
| 02 | **Sign in** | bg `#E3E4E6`. Top ~280px: four small **crumpled receipt slips** (paper `#EFEEEB`, crease 0.69, torn edge 10×5) scattered at angles (−9°, 7°, −4°, 12°) showing sample receipts. Below: the clean **form sheet** (`paperClean`, almost no crease, **straight top edge, no zigzag**), shadow above it. Heading "Let's flatten these out." 25/600. Email field, Password field with "Forgot?" next to the label and an eye toggle inside the field, cobalt **Sign in**, outlined **Continue with Apple**, "New to Fatourati? Create an account" at the bottom. |
| 03 | **Home** | Header, invoice sheet with Oct/Sep sheets behind, recent receipts, tab bar. See §4. |
| 04 | **Home, empty** | Same layout. Invoice Nº 0001, `$0.00` in muted grey `#86857F`, "A blank invoice. It fills itself in as you scan." Three blank table rows with **dashed placeholder lines** in each column. Note row: "Set your first monthly budget". No sheets behind. Recent receipts = dashed box "No receipts yet / Tap Scan below to add your first one." Scan button gets a faint cobalt ring (`0 0 0 5px rgba(35,64,200,0.14)`). |
| 05 | **Receipt detail** | Back / `RECEIPT` / share in the top bar. Creased receipt sheet: `RECEIPT · GROCERIES` (cobalt) + date/time, store name 24/600 + area, amount mono 34 on the right. Ruled table ITEM / QTY / AMOUNT (rows ~35px), double rule, `TOTAL · 9 ITEMS · CARD` + total. Dashed divider then "Groceries after this 186.40 / 250" + bar + "$63.60 left this month". Bottom: outlined **Change category**, cobalt **Split items**. |
| 06 | **Budgets** | Title + month switcher (‹ Nov 2026 ›, next disabled on the current month) + black "+" (new budget). **Budget sheet** summary: `$320.90 of $390 budgeted`, bar 82%, "$69.10 left across 3 budgets", "4 days left". Then one creased slip per budget: name, spent / limit, 4px bar, "left" + "$x a day". Transport in red ("Over by $3.00"). Last: dashed **Everything else · $126.90 — Not in any budget yet — Set budget**. |
| 07 | **Assistant (Claude Sonnet)** | Title + "+" (new chat). Segmented switch: **Assistant / Claude Sonnet** (active) and **Arabizi [BETA] / Fine-tuned Qwen**. Chat with ink user bubbles and creased answer cards that include a mini bar for the category asked about. Suggestion chips. Input "Ask about your spending…" with cobalt send button. |
| 08 | **Assistant (Arabizi Beta, Qwen)** | Same frame, Arabizi segment active. Dashed BETA note: "Ask in Lebanese Arabizi. Answers come straight from your receipts." Arabizi questions in mono ("addeh sraft 3al akl hal shahr?"). Answers are mini invoices: `ARABIZI · BETA` + category/month, big amount, sub-line. **Show / Hide query** toggles a dark code block with the generated SQL. The latest answer has **"Was this right?" ✓ / ✗** (store this feedback, it is training data for the fine-tuned model). Input placeholder "Es2al bel arabizi… e.g. addeh dafa3et?". |
| 09 | **Scan · Camera** | Dark viewfinder (`#161718`, frame `#232426`). Close (back to Home), title "Scan receipt", flash toggle. White corner brackets (28px, 3px) around the detected receipt. Pill above: cobalt dot + "Receipt found · hold steady". Hint in mono 11.5 `#A9AAAD`: "Fit the whole receipt inside the corners". Controls: **Upload** (from gallery), white **shutter** (76px ring, 60px fill), **Long receipt** mode. |
| 10 | **Scan · Reading** | bg grey. `READING RECEIPT` cap title, cancel (X). The captured receipt as a creased slip with a **cobalt scan line** (2px + soft glow) and a faint cobalt tint over the part already read. Below: a checklist with a 1px ink rule on top and dashed dividers: ✓ Store · Spinneys Achrafieh, ✓ Date · 18 Nov 2026 · 18:42, ✓ Items · 9 found, then a spinner row "Checking the total…". Footer cap: "Usually takes a few seconds". Fill the rows in as the OCR returns each field. |
| 11 | **Scan · Review** | Title "Check the details", back, **Retake** (cobalt). Creased sheet `NEW RECEIPT · FOR Nº 0447` / `TAP TO EDIT`. Editable fields with cap labels and a bottom rule: Store, Date (mono), Currency segmented **USD / LBP**. Ruled items table (first 4 rows + "+ 5 more items · 13.75" expander). **Low-confidence values** get a cobalt tint row, a `CHECK THIS` cap under the name and a dashed cobalt underline on the value. Double rule + total, then "✓ Items add up to the total" (show a warning instead when they don't). **Category chips** (selected = ink fill), with "Suggested from the store". Full-width cobalt **Save to November invoice**. |
| 12 | **Scan · Filed** | Cobalt check circle, "Filed under Groceries" 26/600, "Spinneys Achrafieh, $38.40, added to this month's invoice." Mini invoice showing the change: Groceries row highlighted with a cobalt tint, old value struck through (`148.00`) → new `186.40 / 250`, bar with the new part in cobalt, "+38.40 from this receipt" and "63.60 left"; Total `409.40` struck → `$447.80`. "View receipt" link. Buttons: outlined **Scan another**, cobalt **Done** (to Home). |
| 13 | **Receipts tab** | Title "Receipts" + search + month (calendar) icons. Cap `NOVEMBER 2026` with `Total $447.80` (mono). Horizontally scrolling **filter chips**: All / Groceries / Eating out / Transport / Other (selected = ink fill); when filtered, the right-hand text becomes "N receipts shown". The list is **one long creased paper roll** (no torn edge, it continues as you scroll) with cap group headings ("THIS WEEK", "EARLIER IN NOVEMBER") and dashed dividers. Rows: same as Home's recent receipts (day + NOV block, store over "Category · N items", amount right, `≈ $` under LBP amounts). Roll ends with a double rule + `OCTOBER 2026` cap + "Older receipts →". Empty filter: "No receipts in this category yet." Receipts other than Spinneys and Zaatar w Zeit are sample data. |

Not designed yet: settings/profile, budget editor, receipt search results. Build these from the same components, and ask before inventing new patterns.

---

## 7. Do / don't
- **Do** keep numbers in Geist Mono and right-aligned. **Do** keep the one-cobalt-accent rule.
- **Do** keep text contrast ≥ 4.5:1 (that is why secondary text on paper is `#46453F`, not lighter).
- **Don't** add gradients, glass, coloured cards, emoji, or extra accent colours.
- **Don't** put zigzags between screen sections or on buttons.
- **Don't** raise crease opacity above ~0.7, or put the crease on near-white surfaces (it vanishes) or on the tab bar.
