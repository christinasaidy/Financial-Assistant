import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { itemName, quantityLabel } from '@/features/receipts/domain';
import { colors, fonts, radius, touchTarget } from '@/shared/theme';
import { AppText, Button, Chip, DashedLine, DoubleRule, LineIcon, PaperSheet, TextLink } from '@/shared/ui';

import type { ScanService } from '../application/scanService';
import {
  addsUp,
  checkDraft,
  checksFor,
  draftFrom,
  FIRST_ITEMS,
  linesTotal,
  parseDate,
  type Category,
  type Checks,
  type Draft,
  type DraftProblems,
  type Receipt,
} from '../domain';
import { useScanService } from './ReadingScreen';
import { cell, money, newReceiptLabel, saveLabel, scanErrorSentence } from './scanText';

type Props = { service?: ScanService; today?: () => Date };

type Loaded = { receipt: Receipt; categories: Category[]; invoiceNumber: number };

/**
 * Review (design/screens/11-scan-review.png): "Check the details", Back and Retake; the creased sheet with the
 * store, the date and USD / LBP to edit, the items (four, then "+ N more"), the total and whether the items add
 * up; CHECK THIS where the backend flagged something (D051); the category chips; "Save to November invoice".
 */
export function ReviewScreen({ service, today = () => new Date() }: Props) {
  const scan = useScanService(service);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [problems, setProblems] = useState<DraftProblems>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [allItems, setAllItems] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    scan
      .loadReview(id, today())
      .then((result) => {
        if (!active) return;
        setLoaded(result);
        setDraft(draftFrom(result.receipt, today()));
      })
      .catch((error: unknown) => active && setLoadError(scanErrorSentence(error)));
    return () => {
      active = false;
    };
    // Loaded once for the receipt this screen opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan, id]);

  const retake = () => {
    if (loaded?.receipt.status !== 'confirmed') void scan.discard(id);
    router.dismissTo('/scan');
  };

  const change = (patch: Partial<Draft>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
    setFailure(null);
    setProblems((current) => {
      const next = { ...current };
      if ('shopName' in patch) delete next.store;
      if ('date' in patch) delete next.date;
      if ('total' in patch || 'currency' in patch) delete next.total;
      if ('categoryId' in patch) delete next.category;
      return next;
    });
  };

  const save = async () => {
    if (!draft || busy) return;
    const found = checkDraft(draft);
    setProblems(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      await scan.save(id, draft);
      router.replace({ pathname: '/scan/filed', params: { id: String(id) } });
    } catch (error) {
      setFailure(scanErrorSentence(error));
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={[styles.screen, { paddingTop: insets.top }]} behavior={Platform.OS === 'ios' ? 'padding' : undefined} testID="scan-review">
      <View style={styles.bar}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back to the camera" onPress={retake} style={styles.iconButton}>
          <LineIcon name="back" />
        </Pressable>
        <AppText weight={600} size={16} accessibilityRole="header">
          Check the details
        </AppText>
        <Pressable accessibilityRole="button" accessibilityLabel="Retake" onPress={retake} style={styles.retake}>
          <AppText weight={500} size={14} color="cobalt">
            Retake
          </AppText>
        </Pressable>
      </View>

      {!loaded && !loadError ? <ActivityIndicator style={styles.message} color={colors.inkMuted} accessibilityLabel="Loading" /> : null}
      {loadError ? (
        <View style={styles.message}>
          <AppText size={14} color="inkMuted">
            {loadError}
          </AppText>
          <TextLink label="Retake" onPress={retake} />
        </View>
      ) : null}

      {loaded && draft ? (
        <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 30 }]} keyboardShouldPersistTaps="handled">
          <ReceiptSheet
            draft={draft}
            checks={checksFor(loaded.receipt)}
            problems={problems}
            invoiceNumber={loaded.invoiceNumber}
            allItems={allItems}
            onAllItems={() => setAllItems(true)}
            onChange={change}
          />

          <View style={styles.category}>
            <View style={styles.between}>
              <AppText cap color="ink">
                Category
              </AppText>
              {loaded.receipt.categoryId !== null && draft.categoryId === loaded.receipt.categoryId ? (
                <AppText size={12.5} color="inkMuted">
                  Suggested from the store
                </AppText>
              ) : null}
            </View>
            <View accessibilityRole="radiogroup" accessibilityLabel="Category" style={styles.chips}>
              {loaded.categories.map((category) => (
                <Chip key={category.id} label={category.name} selected={category.id === draft.categoryId} onPress={() => change({ categoryId: category.id })} testID={`category-${category.id}`} />
              ))}
            </View>
            {problems.category ? <ErrorLine text={problems.category} /> : null}
          </View>

          {failure ? (
            <AppText size={14} color="redText" style={styles.failure} accessibilityLiveRegion="polite">
              {failure}
            </AppText>
          ) : null}
          <View style={styles.saveButton}>
            <Button label={saveLabel(parseDate(draft.date), today())} onPress={() => void save()} busy={busy} />
          </View>
        </ScrollView>
      ) : null}
    </KeyboardAvoidingView>
  );
}

