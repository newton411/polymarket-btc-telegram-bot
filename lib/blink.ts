import { createClient, AsyncStorageAdapter } from '@blinkdotnew/sdk';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as WebBrowser from 'expo-web-browser';

export const blink = createClient({
  projectId: process.env.EXPO_PUBLIC_BLINK_PROJECT_ID!,
  auth: {
    mode: 'headless',
    webBrowser: WebBrowser, // REQUIRED for OAuth on mobile
  },
  storage: new AsyncStorageAdapter(AsyncStorage),
});
