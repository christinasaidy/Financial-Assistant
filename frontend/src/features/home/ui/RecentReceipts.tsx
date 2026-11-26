import { StyleSheet, View } from 'react-native';

import { colors } from '@/shared/theme';
import { AppText, DashedLine, Icon, TextLink } from '@/shared/ui';

import { receiptSubline } from '../domain/rules';
import type { RecentReceipt } from '../domain/types';
import { receiptAmount, receiptApproxUsd, receiptDay } from './homeText';

type Props = {
  receipts: RecentReceipt[];
  onSeeAll: () => void;
};

/**
 * RECENT RECEIPTS on the grey background (DESIGN.md §4): a cap heading with "See all", a 1 px ink rule, and
 * rows with the date block, the shop over "Groceries · 9 items", and the amount (≈ dollars under pounds),
 * dashed rules between them. With no receipts: the dashed box of screen 04.
 */
export function RecentReceipts({ receipts, onSeeAll }: Props) {
  if (receipts.length === 0) {
    return (
      <View style={styles.emptyPlace}>
        <AppText cap color="ink" accessibilityRole="header">
          Recent receipts
        </AppText>
        <View style={styles.emptyBox} testID="recent-empty">
          <Icon name="receipts" size={30} color="inkMuted" />
          <View style={styles.emptyText}>
            <AppText weight={500} size={15}>
              No receipts yet
            </AppText>
            <AppText size={13} color="inkMuted">
              Tap Scan below to add your first one.
            </AppText>
          </View>
        </View>
      </View>
    );
  }
  return (
    <View>
      <View style={styles.head}>
        <AppText cap color="ink" accessibilityRole="header">
          Recent receipts
        </AppText>
        <TextLink label="See all" onPress={onSeeAll} align="center" testID="recent-see-all" />
      </View>
      <View style={styles.list}>
        {receipts.map((receipt) => (
          <ReceiptRow key={receipt.id} receipt={receipt} />
        ))}
      </View>
    </View>
  );
}

function ReceiptRow({ receipt }: { receipt: RecentReceipt }) {
  const { day, month } = receiptDay(receipt);
  const sub = receiptSubline(receipt.category, receipt.itemCount);
  const approx = receiptApproxUsd(receipt);
  return (
    <View testID={`recent-${receipt.id}`}>
      <View style={styles.row}>
        <View style={styles.date}>
          <AppText font="mono" weight={500} size={18} style={styles.day}>
            {day}
          </AppText>
          <AppText cap size={9.5}>
            {month}
          </AppText>
        </View>
        <View style={styles.middle}>
          <AppText weight={500} size={15} numberOfLines={1}>
            {receipt.shopName ?? 'Receipt'}
          </AppText>
          {sub ? (
            <AppText size={12.5} color="inkMuted" numberOfLines={1}>
              {sub}
            </AppText>
          ) : null}
        </View>
        <View style={styles.amount}>
          <AppText font="mono" weight={500} size={15}>
            {receiptAmount(receipt)}
          </AppText>
          {approx ? (
            <AppText font="mono" size={11.5} color="inkMuted">
              {approx}
            </AppText>
          ) : null}
        </View>
      </View>
      <DashedLine color="dashedBg" />
    </View>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, marginHorizontal: 20, marginBottom: 2, minHeight: 36 },
  list: { marginHorizontal: 20, borderTopWidth: 1, borderTopColor: colors.ink },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 58 },
  date: { width: 36, alignItems: 'center', gap: 3 },
  day: { lineHeight: 18 },
  middle: { flex: 1, minWidth: 0, gap: 3 },
  amount: { alignItems: 'flex-end', gap: 3 },
  emptyPlace: { marginTop: 18, marginHorizontal: 20 },
  emptyBox: {
    marginTop: 10,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.dashedBg,
    borderRadius: 6,
    paddingVertical: 20,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  emptyText: { flex: 1, gap: 3 },
});
