import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '@/shared/theme';
import { AppText, Button, DoubleRule, LineIcon, PaperSheet, TextLink } from '@/shared/ui';

import type { ScanService } from '../application/scanService';
import type { Filed } from '../domain';
import { useScanService } from './ReadingScreen';
import { cell, filedCaps, limitCell, money, scanErrorSentence } from './scanText';

type Props = { service?: ScanService };

/**
 * Filed (design/screens/12-scan-filed.png): a cobalt check, "Filed under Groceries", the receipt in one sentence,
 * and a mini invoice of the change: the category's row with its old value struck through, the new part of the
 * bar in cobalt, "+38.40 from this receipt" and what is left; the old total struck through and the new one.
 */
export function FiledScreen({ service }: Props) {
  const scan = useScanService(service);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const [filed, setFiled] = useState<Filed | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    scan
      .filed(id)
      .then((result) => active && setFiled(result))
      .catch((caught: unknown) => active && setError(scanErrorSentence(caught)));
    return () => {
      active = false;
    };
  }, [scan, id]);

  const done = () => router.dismissTo('/(tabs)');

  return (
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom }]} testID="scan-filed">
      {!filed && !error ? <ActivityIndicator style={styles.loading} color={colors.inkMuted} accessibilityLabel="Loading" /> : null}
      {error ? (
        <View style={styles.head}>
          <AppText size={15} color="inkSoft" style={styles.center}>
            The receipt is saved, but its summary could not load. {error}
          </AppText>
        </View>
      ) : null}
      {filed ? <FiledBody filed={filed} onView={() => router.push({ pathname: '/receipt/[id]', params: { id: String(id) } })} /> : null}

      <View style={styles.buttons}>
        <View style={styles.half}>
          <Button kind="secondary" label="Scan another" onPress={() => router.dismissTo('/scan')} />
        </View>
        <View style={styles.half}>
          <Button label="Done" onPress={done} />
        </View>
      </View>
    </View>
  );
}

function FiledBody({ filed, onView }: { filed: Filed; onView: () => void }) {
  const { receipt, budget, category } = filed;
  const own = receipt.currency ?? 'USD';
  const caps = filedCaps(filed.invoiceNumber, filed.month);
  const currency = budget?.currency ?? own;
  const limit = budget ? Number.parseFloat(budget.limit) || 0 : 0;
  const share = (value: number) => (limit > 0 ? Math.min(Math.max((value / limit) * 100, 0), 100) : 0);
  const left = budget ? limit - budget.after : 0;
  return (
    <>
      <View style={styles.head}>
        <View style={styles.badge}>
          <LineIcon name="check" size={28} color="white" />
        </View>
        <AppText weight={600} size={26} tracking={-0.02} accessibilityRole="header" style={styles.title}>
          {category ? `Filed under ${category}` : 'Filed'}
        </AppText>
        <AppText size={15} color="inkSoft" style={styles.center}>
          {receipt.shopName ?? 'The receipt'},{' '}
          <AppText font="mono" size={15}>
            {receipt.total ? money(receipt.total, own) : ''}
          </AppText>
          , added to this month’s invoice.
        </AppText>
      </View>

      <PaperSheet on="bg" outerStyle={styles.sheetPlace} style={styles.sheet} testID="filed-invoice">
        <View style={styles.between}>
          <AppText cap color="cobalt">
            {caps.invoice}
          </AppText>
          <AppText cap>{caps.month}</AppText>
        </View>
        <View style={styles.change}>
          <View style={[styles.between, styles.baseline]}>
            <AppText weight={600} size={15}>
              {category ?? 'Everything else'}
            </AppText>
            <AppText font="mono" size={15}>
              {budget ? (
                <>
                  <AppText font="mono" size={13} color="struck" style={styles.struck}>
                    {cell(budget.before, currency)}
                  </AppText>
                  {`  ${cell(budget.after, currency)} `}
                  <AppText font="mono" size={15} color="inkSoft">
                    / {limitCell(budget.limit, currency)}
                  </AppText>
                </>
              ) : (
                cell(filed.added, currency)
              )}
            </AppText>
          </View>
          {budget ? (
            <View style={styles.track}>
              <View style={[styles.part, { left: 0, width: `${share(budget.before)}%`, backgroundColor: colors.ink }]} />
              <View style={[styles.part, { left: `${share(budget.before)}%`, width: `${share(budget.after) - share(budget.before)}%`, backgroundColor: colors.cobalt }]} />
            </View>
          ) : null}
          <View style={[styles.between, styles.changeFoot]}>
            <AppText size={12.5} color="noteText">
              <AppText font="mono" weight={600} size={12.5} color="cobalt">
                +{cell(filed.added, currency)}
              </AppText>{' '}
              from this receipt
            </AppText>
            {budget ? (
              <AppText font="mono" size={12.5} color={left < 0 ? 'redText' : 'noteText'}>
                {left < 0 ? `${cell(-left, currency)} over` : `${cell(left, currency)} left`}
              </AppText>
            ) : null}
          </View>
        </View>
        <DoubleRule style={styles.double} />
        <View style={styles.totalRow}>
          <AppText cap color="ink">
            Total
          </AppText>
          <AppText font="mono" weight={600} size={17}>
            <AppText font="mono" size={13} color="struck" style={styles.struck}>
              {cell(filed.totalBefore, 'USD')}
            </AppText>
            {`  ${money(filed.totalAfter, 'USD')}`}
          </AppText>
        </View>
      </PaperSheet>

      <View style={styles.view}>
        <TextLink label="View receipt" onPress={onView} align="center" testID="view-receipt" />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  loading: { marginTop: 96 },
  head: { marginTop: 96, alignItems: 'center', paddingHorizontal: 28 },
  badge: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.cobalt, alignItems: 'center', justifyContent: 'center' },
  title: { marginTop: 18, marginBottom: 6, textAlign: 'center' },
  center: { textAlign: 'center', lineHeight: 21.75 },
  sheetPlace: { marginTop: 30, marginHorizontal: 14 },
  sheet: { paddingTop: 14, paddingHorizontal: 16, paddingBottom: 22 },
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  baseline: { alignItems: 'baseline', gap: 8 },
  change: {
    marginTop: 14,
    marginHorizontal: -10,
    paddingVertical: 12,
    paddingHorizontal: 10,
    backgroundColor: colors.cobaltTint,
    borderTopWidth: 1,
    borderTopColor: colors.ink,
  },
  struck: { textDecorationLine: 'line-through' },
  track: { height: 4, marginTop: 10, backgroundColor: colors.barTrack },
  part: { position: 'absolute', top: 0, height: 4 },
  changeFoot: { marginTop: 7 },
  double: { marginTop: 12 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 9 },
  view: { alignItems: 'center', marginTop: 16, minHeight: 44, justifyContent: 'center' },
  buttons: { flexDirection: 'row', gap: 10, marginTop: 'auto', marginHorizontal: 16, marginBottom: 30 },
  half: { flex: 1 },
});
