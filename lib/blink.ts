/**
 * RECON HFT — Blink SDK Client
 *
 * Two clients:
 *  1. `blink`  — synchronous singleton for DB reads anywhere in the app.
 *  2. `getAuthClient()` — async, returns the correctly configured client for
 *     auth operations (email/password on web, Google OAuth on native).
 *
 * Google OAuth is intentionally blocked on web because the app runs inside an
 * iframe in the Blink preview, and window.open() popups are blocked there.
 */

import { createClient, AsyncStorageAdapter } from '@blinkdotnew/sdk';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const PROJECT_ID     = process.env.EXPO_PUBLIC_BLINK_PROJECT_ID     || 'polymarket-btc-bot-ec8rjv2k';
const PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_BLINK_PUBLISHABLE_KEY || 'blnk_pk_3xFJaM3DR24Bzcq--SuMXqVHayXzpFnN';

// ── Shared storage adapter (native only) ─────────────────────────────────────
const storageOpts = Platform.OS !== 'web'
  ? { storage: new AsyncStorageAdapter(AsyncStorage) }
  : {};

// ── 1. Synchronous DB client (no auth config needed) ─────────────────────────
export const blink = createClient({
  projectId:      PROJECT_ID,
  publishableKey: PUBLISHABLE_KEY,
  auth: { mode: 'headless' },
  ...storageOpts,
});

// ── 2. Auth client — lazily initialised once ─────────────────────────────────
let _authClient: ReturnType<typeof createClient> | null = null;

export async function getAuthClient(): Promise<ReturnType<typeof createClient>> {
  if (_authClient) return _authClient;

  if (Platform.OS !== 'web') {
    // Native — dynamically import expo-web-browser so Google OAuth works
    try {
      const WebBrowser = await import('expo-web-browser');
      _authClient = createClient({
        projectId:      PROJECT_ID,
        publishableKey: PUBLISHABLE_KEY,
        auth: { mode: 'headless', webBrowser: WebBrowser },
        ...storageOpts,
      });
    } catch {
      // Fallback if expo-web-browser unavailable
      _authClient = createClient({
        projectId:      PROJECT_ID,
        publishableKey: PUBLISHABLE_KEY,
        auth: { mode: 'headless' },
        ...storageOpts,
      });
    }
  } else {
    // Web — email/password only, no popup needed
    _authClient = createClient({
      projectId:      PROJECT_ID,
      publishableKey: PUBLISHABLE_KEY,
      auth: { mode: 'headless' },
    });
  }

  return _authClient;
}
