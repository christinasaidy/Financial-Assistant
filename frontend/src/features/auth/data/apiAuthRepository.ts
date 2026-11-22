import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import type { AuthRepository, SignInResult } from '../application/interfaces';
import { AuthError } from '../domain/errors';
import { isGender, type SignUpDetails, type User } from '../domain/types';

/** The backend's shapes (backend/app/api/auth/schemas.py), snake_case as sent over HTTP. */
export type UserDto = {
  id: number;
  email: string;
  first_name?: string | null;
  gender?: string | null;
};

export type TokenDto = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserDto;
};

export type RegisterBodyDto = {
  email: string;
  password: string;
  first_name: string;
  gender: string;
};

export function toUser(dto: UserDto): User {
  return {
    id: dto.id,
    email: dto.email,
    firstName: dto.first_name ?? null,
    gender: isGender(dto.gender) ? dto.gender : null,
  };
}

/** HTTP failure -> the auth error the screens understand (statuses from backend/app/api/error_handlers.py). */
export function toAuthError(error: unknown): AuthError {
  if (error instanceof AuthError) return error;
  if (error instanceof NetworkError) return new AuthError('network', error.message);
  if (error instanceof ApiError) {
    if (error.status === 401) return new AuthError('invalid-credentials', error.detail);
    if (error.status === 409) return new AuthError('email-taken', error.detail);
    if (error.status === 422 || error.status === 400) return new AuthError('invalid-details', error.detail);
    return new AuthError('unexpected', error.detail);
  }
  return new AuthError('unexpected', error instanceof Error ? error.message : String(error));
}

/** AuthRepository against the Fatourati backend: POST /auth/register, POST /auth/login, GET /auth/me. */
export class ApiAuthRepository implements AuthRepository {
  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  async register(details: SignUpDetails): Promise<User> {
    const body: RegisterBodyDto = {
      email: details.email,
      password: details.password,
      first_name: details.firstName,
      gender: details.gender,
    };
    try {
      return toUser(await this.http.request<UserDto>('/auth/register', { method: 'POST', body, auth: 'none' }));
    } catch (error) {
      throw toAuthError(error);
    }
  }

  async login(email: string, password: string): Promise<SignInResult> {
    try {
      const dto = await this.http.request<TokenDto>('/auth/login', {
        method: 'POST',
        body: { email, password },
        auth: 'none',
      });
      return { accessToken: dto.access_token, expiresInSeconds: dto.expires_in, user: toUser(dto.user) };
    } catch (error) {
      throw toAuthError(error);
    }
  }

  async currentUser(accessToken: string): Promise<User> {
    try {
      return toUser(await this.http.request<UserDto>('/auth/me', { auth: accessToken }));
    } catch (error) {
      throw toAuthError(error);
    }
  }
}
