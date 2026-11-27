import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Easing, Image, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { getContainer } from '@/container';
import { colors, radius, touchTarget } from '@/shared/theme';
import { AppText, Button, DashedLine, LineIcon, PaperSheet } from '@/shared/ui';

import type { ScanService } from '../application/scanService';
import type { Receipt } from '../domain';
import { checkingLabel, readingRows, scanErrorSentence } from './scanText';

/** The app's ScanService from the container, unless a test passes one. */
export function useScanService(service?: ScanService): ScanService {
  return useMemo(() => service ?? getContainer().scan, [service]);
}

/** How fast the rows tick off once the backend has read the receipt, and the pause before Review. */
const ROW_MS = 350;
const DONE_MS = 500;

const SLIP = { width: 230, height: 318 };

type Props = { service?: ScanService; rowMs?: number };

/**
 * Reading (design/screens/10-scan-reading.png): the photo as a creased slip with a cobalt scan line and a faint
 * tint over what is read, and a checklist. The backend reads the whole receipt at once, so the rows fill in one
 * after another as soon as it has (D051), then Review opens.
 */
export function ReadingScreen({ service, rowMs = ROW_MS }: Props) {
  const scan = useScanService(service);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { uri, type } = useLocalSearchParams<{ uri: string; type?: string }>();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [shown, setShown] = useState(0);
  const [failure, setFailure] = useState<{
    sentence: string;
    id: number | null;
    unreadable: boolean;
  } | null>(null);
  const idRef = useRef<number | null>(null);
  const stop = useRef({ aborted: false });
  const [line] = useState(() => new Animated.Value(0));

  // Send the photo and wait for it to be read.
  useEffect(() => {
    const signal = { aborted: false };
    stop.current = signal;
    (async () => {
      try {
        const id = await scan.upload({ uri, mimeType: type ?? 'image/jpeg' });
        idRef.current = id;
        const read = await scan.waitUntilRead(id, { signal });
        if (!signal.aborted) setReceipt(read);
      } catch (error) {
        if (signal.aborted) return;
        const code = typeof error === 'object' && error && 'code' in error ? (error as { code: string }).code : '';
        setFailure({
          sentence: scanErrorSentence(error),
          id: idRef.current,
          unreadable: code === 'failed',
        });
      }
    })();
    return () => {
      signal.aborted = true;
    };
  }, [scan, uri, type]);

  // The scan line runs down the slip until the receipt is read.
  useEffect(() => {
    if (receipt || failure) {
      line.stopAnimation();
      Animated.timing(line, {
        toValue: 1,
        duration: 250,
        useNativeDriver: false,
      }).start();
      return undefined;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(line, {
          toValue: 1,
          duration: 1400,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: false,
        }),
        Animated.timing(line, {
          toValue: 0,
          duration: 1400,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: false,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [receipt, failure, line]);

  // Tick the rows off, then open Review.
  useEffect(() => {
    if (!receipt) return undefined;
    const timer =
      shown < 4
        ? setTimeout(() => setShown((count) => count + 1), rowMs)
        : setTimeout(
            () =>
              router.replace({
                pathname: '/scan/review',
                params: { id: String(receipt.id) },
              }),
            DONE_MS,
          );
    return () => clearTimeout(timer);
  }, [receipt, shown, router, rowMs]);

  const cancel = () => {
    stop.current.aborted = true;
    if (idRef.current !== null && !receipt) void scan.discard(idRef.current);
    router.back();
  };

  const top = line.interpolate({
    inputRange: [0, 1],
    outputRange: [SLIP.height * 0.06, SLIP.height * 0.94],
  });
  const rows = receipt ? readingRows(receipt) : [];

  return (
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom }]} testID="scan-reading">
      <View style={styles.bar}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cancel and go back to camera"
          onPress={cancel}
          style={styles.iconButton}
        >
          <LineIcon name="close" />
        </Pressable>
        <AppText cap color="ink" accessibilityRole="header">
          Reading receipt
        </AppText>
        <View style={styles.iconButton} />
      </View>

      <PaperSheet shadow={styles.slipShadow} outerStyle={styles.slipPlace} style={styles.slip}>
        {uri ? (
          <Image source={{ uri }} style={StyleSheet.absoluteFill} resizeMode="cover" accessibilityIgnoresInvertColors />
        ) : null}
        <Animated.View style={[styles.tint, { height: top }]} pointerEvents="none" />
        <Animated.View style={[styles.scanLine, { top }]} pointerEvents="none" />
      </PaperSheet>

      <View style={styles.steps} accessibilityLiveRegion="polite">
        {failure ? (
          <View style={styles.failure}>
            <AppText size={15} color="noteText">
              {failure.sentence}
            </AppText>
            <Button label="Retake" onPress={cancel} />
            {failure.unreadable && failure.id !== null ? (
              <Button
                kind="secondary"
                label="Fill it in by hand"
                onPress={() =>
                  router.replace({
                    pathname: '/scan/review',
                    params: { id: String(failure.id) },
                  })
                }
              />
            ) : null}
          </View>
        ) : null}
        {!failure && !receipt ? <Step spinner label="Reading the receipt…" /> : null}
        {rows.slice(0, shown).map((row) => (
          <Step key={row.label} label={row.label} value={row.value} mono={row.mono} />
        ))}
        {receipt && shown < rows.length ? <Step spinner label={checkingLabel(rows[shown]!.label)} last /> : null}
      </View>

      <AppText cap color="inkMuted" style={styles.footer}>
        Usually takes a few seconds
      </AppText>
    </View>
  );
}

function Step({
  label,
  value,
  mono = false,
  spinner = false,
  last = false,
}: {
  label: string;
  value?: string;
  mono?: boolean;
  spinner?: boolean;
  last?: boolean;
}) {
  return (
    <View testID={spinner ? 'step-checking' : `step-${label}`}>
      <View style={styles.step}>
        <View style={styles.stepIcon}>
          {spinner ? (
            <ActivityIndicator size="small" color={colors.cobalt} />
          ) : (
            <LineIcon name="check" color="cobalt" />
          )}
        </View>
        {spinner ? (
          <AppText size={14.5} color="inkSoft" style={styles.stepText}>
            {label}
          </AppText>
        ) : (
          <View style={[styles.stepText, styles.stepRow]}>
            <AppText size={14.5}>{label}</AppText>
            <AppText font={mono ? 'mono' : 'sans'} weight={500} size={14.5} numberOfLines={1} style={styles.value}>
              {value}
            </AppText>
          </View>
        )}
      </View>
      {last || spinner ? null : <DashedLine color="dashedBg" />}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  bar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 12,
    paddingHorizontal: 8,
  },
  iconButton: {
    width: touchTarget,
    height: touchTarget,
    borderRadius: radius.button,
    alignItems: 'center',
    justifyContent: 'center',
  },
  slipPlace: { alignSelf: 'center', width: SLIP.width, marginTop: 20 },
  slip: { height: SLIP.height - 6 },
  slipShadow: {
    shadowColor: 'rgb(40,35,25)',
    shadowOpacity: 0.16,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 10 },
  },
  tint: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    backgroundColor: colors.cobaltTint,
  },
  scanLine: {
    position: 'absolute',
    left: -4,
    right: -4,
    height: 2,
    backgroundColor: colors.cobalt,
    shadowColor: colors.cobalt,
    shadowOpacity: 0.35,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 0 },
  },
  steps: {
    marginTop: 26,
    marginHorizontal: 20,
    borderTopWidth: 1,
    borderTopColor: colors.ink,
  },
  step: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 44 },
  stepIcon: { width: 24, alignItems: 'center' },
  stepText: { flex: 1 },
  stepRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  value: { flexShrink: 1, textAlign: 'right' },
  failure: { gap: 12, paddingTop: 14 },
  footer: { marginTop: 'auto', marginBottom: 34, textAlign: 'center' },
});
