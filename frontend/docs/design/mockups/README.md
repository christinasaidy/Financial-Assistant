# Mockups (reference for building the screens)

These are the approved HTML mockups from the design canvas, copied here so the app can be built from them. They
are **references, not code to port line by line**: the values to use are the tokens in `../DESIGN.md`, and the
reasons are in `../DECISIONS.md`. Where a mockup and DESIGN.md disagree, DESIGN.md wins.

Each file is one 390 x 844 iPhone screen. They load images by an id (`/_blob/<id>`); the table maps each id to the
file in this repo.

## Which mockup is which screen (D039)

| Screen | Light | Dark |
|---|---|---|
| Launch (yellow paper; the same in both themes) | `LaunchYellow.dc.html` | none: use the light one |
| Sign in (lightly creased paper) | `SignInCreased.dc.html` wraps `SignInBodyLight.dc.html` | `SignInCreasedDark.dc.html` wraps `SignInBodyDark.dc.html` |
| Create account | `CreateAccount.dc.html` (drawn on milky paper: build it on lightly creased paper, and add the gender choice, D041) | `CreateAccountDark.dc.html` |
| Home with data (lightly creased paper) | `Wrinkle.dc.html` wraps `HomeBodyLight.dc.html` | `WrinkleDark.dc.html` wraps `HomeBodyDark.dc.html` |
| Home before any receipts | `Empty.dc.html` (plain paper, older header: use the creased paper and highlighted wordmark of the Home mockup) | `EmptyDark.dc.html` |

Real data replaces the example numbers ($447.80, Spinneys Achrafieh, ...); "Christina" is the signed-in user's
first name.

## Image ids

| Id in the mockups | File |
|---|---|
| `e396e385…` / `31af3f95…` | `assets/fonts/DejaVuSansMono.ttf` / `DejaVuSansMono-Bold.ttf` |
| `427875e5…` / `775de8ac…` | `assets/fonts/DejaVuSans.ttf` / `DejaVuSans-Bold.ttf` |
| `68091e1f…` / `1ddc5343…` | `assets/paper/grain-light.png` (256 px tile, repeat; only on the yellow launch since D042) / grain-dark, removed |
| `30d76934…` / `55bd9532…` | crease shading; removed from the app by D042 (screens are plain) |
| `d2554d85…` | `assets/wordmark/fatourati-large.svg` in ink (#1c1d21) |
| `3df1b468…` / `406e1f00…` | `assets/wordmark/fatourati-small.svg` in ink / ink-dark |
| `7f9e0f22…` `7a74bbe0…` `0d7e61e0…` `26e0734e…` `6c2e0c17…` `f3b5ea0e…` | printed icons (light): home (ink), receipts, scan (paper colour, on the blue square), budgets, assistant (ink-2), notifications (ink) |
| `077860cc…` `dad55022…` `e854d5db…` `8d9ce7e3…` `db3115be…` `7b888e11…` | the same icons in dark colours |

Icons are `assets/icons/<name>-printed.svg`; they draw in `currentColor`.

## Things the mockups cannot show

- The highlighter swipe uses CSS `clip-path`; in React Native draw it as an SVG polygon behind the wordmark.
- Paper textures are CSS backgrounds. Since D042 the app's screens are plain; only the launch tiles the grain.
- "Continue with Apple" and "Forgot password?" are **not built yet** (D040).
