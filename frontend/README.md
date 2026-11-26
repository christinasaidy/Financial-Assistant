# Fatourati (mobile app)

React Native with Expo SDK 58, TypeScript (strict) and Expo Router. Designed and tested on an iPhone with
Expo Go (D004). The design is in [design/DESIGN.md](design/DESIGN.md), with its tokens in
[design/theme.ts](design/theme.ts), the screens in [design/screens/](design/screens/) and their exact markup in
[design/reference/](design/reference/) (D044). The reasons are in [docs/design/DECISIONS.md](docs/design/DECISIONS.md).

## Run it on the iPhone (Expo Go)

1. Install [Expo Go](https://apps.apple.com/app/expo-go/id982107779) from the App Store. It runs only the
   latest Expo SDK, which is why this app follows the latest one.
2. Start the backend so the phone can reach it, from `backend/`:
   `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
   (`--host 0.0.0.0` listens on the Wi-Fi too, not only on the laptop itself). The first time, Windows asks
   whether Python may use private networks: allow it.
3. In `frontend/`: `npm install`, then **`npm run phone`**. It finds the laptop's address on whatever Wi-Fi or
   hotspot it is on, starts Expo there and prints the link to open in Expo Go (`exp://<address>:8081`). Nothing
   to edit when the network changes: the app finds the backend on that same laptop, port 8000. The iPhone and
   the laptop must be on the same network (the iPhone's own hotspot works: connect the laptop to it).
   `.env` is optional; set `EXPO_PUBLIC_API_URL` only for a backend somewhere else (then restart with
   `npm run phone -- --clear`).

To check the phone can reach the backend, open `http://<laptop-IP>:8000/docs` in Safari on the iPhone.

**Splash screen.** `app.json` configures a plain white native splash, like the launch screen's background,
but **Expo Go shows its own splash** (the Expo Go icon); the configured one appears only in a development or store
build. The launch route (`app/index.tsx`) shows right after, while the saved session is checked.

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
    settings.tsx               settings, pushed over the tabs from the account button (features/settings/ui/SettingsScreen)
  src/
    container.ts               composition root
    shared/
      theme/                   tokens.ts: design/theme.ts re-exported, plus the reference screens' extra colours
      ui/                      AppText, paper (PaperSheet, Crease, TornEdge, Perforation, DashedLine, DoubleRule),
                               Wordmark, Icon + LineIcon, Button, TextField, SegmentedChoice, TextLink, TabBar,
                               PlaceholderScreen; art/ = the five tab icons, converted
      api/httpClient.ts        fetch wrapper: base URL, JSON, bearer token, ApiError, NetworkError
      storage/tokenStore.ts    one value in the Keychain (expo-secure-store): the session
      format/                  money.ts (D034), dates.ts (dd/mm/yyyy, 24 h)
    features/
      auth/{domain,application,data,ui}
      launch/ui                LaunchScreen (the creased launch sheet); no other layers
      home/{domain,application,data,ui}     Home: the month's invoice and recent receipts
      settings/ui              Settings: the account and sign out
  tests/                       mirrors src/; plus architecture.test.ts and routes.test.tsx
  assets/                      icons (the five kept), paper/crease.jpg (fonts come from @expo-google-fonts)
  scripts/convert-svgs.mjs     SVG → react-native-svg data
  design/                      THE DESIGN (D044): DESIGN.md, theme.ts, screens/, reference/, assets/
  docs/design/                 DECISIONS.md, and the first design (superseded)
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

- **Design**: follow `design/DESIGN.md`; open the screen's image in `design/screens/` and, for exact values,
  `design/reference/<screen>.html`. Light only (D044).
- **Theme**: `colors`, `fonts`, `radius`, `crease`, `tornEdge`, `shadow` from `@/shared/theme` (design/theme.ts
  plus the reference screens' extra colours). Spacing is the reference's own px values.
- **Text**: always `AppText`: `font` (sans, mono, arabic), `weight`, `size`, `color`, `tracking` (em), or `cap`
  for the small capital labels. Numbers in mono (tabular). Text follows the iPhone's text-size setting.
- **Paper**: `PaperSheet` (crease on top of the content, torn edge, shadow; pass `on` with the colour behind so
  the teeth are creased too).
- **Session**: `useSession()` from `@/features/auth/ui/SessionProvider` gives
  `{ status, user, signIn, signUp, signOut }`. The routes follow `status` by themselves: no manual navigation
  after signing in or out.
- **HTTP**: services never call `fetch`; their data layer uses the `HttpClient` the container gives it. A 401 on
  a signed-in request signs the user out everywhere.

## Open questions

Not designed yet (D044), built simply until Christina decides:

- **Loading and errors**: a spinner under the header; a sentence with Try again.
- **Switching months** on Home: the older sheets behind the invoice show, but do not open their month yet.
- **The bell** does nothing (no notifications screen).
- **Receipt rows** on Home do not open a receipt yet (receipt detail is the next feature).
- **Large text sizes**: the invoice table's columns are fixed (60 and 84 px) as in the design.
- **App icon**: not designed, so `app.json` has none (Expo's default icon is used).
