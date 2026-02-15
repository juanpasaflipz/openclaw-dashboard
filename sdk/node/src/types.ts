// ── Pagination ──────────────────────────────────────────────────────────────

export interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

export interface PaginationParams {
  page?: number;
  per_page?: number;
}

// ── Agents ──────────────────────────────────────────────────────────────────

export interface Agent {
  id: number;
  name: string;
  description: string | null;
  agent_type: "direct" | "external" | "nautilus";
  is_active: boolean;
  role?: string | null;
  personality?: string | null;
  llm_config?: Record<string, unknown> | null;
  identity_config?: Record<string, unknown> | null;
  last_connected_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentParams {
  name: string;
  description?: string;
  agent_type?: "direct" | "external" | "nautilus";
  personality?: string;
  llm_config?: Record<string, unknown>;
  identity_config?: Record<string, unknown>;
}

export interface UpdateAgentParams {
  name?: string;
  description?: string;
  personality?: string;
  is_active?: boolean;
  llm_config?: Record<string, unknown>;
  identity_config?: Record<string, unknown>;
}

export interface ListAgentsParams extends PaginationParams {
  is_active?: boolean;
  agent_type?: string;
}

// ── Tasks ───────────────────────────────────────────────────────────────────

export type TaskStatus =
  | "queued"
  | "running"
  | "blocked"
  | "completed"
  | "failed"
  | "canceled";

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  assigned_to_agent_id: number;
  created_by_agent_id: number | null;
  created_by_user_id: number | null;
  parent_task_id: string | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  priority: number;
  due_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskParams {
  title: string;
  assigned_to_agent_id: number;
  created_by_agent_id?: number;
  parent_task_id?: string;
  input?: Record<string, unknown>;
  priority?: number;
  due_at?: string;
  idempotency_key?: string;
}

export interface ListTasksParams extends PaginationParams {
  status?: TaskStatus;
  assigned_to_agent_id?: number;
  created_by_agent_id?: number;
  parent_task_id?: string;
}

export type TaskEventType =
  | "created"
  | "assigned"
  | "started"
  | "progress"
  | "tool_call"
  | "tool_result"
  | "completed"
  | "failed"
  | "escalated"
  | "blocked"
  | "canceled";

export interface TaskEvent {
  id: number;
  task_id: string;
  agent_id: number | null;
  event_type: TaskEventType;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ListTaskEventsParams extends PaginationParams {
  event_type?: TaskEventType;
  agent_id?: number;
}

// ── Messages ────────────────────────────────────────────────────────────────

export interface Message {
  id: number;
  task_id: string | null;
  thread_id: string | null;
  from_agent_id: number | null;
  to_agent_id: number | null;
  from_user_id: number | null;
  role: "system" | "agent" | "user";
  content: string;
  created_at: string;
}

export interface SendMessageParams {
  content: string;
  from_agent_id?: number;
  to_agent_id?: number;
  task_id?: string;
  thread_id?: string;
  idempotency_key?: string;
}

export interface ListMessagesParams extends PaginationParams {
  task_id?: string;
  thread_id?: string;
  agent_id?: number;
}

// ── Governance ──────────────────────────────────────────────────────────────

export type GovernanceRequestStatus =
  | "pending"
  | "approved"
  | "denied"
  | "expired"
  | "applied";

export interface PolicyChangeRequest {
  id: number;
  agent_id: number;
  policy_id: number | null;
  status: GovernanceRequestStatus;
  requested_changes: Record<string, unknown>;
  reason: string;
  requested_at: string;
  expires_at: string | null;
  reviewed_at: string | null;
}

export interface CreatePolicyChangeRequestParams {
  agent_id: number;
  requested_changes: Record<string, unknown>;
  reason: string;
  policy_id?: number;
  idempotency_key?: string;
}

export interface ListGovernanceRequestsParams extends PaginationParams {
  status?: GovernanceRequestStatus;
  agent_id?: number;
}

export interface ApproveRequestParams {
  mode: "one_time" | "delegate";
  delegation_duration_minutes?: number;
  max_spend_delta?: string;
  max_model_upgrade?: string;
}

export interface DelegationGrant {
  id: number;
  agent_id: number;
  allowed_changes: Record<string, unknown>;
  max_spend_delta: string | null;
  valid_from: string;
  valid_to: string;
  active: boolean;
  revoked_at: string | null;
}

export interface ApplyDelegationParams {
  grant_id: number;
  agent_id: number;
  changes: Record<string, unknown>;
}

export interface ListDelegationsParams extends PaginationParams {
  agent_id?: number;
  active?: boolean;
}

export interface AuditEntry {
  id: number;
  agent_id: number | null;
  actor_id: number | null;
  event_type: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ListAuditParams extends PaginationParams {
  agent_id?: number;
  event_type?: string;
  from?: string;
  to?: string;
}

// ── Observability ───────────────────────────────────────────────────────────

export type ObsEventType =
  | "run_started"
  | "run_finished"
  | "action_started"
  | "action_finished"
  | "tool_call"
  | "tool_result"
  | "llm_call"
  | "error"
  | "metric"
  | "heartbeat";

export type ObsEventStatus = "success" | "error" | "info";

export interface ObsEvent {
  uid: string;
  event_type: ObsEventType;
  status: ObsEventStatus;
  agent_id: number | null;
  run_id: string | null;
  model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface IngestEventParams {
  event_type: ObsEventType;
  status?: ObsEventStatus;
  agent_id?: number;
  run_id?: string;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  latency_ms?: number;
  payload?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface ListObsEventsParams extends PaginationParams {
  agent_id?: number;
  event_type?: ObsEventType;
  run_id?: string;
  status?: ObsEventStatus;
  from?: string;
  to?: string;
}

export type RunStatus = "running" | "success" | "error";

export interface ObsRun {
  run_id: string;
  agent_id: number | null;
  status: RunStatus;
  model: string | null;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  total_latency_ms: number;
  tool_calls_count: number;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface StartRunParams {
  agent_id?: number;
  model?: string;
  metadata?: Record<string, unknown>;
}

export interface FinishRunParams {
  status: "success" | "error";
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  latency_ms?: number;
  tool_calls_count?: number;
  error_message?: string;
}

export interface ListRunsParams extends PaginationParams {
  agent_id?: number;
  status?: RunStatus;
  from?: string;
  to?: string;
}

// ── Client Options ──────────────────────────────────────────────────────────

export interface ClientOptions {
  apiKey: string;
  baseUrl: string;
  maxRetries?: number;
  timeoutMs?: number;
}

// ── API Response Wrappers ───────────────────────────────────────────────────

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
