import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { spacing } from '../theme';
import { AppText } from './AppText';
import { Paper } from './Paper';

type Props = {
  /** The screen's name, normal case ("Receipts"). */
  title: string;
  /** The feature folder that will replace this placeholder (shown, so nobody mistakes it for a design). */
  owner: string;
  children?: ReactNode;
};

/**
 * TEMPORARY. Stands in for a screen that is not built yet, so the routes and the tab bar can be tried.
 * Each feature replaces its placeholder with its own screen from src/features/<feature>/ui.
 */
export function PlaceholderScreen({ title, owner, children }: Props) {
  const insets = useSafeAreaInsets();
  return (
    <Paper variant="creased">
      <View style={[styles.content, { paddingTop: insets.top + spacing.xl }]}>
        <AppText variant="screen-title" accessibilityRole="header">
          {title}
        </AppText>
        <AppText variant="sentence" color="ink-2">
          This screen is not built yet.
        </AppText>
        <AppText variant="caption">To do: src/features/{owner}</AppText>
        {children}
      </View>
    </Paper>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing['screen-margin'], gap: spacing.sm },
});