function ErrorLine({ text }: { text: string }) {
  return (
    <AppText size={13} color="redText" style={styles.error}>
      {text}
    </AppText>
  );
}

function CheckThis() {
  return (
    <AppText cap size={9.5} color="cobalt">
      Check this
    </AppText>
  );
}

/** A field of the sheet: a cap label, the value to edit, a line under it (design/reference/11: .fld). */
function Field({ label, check, error, mono = false, ...input }: { label: string; check: boolean; error?: string; mono?: boolean } & TextInputProps) {
  return (
    <View style={[styles.field, check ? styles.checked : null]}>
      <View style={styles.fieldHead}>
        <AppText cap importantForAccessibility="no" accessibilityElementsHidden>
          {label}
        </AppText>
        {check ? <CheckThis /> : null}
      </View>
      <TextInput
        {...input}
        accessibilityLabel={label}
        accessibilityHint={error ?? (check ? 'Check this' : undefined)}
        selectionColor={colors.cobalt}
        placeholderTextColor={colors.placeholder}
        style={[styles.input, mono ? styles.monoInput : null]}
      />
      {error ? <ErrorLine text={error} /> : null}
    </View>
  );
}

type SheetProps = {
  draft: Draft;
  checks: Checks;
  problems: DraftProblems;
  invoiceNumber: number;
  allItems: boolean;
  onAllItems: () => void;
  onChange: (patch: Partial<Draft>) => void;
};

