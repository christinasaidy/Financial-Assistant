// Fatourati design tokens (invoice direction). See DESIGN.md.

export const colors = {
  bg: '#E3E4E6',
  paper: '#EFEEEB',
  paperClean: '#FCFBF8',
  tabBar: '#F6F6F5',
  launchPaper: '#C9C9C6',

  ink: '#1A1A1A',
  inkSoft: '#46453F',   // secondary text on paper
  inkMuted: '#55544F',  // secondary text on bg, inactive tabs
  capLabel: '#4A4944',  // small uppercase mono labels
  zeroAmount: '#86857F',

  cobalt: '#2340C8',
  cobaltPressed: '#182E96',
  red: '#B3261E',
  redText: '#A3231B',

  ruleSoft: 'rgba(0,0,0,0.13)',
  barTrack: 'rgba(0,0,0,0.12)',
  dashed: 'rgba(0,0,0,0.28)',
  dashedBg: '#B3B5BA',
  perfDot: '#C9CBCF',
  sheetBehind1: '#D2D4D8',
  sheetBehind2: '#F5F5F4',
  userBubbleText: '#F6F6F5',
} as const;

// Load with expo-font, e.g. via @expo-google-fonts/geist, @expo-google-fonts/geist-mono
// and @expo-google-fonts/noto-naskh-arabic (check the exact export names in each package).
export const fonts = {
  sans: { regular: 'Geist_400Regular', medium: 'Geist_500Medium', semibold: 'Geist_600SemiBold' },
  mono: { regular: 'GeistMono_400Regular', medium: 'GeistMono_500Medium', semibold: 'GeistMono_600SemiBold' },
  arabic: { semibold: 'NotoNaskhArabic_600SemiBold', bold: 'NotoNaskhArabic_700Bold' },
} as const;

export const type = {
  cap: { fontFamily: fonts.mono.medium, fontSize: 10.5, letterSpacing: 0.84, textTransform: 'uppercase' as const, color: colors.capLabel },
  bigTotal: { fontFamily: fonts.mono.medium, fontSize: 52, letterSpacing: -2, color: colors.ink },
  title: { fontFamily: fonts.sans.semibold, fontSize: 20, color: colors.ink },
  rowLabel: { fontFamily: fonts.sans.medium, fontSize: 15, color: colors.ink },
  rowNumber: { fontFamily: fonts.mono.regular, fontSize: 15, color: colors.ink, fontVariant: ['tabular-nums'] as const },
  subNumber: { fontFamily: fonts.mono.regular, fontSize: 11, color: colors.inkSoft },
  body: { fontFamily: fonts.sans.regular, fontSize: 15, lineHeight: 21, color: colors.ink },
};

export const crease = {
  main: 0.6,      // home, receipt, budgets, assistant cards
  heavy: 0.69,    // sign-in slips, launch sheet
  tileWidth: 300, // px
  blend: 'overlay' as const,
};

export const tornEdge = { tooth: 12, height: 6, slipTooth: 10, slipHeight: 5, launchTooth: 14, launchHeight: 7 };

export const radius = { button: 12, scan: 16, chip: 20, input: 14, sheet: 0 };

export const shadow = {
  sheet: { shadowColor: 'rgb(40,35,25)', shadowOpacity: 0.14, shadowRadius: 14, shadowOffset: { width: 0, height: 10 }, elevation: 6 },
};

export const fx = { usdLbpSampleRate: 89500 };
