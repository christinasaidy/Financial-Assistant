import { AuthService } from '@/features/auth/application/authService';
import { AuthError } from '@/features/auth/domain/errors';

import { christina, FakeAuthRepository, FakeTokenStore } from './fakes';

const NOW = Date.UTC(2026, 10, 23, 12, 0);

function setup() {
  const repository = new FakeAuthRepository();
  const store = new FakeTokenStore();
  let now = NOW;
  const service = new AuthService(repository, store, () => now);
  const advance = (ms: number) => {
    now += ms;
  };
  return { repository, store, service, advance };
}

async function withAccount() {
  const context = setup();
  await context.repository.register({ ...christina, firstName: 'Christina', gender: 'female', password: 'pass-1234' });
  return context;
}

describe('AuthService.signIn', () => {
  it('saves the session and makes the token and user available', async () => {
    const { service, store } = await withAccount();
    const user = await service.signIn('christina@example.com', 'pass-1234');

    expect(user.firstName).toBe('Christina');
    expect(service.currentUser()).toEqual(user);
    expect(service.accessToken()).toMatch(/^token-/);
    expect(store.saved?.expiresAt).toBe(NOW + 3600 * 1000);
  });

  it('trims the email the user typed', async () => {
    const { service, repository } = await withAccount();
    await service.signIn('  christina@example.com ', 'pass-1234');
    expect(repository.calls).toContain('login christina@example.com');
  });

  it('passes a wrong password on as AuthError and stays signed out', async () => {
    const { service, store } = await withAccount();
    await expect(service.signIn('christina@example.com', 'nope')).rejects.toMatchObject({
      code: 'invalid-credentials',
    });
    expect(service.currentUser()).toBeNull();
    expect(store.saved).toBeNull();
  });

  it('tells subscribers', async () => {
    const { service } = await withAccount();
    const seen: (string | null)[] = [];
    service.subscribe((user) => seen.push(user?.email ?? null));
    await service.signIn('christina@example.com', 'pass-1234');
    await service.signOut();
    expect(seen).toEqual(['christina@example.com', null]);
  });
});

describe('AuthService.signUp', () => {
  it('creates the account with name and gender, then signs in', async () => {
    const { service, repository } = setup();
    const user = await service.signUp({
      email: ' maya@example.com',
      password: 'pass-1234',
      firstName: ' Maya ',
      gender: 'prefer_not_to_say',
    });
    expect(user).toMatchObject({ email: 'maya@example.com', firstName: 'Maya', gender: 'prefer_not_to_say' });
    expect(repository.calls).toEqual(['register maya@example.com', 'login maya@example.com']);
    expect(service.currentUser()?.email).toBe('maya@example.com');
  });

  it('does not sign in when the email is taken', async () => {
    const { service } = await withAccount();
    const attempt = service.signUp({
      email: 'christina@example.com',
      password: 'other',
      firstName: 'C',
      gender: 'female',
    });
    await expect(attempt).rejects.toBeInstanceOf(AuthError);
    await expect(attempt).rejects.toMatchObject({ code: 'email-taken' });
    expect(service.currentUser()).toBeNull();
  });
});

describe('AuthService.signOut and expireSession', () => {
  it('signOut forgets the session everywhere', async () => {
    const { service, store } = await withAccount();
    await service.signIn('christina@example.com', 'pass-1234');
    await service.signOut();
    expect(service.currentUser()).toBeNull();
    expect(service.accessToken()).toBeNull();
    expect(store.saved).toBeNull();
  });

  it('expireSession (a 401 mid-session) signs out', async () => {
    const { service, store } = await withAccount();
    await service.signIn('christina@example.com', 'pass-1234');
    service.expireSession();
    await Promise.resolve();
    expect(service.currentUser()).toBeNull();
    expect(store.saved).toBeNull();
  });

  it('stops giving out the token once it has expired', async () => {
    const { service, advance } = await withAccount();
    await service.signIn('christina@example.com', 'pass-1234');
    advance(3600 * 1000);
    expect(service.accessToken()).toBeNull();
  });
});

describe('AuthService.restoreSession', () => {
  it('is signed out when nothing is saved', async () => {
    const { service } = setup();
    expect(await service.restoreSession()).toBeNull();
  });

  it('picks the saved session up and refreshes the user from the backend', async () => {
    const first = await withAccount();
    await first.service.signIn('christina@example.com', 'pass-1234');

    // A new launch: a new service over the same backend and Keychain.
    const relaunched = new AuthService(first.repository, first.store, () => NOW + 1000);
    const user = await relaunched.restoreSession();
    expect(user?.email).toBe('christina@example.com');
    expect(relaunched.accessToken()).toBe(first.store.saved?.accessToken);
  });

  it('drops a saved session that has expired, without calling the backend', async () => {
    const first = await withAccount();
    await first.service.signIn('christina@example.com', 'pass-1234');
    first.repository.calls = [];

    const relaunched = new AuthService(first.repository, first.store, () => NOW + 3600 * 1000);
    expect(await relaunched.restoreSession()).toBeNull();
    expect(first.repository.calls).toEqual([]);
    expect(first.store.saved).toBeNull();
  });

  it('drops a saved session the backend rejects', async () => {
    const first = await withAccount();
    await first.service.signIn('christina@example.com', 'pass-1234');
    first.repository.validTokens.clear();

    const relaunched = new AuthService(first.repository, first.store, () => NOW + 1000);
    expect(await relaunched.restoreSession()).toBeNull();
    expect(first.store.saved).toBeNull();
  });

  it('keeps the saved session when the backend cannot be reached (offline start)', async () => {
    const first = await withAccount();
    await first.service.signIn('christina@example.com', 'pass-1234');
    first.repository.offline = true;

    const relaunched = new AuthService(first.repository, first.store, () => NOW + 1000);
    expect((await relaunched.restoreSession())?.email).toBe('christina@example.com');
    expect(first.store.saved).not.toBeNull();
  });
});
