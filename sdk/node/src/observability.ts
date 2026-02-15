import type { HttpClient } from "./client";
import type {
  ObsEvent,
  IngestEventParams,
  ListObsEventsParams,
  ObsRun,
  StartRunParams,
  FinishRunParams,
  ListRunsParams,
  Pagination,
} from "./types";

export class ObservabilityResource {
  constructor(private readonly http: HttpClient) {}

  // ── Events ──────────────────────────────────────────────────────────────

  async ingestEvent(params: IngestEventParams): Promise<ObsEvent> {
    const res = await this.http.post<{ event: ObsEvent }>(
      "/observability/events",
      params
    );
    return res.event;
  }

  async ingestBatch(
    events: IngestEventParams[]
  ): Promise<{ accepted: number; rejected: unknown[] }> {
    return this.http.post("/observability/events/batch", { events });
  }

  async listEvents(
    params?: ListObsEventsParams
  ): Promise<{ events: ObsEvent[]; pagination: Pagination }> {
    return this.http.get("/observability/events", params);
  }

  // ── Runs ────────────────────────────────────────────────────────────────

  async startRun(params?: StartRunParams): Promise<ObsRun> {
    const res = await this.http.post<{ run: ObsRun }>(
      "/observability/runs",
      params
    );
    return res.run;
  }

  async finishRun(runId: string, params: FinishRunParams): Promise<ObsRun> {
    const res = await this.http.post<{ run: ObsRun }>(
      `/observability/runs/${runId}/finish`,
      params
    );
    return res.run;
  }

  async listRuns(
    params?: ListRunsParams
  ): Promise<{ runs: ObsRun[]; pagination: Pagination }> {
    return this.http.get("/observability/runs", params);
  }

  async getRun(
    runId: string
  ): Promise<{ run: ObsRun; events: ObsEvent[] }> {
    return this.http.get(`/observability/runs/${runId}`);
  }
}
