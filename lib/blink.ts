import { createClient, AsyncStorageAdapter } from '@blinkdotnew/sdk';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const PROJECT_ID =
  process.env.EXPO_PUBLIC_BLINK_PROJECT_ID || 'polymarket-btc-bot-ec8rjv2k';
const PUBLISHABLE_KEY =
  process.env.EXPO_PUBLIC_BLINK_PUBLISHABLE_KEY ||
  'blnk_pk_3xFJaM3DR24Bzcq--SuMXqVHayXzpFnN';

// ─── Build a correctly-configured client for the current platform ───────────
// Web preview runs inside an iframe → window.open popups are blocked.
// Google OAuth therefore CANNOT work on web in this environment.
// Solution: email+password on web, Google OAuth on native (iOS/Android).
async function buildClient() {
  if (Platform.OS !== 'web') {
    // Native: import expo-web-browser so OAuth popups open in the system browser
    const WebBrowser = await import('expo-web-browser');
    return createClient({
      projectId: PROJECT_ID,
      publishableKey: PUBLISHABLE_KEY,
      auth: {
        mode: 'headless',
        webBrowser: WebBrowser,
      },
      storage: new AsyncStorageAdapter(AsyncStorage),
    });
  }

  // Web: no webBrowser — email/password only (no popup needed)
  return createClient({
    projectId: PROJECT_ID,
    publishableKey: PUBLISHABLE_KEY,
    auth: { mode: 'headless' },
  });
}

// Singleton so the heavy import only runs once
let _clientPromise: ReturnType<typeof buildClient> | null = null;

export function getBlinkClient() {
  if (!_clientPromise) _clientPromise = buildClient();
  return _clientPromise;
}

// Synchronous client used for DB reads (no auth methods called on it)
export const blink = createClient({
  projectId: PROJECT_ID,
  publishableKey: PUBLISHABLE_KEY,
  auth: { mode: 'headless' },
  ...(Platform.OS !== 'web'
    ? { storage: new AsyncStorageAdapter(AsyncStorage) }
    : {}),
});
