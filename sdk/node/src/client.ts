import type { ApiError, ClientOptions } from "./types";
import {
  ApiRequestError,
  NetworkError,
  TimeoutError,
  GreenMonkeyError,
} from "./errors";

const DEFAULT_MAX_RETRIES = 5;
const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_BACKOFF_MS = 30_000;
const BASE_DELAY_MS = 1_000;

export class HttpClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly maxRetries: number;
  private readonly timeoutMs: number;

  constructor(opts: ClientOptions) {
    if (!opts.apiKey) throw new GreenMonkeyError("apiKey is required");
    if (!opts.baseUrl) throw new GreenMonkeyError("baseUrl is required");

    this.apiKey = opts.apiKey;
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.maxRetries = opts.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  async get<T>(path: string, params?: object): Promise<T> {
    const url = this.buildUrl(path, params as Record<string, unknown>);
    return this.request<T>("GET", url);
  }

  async post<T>(path: string, body?: object): Promise<T> {
    const url = this.buildUrl(path);
    return this.request<T>("POST", url, body as Record<string, unknown>);
  }

  private buildUrl(path: string, params?: Record<string, unknown>): string {
    const url = new URL(`${this.baseUrl}/api/v1${path}`);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }
    }
    return url.toString();
  }

  private async request<T>(
    method: string,
    url: string,
    body?: Record<string, unknown>
  ): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      if (attempt > 0) {
        const delay = this.backoffDelay(attempt);
        await sleep(delay);
      }

      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);

        const headers: Record<string, string> = {
          Authorization: `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        };

        const res = await fetch(url, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timer);

        if (res.ok) {
          return (await res.json()) as T;
        }

        // Parse error body
        let errorBody: ApiError;
        try {
          const json = (await res.json()) as { error?: ApiError };
          errorBody = json.error ?? {
            code: "UNKNOWN",
            message: res.statusText,
          };
        } catch {
          errorBody = { code: "UNKNOWN", message: res.statusText };
        }

        const apiErr = new ApiRequestError(res.status, errorBody);

        // Only retry on 429 / 5xx
        if (!apiErr.retryable) {
          throw apiErr;
        }

        // Respect Retry-After header for 429
        if (res.status === 429) {
          const retryAfter = res.headers.get("Retry-After");
          if (retryAfter) {
            const waitSec = parseInt(retryAfter, 10);
            if (!isNaN(waitSec) && waitSec > 0) {
              await sleep(waitSec * 1000);
            }
          }
        }

        lastError = apiErr;
      } catch (err) {
        if (err instanceof ApiRequestError) {
          throw err; // Non-retryable API errors already thrown above
        }

        if (err instanceof DOMException && err.name === "AbortError") {
          lastError = new TimeoutError(this.timeoutMs);
        } else {
          lastError = new NetworkError(
            "Network request failed",
            err
          );
        }

        // Network/timeout errors are retryable
      }
    }

    throw lastError ?? new GreenMonkeyError("Request failed after retries");
  }

  private backoffDelay(attempt: number): number {
    const exponential = BASE_DELAY_MS * Math.pow(2, attempt - 1);
    const jitter = Math.random() * 1000;
    return Math.min(exponential + jitter, MAX_BACKOFF_MS);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
