// Starts Expo for the iPhone on whatever network the laptop is on:  npm run phone
//
// Expo Go needs the laptop's address on the network the phone is on. A laptop can have several (Wi-Fi, an
// Ethernet or virtual adapter), and Expo may pick the wrong one, so this picks the Wi-Fi one (or the only
// private one) and tells Expo to use it. The app then finds the backend on the same address, port 8000
// (src/shared/api/httpClient.ts, backendUrl), so nothing needs editing when the Wi-Fi changes.
//
// The backend must run on all interfaces:  uvicorn app.main:app --host 0.0.0.0 --port 8000
import { spawn } from 'node:child_process';
import { networkInterfaces } from 'node:os';

const PRIVATE = /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/;
const WIRELESS = /wi-?fi|wlan|wireless|^en0$/i;
const VIRTUAL = /vethernet|virtual|vmware|vbox|docker|wsl|hyper-v|loopback|bluetooth/i;

function pickAddress(interfaces) {
  const candidates = Object.entries(interfaces)
    .filter(([name]) => !VIRTUAL.test(name))
    .flatMap(([name, addresses]) =>
      (addresses ?? [])
        .filter((address) => address.family === 'IPv4' && !address.internal && PRIVATE.test(address.address))
        .map((address) => ({ name, address: address.address })),
    );
  return (candidates.find((candidate) => WIRELESS.test(candidate.name)) ?? candidates[0]) ?? null;
}

const picked = pickAddress(networkInterfaces());
if (!picked) {
  console.error('No network found. Join a Wi-Fi (or the iPhone hotspot) and run `npm run phone` again.');
  process.exit(1);
}

console.log(`\nLaptop on ${picked.name}: ${picked.address}`);
console.log(`In Expo Go, open: exp://${picked.address}:8081`);
console.log(`The app will use the backend at http://${picked.address}:8000\n`);

const child = spawn('npx', ['expo', 'start', '--lan', '--port', '8081', ...process.argv.slice(2)], {
  stdio: 'inherit',
  shell: true,
  env: { ...process.env, REACT_NATIVE_PACKAGER_HOSTNAME: picked.address },
});
child.on('exit', (code) => process.exit(code ?? 0));
