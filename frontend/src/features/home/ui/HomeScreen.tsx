import { useRouter } from 'expo-router';
import type { ReactNode } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { spacing, useTheme } from '@/shared/theme';
import { AppText, DashedRule, Paper, TextLink } from '@/shared/ui';

import type { HomeService } from '../application/homeService';
import type { HomeError } from '../domain/errors';
import { greeting, isMonthEmpty } from '../domain/rules';
import type { HomeOverview } from '../domain/types';
import { BudgetsSection } from './BudgetsSection';
import { HomeHeader } from './HomeHeader';
import { MonthSection, ScanPrompt } from './MonthSection';
import { RecentSection } from './RecentSection';
import { useHomeOverview, useHomeService } from './useHomeOverview';

type Props = {
  /** Defaults to the app's HomeService from the container; tests pass one built on a fake. */
  service?: HomeService;
};

/**
 * Home (D035-D037, D042), on plain paper: the header, "Hello, <first name>", this month's total,
 * the budgets closest to their limit and the newest receipts. Each part shows its own empty state, so a
 * user with receipts but no budgets sees both. Pull down to reload; it also reloads when the tab comes back.
 */
export function HomeScreen({ service }: Props) {
  const home = useHomeOverview(useHomeService(service));
  const { user } = useSession();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { state } = home;

  const openBudgets = () => router.navigate('/budgets');
  const openScan = () => router.navigate('/scan');

  return (
    <Paper variant="plain">
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top }]}
        refreshControl={
          <RefreshControl refreshing={home.refreshing} onRefresh={home.refresh} tintColor={colors['ink-2']} />
        }
        testID="home-scroll"
      >
        <HomeHeader />
        <View style={styles.main}>
          <AppText variant="screen-title" accessibilityRole="header">
            {greeting(user?.firstName)}
          </AppText>
          {state.status === 'loading' ? <AppText variant="caption">Loading…</AppText> : null}
          {state.status === 'failed' ? <LoadError error={state.error} onRetry={home.retry} /> : null}
          {state.status === 'loaded' ? (
            <>
              {state.refreshError ? <LoadError error={state.refreshError} onRetry={home.retry} /> : null}
              <Overview overview={state.overview} onOpenBudgets={openBudgets} onScan={openScan} />
            </>
          ) : null}
        </View>
      </ScrollView>
    </Paper>
  );
}

function Overview({
  overview,
  onOpenBudgets,
  onScan,
}: {
  overview: HomeOverview;
  onOpenBudgets: () => void;
  onScan: () => void;
}) {
  const sections: ReactNode[] = [
    <MonthSection key="month" spending={overview.spending} />,
    isMonthEmpty(overview.spending) ? <ScanPrompt key="scan" onScan={onScan} /> : null,
    <BudgetsSection key="budgets" budgets={overview.budgets} onOpenBudgets={onOpenBudgets} />,
    <RecentSection key="recent" receipts={overview.recent} />,
  ].filter(Boolean);
  // Sections are separated by a dashed rule with 24 px above and below (D031, D032): the main column's gap.
  return sections.flatMap((section, index) =>
    index === 0 ? [section] : [<DashedRule key={`rule-${index}`} />, section],
  );
}

/** A plain, specific sentence and TRY AGAIN. Loading and error looks are not designed yet (README). */
function LoadError({ error, onRetry }: { error: HomeError; onRetry: () => void }) {
  const sentence =
    error.code === 'network'
      ? 'Fatourati could not reach the server, so this month’s spending is not shown. Check the connection.'
      : 'The server could not send this month’s spending.';
  return (
    <View style={styles.error} testID="home-error">
      <AppText variant="sentence">{sentence}</AppText>
      <TextLink label="Try again" onPress={onRetry} testID="home-try-again" />
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingBottom: spacing.xl },
  main: {
    paddingTop: spacing.lg,
    paddingHorizontal: spacing['screen-margin'],
    gap: spacing.xl,
  },
  error: { gap: spacing.sm },
});
