# FairEnrol mobile app with Capacitor

FairEnrol is a Vite + React app with a separate API. Capacitor packages the Vite output from `dist/`; `npm run build:mobile` builds both React frontends and places the Careers app at `dist/careers/` so the native app includes both workspaces. Mobile layouts use fixed bottom navigation with safe-area spacing.

## Windows development

Use Node.js 22.6+ (this workspace was built with Node 24), Android Studio Otter 2025.2.1 or newer, and an Android SDK/emulator. This project builds with Android Studio's bundled JDK 21; the machine-wide Java 25 currently fails Gradle's Android build.

From PowerShell at the repository root:

```powershell
npm.cmd ci
npm.cmd run careers:install
Copy-Item .env.capacitor.example .env.capacitor.local
docker compose up -d postgres tidecloak
```

For the Android Studio emulator, `.env.capacitor.local` uses `http://10.0.2.2:3001`, the emulator's route back to the Windows host. Start the API bound to the host network and both web frontends in another terminal:

```powershell
$env:API_HOST = '0.0.0.0'
npm.cmd run dev
```

The root app is at `http://localhost:5137/`; Careers is at `http://localhost:5137/careers/`. The native package reads the built bundle and calls the API at `VITE_API_BASE_URL`.

For a physical Android phone, replace `10.0.2.2` in `.env.capacitor.local` with the Windows machine's LAN IPv4 address, keep `API_HOST=0.0.0.0`, and allow the API port through Windows Defender Firewall on the private network. The phone and PC must share a network.

The local API uses HTTP, so enable mixed content only for local Android testing. Select Android Studio's JDK 21 in this PowerShell session so Gradle does not use the machine-wide JDK 25:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
$env:CAPACITOR_LOCAL_ANDROID_HTTP = '1'
npm.cmd run cap:sync
npx.cmd cap run android --target emulator-5554
```

The `/careers/index.html` path is used for the nested app because the Capacitor asset server treats `/careers/` as a root SPA fallback. Android Studio can also run the project with `npm.cmd run cap:open:android` and its Run button. The web assets and nested Careers bundle are copied during `cap:sync`.

Build a debug APK from PowerShell:

```powershell
Push-Location android
.\gradlew.bat assembleDebug
Pop-Location
```

The APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`. Test on the Medium Phone and a physical Android device where possible: check safe-area padding, bottom-tab navigation, keyboard overlap in forms/chat, back navigation, sign-in return, and a protected read/write workflow in both workspaces.

Before creating a release build, use a reachable HTTPS API and turn off the local mixed-content flag:

```powershell
$env:VITE_API_BASE_URL = 'https://YOUR_API_HOST'
$env:CAPACITOR_LOCAL_ANDROID_HTTP = '0'
npm.cmd run cap:sync
Push-Location android
.\gradlew.bat bundleRelease
Pop-Location
```

Configure Android release signing in Android Studio/Gradle before distributing the AAB. Do not ship an HTTP API URL or a build synced with `CAPACITOR_LOCAL_ANDROID_HTTP=1`.

## iOS test and build

Windows can edit the React app and install `@capacitor/ios`, but it cannot compile, run the iOS simulator, or sign an iOS app. Those steps require a Mac with Xcode 26 or newer for Capacitor 8.

On a Mac, check out the same repository and run:

```bash
npm ci
npm --prefix careers/frontend ci
cp .env.capacitor.example .env.capacitor.local
```

Set `VITE_API_BASE_URL` in `.env.capacitor.local` to a reachable HTTPS API URL, then add/sync/open the iOS target:

```bash
npx cap add ios                 # first time only
npm run cap:sync
npx cap open ios
```

In Xcode, select an iPhone simulator or a connected device and press Run. For an App Store archive, select the App target, configure the Apple development team and bundle identifier, then choose **Product → Archive**. Xcode Organizer validates signing and exports the archive for TestFlight/App Store Connect.

## TideCloak and API origins

The backend's CORS allowlist includes `https://localhost` and `capacitor://localhost`; add the actual native redirect URL `https://localhost/auth/redirect` and web origin `https://localhost` to the Tide client if the existing realm requires explicit redirect/origin entries. Keep the normal browser URL `http://localhost:5137` for web development. This mobile wrapper assumes the current Tide integration works; it does not change realm roles or governance state.

For a deployed backend, set `VITE_API_BASE_URL` to its HTTPS origin when running `npm run build:mobile`, and configure that backend to allow the Capacitor WebView origin. Keep API calls behind the existing Tide `secureFetch` transport.

## Files

- `capacitor.config.ts` — app id/name, `dist` web directory, HTTPS WebView origins, and opt-in local Android HTTP testing.
- `scripts/build-mobile.mjs` — builds both Vite apps and stages Careers under the root `dist/`.
- `src/api/client.js` and `careers/frontend/src/api/config.js` — resolve API requests against `VITE_API_BASE_URL`.
- `src/App.jsx`, `src/style.css`, and `careers/frontend/src/components/Layout.jsx` — responsive bottom navigation and safe-area styles.
- `server/app.js` — narrow CORS allowlist for browser and Capacitor origins.

Official references: [Capacitor installation](https://capacitorjs.com/docs/v8/getting-started/installation), [Android](https://capacitorjs.com/docs/v8/android), and [iOS](https://capacitorjs.com/docs/v8/ios).
