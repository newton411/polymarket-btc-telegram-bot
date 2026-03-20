import { useState, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { getBlinkClient } from '@/lib/blink';

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string;
  photoURL?: string;
}

export function useAuth() {
  const [user, setUser]                   = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading]         = useState(true);
  const [isAuthenticated, setIsAuth]      = useState(false);
  const [authError, setAuthError]         = useState<string | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let mounted = true;

    getBlinkClient().then((client) => {
      if (!mounted) return;
      unsubRef.current = client.auth.onAuthStateChanged((state: any) => {
        if (!mounted) return;
        setUser(state.user as AuthUser | null);
        setIsAuth(!!state.isAuthenticated);
        setIsLoading(!!state.isLoading);
      });
    });

    return () => {
      mounted = false;
      unsubRef.current?.();
    };
  }, []);

  // ── Google OAuth: only works on native (no iframe popup restrictions) ──────
  const signInWithGoogle = async () => {
    if (Platform.OS === 'web') {
      setAuthError('Google sign-in is not available in the web preview. Please use email + password.');
      throw new Error('Google OAuth unavailable on web');
    }
    setAuthError(null);
    try {
      const client = await getBlinkClient();
      await client.auth.signInWithGoogle();
    } catch (err: any) {
      const msg = err?.message || String(err);
      console.error('Google sign-in error:', msg);
      setAuthError(msg);
      throw err;
    }
  };

  // ── Email/password: works everywhere ─────────────────────────────────────
  const signInWithEmail = async (email: string, password: string) => {
    setAuthError(null);
    try {
      const client = await getBlinkClient();
      await client.auth.signInWithEmail(email, password);
    } catch (err: any) {
      const msg = err?.message || String(err);
      setAuthError(msg);
      throw err;
    }
  };

  const signUpWithEmail = async (email: string, password: string, displayName?: string) => {
    setAuthError(null);
    try {
      const client = await getBlinkClient();
      await client.auth.signUp({ email, password, displayName });
    } catch (err: any) {
      const msg = err?.message || String(err);
      setAuthError(msg);
      throw err;
    }
  };

  const signOut = async () => {
    try {
      const client = await getBlinkClient();
      await client.auth.signOut();
    } catch (err) {
      console.error('Sign-out error:', err);
    }
  };

  return {
    user,
    isLoading,
    isAuthenticated,
    authError,
    /** true when running in browser — Google OAuth unavailable */
    isWeb: Platform.OS === 'web',
    signInWithGoogle,
    signInWithEmail,
    signUpWithEmail,
    signOut,
  };
}
