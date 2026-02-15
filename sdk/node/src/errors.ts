import type { ApiError } from "./types";

export class GreenMonkeyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GreenMonkeyError";
  }
}

export class ApiRequestError extends GreenMonkeyError {
  public readonly status: number;
  public readonly code: string;
  public readonly details: Record<string, unknown> | undefined;

  constructor(status: number, body: ApiError) {
    super(body.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  get retryable(): boolean {
    return this.status === 429 || this.status >= 500;
  }
}

export class NetworkError extends GreenMonkeyError {
  public readonly cause: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export class TimeoutError extends GreenMonkeyError {
  constructor(timeoutMs: number) {
    super(`Request timed out after ${timeoutMs}ms`);
    this.name = "TimeoutError";
  }
}
