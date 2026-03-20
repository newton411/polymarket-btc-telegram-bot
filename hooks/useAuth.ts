/**
 * useAuth — stable auth state hook for RECON HFT
 *
 * Strategy:
 *  - Subscribes to auth state via onAuthStateChanged on the auth client.
 *  - On web: exposes email/password sign-in and sign-up only.
 *  - On native: also exposes Google OAuth via expo-web-browser.
 *  - Never calls blink.auth.login() (managed mode) — always headless.
 */

import { useState, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { getAuthClient } from '@/lib/blink';

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string;
  photoURL?: string;
}

export function useAuth() {
  const [user,            setUser]   = useState<AuthUser | null>(null);
  const [isLoading,       setLoad]   = useState(true);
  const [isAuthenticated, setAuth]   = useState(false);
  const [authError,       setError]  = useState<string | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        const client = await getAuthClient();
        if (!alive) return;

        // Subscribe to auth state changes
        const unsub = client.auth.onAuthStateChanged((state: any) => {
          if (!alive) return;
          setUser(state.user ?? null);
          setAuth(!!state.isAuthenticated);
          // Only set loading false once we get the first real state emission
          setLoad(!!state.isLoading);
        });

        unsubRef.current = unsub;
      } catch (err: any) {
        if (!alive) return;
        console.error('[useAuth] client init error:', err?.message || err);
        setLoad(false);
        setError('Failed to initialise auth. Please refresh.');
      }
    })();

    // Safety net: if auth state never fires, unblock UI after 4s
    const timeout = setTimeout(() => {
      if (alive) setLoad(false);
    }, 4000);

    return () => {
      alive = false;
      clearTimeout(timeout);
      unsubRef.current?.();
    };
  }, []);

  // ── Google OAuth ────────────────────────────────────────────────────────────
  const signInWithGoogle = async () => {
    if (Platform.OS === 'web') {
      const msg = 'Google sign-in is not available in the browser preview. Use email + password instead.';
      setError(msg);
      throw new Error(msg);
    }
    setError(null);
    try {
      const client = await getAuthClient();
      await client.auth.signInWithGoogle();
    } catch (err: any) {
      const msg = err?.message || String(err);
      setError(msg);
      throw err;
    }
  };

  // ── Email / password ─────────────────────────────────────────────────────────
  const signInWithEmail = async (email: string, password: string) => {
    setError(null);
    try {
      const client = await getAuthClient();
      await client.auth.signInWithEmail(email, password);
    } catch (err: any) {
      const msg = _friendlyAuthError(err?.message || String(err));
      setError(msg);
      throw new Error(msg);
    }
  };

  const signUpWithEmail = async (email: string, password: string) => {
    setError(null);
    try {
      const client = await getAuthClient();
      await client.auth.signUp({ email, password });
    } catch (err: any) {
      const msg = _friendlyAuthError(err?.message || String(err));
      setError(msg);
      throw new Error(msg);
    }
  };

  // ── Sign out ─────────────────────────────────────────────────────────────────
  const signOut = async () => {
    setError(null);
    try {
      const client = await getAuthClient();
      await client.auth.signOut();
    } catch (err: any) {
      console.warn('[useAuth] sign-out error:', err?.message);
    }
  };

  return {
    user,
    isLoading,
    isAuthenticated,
    authError,
    /** true when the app is running in a browser (web) */
    isWeb: Platform.OS === 'web',
    signInWithGoogle,
    signInWithEmail,
    signUpWithEmail,
    signOut,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _friendlyAuthError(raw: string): string {
  if (!raw) return 'Authentication failed. Please try again.';
  const r = raw.toLowerCase();
  if (r.includes('auth proxy') || r.includes('proxy unavailable'))
    return 'Auth service temporarily unavailable. Please try again in a moment.';
  if (r.includes('invalid credential') || r.includes('wrong password') || r.includes('invalid_credentials'))
    return 'Incorrect email or password.';
  if (r.includes('user not found') || r.includes('no user'))
    return 'No account found with this email. Try creating one.';
  if (r.includes('email already') || r.includes('already in use'))
    return 'An account with this email already exists. Sign in instead.';
  if (r.includes('weak password') || r.includes('password should'))
    return 'Password is too weak. Use at least 8 characters.';
  if (r.includes('network') || r.includes('fetch'))
    return 'Network error. Please check your connection and try again.';
  return raw.length < 120 ? raw : 'Authentication failed. Please try again.';
}
