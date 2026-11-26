import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { SessionProvider, useSession } from '@/features/auth/ui/SessionProvider';
import { colors, fonts } from '@/shared/theme';

// Keep the native splash up until the fonts are ready, so no text flashes in the system font.
void SplashScreen.preventAutoHideAsync();

/**
 * Geist, Geist Mono (400, 500, 600) and Noto Naskh Arabic (600, 700), DESIGN.md §2. Only the weights the
 * design uses are bundled; the names are the ones design/theme.ts gives.
 */
const fontFiles = {
  [fonts.sans.regular]: require('@expo-google-fonts/geist/400Regular/Geist_400Regular.ttf'),
  [fonts.sans.medium]: require('@expo-google-fonts/geist/500Medium/Geist_500Medium.ttf'),
  [fonts.sans.semibold]: require('@expo-google-fonts/geist/600SemiBold/Geist_600SemiBold.ttf'),
  [fonts.mono.regular]: require('@expo-google-fonts/geist-mono/400Regular/GeistMono_400Regular.ttf'),
  [fonts.mono.medium]: require('@expo-google-fonts/geist-mono/500Medium/GeistMono_500Medium.ttf'),
  [fonts.mono.semibold]: require('@expo-google-fonts/geist-mono/600SemiBold/GeistMono_600SemiBold.ttf'),
  [fonts.arabic.semibold]: require('@expo-google-fonts/noto-naskh-arabic/600SemiBold/NotoNaskhArabic_600SemiBold.ttf'),
  [fonts.arabic.bold]: require('@expo-google-fonts/noto-naskh-arabic/700Bold/NotoNaskhArabic_700Bold.ttf'),
};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fontFiles);
  const ready = fontsLoaded || fontError !== null;

  useEffect(() => {
    if (ready) SplashScreen.hide();
  }, [ready]);

  if (!ready) return null;

  return (
    <SessionProvider>
      {/* Light only (D044): dark status-bar text everywhere. */}
      <StatusBar style="dark" />
      <Routes />
    </SessionProvider>
  );
}

/**
 * Who may see which routes. While the saved session is checked, only the launch route (index) exists.
 * Signed out: the (auth) screens. Signed in: the (tabs), settings pushed over them from the account button,
 * and the budget form as a sheet over Budgets.
 * When the session ends (sign out, or a 401), the signed-in routes disappear and the router goes back to
 * index, which sends the user to sign in.
 */
function Routes() {
  const { status } = useSession();
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={status === 'signedOut'}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Protected guard={status === 'signedIn'}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="settings" />
        <Stack.Screen name="budget-form" options={{ presentation: 'modal' }} />
      </Stack.Protected>
    </Stack>
  );
}
