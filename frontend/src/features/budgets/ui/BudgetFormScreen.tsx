import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '@/shared/theme';
import { AppText, Button, Chip, PaperSheet, SegmentedChoice, TextField, TextLink } from '@/shared/ui';

import type { BudgetsService } from '../application/budgetsService';
import { BudgetsError, checkLimit, type Budget, type BudgetCurrency, type BudgetMonth, type LimitProblem } from '../domain';
import { errorSentence, longMonthLabel, monthLabel } from './budgetsText';
import { useBudgetsService } from './useBudgetMonth';

const currencies = [
  { value: 'USD', label: 'USD' },
  { value: 'LBP', label: 'LBP' },
] as const;

function limitMessage(problem: LimitProblem, currency: BudgetCurrency): string {
  switch (problem) {
    case 'limit-missing':
      return 'Enter a monthly limit.';
    case 'limit-not-a-number':
      return 'Enter the limit as a number, like 250.';
    case 'limit-not-positive':
      return 'The limit must be more than 0.';
    case 'limit-too-precise':
      return currency === 'USD' ? 'Use at most two decimals.' : 'Pounds have no decimals.';
  }
}

/** "2026-11" -> 1 November 2026, local; the current month if missing or unreadable. */
function parseMonth(value: string | undefined): Date {
  const match = /^(\d{4})-(\d{2})$/.exec(value ?? '');
  if (!match) {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  }
  return new Date(Number(match[1]), Number(match[2]) - 1, 1);
}

/** A limit as it goes back into the field: "250.00" -> "250", "62.50" -> "62.5". */
function editableLimit(limit: string): string {
  return String(Number.parseFloat(limit));
}

type Props = {
  service?: BudgetsService;
};

/**
 * The budget form (D046), a sheet over Budgets on the sign-in form's clean paper. New: NEW BUDGET, the
 * categories without a budget as chips, the amount and USD / LBP, Save budget. Editing: the category's name,
 * the same fields filled in, and an outlined Remove budget. A limit applies from the month on screen onwards.
 */
