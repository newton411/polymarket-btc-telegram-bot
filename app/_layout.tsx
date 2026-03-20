import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BlinkProvider, BlinkAuthProvider } from '@blinkdotnew/react-native';
import { useFrameworkReady } from '@/hooks/useFrameworkReady';

// Create a client for React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

export default function RootLayout() {
  useFrameworkReady();

  return (
    <BlinkProvider projectId={process.env.EXPO_PUBLIC_BLINK_PROJECT_ID!}>
      <BlinkAuthProvider>
        <QueryClientProvider client={queryClient}>
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="+not-found" />
          </Stack>
          <StatusBar style="auto" />
        </QueryClientProvider>
      </BlinkAuthProvider>
    </BlinkProvider>
  );
}