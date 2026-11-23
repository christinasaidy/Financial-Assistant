import { SecureTokenStore } from '@/features/auth/data/secureTokenStore';
import { secureValue } from '@/shared/storage/tokenStore';

import { christina } from './fakes';

describe('SecureTokenStore (on the mocked expo-secure-store)', () => {
  it('saves, loads and clears the session', async () => {
    const store = new SecureTokenStore(secureValue('test.session'));
    const session = { accessToken: 'jwt', expiresAt: 1_800_000_000_000, user: christina };

    await store.save(session);
    expect(await store.load()).toEqual(session);

    await store.clear();
    expect(await store.load()).toBeNull();
  });

  it('treats an unreadable value as no session', async () => {
    const value = secureValue('test.broken');
    const store = new SecureTokenStore(value);

    await value.write('not json');
    expect(await store.load()).toBeNull();

    await value.write(JSON.stringify({ accessToken: 'jwt' }));
    expect(await store.load()).toBeNull();
  });
});