function ReceiptSheet({ draft, checks, problems, invoiceNumber, allItems, onAllItems, onChange }: SheetProps) {
  const shown = allItems ? draft.lines : draft.lines.slice(0, FIRST_ITEMS);
  const hidden = draft.lines.slice(shown.length);
  const fits = addsUp(draft);
  return (
    <PaperSheet on="bg" outerStyle={styles.sheetPlace} style={styles.sheet} testID="review-sheet">
      <View style={styles.between}>
        <AppText cap color="cobalt">
          {newReceiptLabel(invoiceNumber)}
        </AppText>
        <AppText cap>Tap to edit</AppText>
      </View>

      <Field label="Store" check={checks.store} error={problems.store} value={draft.shopName} onChangeText={(shopName) => onChange({ shopName })} autoCapitalize="words" />

      <View style={styles.pair}>
        <View style={styles.flex}>
          <Field label="Date" mono check={checks.date} error={problems.date} value={draft.date} onChangeText={(date) => onChange({ date })} placeholder="18/11/2026" keyboardType="numbers-and-punctuation" />
        </View>
        <View style={styles.currency}>
          <AppText cap importantForAccessibility="no" accessibilityElementsHidden>
            Currency
          </AppText>
          <View accessibilityRole="radiogroup" accessibilityLabel="Currency" style={styles.smallTrack}>
            {(['USD', 'LBP'] as const).map((currency) => {
              const chosen = draft.currency === currency;
              return (
                <Pressable
                  key={currency}
                  accessibilityRole="radio"
                  accessibilityLabel={currency}
                  accessibilityState={{ checked: chosen }}
                  onPress={() => onChange({ currency })}
                  style={[styles.smallSegment, chosen ? styles.smallChosen : null]}
                  testID={`currency-${currency}`}
                >
                  <AppText font="mono" weight={chosen ? 600 : 500} size={13} color={chosen ? 'ink' : 'inkSoft'}>
                    {currency}
                  </AppText>
                </Pressable>
              );
            })}
          </View>
        </View>
      </View>

      {draft.lines.length > 0 ? (
        <View style={styles.table}>
          <View style={[styles.tr, styles.headRow]}>
            <View style={styles.itemCell}>
              <AppText cap>Item</AppText>
            </View>
            <View style={[styles.numberCell, styles.qty]}>
              <AppText cap>Qty</AppText>
            </View>
            <View style={[styles.numberCell, styles.amount]}>
              <AppText cap>Amount</AppText>
            </View>
          </View>
          {shown.map((line, index) => {
            const check = checks.lines.includes(index);
            return (
              <View key={line.id ?? index} style={[styles.tr, styles.bodyRow, check ? styles.checkedRow : null]} testID={`review-line-${index}`}>
                <View style={styles.itemCell}>
                  <AppText size={14.5}>{itemName(line)}</AppText>
                  {check ? <CheckThis /> : null}
                </View>
                <View style={[styles.numberCell, styles.qty]}>
                  <AppText font="mono" size={13} color="inkSoft">
                    {quantityLabel(line)}
                  </AppText>
                </View>
                <View style={[styles.numberCell, styles.amount]}>
                  <AppText font="mono" size={14}>
                    {cell(line.lineTotal, draft.currency)}
                  </AppText>
                  {check ? <DashedLine color="cobalt" width={1.5} /> : null}
                </View>
              </View>
            );
          })}
          {hidden.length > 0 ? (
            <Pressable accessibilityRole="button" accessibilityLabel={`Show ${hidden.length} more items`} onPress={onAllItems} style={styles.more} testID="more-items">
              <AppText weight={500} size={13.5} color="cobalt">
                + {hidden.length} more {hidden.length === 1 ? 'item' : 'items'}
              </AppText>
              <AppText font="mono" size={13.5} color="inkSoft">
                {cell(linesTotal(hidden), draft.currency)}
              </AppText>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      <View>
        <DoubleRule />
        <View style={[styles.totalRow, checks.total ? styles.checkedRow : null]}>
          <View>
            <AppText cap color="ink">
              Total
            </AppText>
            {checks.total ? <CheckThis /> : null}
          </View>
          <View style={styles.totalInput}>
            {draft.currency === 'USD' ? (
              <AppText font="mono" weight={600} size={18}>
                $
              </AppText>
            ) : null}
            <TextInput
              value={draft.total}
              onChangeText={(total) => onChange({ total })}
              accessibilityLabel="Total"
              keyboardType="decimal-pad"
              selectionColor={colors.cobalt}
              placeholder="0.00"
              placeholderTextColor={colors.placeholder}
              // Geist Mono is 0.6 em a character: the field is exactly as wide as the amount, so "$" sits beside it.
              style={[styles.total, { width: Math.max(draft.total.length, 4) * 18 * 0.6 + 4 }]}
            />
            {draft.currency === 'LBP' ? (
              <AppText font="mono" weight={600} size={18}>
                {' '}LBP
              </AppText>
            ) : null}
          </View>
        </View>
        {problems.total ? <ErrorLine text={problems.total} /> : null}
        {fits === true ? (
          <View style={styles.fits}>
            <LineIcon name="check" size={14} color="cobalt" />
            <AppText size={12.5} color="noteText">
              Items add up to the total
            </AppText>
          </View>
        ) : null}
        {fits === false ? (
          <AppText size={12.5} color="redText" style={styles.fits} testID="mismatch">
            The items add up to {money(linesTotal(draft.lines), draft.currency)}, not the total. Check the total.
          </AppText>
        ) : null}
      </View>
    </PaperSheet>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  bar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, paddingHorizontal: 8 },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  retake: { minHeight: touchTarget, paddingHorizontal: 10, justifyContent: 'center' },
  message: { marginTop: 14, marginHorizontal: 20, gap: 8 },
  scroll: { flexGrow: 1 },
  sheetPlace: { marginTop: 8, marginHorizontal: 14 },
  sheet: { paddingTop: 14, paddingHorizontal: 16, paddingBottom: 20, gap: 12 },
  between: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  field: { gap: 5, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: colors.fieldRule },
  checked: { backgroundColor: colors.cobaltTint, marginHorizontal: -6, paddingHorizontal: 6 },
  fieldHead: { flexDirection: 'row', justifyContent: 'space-between' },
  input: { minHeight: 26, padding: 0, fontFamily: fonts.sans.medium, fontSize: 16, color: colors.ink },
  monoInput: { fontFamily: fonts.mono.medium, fontSize: 15 },
  pair: { flexDirection: 'row', gap: 14 },
  flex: { flex: 1 },
  currency: { width: 128, gap: 5 },
  smallTrack: { flexDirection: 'row', padding: 2, borderRadius: 9, backgroundColor: colors.smallTrack },
  smallSegment: { flex: 1, minHeight: 32, borderRadius: 7, alignItems: 'center', justifyContent: 'center' },
  smallChosen: {
    backgroundColor: colors.paperClean,
    shadowColor: '#000000',
    shadowOpacity: 0.15,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
  },
  table: { borderTopWidth: 1, borderTopColor: colors.ink },
  tr: { flexDirection: 'row' },
  headRow: { minHeight: 26 },
  bodyRow: { minHeight: 34, borderTopWidth: 1, borderTopColor: colors.ruleSoft },
  checkedRow: { backgroundColor: colors.cobaltTint, marginHorizontal: -6, paddingHorizontal: 6 },
  itemCell: { flex: 1, minWidth: 0, justifyContent: 'center', paddingVertical: 3, paddingRight: 8 },
  numberCell: { justifyContent: 'center', alignItems: 'flex-end', borderLeftWidth: 1, borderLeftColor: colors.ruleSoft, paddingRight: 2 },
  qty: { width: 58 },
  amount: { width: 70 },
  more: { minHeight: 36, borderTopWidth: 1, borderTopColor: colors.ruleSoft, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 2 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 9 },
  totalInput: { flexDirection: 'row', alignItems: 'center' },
  total: { padding: 0, textAlign: 'right', fontFamily: fonts.mono.semibold, fontSize: 18, color: colors.ink },
  fits: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 },
  error: { marginTop: 4 },
  category: { marginTop: 16, marginHorizontal: 16 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  failure: { marginTop: 14, marginHorizontal: 16 },
  saveButton: { marginTop: 'auto', paddingTop: 24, marginHorizontal: 16 },
});
