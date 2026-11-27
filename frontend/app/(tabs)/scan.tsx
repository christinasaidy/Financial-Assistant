import { Redirect } from 'expo-router';

/** The Scan tab never shows: pressing it opens the scan flow (app/scan) over the tabs. Here in case of a link. */
export default function ScanTabRoute() {
  return <Redirect href="/scan" />;
}
