import { Stack } from 'expo-router';

import { colors } from '@/shared/theme';

/** The scan flow, a full-screen modal over the tabs: camera, reading, review, filed. */
export default function ScanLayout() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />;
}
