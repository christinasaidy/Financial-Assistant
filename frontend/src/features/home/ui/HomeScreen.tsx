import { useRouter } from 'expo-router';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { colors } from '@/shared/theme';
import { AppText, TextLink, useScanHint } from '@/shared/ui';

import type { HomeService } from '../application/homeService';
import type { HomeError } from '../domain/errors';
import { isMonthEmpty } from '../domain/rules';
import { HomeHeader } from './HomeHeader';
import { InvoiceSheet } from './InvoiceSheet';
import { RecentReceipts } from './RecentReceipts';
import { useHomeOverview, useHomeService } from './useHomeOverview';

type Props = {
  /** Defaults to the app's HomeService from the container; tests pass one built on a fake. */
  service?: HomeService;
};

/**
 * Home (design/screens/03-home.png and 04-home-empty.png): the header, this month's invoice and the recent
 * receipts, on the grey background. A month with nothing in it is the blank invoice, and Scan wears its faint
 * ring. Pull down to reload; it also reloads when the tab comes back.
 */
export function HomeScreen({ service }: Props) {
  const home = useHomeOverview(useHomeService(service));
  const { user } = useSession();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { state } = home;
  useScanHint(state.status === 'loaded' && isMonthEmpty(state.overview.spending));

  return (
    <View style={styles.screen}>
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top }]}
        refreshControl={<RefreshControl refreshing={home.refreshing} onRefresh={home.refresh} tintColor={colors.inkMuted} />}
        testID="home-scroll"
      >
        <HomeHeader />
        {state.status === 'loading' ? (
          <View style={styles.message}>
            <ActivityIndicator color={colors.inkMuted} accessibilityLabel="Loading" />
          </View>
        ) : null}
        {state.status === 'failed' ? <LoadError error={state.error} onRetry={home.retry} /> : null}
        {state.status === 'loaded' ? (
          <>
            {state.refreshError ? <LoadError error={state.refreshError} onRetry={home.retry} /> : null}
            <InvoiceSheet
              overview={state.overview}
              firstName={user?.firstName}
              onNote={() => router.navigate(state.overview.budgets.length > 0 ? '/assistant' : '/budgets')}
            />
            <RecentReceipts
              receipts={state.overview.recent}
              onSeeAll={() => router.navigate('/receipts')}
              onOpen={(id) => router.navigate({ pathname: '/receipt/[id]', params: { id: String(id) } })}
            />
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

/** A plain, specific sentence and "Try again". Loading and error looks are not designed yet (README). */
function LoadError({ error, onRetry }: { error: HomeError; onRetry: () => void }) {
  const sentence =
    error.code === 'network'
      ? 'Fatourati could not reach the server, so this month’s invoice is not shown. Check the connection.'
      : 'The server could not send this month’s invoice.';
  return (
    <View style={styles.message} testID="home-error">
      <AppText size={14} color="inkMuted">
        {sentence}
      </AppText>
      <TextLink label="Try again" onPress={onRetry} testID="home-try-again" />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { paddingBottom: 24 },
  message: { marginTop: 14, marginHorizontal: 20, gap: 8 },
});
