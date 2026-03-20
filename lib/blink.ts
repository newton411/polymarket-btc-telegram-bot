import { createClient, AsyncStorageAdapter } from '@blinkdotnew/sdk';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as WebBrowser from 'expo-web-browser';

export const blink = createClient({
  projectId: process.env.EXPO_PUBLIC_BLINK_PROJECT_ID || 'polymarket-btc-bot-ec8rjv2k',
  publishableKey: process.env.EXPO_PUBLIC_BLINK_PUBLISHABLE_KEY || 'blnk_pk_3xFJaM3DR24Bzcq--SuMXqVHayXzpFnN',
  auth: {
    mode: 'headless',
    webBrowser: WebBrowser,
  },
  storage: new AsyncStorageAdapter(AsyncStorage),
});
