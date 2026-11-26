import { Pressable, StyleSheet, View, type DimensionValue } from 'react-native';

import { colors } from '@/shared/theme';
import { AppText, DashedLine, DoubleRule, LineIcon, PaperSheet } from '@/shared/ui';

import { barWidthPercent, billedTo, isMonthEmpty, isOver } from '../domain/rules';
import type { BudgetUse, HomeOverview } from '../domain/types';
import { invoiceLabel, invoiceLine, limitCell, monthLabel, monthTotal, olderMonthLabel, remainderText, spentCell } from './homeText';

type Props = {
  overview: HomeOverview;
  firstName: string | null | undefined;
  /** The note: set a first budget (no budgets yet) or ask the assistant. */
  onNote: () => void;
};

/**
 * This month's invoice (DESIGN.md §4, design/reference/03-home.html and 04-home-empty.html): a creased
 * sheet with a torn edge, older months peeking behind it, the number and month, "Billed to", the big total,
 * the ruled BUDGET / LIMIT / SPENT table with "Everything else", the double rule and TOTAL, and the note.
 */
export function InvoiceSheet({ overview, firstName, onNote }: Props) {
  const { spending, budgets, olderMonths } = overview;
  const empty = isMonthEmpty(spending);
  const line = invoiceLine(spending);
  const peeking = olderMonths.length > 0;
  return (
    <View style={[styles.place, peeking ? styles.withPeeks : styles.alone]}>
      {peeking ? <OlderSheets months={olderMonths} /> : null}
      <PaperSheet on="bg" style={styles.sheet} testID="invoice">
        <View style={styles.between}>
          <AppText cap color="cobalt">
            {invoiceLabel(overview.invoiceNumber)}
          </AppText>
          <AppText cap>{monthLabel(spending)}</AppText>
        </View>
        <AppText size={14} color="inkSoft" style={styles.billed}>
          {billedTo(firstName)}
        </AppText>
        <AppText
          font="mono"
          weight={500}
          size={52}
          tracking={-0.04}
          color={empty ? 'zeroAmount' : 'ink'}
          style={styles.total}
          testID="invoice-total"
        >
          {monthTotal(spending)}
        </AppText>
        {line ? (
          <AppText font={line.blank ? 'sans' : 'mono'} size={line.blank ? 13 : 12} color="inkSoft" style={styles.line} testID="invoice-line">
            {line.text}
          </AppText>
        ) : null}

        <View style={styles.table}>
          <View style={[styles.row, styles.headRow]}>
            <View style={styles.nameCell}>
              <AppText cap>Budget</AppText>
            </View>
            <View style={[styles.numberCell, styles.limitCell]}>
              <AppText cap>Limit</AppText>
            </View>
            <View style={[styles.numberCell, styles.spentCell]}>
              <AppText cap>Spent</AppText>
            </View>
          </View>
          {budgets.length === 0 ? (
            <BlankRows />
          ) : (
            <>
              {budgets.map((budget) => (
                <BudgetRow key={budget.categoryId} budget={budget} />
              ))}
              <EverythingElseRow amount={overview.everythingElse} />
            </>
          )}
          <DoubleRule style={styles.double} />
          <View style={styles.totalRow}>
            <AppText cap color="ink">
              Total
            </AppText>
            <AppText font="mono" weight={600} size={17} color={empty ? 'zeroAmount' : 'ink'}>
              {monthTotal(spending)}
            </AppText>
          </View>
        </View>

        <Note hasBudgets={budgets.length > 0} onPress={onNote} />
      </PaperSheet>
    </View>
  );
}

/** Two older months peeking ~30 px above the invoice, rotated −1.6° and +1°, labelled on the right. */
function OlderSheets({ months }: { months: string[] }) {
  const [older, newer] = months;
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants" testID="older-months">
      {older ? (
        <View style={[styles.peek, styles.peekOld]}>
          <AppText cap>{olderMonthLabel(older)}</AppText>
        </View>
      ) : null}
      {newer ? (
        <View style={[styles.peek, styles.peekNew]}>
          <AppText cap>{olderMonthLabel(newer)}</AppText>
        </View>
      ) : null}
    </View>
  );
}

function BudgetRow({ budget }: { budget: BudgetUse }) {
  const over = isOver(budget);
  return (
    <View style={[styles.row, styles.bodyRow]} testID={`budget-${budget.categoryId}`}>
      <View style={styles.nameCell}>
        <AppText weight={500} size={15}>
          {budget.name}
        </AppText>
        <View style={styles.track}>
          <View
            style={[styles.fill, { width: `${barWidthPercent(budget.percentUsed)}%`, backgroundColor: over ? colors.red : colors.ink }]}
            testID={`budget-bar-${budget.categoryId}`}
          />
        </View>
      </View>
      <View style={[styles.numberCell, styles.limitCell]}>
        <AppText font="mono" size={14} color="inkSoft">
          {limitCell(budget)}
        </AppText>
      </View>
      <View style={[styles.numberCell, styles.spentCell]}>
        <AppText font="mono" weight={over ? 500 : 400} size={15} color={over ? 'red' : 'ink'}>
          {spentCell(budget)}
        </AppText>
        <AppText font="mono" size={11} color={over ? 'red' : 'inkSoft'}>
          {remainderText(budget)}
        </AppText>
      </View>
    </View>
  );
}

