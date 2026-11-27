import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { monthName } from '@/shared/format/dates';
import { colors, fonts, radius, touchTarget } from '@/shared/theme';
import { AppText, Chip, DoubleRule, LineIcon, PaperSheet, ReceiptRow, TextLink, type LineIconName } from '@/shared/ui';

import type { ReceiptsService } from '../application/receiptsService';
import { filterReceipts, filtersFor, groupReceipts, sameFilter, type Filter, type ReceiptMonth } from '../domain';
import { dayBlock, errorSentence, listAmount, listApprox, listSubline, monthTitle, totalOrShown } from './receiptsText';
import { useReceiptMonth, useReceiptsService } from './useReceipts';

type Props = {
  service?: ReceiptsService;
  /** Today, for "This week" and the current month; tests fix it. */
  today?: () => Date;
};

/** The roll's shadow (design/reference/13). */
const ROLL_SHADOW = {
  shadowColor: 'rgb(40,35,25)',
  shadowOpacity: 0.14,
  shadowRadius: 14,
  shadowOffset: { width: 0, height: 10 },
} as const;

/**
 * The Receipts tab (design/screens/13-receipts.png): title with search and month buttons, the month and its
 * total, filter chips, and one long creased roll of receipts grouped by week, ending with the month before.
 * Search and the month switcher are simple versions built from the design's parts (D050).
 */
export function ReceiptsScreen({ service, today = () => new Date() }: Props) {
  const receipts = useReceiptMonth(useReceiptsService(service), today);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [filter, setFilter] = useState<Filter>({ key: 'all' });
  const [search, setSearch] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const now = today();
  const current = receipts.month.getFullYear() === now.getFullYear() && receipts.month.getMonth() === now.getMonth();

  const changeMonth = (by: number) => {
    setFilter({ key: 'all' });
    if (by < 0) receipts.previous();
    else receipts.next();
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: insets.top }]} keyboardShouldPersistTaps="handled" testID="receipts-scroll">
        <View style={styles.header}>
          <AppText weight={600} size={20} tracking={-0.01} accessibilityRole="header">
            Receipts
          </AppText>
          <View style={styles.row}>
            <IconButton icon="search" label="Search receipts" active={search !== null} onPress={() => setSearch((value) => (value === null ? '' : null))} />
            <IconButton icon="calendar" label="Change month" active={switching} onPress={() => setSwitching((value) => !value)} />
          </View>
        </View>

        {search !== null ? (
          <View style={styles.search}>
            <TextInput
              value={search}
              onChangeText={setSearch}
              placeholder="Search shops and categories"
              placeholderTextColor={colors.placeholder}
              selectionColor={colors.cobalt}
              accessibilityLabel="Search shops and categories"
              autoFocus
              returnKeyType="search"
              style={styles.searchInput}
            />
          </View>
        ) : null}

        {switching ? (
          <View style={styles.switcher}>
            <IconButton icon="chevronLeft" label="Previous month" onPress={() => changeMonth(-1)} size={18} />
            <AppText font="mono" weight={500} size={13}>
              {monthTitle(receipts.month)}
            </AppText>
            <IconButton icon="chevronRight" label="Next month" onPress={() => changeMonth(1)} size={18} disabled={current} />
          </View>
        ) : null}

        {receipts.state.status === 'loading' ? <ActivityIndicator style={styles.message} color={colors.inkMuted} accessibilityLabel="Loading" /> : null}
        {receipts.state.status === 'failed' ? (
          <View style={styles.message}>
            <AppText size={14} color="inkMuted">
              {errorSentence(receipts.state.error, 'load')}
            </AppText>
            <TextLink label="Try again" onPress={receipts.retry} />
          </View>
        ) : null}
        {receipts.state.status === 'loaded' ? (
          <MonthRoll
            data={receipts.state.data}
            filter={filter}
            onFilter={setFilter}
            search={search ?? ''}
            today={now}
            onOpen={(id) => router.navigate({ pathname: '/receipt/[id]', params: { id: String(id) } })}
            onOlder={() => changeMonth(-1)}
          />
        ) : null}
      </ScrollView>
    </View>
  );
}

function IconButton({
  icon,
  label,
  onPress,
  active = false,
  disabled = false,
  size = 20,
}: {
  icon: LineIconName;
  label: string;
  onPress: () => void;
  active?: boolean;
  disabled?: boolean;
  size?: number;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled, expanded: active || undefined }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.iconButton, active ? styles.iconActive : null, disabled ? styles.disabled : null]}
    >
      <LineIcon name={icon} size={size} />
    </Pressable>
  );
}