export function BudgetFormScreen({ service }: Props) {
  const budgets = useBudgetsService(service);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ month?: string; categoryId?: string }>();
  const month = parseMonth(params.month);
  const editingId = params.categoryId ? Number(params.categoryId) : null;

  const [data, setData] = useState<BudgetMonth | null>(null);
  const [loadError, setLoadError] = useState<BudgetsError | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(editingId);
  const [limit, setLimit] = useState('');
  const [currency, setCurrency] = useState<BudgetCurrency>('USD');
  const [errors, setErrors] = useState<{ category: string | null; limit: string | null; form: string | null }>({
    category: null,
    limit: null,
    form: null,
  });
  const [busy, setBusy] = useState<'save' | 'remove' | null>(null);

  const editing: Budget | null = data && editingId !== null ? (data.budgets.find((budget) => budget.categoryId === editingId) ?? null) : null;

  useEffect(() => {
    let active = true;
    budgets
      .loadMonth(month)
      .then((loaded) => {
        if (!active) return;
        setData(loaded);
        const existing = editingId !== null ? loaded.budgets.find((budget) => budget.categoryId === editingId) : undefined;
        if (existing) {
          setLimit(editableLimit(existing.limit));
          setCurrency(existing.currency);
        }
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof BudgetsError ? error : new BudgetsError('unexpected', String(error)));
      });
    return () => {
      active = false;
    };
    // Loaded once, for the month and budget the form was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    if (busy) return;
    const checked = checkLimit(limit, currency);
    const found = {
      category: categoryId === null ? 'Choose a category.' : null,
      limit: 'problem' in checked ? limitMessage(checked.problem, currency) : null,
      form: null,
    };
    setErrors(found);
    if (categoryId === null || 'problem' in checked) return;
    setBusy('save');
    try {
      await budgets.save({ categoryId, month, currency, limit: checked.limit });
      router.back();
    } catch (error) {
      setErrors({ category: null, limit: null, form: errorSentence(error as BudgetsError, 'save') });
      setBusy(null);
    }
  }

  function remove() {
    if (!editing || busy) return;
    Alert.alert(`Remove the ${editing.name} budget?`, 'It is removed for every month.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          setBusy('remove');
          try {
            await budgets.remove(editing.categoryId);
            router.back();
          } catch (error) {
            setErrors({ category: null, limit: null, form: errorSentence(error as BudgetsError, 'remove') });
            setBusy(null);
          }
        },
      },
    ]);
  }

  return (
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <PaperSheet color="paperClean" crease={0.15} creaseTileWidth={520} tear={null} shadow={null} outerStyle={styles.fill} style={styles.fill}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: 22 + insets.bottom }]} keyboardShouldPersistTaps="handled">
          <View style={styles.between}>
            <AppText cap color="cobalt">
              {editingId !== null ? 'Edit budget' : 'New budget'}
            </AppText>
            <AppText cap color="capOnForm">
              {monthLabel(month)}
            </AppText>
          </View>
          <AppText weight={600} size={25} tracking={-0.02} accessibilityRole="header" style={styles.heading}>
            {editing ? editing.name : 'Set a monthly limit.'}
          </AppText>
          <AppText size={15} color="formSoft" style={styles.sentence}>
            It applies from {longMonthLabel(month)} onwards.
          </AppText>

          {!data && !loadError ? <ActivityIndicator color={colors.inkMuted} accessibilityLabel="Loading" /> : null}
          {loadError ? (
            <View style={styles.loadError}>
              <AppText size={14} color="redText">
                {errorSentence(loadError, 'load')}
              </AppText>
              <TextLink label="Close" onPress={() => router.back()} />
            </View>
          ) : null}

          {data ? (
            <View style={styles.fields}>
              {editingId === null ? (
                <View>
                  <AppText cap color="fieldLabel" importantForAccessibility="no" accessibilityElementsHidden>
                    Category
                  </AppText>
                  {data.unbudgeted.length === 0 ? (
                    <AppText size={14} color="formSoft" style={styles.none}>
                      Every category has a budget already. Tap one on Budgets to change it.
                    </AppText>
                  ) : (
                    <View accessibilityRole="radiogroup" accessibilityLabel="Category" style={styles.chips}>
                      {data.unbudgeted.map((category) => (
                        <Chip
                          key={category.id}
                          label={category.name}
                          selected={category.id === categoryId}
                          onPress={() => {
                            setCategoryId(category.id);
                            setErrors((current) => ({ ...current, category: null, form: null }));
                          }}
                          testID={`category-${category.id}`}
                        />
                      ))}
                    </View>
                  )}
                  {errors.category ? (
                    <AppText size={13} color="redText" style={styles.fieldError}>
                      {errors.category}
                    </AppText>
                  ) : null}
                </View>
              ) : null}

              <TextField
                label="Monthly limit"
                value={limit}
                onChangeText={(value) => {
                  setLimit(value);
                  setErrors((current) => ({ ...current, limit: null, form: null }));
                }}
                error={errors.limit}
                placeholder={currency === 'USD' ? '250' : '3,000,000'}
                keyboardType="decimal-pad"
                returnKeyType="done"
              />
              <SegmentedChoice
                label="Currency"
                choices={currencies}
                value={currency}
                onChange={(value) => {
                  setCurrency(value);
                  setErrors((current) => ({ ...current, limit: null }));
                }}
                testIDPrefix="currency"
              />

              {errors.form ? (
                <AppText size={14} color="redText" accessibilityLiveRegion="polite">
                  {errors.form}
                </AppText>
              ) : null}

              <View style={styles.buttons}>
                <Button label="Save budget" onPress={() => void save()} busy={busy === 'save'} disabled={busy === 'remove'} />
                {editing ? <Button kind="secondary" label="Remove budget" onPress={remove} busy={busy === 'remove'} disabled={busy === 'save'} /> : null}
              </View>
            </View>
          ) : null}
        </ScrollView>
      </PaperSheet>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingTop: 30, paddingHorizontal: 22 },
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  heading: { marginTop: 14, marginBottom: 4, lineHeight: 27.5 },
  sentence: { lineHeight: 21, marginBottom: 18 },
  loadError: { gap: 8 },
  fields: { gap: 22 },
  chips: { marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  none: { marginTop: 8 },
  fieldError: { marginTop: 6 },
  buttons: { gap: 10, marginTop: 4 },
});
