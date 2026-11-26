import { StyleSheet, View } from 'react-native';

import { colors } from '@/shared/theme';
import { AppText, Icon, ReceiptRow, TextLink } from '@/shared/ui';

import { receiptSubline } from '../domain/rules';
import type { RecentReceipt } from '../domain/types';
import { receiptAmount, receiptApproxUsd, receiptDay } from './homeText';

type Props = {
  receipts: RecentReceipt[];
  onSeeAll: () => void;
  /** Opens a receipt's page. */
  onOpen: (id: number) => void;
};

/**
 * RECENT RECEIPTS on the grey background (DESIGN.md §4): a cap heading with "See all", a 1 px ink rule, and
 * rows with the date block, the shop over "Groceries · 9 items", and the amount (≈ dollars under pounds),
 * dashed rules between them. With no receipts: the dashed box of screen 04.
 */
export function RecentReceipts({ receipts, onSeeAll, onOpen }: Props) {
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
          <Row key={receipt.id} receipt={receipt} onOpen={onOpen} />
        ))}
      </View>
    </View>
  );
}

function Row({ receipt, onOpen }: { receipt: RecentReceipt; onOpen: (id: number) => void }) {
  const { day, month } = receiptDay(receipt);
  return (
    <ReceiptRow
      on="bg"
      day={day}
      month={month}
      name={receipt.shopName ?? 'Receipt'}
      sub={receiptSubline(receipt.category, receipt.itemCount)}
      amount={receiptAmount(receipt)}
      approx={receiptApproxUsd(receipt)}
      onPress={() => onOpen(receipt.id)}
      testID={`recent-${receipt.id}`}
    />
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, marginHorizontal: 20, marginBottom: 2, minHeight: 36 },
  list: { marginHorizontal: 20, borderTopWidth: 1, borderTopColor: colors.ink },
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