type RollProps = {
  data: ReceiptMonth;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  search: string;
  today: Date;
  onOpen: (id: number) => void;
  onOlder: () => void;
};

function MonthRoll({ data, filter, onFilter, search, today, onOpen, onOlder }: RollProps) {
  const filters = filtersFor(data.receipts);
  const shown = filterReceipts(data.receipts, filter, search);
  const narrowed = filter.key !== 'all' || search.trim() !== '';
  const groups = groupReceipts(shown, monthName(data.month), today);
  const before = new Date(data.month.getFullYear(), data.month.getMonth() - 1, 1);
  const empty =
    data.receipts.length === 0
      ? `No receipts in ${monthName(data.month)} yet. Tap Scan to add one.`
      : search.trim()
        ? `No receipts match “${search.trim()}”.`
        : 'No receipts in this category yet.';

  return (
    <>
      <View style={styles.totalRow}>
        <AppText cap color="ink">
          {monthTitle(data.month)}
        </AppText>
        <AppText font="mono" size={13} color="inkSoft" testID="receipts-total">
          {totalOrShown(data.total, narrowed ? shown.length : null)}
        </AppText>
      </View>

      {data.receipts.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
          {filters.map((item) => (
            <Chip
              key={item.key === 'category' ? `c${item.id}` : item.key}
              compact
              label={item.key === 'all' ? 'All' : item.key === 'other' ? 'Other' : item.name}
              selected={sameFilter(item, filter)}
              onPress={() => onFilter(item)}
            />
          ))}
        </ScrollView>
      ) : (
        <View style={styles.chipsSpace} />
      )}

      <PaperSheet tear={null} shadow={ROLL_SHADOW} outerStyle={styles.rollPlace} style={styles.roll} testID="receipts-roll">
        {groups.length === 0 ? (
          <AppText size={15} color="inkSoft" style={styles.empty}>
            {empty}
          </AppText>
        ) : (
          groups.map((group) => (
            <View key={group.title}>
              <AppText cap style={styles.groupTitle}>
                {group.title}
              </AppText>
              {group.receipts.map((receipt) => {
                const { day, month } = dayBlock(receipt.receiptDate);
                return (
                  <ReceiptRow
                    key={receipt.id}
                    on="paper"
                    day={day}
                    month={month}
                    name={receipt.shopName ?? 'Receipt'}
                    sub={listSubline(receipt)}
                    amount={listAmount(receipt)}
                    approx={listApprox(receipt)}
                    onPress={() => onOpen(receipt.id)}
                    testID={`receipt-${receipt.id}`}
                  />
                );
              })}
            </View>
          ))
        )}
        {data.hasOlder ? (
          <View style={styles.older}>
            <DoubleRule />
            <Pressable accessibilityRole="link" accessibilityLabel={`Older receipts, ${monthTitle(before)}`} onPress={onOlder} style={styles.olderRow} testID="older-receipts">
              <AppText cap color="ink">
                {monthTitle(before)}
              </AppText>
              <AppText weight={500} size={14} color="cobalt">
                Older receipts →
              </AppText>
            </Pressable>
          </View>
        ) : (
          <View style={styles.rollEnd} />
        )}
      </PaperSheet>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { flexGrow: 1, paddingBottom: 14 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, paddingRight: 8, paddingLeft: 20 },
  row: { flexDirection: 'row' },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  iconActive: { backgroundColor: colors.segmentTrack },
  disabled: { opacity: 0.35 },
  search: { marginTop: 6, marginHorizontal: 16 },
  searchInput: {
    minHeight: 44,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.inputBorder,
    borderRadius: radius.input,
    backgroundColor: colors.paperClean,
    fontFamily: fonts.sans.regular,
    fontSize: 16,
    color: colors.ink,
  },
  switcher: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  message: { marginTop: 14, marginHorizontal: 20, gap: 8 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 6, marginHorizontal: 20 },
  // A horizontal row inside the page's scroll: it must not grow with the page.
  chipRow: { flexGrow: 0 },
  chips: { gap: 8, paddingTop: 12, paddingHorizontal: 16, paddingBottom: 14, alignItems: 'center' },
  chipsSpace: { height: 14 },
  rollPlace: { flexGrow: 1, marginHorizontal: 14 },
  roll: { flexGrow: 1, paddingTop: 4, paddingHorizontal: 16 },
  groupTitle: { paddingTop: 16, paddingBottom: 10 },
  empty: { paddingVertical: 20 },
  older: { marginTop: 6 },
  olderRow: { minHeight: 52, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rollEnd: { height: 16 },
});
