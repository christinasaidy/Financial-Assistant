import { useLocalSearchParams, useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, Share, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { formatMoney } from '@/shared/format/money';
import { colors, radius, touchTarget } from '@/shared/theme';
import { AppText, Button, DashedLine, DoubleRule, LineIcon, PaperSheet, TextLink } from '@/shared/ui';

import type { ReceiptsService } from '../application/receiptsService';
import { categoryName, itemName, quantityLabel, type ReceiptPage } from '../domain';
import { budgetAfter, errorSentence, lineAmount, receiptLabel, receiptWhen, shareText, totalLabel } from './receiptsText';
import { useReceiptPage, useReceiptsService } from './useReceipts';

type Props = { service?: ReceiptsService };

/**
 * A receipt's page (design/screens/05-receipt-detail.png): Back, RECEIPT, share; the creased receipt with its
 * category and date, the shop and total, the ruled ITEM / QTY / AMOUNT table, the total, and how the
 * category's budget stands after it; Change category and Split items at the bottom.
 */
export function ReceiptScreen({ service }: Props) {
  const receipts = useReceiptsService(service);
  const params = useLocalSearchParams<{ id: string }>();
  const id = Number(params.id);
  const page = useReceiptPage(receipts, id);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const loaded = page.state.status === 'loaded' ? page.state.data : null;

  const share = () => {
    if (!loaded) return;
    void Share.share({ message: shareText(loaded.receipt, categoryName(loaded.categories, loaded.receipt.categoryId)) });
  };

  return (
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
      <View style={styles.bar}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} style={styles.iconButton} testID="receipt-back">
          <LineIcon name="back" />
        </Pressable>
        <AppText cap color="ink" accessibilityRole="header">
          Receipt
        </AppText>
        <Pressable accessibilityRole="button" accessibilityLabel="Share receipt" onPress={share} disabled={!loaded} style={styles.iconButton} testID="receipt-share">
          <LineIcon name="share" />
        </Pressable>
      </View>

      {page.state.status === 'loading' ? <ActivityIndicator style={styles.message} color={colors.inkMuted} accessibilityLabel="Loading" /> : null}
      {page.state.status === 'failed' ? (
        <View style={styles.message}>
          <AppText size={14} color="inkMuted">
            {errorSentence(page.state.error, 'load')}
          </AppText>
          <TextLink label="Try again" onPress={page.retry} />
        </View>
      ) : null}
      {loaded ? (
        <>
          <ScrollView style={styles.fill} contentContainerStyle={styles.scroll}>
            <ReceiptSheet page={loaded} />
          </ScrollView>
          <View style={styles.buttons}>
            <View style={styles.half}>
              <Button kind="secondary" label="Change category" onPress={() => router.navigate({ pathname: '/receipt-category', params: { id: String(id) } })} />
            </View>
            <View style={styles.half}>
              <Button label="Split items" onPress={() => router.navigate({ pathname: '/receipt-split', params: { id: String(id) } })} />
            </View>
          </View>
        </>
      ) : null}
    </View>
  );
}

