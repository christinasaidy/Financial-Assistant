# Fatourati (mobile app)

React Native with Expo SDK 58, TypeScript (strict) and Expo Router. Designed and tested on an iPhone with
Expo Go (D004). The design system is in [docs/design/DESIGN.md](docs/design/DESIGN.md) (values) and
[docs/design/DECISIONS.md](docs/design/DECISIONS.md) (reasons); the approved screens are in
[docs/design/mockups/](docs/design/mockups/README.md).

## Run it on the iPhone (Expo Go)

1. Install [Expo Go](https://apps.apple.com/app/expo-go/id982107779) from the App Store. It runs only the
   latest Expo SDK, which is why this app follows the latest one.
2. Start the backend so the phone can reach it, from `backend/`:
   `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
   (`--host 0.0.0.0` listens on the Wi-Fi too, not only on the laptop itself). The first time, Windows asks
   whether Python may use private networks: allow it.
3. In `frontend/`, copy `.env.example` to `.env` and put the laptop's Wi-Fi address in it. Find it with
   `ipconfig` ("IPv4 Address"), for example `EXPO_PUBLIC_API_URL=http://192.168.1.23:8000`. `localhost` does
   not work: on the phone it means the phone. **The iPhone and the laptop must be on the same Wi-Fi.**
4. `npm install`, then `npx expo start`. Scan the QR code with the iPhone's Camera app; it opens in Expo Go.
   After changing `.env`, restart with `npx expo start --clear`.

To check the phone can reach the backend, open `http://<laptop-IP>:8000/docs` in Safari on the iPhone.

**Splash screen.** `app.json` configures the native splash as the yellow launch (`#f5e54a` and the large
wordmark, `assets/splash/wordmark-large.png`, D039), but **Expo Go shows its own splash** (the Expo Go icon);
the configured one appears only in a development or store build. The yellow launch route (`app/index.tsx`)
shows right after, while the saved session is checked. The native splash is plain yellow: a splash image cannot
tile the grain.

## Commands

| Command | What it does |
|---|---|
| `npx expo start` | Dev server; scan the QR code with the iPhone |
| `npm test` (`npx jest`) | Unit, component, routing and architecture tests |
| `npm run typecheck` (`npx tsc --noEmit`) | Type check |
| `npm run lint` | ESLint (eslint-config-expo) over the whole folder |
| `npx expo export --platform ios` | Builds the iOS JavaScript bundle (a release-build check that works on Windows) |
| `npm run convert-svgs` | Regenerates the icon and wordmark components after an SVG in `assets/` changes |
| `npx expo install <package>` | Adds a package at the version that matches the SDK (use it instead of `npm install <package>`) |

Only libraries that run in Expo Go may be added (no custom native code), and no icon libraries or UI kits (D008,
`.claude/skills/anti-ai-slop`).

## Architecture

The app follows the same clean architecture as the backend (controller → service → repository, with
interfaces, one service per feature). Each feature has four layers; **source dependencies point inward only**:

```
ui  ──►  application  ──►  domain
              ▲
data ─────────┘   (data implements the application's interfaces)
```

| Layer | Holds | May import |
|---|---|---|
| `domain/` | Plain types and rules (`User`, `Gender`, `Session`, `AuthError`). | Only domain code. No React, no Expo, no packages. |
| `application/` | The use cases (`AuthService`) and the interfaces they need (`AuthRepository`, `TokenStore`: the "ports"). | Domain, and UI-free shared code (`shared/format`). No packages. |
| `data/` | The implementations of those interfaces against the outside world (backend over HTTP, Keychain). Maps API shapes (snake_case DTOs) to domain types. | Domain, its own application code, `shared/api`, `shared/storage`, `shared/format`, packages. |
| `ui/` | Screens, components and hooks for the feature. | Anything except `data/`. Gets services through providers/hooks (built by the container). |

Around the features:

- **`src/container.ts`** is the composition root: the only file that imports from a `data/` folder. It builds the
  HTTP client, the repositories and the services and connects them (backend equivalent: `app/api/container.py`).
- **`src/shared/`** is code every feature uses. It never imports a feature.
- **`app/`** holds Expo Router routes **only**: thin files that render a screen from `src/features/*/ui` (or a
  shared component). Routes never import `data/`, `application/`, `domain/` or the container.

Why: the use cases can be tested without a phone, a backend or a Keychain (tests pass fakes for the
interfaces), and the backend, storage or navigation library can change without touching the rules.

`tests/architecture.test.ts` enforces all of this, like the backend's `tests/test_architecture.py`: it reads
every import in `app/` and `src/` and fails on one that points the wrong way. It also feeds itself made-up
violations to prove it catches them.

### Folder map

```
frontend/
  app/                         Expo Router routes only
    _layout.tsx                fonts, splash, SessionProvider, status bar, who sees which routes
    index.tsx                  launch route: LaunchScreen while the session is checked, then redirects
    (auth)/sign-in.tsx         sign in (features/auth/ui/SignInScreen)
    (auth)/sign-up.tsx         create account (features/auth/ui/SignUpScreen)
    (tabs)/_layout.tsx         the five tabs with Fatourati's tab bar
    (tabs)/index.tsx           Home (features/home/ui/HomeScreen)
    (tabs)/receipts|scan|budgets|assistant.tsx   placeholders
  src/
    container.ts               composition root
    shared/
      theme/                   tokens.ts (from DESIGN.md), textStyles.ts, useTheme() (light/dark)
      ui/                      AppText, Paper, Wordmark, Icon, Button, TextField, DashedRule, TabBar,
                               HighlightSwipe, PlaceholderScreen; art/ = converted SVGs
      api/httpClient.ts        fetch wrapper: base URL, JSON, bearer token, ApiError, NetworkError
      storage/tokenStore.ts    one secret value in the Keychain (expo-secure-store)
      format/                  money.ts (D034), dates.ts (dd/mm/yyyy, 24 h)
    features/
      auth/{domain,application,data,ui}
      launch/ui                LaunchScreen (yellow paper, large wordmark); no other layers
      home/{domain,application,data,ui}     empty, for Home
  tests/                       mirrors src/; plus architecture.test.ts and routes.test.tsx
  assets/                      fonts (+ DejaVu LICENSE), icons, wordmark, paper textures, splash
  scripts/convert-svgs.mjs     SVG → react-native-svg data
  docs/design/                 the design system
```

### How a feature adds a screen

Example: Home.

1. **Domain** (`src/features/home/domain/`): the types the screen shows, e.g. `MonthSummary`. Plain
   TypeScript.
2. **Application** (`src/features/home/application/`): `interfaces.ts` with the port it needs
   (`HomeRepository`), and `homeService.ts` with the use case (`loadHome()`), depending only on the interface.
3. **Data** (`src/features/home/data/`): `apiHomeRepository.ts` implements `HomeRepository` with the
   `HttpClient` (`GET /spending/summary`, `GET /budgets`, `GET /receipts`) and maps the DTOs. Amounts arrive as
   strings: keep them as strings and format them with `shared/format/money.ts`.
4. **Container** (`src/container.ts`): build `new HomeService(new ApiHomeRepository(http))` and add it to
   `Container` as `home`.
5. **UI** (`src/features/home/ui/`): `HomeScreen.tsx`, getting the service with `getContainer().home` (wrap
   that in a hook such as `useHomeService()`), and the user from `useSession()`. Build it from `src/shared/ui`
   and the theme; use only values from DESIGN.md.
6. **Route**: replace the body of `app/(tabs)/index.tsx` with `export { HomeScreen as default } from
   '@/features/home/ui/HomeScreen';` (or a one-line component), and delete the TODO.
7. **Tests** in `tests/features/home/`: the service with a fake repository, the repository with a mocked
   fetch, the screen with `@testing-library/react-native` (v14: `render`, `fireEvent` and `act` are async, so
   `await` them). Run `npx jest`, `npx tsc --noEmit` and `npm run lint`.

A new route is a new file in `app/` (see the [Expo Router docs](https://docs.expo.dev/router/introduction/)).
Signed-out routes go in `app/(auth)/`, signed-in ones in `app/(tabs)/` or a new group guarded in
`app/_layout.tsx`.

## Shared pieces, in short

- **Theme**: `useTheme()` returns `{ scheme, colors }` for the phone's light or dark setting (D003).
  `colors` has every DESIGN.md colour token by name (`colors['ink-2']`). Spacing, sizes and fonts are in
  `@/shared/theme` (`spacing.lg`, `spacing['screen-margin']`, `sizes.button`).
- **Text**: always `AppText` with one of the nine `variant`s (D014); write text in normal case, the variant adds
  capitals (D012). Text follows the iPhone's text-size setting (D013).
- **Session**: `useSession()` from `@/features/auth/ui/SessionProvider` gives
  `{ status, user, signIn, signUp, signOut }`. The routes follow `status` by themselves: no manual navigation
  after signing in or out.
- **HTTP**: services never call `fetch`; their data layer uses the `HttpClient` the container gives it. A 401 on
  a signed-in request signs the user out everywhere.

## Open questions

Values the foundation needed that DESIGN.md does not record yet. Each uses the closest recorded value or the
approved mockup, and should be decided with Christina and recorded in DECISIONS.md:

- **Main button states**: pressed, disabled and busy have no look yet (only behaviour and VoiceOver). Its side
  padding when a long label wraps at large text sizes uses `spacing.lg` (16). The label uses the `paper` token
  (#f7f8f6 / #17181b); the mockups still show the old #f3f4f1.
- **Fill-in field** (D040): the 40 px value row, the 4 px caption gap and the 12 px gap before SHOW come from the
  sign-in mockup. Error text style and place are not decided (built as a `sentence` in `limit-reached` under the
  line); placeholder colour (`ink-2`), focus look and whether the line changes colour on error are not decided.
- **Sign in and create account** (D040, D041): the mockups' off-scale gaps are rounded to the 4 px scale: 24 px
  between fields (mockup 20), 32 px above the first field and above the button (mockup 28 on create account,
  and the space Forgot password? left on sign in). The top is the safe area plus 48 px (sign in) or 32 px (create
  account), close to the mockups' 112 and 96 px from the top of the screen. The password hint is `meta` 4 px
  under the line (mockup 6 px) and gives way to the error. Messages about the whole form (wrong password, no
  connection) sit 24 px above the button in the field-error style. Gender: 8 px between the caption and the
  options and between options, unchosen labels `ink-2`. None of these is in DESIGN.md yet.
- **Tab bar**: 4 px between icon and label (the mockup's Scan tab uses 2 px, which is off the 4 px scale) and
  4 px padding inside the yellow swipe. At very large text sizes the labels shrink to fit one line
  (ASSISTANT barely fits a fifth of the screen); not decided.
- **Dark mode on yellow**: the selected tab's label is ink #1c1d21 as D038 says (the dark mockup uses #17181b).
  Dark creased paper is #17181b as D039 says (the dark mockup uses #1a1b1e).
- **Printed look for text** (D011, still open in DECISIONS.md): text is drawn clean for now.
- **App icon**: not designed, so `app.json` has none (Expo's default icon is used).
