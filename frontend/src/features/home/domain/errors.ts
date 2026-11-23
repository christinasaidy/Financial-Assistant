/** Why Home could not load, in terms the screen can act on. The data layer turns HTTP failures into these. */
export type HomeErrorCode =
  /** The phone could not reach the backend. */
  | 'network'
  /** The backend answered with an error, or with something Home cannot read. */
  | 'unexpected';

export class HomeError extends Error {
  readonly code: HomeErrorCode;

  constructor(code: HomeErrorCode, message: string) {
    super(message);
    this.name = 'HomeError';
    this.code = code;
  }
}
