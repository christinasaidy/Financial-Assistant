import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { AuthService } from '@/features/auth/application/authService';
import { SessionProvider, useSession } from '@/features/auth/ui/SessionProvider';

import { FakeAuthRepository, FakeTokenStore } from './fakes';

async function setup() {
  const repository = new FakeAuthRepository();
  await repository.register({ email: 'maya@example.com', password: 'pass-1234', firstName: 'Maya', gender: 'female' });
  const service = new AuthService(repository, new FakeTokenStore());
  const wrapper = ({ children }: { children: ReactNode }) => (
    <SessionProvider authService={service}>{children}</SessionProvider>
  );
  const { result } = await renderHook(() => useSession(), { wrapper });
  return { service, result };
}

describe('SessionProvider', () => {
  it('goes from loading to signed out, then follows sign in, a 401 and sign out', async () => {
    const { service, result } = await setup();
    await waitFor(() => expect(result.current.status).toBe('signedOut'));

    await act(() => result.current.signIn('maya@example.com', 'pass-1234'));
    expect(result.current.status).toBe('signedIn');
    expect(result.current.user?.firstName).toBe('Maya');

    await act(async () => service.expireSession());
    expect(result.current).toMatchObject({ status: 'signedOut', user: null });

    await act(() => result.current.signIn('maya@example.com', 'pass-1234'));
    await act(() => result.current.signOut());
    expect(result.current.status).toBe('signedOut');
  });

  it('refuses to be used outside the provider', async () => {
    jest.spyOn(console, 'error').mockImplementation(() => undefined);
    await expect(renderHook(() => useSession())).rejects.toThrow('useSession must be used inside <SessionProvider>');
  });
});
