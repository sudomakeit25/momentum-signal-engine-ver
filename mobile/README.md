# MSE Mobile

React Native + Expo client for the Momentum Signal Engine backend.

Screens:
- **Scanner** — top 30 momentum stocks, pull-to-refresh
- **Search** — ticker input + popular / forex / commodities / indices chips
- **Watchlist** — server-side watchlist from Redis
- **Settings** — version, backend URL, push notifications placeholder
- **Instrument detail** — Overview / Seasonality / Fundamentals / News tabs
  (deep link: `mse://instrument/NVDA`)

The API base is baked into `app.json` under `expo.extra.apiBase` and
defaults to the production backend. Override at build time via EAS
env for staging.

## Run

```sh
cd mobile
npm install
npm run ios      # iOS simulator (requires Xcode)
npm run android  # Android emulator
npm run start    # Pick a target via the Expo dev CLI
```

Open the Expo Go app on a phone and scan the QR code printed by
`npm run start` to test on a real device without signing.

## Build for TestFlight / Play Store

Use EAS Build (`npx eas build --platform ios`). Requires an Apple
Developer Team ID + bundle ID set in `app.json`
(currently `com.sudomakeit25.mse`).