function ReceiptSheet({ page }: { page: ReceiptPage }) {
  const { receipt, categories, budget } = page;
  const category = categoryName(categories, receipt.categoryId);
  const after = budget ? budgetAfter(budget) : null;
  return (
    <PaperSheet on="bg" outerStyle={styles.sheetPlace} style={styles.sheet} testID="receipt-sheet">
      <View style={styles.between}>
        <AppText cap color="cobalt">
          {receiptLabel(category)}
        </AppText>
        <AppText cap>{receiptWhen(receipt)}</AppText>
      </View>
      <View style={styles.head}>
        <AppText weight={600} size={24} tracking={-0.02} style={styles.shop}>
          {receipt.shopName ?? 'Receipt'}
        </AppText>
        {receipt.total && receipt.currency ? (
          <AppText font="mono" weight={500} size={34} tracking={-0.03} style={styles.amount} testID="receipt-total">
            {formatMoney(receipt.total, receipt.currency)}
          </AppText>
        ) : null}
      </View>

      <View style={styles.table}>
        <View style={[styles.tr, styles.headRow]}>
          <View style={styles.itemCell}>
            <AppText cap>Item</AppText>
          </View>
          <View style={[styles.numberCell, styles.qty]}>
            <AppText cap>Qty</AppText>
          </View>
          <View style={[styles.numberCell, styles.amountCol]}>
            <AppText cap>Amount</AppText>
          </View>
        </View>
        {receipt.lines.map((line, index) => {
          const own = line.categoryId !== null && line.categoryId !== receipt.categoryId ? categoryName(categories, line.categoryId) : null;
          return (
            <View key={line.id ?? index} style={[styles.tr, styles.bodyRow]} testID={`line-${index}`}>
              <View style={styles.itemCell}>
                <AppText size={14.5}>{itemName(line)}</AppText>
                {own ? (
                  <AppText cap size={9.5} color="cobalt">
                    {own}
                  </AppText>
                ) : null}
              </View>
              <View style={[styles.numberCell, styles.qty]}>
                <AppText font="mono" size={13} color="inkSoft">
                  {quantityLabel(line)}
                </AppText>
              </View>
              <View style={[styles.numberCell, styles.amountCol]}>
                <AppText font="mono" size={14}>
                  {lineAmount(line.lineTotal, receipt)}
                </AppText>
              </View>
            </View>
          );
        })}
        <DoubleRule style={styles.double} />
        <View style={styles.totalRow}>
          <AppText cap color="ink">
            {totalLabel(receipt)}
          </AppText>
          {receipt.total && receipt.currency ? (
            <AppText font="mono" weight={600} size={17}>
              {formatMoney(receipt.total, receipt.currency)}
            </AppText>
          ) : null}
        </View>
      </View>

      {budget && after ? (
        <View style={styles.budget} testID="budget-after">
          <DashedLine />
          <View style={styles.budgetBody}>
            <View style={[styles.between, styles.baseline]}>
              <AppText weight={500} size={14}>
                {budget.name} after this
              </AppText>
              <AppText font="mono" size={13} color="inkSoft">
                {after.amounts}
              </AppText>
            </View>
            <View style={styles.track}>
              <View style={[styles.fill3, { width: `${after.percent}%`, backgroundColor: after.over ? colors.red : colors.ink }]} />
            </View>
            <AppText font="mono" size={11.5} color={after.over ? 'redText' : 'inkSoft'}>
              {after.left}
            </AppText>
          </View>
        </View>
      ) : null}
    </PaperSheet>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  fill: { flex: 1 },
  scroll: { paddingBottom: 16 },
  bar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 12, paddingHorizontal: 8, paddingBottom: 4 },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  message: { marginTop: 14, marginHorizontal: 20, gap: 8 },
  sheetPlace: { marginTop: 6, marginHorizontal: 14 },
  sheet: { paddingTop: 18, paddingHorizontal: 18, paddingBottom: 24 },
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  baseline: { alignItems: 'baseline' },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12, marginTop: 14 },
  shop: { flexShrink: 1, lineHeight: 26.5 },
  amount: { lineHeight: 36 },
  table: { marginTop: 16, borderTopWidth: 1, borderTopColor: colors.ink },
  tr: { flexDirection: 'row' },
  headRow: { minHeight: 28 },
  bodyRow: { minHeight: 34, borderTopWidth: 1, borderTopColor: colors.ruleSoft },
  itemCell: { flex: 1, minWidth: 0, justifyContent: 'center', paddingVertical: 4, paddingRight: 10 },
  numberCell: { justifyContent: 'center', alignItems: 'flex-end', borderLeftWidth: 1, borderLeftColor: colors.ruleSoft, paddingRight: 2 },
  qty: { width: 62 },
  amountCol: { width: 70 },
  double: { marginTop: 2 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 9 },
  budget: { marginTop: 14 },
  budgetBody: { paddingTop: 12, gap: 7 },
  track: { height: 3, backgroundColor: colors.barTrack },
  fill3: { height: 3 },
  buttons: { flexDirection: 'row', gap: 10, marginHorizontal: 16, marginTop: 8, marginBottom: 28 },
  half: { flex: 1 },
});
