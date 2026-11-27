/** Why receipts could not load or a change could not be saved. The data layer turns HTTP failures into these. */
export type ReceiptsErrorCode = 'network' | 'refused' | 'unexpected';

export class ReceiptsError extends Error {
  readonly code: ReceiptsErrorCode;

  constructor(code: ReceiptsErrorCode, message: string) {
    super(message);
    this.name = 'ReceiptsError';
    this.code = code;
  }
}
