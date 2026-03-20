import { useState, useEffect } from 'react';
import { blink } from '@/lib/blink';

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string;
  photoURL?: string;
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const unsubscribe = blink.auth.onAuthStateChanged((state) => {
      setUser(state.user as AuthUser | null);
      setIsAuthenticated(state.isAuthenticated);
      setIsLoading(state.isLoading);
    });
    return unsubscribe;
  }, []);

  const signInWithGoogle = async () => {
    try {
      await blink.auth.signInWithGoogle();
    } catch (err: any) {
      console.error('Google sign-in error:', err?.message || err);
      throw err;
    }
  };

  const signOut = async () => {
    try {
      await blink.auth.signOut();
    } catch (err) {
      console.error('Sign-out error:', err);
    }
  };

  return { user, isLoading, isAuthenticated, signInWithGoogle, signOut };
}
