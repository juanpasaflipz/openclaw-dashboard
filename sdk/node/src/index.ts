import { HttpClient } from "./client";
import { AgentsResource } from "./agents";
import { TasksResource } from "./tasks";
import { MessagesResource } from "./messages";
import { GovernanceResource } from "./governance";
import { ObservabilityResource } from "./observability";
import type {
  ClientOptions,
  Agent,
  CreateAgentParams,
  Task,
  CreateTaskParams,
  Message,
  SendMessageParams,
  ObsEvent,
  IngestEventParams,
  PolicyChangeRequest,
  CreatePolicyChangeRequestParams,
} from "./types";

export class GreenMonkeyClient {
  public readonly agents: AgentsResource;
  public readonly tasks: TasksResource;
  public readonly messages: MessagesResource;
  public readonly governance: GovernanceResource;
  public readonly observability: ObservabilityResource;

  private readonly http: HttpClient;
  private idempotencyCounter = 0;

  constructor(opts: ClientOptions) {
    this.http = new HttpClient(opts);
    this.agents = new AgentsResource(this.http);
    this.tasks = new TasksResource(this.http);
    this.messages = new MessagesResource(this.http);
    this.governance = new GovernanceResource(this.http);
    this.observability = new ObservabilityResource(this.http);
  }

  // ── Convenience Helpers ───────────────────────────────────────────────

  /**
   * Register a new agent and return it. Generates an idempotency-safe name
   * so repeated calls with the same params are safe.
   */
  async registerAgent(params: CreateAgentParams): Promise<Agent> {
    return this.agents.create(params);
  }

  /**
   * Create a task with an auto-generated idempotency key (if not provided).
   */
  async createTask(
    params: Omit<CreateTaskParams, "idempotency_key"> & {
      idempotency_key?: string;
    }
  ): Promise<Task> {
    return this.tasks.create({
      ...params,
      idempotency_key: params.idempotency_key ?? this.generateIdempotencyKey("task"),
    });
  }

  /**
   * Send a message with an auto-generated idempotency key (if not provided).
   */
  async sendMessage(
    params: Omit<SendMessageParams, "idempotency_key"> & {
      idempotency_key?: string;
    }
  ): Promise<Message> {
    return this.messages.send({
      ...params,
      idempotency_key: params.idempotency_key ?? this.generateIdempotencyKey("msg"),
    });
  }

  /**
   * Emit an observability event with an auto-generated idempotency key (if not provided).
   */
  async emitEvent(
    params: Omit<IngestEventParams, "idempotency_key"> & {
      idempotency_key?: string;
    }
  ): Promise<ObsEvent> {
    return this.observability.ingestEvent({
      ...params,
      idempotency_key: params.idempotency_key ?? this.generateIdempotencyKey("evt"),
    });
  }

  /**
   * Submit a governance policy change request with an auto-generated
   * idempotency key (if not provided).
   */
  async requestPolicyChange(
    params: Omit<CreatePolicyChangeRequestParams, "idempotency_key"> & {
      idempotency_key?: string;
    }
  ): Promise<PolicyChangeRequest> {
    return this.governance.createRequest({
      ...params,
      idempotency_key: params.idempotency_key ?? this.generateIdempotencyKey("gov"),
    });
  }

  private generateIdempotencyKey(prefix: string): string {
    this.idempotencyCounter++;
    const ts = Date.now();
    const rand = Math.random().toString(36).slice(2, 8);
    return `${prefix}-${ts}-${rand}-${this.idempotencyCounter}`;
  }
}

// Re-export everything consumers need
export type * from "./types";
export {
  GreenMonkeyError,
  ApiRequestError,
  NetworkError,
  TimeoutError,
} from "./errors";
export { AgentsResource } from "./agents";
export { TasksResource } from "./tasks";
export { MessagesResource } from "./messages";
export { GovernanceResource } from "./governance";
export { ObservabilityResource } from "./observability";
