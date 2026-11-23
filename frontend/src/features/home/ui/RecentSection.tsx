import { Fragment } from 'react';
import { StyleSheet, View } from 'react-native';

import { spacing } from '@/shared/theme';
import { AppText, DashedRule } from '@/shared/ui';

import type { RecentReceipt } from '../domain/types';
import { receiptMeta, receiptTotal, shopName } from './homeText';

/** RECENT: the newest receipts with dashed rules between them; before any, what will appear (D035-D037). */
export function RecentSection({ receipts }: { receipts: RecentReceipt[] }) {
  return (
    <View style={styles.section}>
      <AppText variant="section-label" accessibilityRole="header">
        Recent
      </AppText>
      {receipts.length === 0 ? (
        <AppText variant="sentence" color="ink-2">
          Receipts you scan show up here, newest first.
        </AppText>
      ) : (
        <View>
          {receipts.map((receipt, index) => (
            <Fragment key={receipt.id}>
              {index > 0 ? <DashedRule /> : null}
              <ReceiptRow receipt={receipt} first={index === 0} last={index === receipts.length - 1} />
            </Fragment>
          ))}
        </View>
      )}
    </View>
  );
}

/** Shop name and total on one line (the name wraps, the total stays right), then date · time · items. */
function ReceiptRow({ receipt, first, last }: { receipt: RecentReceipt; first: boolean; last: boolean }) {
  return (
    <View
      style={[styles.row, !first && styles.notFirst, !last && styles.notLast]}
      accessible
      testID={`home-receipt-${receipt.id}`}
    >
      <View style={styles.line}>
        <AppText variant="shop-name" style={styles.shop}>
          {shopName(receipt)}
        </AppText>
        <AppText variant="total-line" style={styles.total}>
          {receiptTotal(receipt)}
        </AppText>
      </View>
      <AppText variant="meta">{receiptMeta(receipt)}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm },
  row: { gap: spacing.xs },
  notFirst: { paddingTop: spacing.md },
  notLast: { paddingBottom: spacing.md },
  line: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md },
  shop: { flexShrink: 1 },
  total: { flexShrink: 0, textAlign: 'right' },
});
