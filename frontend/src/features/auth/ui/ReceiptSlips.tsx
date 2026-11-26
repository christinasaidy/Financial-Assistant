import { StyleSheet, View } from 'react-native';

import type { ColorName } from '@/shared/theme';
import { AppText, PaperSheet, tears } from '@/shared/ui';

type Slip = {
  left: number;
  top: number;
  width: number;
  rotate: string;
  title: string;
  sub: string;
  subColor: ColorName;
  amount: string;
  amountSize: number;
  /** Where the crease tiling starts on this slip, so the four do not look alike. */
  crease: { x: number; y: number };
};

/** The four slips of design/reference/02-sign-in.html, with their places, angles and sample receipts. */
const slips: readonly Slip[] = [
  { left: 18, top: 86, width: 150, rotate: '-9deg', title: 'SPINNEYS', sub: '18/11 · 9 ITEMS', subColor: 'slipSoft', amount: '$38.40', amountSize: 17, crease: { x: 0.5, y: 0.5 } },
  { left: 150, top: 62, width: 132, rotate: '7deg', title: 'ZAATAR W ZEIT', sub: '17/11 · 2 ITEMS', subColor: 'slipSoft', amount: '450,000 LBP', amountSize: 15, crease: { x: 0.4, y: 0.2 } },
  { left: 236, top: 150, width: 136, rotate: '-4deg', title: 'TRANSPORT', sub: 'OVER BUDGET', subColor: 'slipRed', amount: '63.00 / 60', amountSize: 17, crease: { x: 0.7, y: 0.5 } },
  { left: 64, top: 182, width: 142, rotate: '12deg', title: 'GROCERIES', sub: 'NOVEMBER', subColor: 'slipSoft', amount: '186.40', amountSize: 17, crease: { x: 0.1, y: 0.8 } },
];

/**
 * The crumpled receipt slips scattered above the sign-in form: `paper` with the heavier crease (0.69, 360 px
 * tiles) and a 10 × 5 torn edge, at −9°, 7°, −4° and 12°. Decoration only, so VoiceOver skips them.
 */
export function ReceiptSlips({ top }: { top: number }) {
  return (
    <View style={StyleSheet.absoluteFill} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" pointerEvents="none">
      {slips.map((slip) => (
        <PaperSheet
          key={slip.title}
          crease={0.69}
          creaseTileWidth={360}
          creasePosition={slip.crease}
          tear={tears.slip}
          shadow={styles.shadow}
          outerStyle={[styles.place, { left: slip.left, top: slip.top + top, width: slip.width, transform: [{ rotate: slip.rotate }] }]}
          style={styles.slip}
        >
          <AppText font="mono" weight={600} size={11}>
            {slip.title}
          </AppText>
          <AppText font="mono" size={10} color={slip.subColor}>
            {slip.sub}
          </AppText>
          <AppText font="mono" weight={600} size={slip.amountSize} style={styles.amount}>
            {slip.amount}
          </AppText>
        </PaperSheet>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  place: { position: 'absolute' },
  shadow: {
    shadowColor: 'rgb(30,30,35)',
    shadowOpacity: 0.22,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 6 },
  },
  slip: { paddingTop: 12, paddingHorizontal: 14, paddingBottom: 16, gap: 4 },
  amount: { marginTop: 6 },
});
