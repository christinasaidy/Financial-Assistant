import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { SessionProvider, useSession } from '@/features/auth/ui/SessionProvider';
import { fontFamilies, useTheme } from '@/shared/theme';

// Keep the native splash up until the fonts are ready, so no text flashes in the system font.
void SplashScreen.preventAutoHideAsync();

/** DejaVu 2.37, Book and Bold of Sans Mono and Sans (D006). Licence: assets/fonts/LICENSE. */
const fonts = {
  [fontFamilies.mono]: require('../assets/fonts/DejaVuSansMono.ttf'),
  [fontFamilies.monoBold]: require('../assets/fonts/DejaVuSansMono-Bold.ttf'),
  [fontFamilies.sans]: require('../assets/fonts/DejaVuSans.ttf'),
  [fontFamilies.sansBold]: require('../assets/fonts/DejaVuSans-Bold.ttf'),
};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fonts);
  const ready = fontsLoaded || fontError !== null;

  useEffect(() => {
    if (ready) SplashScreen.hide();
  }, [ready]);

  if (!ready) return null;

  return (
    <SessionProvider>
      <StatusBar style="auto" />
      <Routes />
    </SessionProvider>
  );
}

/**
 * Who may see which routes. While the saved session is checked, only the launch route (index) exists.
 * Signed out: the (auth) screens. Signed in: the (tabs). When the session ends (sign out, or a 401), the
 * (tabs) disappear and the router goes back to index, which sends the user to sign in.
 */
function Routes() {
  const { status } = useSession();
  const { colors } = useTheme();
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={status === 'signedOut'}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Protected guard={status === 'signedIn'}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
    </Stack>
  );
}
