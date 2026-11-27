/** Why Budgets could not load or save, in terms the screen can act on. The data layer turns HTTP failures into these. */
export type BudgetsErrorCode =
  /** The phone could not reach the backend. */
  | 'network'
  /** The backend refused the budget (a message it sends, e.g. an amount it cannot take). */
  | 'rejected'
  /** The backend answered with an error, or with something the app cannot read. */
  | 'unexpected';

export class BudgetsError extends Error {
  readonly code: BudgetsErrorCode;

  constructor(code: BudgetsErrorCode, message: string) {
    super(message);
    this.name = 'BudgetsError';
    this.code = code;
  }
}
