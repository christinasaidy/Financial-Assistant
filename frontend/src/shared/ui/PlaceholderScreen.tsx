import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '../theme';
import { AppText } from './AppText';

type Props = {
  /** The screen's name ("Receipts"). */
  title: string;
  /** The feature folder that will replace this placeholder (shown, so nobody mistakes it for a design). */
  owner: string;
  children?: ReactNode;
};

/**
 * TEMPORARY. Stands in for a screen that is not built yet, so the routes and the tab bar can be tried.
 * The title is the screen title of DESIGN.md (Geist 600 20) on the grey background.
 */
export function PlaceholderScreen({ title, owner, children }: Props) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.screen, { paddingTop: insets.top + 14 }]}>
      <AppText weight={600} size={20} tracking={-0.01} accessibilityRole="header">
        {title}
      </AppText>
      <AppText size={15} color="inkMuted">
        This screen is not built yet.
      </AppText>
      <AppText font="mono" size={12} color="inkMuted">
        To do: src/features/{owner}
      </AppText>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, paddingHorizontal: 20, gap: 8 },
});
