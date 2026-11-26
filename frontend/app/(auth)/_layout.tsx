import { Stack } from 'expo-router';

import { colors } from '@/shared/theme';

/** The signed-out screens: sign in and create account. */
export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />;
}
