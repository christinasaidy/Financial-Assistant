/** Why a question could not be asked or a conversation opened. The data layer turns HTTP failures into these. */
export type AssistantErrorCode =
  /** The phone could not reach the backend, or the answer took too long. */
  | 'network'
  /** The backend refused, with a message to show (today's limit, still answering, ...). */
  | 'refused'
  /** Anything else. */
  | 'unexpected';

export class AssistantError extends Error {
  readonly code: AssistantErrorCode;

  constructor(code: AssistantErrorCode, message: string) {
    super(message);
    this.name = 'AssistantError';
    this.code = code;
  }
}