function EverythingElseRow({ amount }: { amount: string }) {
  return (
    <View style={[styles.row, styles.bodyRow]} testID="everything-else">
      <View style={styles.nameCell}>
        <AppText weight={500} size={15}>
          Everything else
        </AppText>
      </View>
      <View style={[styles.numberCell, styles.limitCell]}>
        <AppText font="mono" size={14} color="inkSoft" accessibilityLabel="No limit">
          —
        </AppText>
      </View>
      <View style={[styles.numberCell, styles.spentCell]}>
        <AppText font="mono" size={15}>
          {amount}
        </AppText>
      </View>
    </View>
  );
}

const BLANK_WIDTHS: DimensionValue[] = ['70%', '52%', '62%'];

/** The blank invoice's three empty rows: dashed placeholder lines in each column (screen 04). */
function BlankRows() {
  return (
    <View accessible accessibilityLabel="No budgets yet" testID="blank-rows">
      {BLANK_WIDTHS.map((width) => (
        <View key={String(width)} style={[styles.row, styles.blankRow]}>
          <View style={styles.nameCell}>
            <DashedLine color="blank" width={1.5} style={{ width }} />
          </View>
          <View style={[styles.numberCell, styles.limitCell, styles.blankNumber]}>
            <DashedLine color="blank" width={1.5} />
          </View>
          <View style={[styles.numberCell, styles.spentCell, styles.blankNumber]}>
            <DashedLine color="blank" width={1.5} />
          </View>
        </View>
      ))}
    </View>
  );
}

/** NOTE in cobalt, the sentence and a cobalt arrow, under a dashed rule. Opens the assistant or Budgets. */
function Note({ hasBudgets, onPress }: { hasBudgets: boolean; onPress: () => void }) {
  return (
    <View style={styles.noteWrap}>
      <DashedLine />
      <Pressable
        accessibilityRole="link"
        accessibilityLabel={hasBudgets ? 'Note: ask me, “addeh sraft 3al akl?”' : 'Note: set your first monthly budget'}
        onPress={onPress}
        style={({ pressed }) => [styles.note, { opacity: pressed ? 0.7 : 1 }]}
        testID="invoice-note"
      >
        <AppText cap color="cobalt">
          Note
        </AppText>
        <AppText size={14} color="noteText" style={styles.noteText}>
          {hasBudgets ? (
            <>
              Ask me —{' '}
              <AppText size={14} weight={500}>
                “addeh sraft 3al akl?”
              </AppText>
            </>
          ) : (
            'Set your first monthly budget'
          )}
        </AppText>
        <LineIcon name="arrow" size={18} color="cobalt" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  place: { marginHorizontal: 14 },
  withPeeks: { marginTop: 4, paddingTop: 30 },
  alone: { marginTop: 14 },
  peek: {
    position: 'absolute',
    height: 60,
    borderRadius: 2,
    alignItems: 'flex-end',
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  peekOld: { top: 0, left: 22, right: 22, backgroundColor: colors.sheetBehind1, transform: [{ rotate: '-1.6deg' }] },
  peekNew: {
    top: 14,
    left: 10,
    right: 10,
    backgroundColor: colors.sheetBehind2,
    transform: [{ rotate: '1deg' }],
    shadowColor: '#000000',
    shadowOpacity: 0.08,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
  },
  sheet: { paddingTop: 16, paddingHorizontal: 18, paddingBottom: 22 },
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  billed: { marginTop: 12 },
  total: { marginTop: 2, lineHeight: 55 },
  line: { marginTop: 4 },
  table: { marginTop: 16, borderTopWidth: 1, borderTopColor: colors.ink },
  row: { flexDirection: 'row' },
  headRow: { minHeight: 28 },
  bodyRow: { minHeight: 46, borderTopWidth: 1, borderTopColor: colors.ruleSoft },
  blankRow: { minHeight: 42, borderTopWidth: 1, borderTopColor: colors.ruleSoft },
  nameCell: { flex: 1, minWidth: 0, justifyContent: 'center', paddingRight: 14 },
  numberCell: {
    justifyContent: 'center',
    alignItems: 'flex-end',
    borderLeftWidth: 1,
    borderLeftColor: colors.ruleSoft,
    paddingRight: 2,
  },
  limitCell: { width: 60 },
  spentCell: { width: 84 },
  blankNumber: { alignItems: 'stretch', paddingRight: 6 },
  track: { height: 3, marginTop: 6, backgroundColor: colors.barTrack },
  fill: { height: 3 },
  double: { marginTop: 2 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 9 },
  noteWrap: { marginTop: 14 },
  note: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44, paddingTop: 10 },
  noteText: { flex: 1 },
});
