/**
 * Design tokens. design/theme.ts (from the design handoff) is the source: its values are re-exported here
 * untouched, so the app cannot drift from it. The few colours the reference screens use that theme.ts does
 * not name are added below, each with the screen it comes from (design/reference/*.html).
 *
 * The app is light only (design/DESIGN.md has no dark colours).
 */
import { colors as designColors, crease, fonts, radius, shadow, tornEdge } from '../../../design/theme';

export { crease, fonts, radius, shadow, tornEdge };

export const colors = {
  ...designColors,
  /** Sign in: small capital labels on the form sheet, the eye icon. */
  capOnForm: '#6A6964',
  /** Sign in: the field labels (EMAIL, PASSWORD). Launch: the tagline. */
  fieldLabel: '#45443F',
  /** Sign in: the line under a field; 2 px cobalt when focused. */
  fieldLine: '#BDBFC4',
  /** Sign in: placeholder text. */
  placeholder: '#8A8984',
  /** Sign in: the sentence under the heading, "New to Fatourati?". */
  formSoft: '#5A5954',
  /** Sign in: the second line of a receipt slip. Launch: USD · LBP. */
  slipSoft: '#3F3E3A',
  /** Sign in: OVER BUDGET on the Transport slip. */
  slipRed: '#8E1B14',
  /** Home: the note's text. */
  noteText: '#3A3934',
  /** Launch: INVOICE Nº 0001. */
  launchCobalt: '#1F37AE',
  /** Launch: the screen behind the sheet. */
  white: '#FFFFFF',
  /** Home, empty: the dashed blanks in the table. */
  blank: 'rgba(0,0,0,0.25)',
  /** Assistant: the segmented switch's track (used for choices such as gender). */
  segmentTrack: 'rgba(0,0,0,0.06)',
  /** Empty Home: the faint ring around Scan. */
  scanRing: 'rgba(35,64,200,0.14)',
} as const;

export type ColorName = keyof typeof colors;

/** Apple's minimum touch area (DESIGN.md §2: touch targets ≥ 44px). */
export const touchTarget = 44;
