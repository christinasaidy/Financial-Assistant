# Fatourati design handoff

1. Put this folder in your repo as `design/`.
2. Add this to your project's `CLAUDE.md`:

```md
## Design
The UI must follow `design/DESIGN.md` exactly. Tokens are in `design/theme.ts`.
Before building or changing any screen, open the matching image in `design/screens/`
and, for exact values, `design/reference/<screen>.html`.
The crease texture is `design/assets/crease.jpg` (overlay blend, on top of content, see DESIGN.md §3).
After building a screen, compare it with its screenshot and fix differences.
Do not invent new colours, fonts or decorations. Ask if a screen is not designed yet.
```

3. Then tell Claude Code, for example:
   > Read design/DESIGN.md and build the Home screen (design/screens/03-home.png) in React Native using design/theme.ts. Start with the CreasedPaper and TornEdge components from §3.

Contents: `DESIGN.md` (spec), `theme.ts` (tokens), `screens/` (8 PNGs at 2×), `reference/` (exact HTML of each screen), `assets/crease.jpg`.
