import { ApiAuthRepository, toUser } from '@/features/auth/data/apiAuthRepository';
import { createHttpClient } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';

function repositoryWith(...replies: Parameters<typeof fetchMock>) {
  const { fetchFn, requests } = fetchMock(...replies);
  const http = createHttpClient({
    baseUrl: 'http://192.168.1.23:8000',
    getToken: () => null,
    onUnauthorized: () => undefined,
    fetchFn,
  });
  return { repository: new ApiAuthRepository(http), requests };
}

const userDto = { id: 7, email: 'christina@example.com', first_name: 'Christina', gender: 'female' };

describe('toUser', () => {
  it('maps snake_case to the domain User', () => {
    expect(toUser(userDto)).toEqual({ id: 7, email: 'christina@example.com', firstName: 'Christina', gender: 'female' });
  });

  it('accepts old accounts with no name or gender, and unknown genders', () => {
    expect(toUser({ id: 1, email: 'a@b.c', first_name: null, gender: null })).toMatchObject({
      firstName: null,
      gender: null,
    });
    expect(toUser({ id: 1, email: 'a@b.c' })).toMatchObject({ firstName: null, gender: null });
    expect(toUser({ id: 1, email: 'a@b.c', gender: 'other' }).gender).toBeNull();
  });
});

describe('ApiAuthRepository', () => {
  it('register sends first_name and gender without a token', async () => {
    const { repository, requests } = repositoryWith({ status: 201, body: userDto });
    const user = await repository.register({
      email: 'christina@example.com',
      password: 'pass-1234',
      firstName: 'Christina',
      gender: 'female',
    });
    expect(requests[0]).toMatchObject({
      url: 'http://192.168.1.23:8000/auth/register',
      method: 'POST',
      body: { email: 'christina@example.com', password: 'pass-1234', first_name: 'Christina', gender: 'female' },
    });
    expect(requests[0]?.headers.Authorization).toBeUndefined();
    expect(user.firstName).toBe('Christina');
  });

  it('login maps the token response', async () => {
    const { repository, requests } = repositoryWith({
      status: 200,
      body: { access_token: 'jwt', token_type: 'bearer', expires_in: 3600, user: userDto },
    });
    const result = await repository.login('christina@example.com', 'pass-1234');
    expect(requests[0]?.body).toEqual({ email: 'christina@example.com', password: 'pass-1234' });
    expect(result).toEqual({
      accessToken: 'jwt',
      expiresInSeconds: 3600,
      user: { id: 7, email: 'christina@example.com', firstName: 'Christina', gender: 'female' },
    });
  });

  it('currentUser calls /auth/me with the given token', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: userDto });
    await repository.currentUser('saved-token');
    expect(requests[0]).toMatchObject({ url: 'http://192.168.1.23:8000/auth/me', method: 'GET' });
    expect(requests[0]?.headers.Authorization).toBe('Bearer saved-token');
  });

  it.each([
    [401, 'invalid-credentials'],
    [409, 'email-taken'],
    [422, 'invalid-details'],
    [500, 'unexpected'],
  ])('turns HTTP %i into AuthError %s', async (status, code) => {
    const { repository } = repositoryWith({ status, body: { detail: 'Backend message' } });
    await expect(repository.login('a@b.c', 'x')).rejects.toMatchObject({ code, message: 'Backend message' });
  });

  it('turns an unreachable server into AuthError network', async () => {
    const { repository } = repositoryWith({ networkError: 'Network request failed' });
    await expect(repository.login('a@b.c', 'x')).rejects.toMatchObject({ code: 'network' });
  });
});
