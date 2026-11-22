---
name: anti-ai-slop
description: Keeps Fatourati's interface from looking like a generic AI-built app. Load before any frontend or design work in this project - screens, components, styles, colors, fonts, icons, copy, mockups or design artifacts - and before proposing any visual choice. Requires reading the design system first and asking Christina design questions instead of filling gaps with defaults.
---

# Anti AI slop (Fatourati)

Generic AI-built interfaces look alike because every open choice falls back to the most common answer: the
blue-to-purple gradient, Inter, a row of three rounded cards with Lucide icons. None of those is bad alone; the
problem is that **nobody decided them**. In this project every visual choice is decided by Christina and recorded.
Your job is to surface the choices, not to fill them in.

## 1. Before touching anything visual

1. Read `frontend/docs/design/DESIGN.md` (the current values) and `frontend/docs/design/DECISIONS.md` (why, and
   what is still open).
2. Use only values that are recorded there. If the task needs one that is not (a color, a size, a spacing, a
   radius, a shadow, an icon, a word of copy), **stop and ask Christina**. Do not pick "for now".
3. After she decides, record it the same turn: a new numbered entry in DECISIONS.md (status, context, options
   considered, decision, consequences) and the value in DESIGN.md's front matter or section.

## 2. Ask a lot of design questions

Christina wants to be asked. When starting any screen or component, ask before building, a few at a time, each
with 2-4 concrete options and your recommendation first, and show them visually when the difference is visual
(a mockup or specimen beats a description). Typical questions:

- Spacing: padding inside the element, gaps between elements, screen side margins.
- Icons: size, and how the icon lines up with the text next to it (see section 4), gap between icon and text.
- Type: which text style for each piece of text, case (upper or normal), line length.
- Shape: corner radius, borders vs. no borders, dividers (solid, dashed, double).
- Color: which token for each surface and text, and the dark-theme counterpart.
- States: empty, loading, error, pressed, disabled.
- Copy: the exact words of labels, buttons, empty states and errors.
- Motion: whether anything moves at all, and how.

## 3. Never, unless Christina asks for it by name

Colors and surfaces:
- Gradients of any kind, above all blue-to-purple, indigo or violet; gradient text; glowing borders or neon on
  black.
- The Tailwind default palette (indigo-500, slate, zinc) or any palette not in DESIGN.md.
- **The Claude look** (Christina hates it): warm charcoal or brown-grey backgrounds, cream or warm off-white text,
  coral, salmon or terracotta accents (around hue 15), golden amber. Dark mode in particular must be cool and
  neutral; oranges must be pure and saturated, never coral.
- Glassmorphism, background blur, frosted cards.
- The same soft drop shadow on every card.

Type:
- Inter, Roboto or any font not in DESIGN.md.
- Everything at one size and one weight; or a giant hero number with tiny grey text under it everywhere.

Icons and imagery:
- Lucide, Heroicons, Feather, Material Symbols, SF Symbols as a stand-in, or any other icon library.
- Emoji used as icons; sparkles (✨) or robot faces for the assistant.
- Stock 3D illustrations, blobs, confetti.

Layout and components:
- A centered hero with one call-to-action button; rows of three identical rounded cards with an icon on top.
- Pill badges on everything; every corner the same large radius by default.
- A chat screen styled like every AI chatbot (bubble avatars, "Ask me anything ✨").

Copy:
- Marketing filler: "Unlock insights", "Seamless", "Effortless", "Supercharge", "Your AI-powered ...".
- Lorem ipsum or invented numbers in anything Christina will judge; use realistic Lebanese receipts (Spinneys,
  Zaatar w Zeit, LBP and USD amounts).

## 4. Icons

- Icons are Christina's own, drawn in Figma and read through the Figma MCP when it is connected. Never substitute a
  library icon. If an icon is missing, leave a clearly marked placeholder box of the right size and ask her for it.
- Alignment matters (her reference: in Revolut the icon's size matches the height of the first character of the
  text beside it, with deliberate margins and padding). The exact rule (cap height or x-height, icon box vs. drawn
  glyph, gap) is **not decided yet**: ask her before placing the first icon next to text, then record it.

## 5. The direction: a receipt

The app should feel like a printed receipt (D002). Receipt motifs (monospace type, dashed or double rules,
item-left / price-right columns, uppercase labels, paper and ink colors, a faded print look for the name) are
candidates, not rules: use one only after it is recorded in DESIGN.md. Do not turn the whole app into a costume.

## 6. Before showing anything

Check the work against this list and fix it first:
- Every color, font, size, spacing, radius and icon comes from DESIGN.md, or is a marked question for Christina.
- Nothing from section 3.
- Both light and dark themes look deliberate, not one theme inverted.
- Text is real and specific; numbers look like real receipts.
- You listed the open design questions this work raised, ready to ask.
