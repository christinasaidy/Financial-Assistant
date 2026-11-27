/**
 * Composition root: the one place that builds the concrete classes and connects them. It is the only file
 * allowed to import from a feature's data/ folder (the architecture test checks this). Screens get services
 * from here through providers and hooks, never by building them.
 *
 * A feature adds itself by building its repository and service below and adding the service to Container.
 */
import { apiBaseUrl, createHttpClient } from '@/shared/api/httpClient';
import { SESSION_KEY, secureValue } from '@/shared/storage/tokenStore';

import { AssistantService } from './features/assistant/application/assistantService';
import { ApiAssistantRepository } from './features/assistant/data/apiAssistantRepository';
import { AuthService } from './features/auth/application/authService';
import { BudgetsService } from './features/budgets/application/budgetsService';
import { ApiBudgetsRepository } from './features/budgets/data/apiBudgetsRepository';
import { ApiAuthRepository } from './features/auth/data/apiAuthRepository';
import { SecureTokenStore } from './features/auth/data/secureTokenStore';
import { HomeService } from './features/home/application/homeService';
import { ReceiptsService } from './features/receipts/application/receiptsService';
import { ApiReceiptsRepository } from './features/receipts/data/apiReceiptsRepository';
import { ScanService } from './features/scan/application/scanService';
import { ApiScanUploader } from './features/scan/data/apiScanUploader';
import { ApiHomeRepository } from './features/home/data/apiHomeRepository';

/** The services screens may use. Repositories and the HTTP client stay inside this file. */
export type Container = {
  auth: AuthService;
  home: HomeService;
  budgets: BudgetsService;
  assistant: AssistantService;
  receipts: ReceiptsService;
  scan: ScanService;
};

export function createContainer(): Container {
  // The client reads the token from the auth service on each request, and tells it when the token is
  // rejected. `auth` is assigned before any request can run.
  let auth: AuthService | null = null;
  const http = createHttpClient({
    baseUrl: apiBaseUrl,
    getToken: () => auth?.accessToken() ?? null,
    onUnauthorized: () => auth?.expireSession(),
  });

  auth = new AuthService(new ApiAuthRepository(http), new SecureTokenStore(secureValue(SESSION_KEY)));

  const home = new HomeService(new ApiHomeRepository(http));

  const budgets = new BudgetsService(new ApiBudgetsRepository(http));

  const assistant = new AssistantService(new ApiAssistantRepository(http));

  const receiptsRepository = new ApiReceiptsRepository(http);
  const receipts = new ReceiptsService(receiptsRepository);

  // Scan sends photos with its own uploader and reads, saves and checks receipts like the Receipts feature.
  const uploader = new ApiScanUploader(http);
  const scan = new ScanService({
    upload: (photo) => uploader.upload(photo),
    remove: (id) => uploader.remove(id),
    receipt: (id) => receiptsRepository.receipt(id),
    receipts: () => receiptsRepository.receipts(),
    categories: () => receiptsRepository.categories(),
    confirm: (id, payload) => receiptsRepository.confirm(id, payload),
    budgets: (month) => receiptsRepository.budgets(month),
    monthTotal: (month) => receiptsRepository.monthTotal(month),
  });

  return { auth, home, budgets, assistant, receipts, scan };
}

let instance: Container | null = null;

/** The app's container, built on first use. */
export function getContainer(): Container {
  instance ??= createContainer();
  return instance;
}
