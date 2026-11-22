import { Stack } from 'expo-router';

import { useTheme } from '@/shared/theme';

/** The signed-out screens: sign in and create account (D040). */
export default function AuthLayout() {
  const { colors } = useTheme();
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }} />;
}
