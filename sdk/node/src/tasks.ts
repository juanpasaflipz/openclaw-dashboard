import type { HttpClient } from "./client";
import type {
  Task,
  CreateTaskParams,
  ListTasksParams,
  TaskEvent,
  ListTaskEventsParams,
  Pagination,
} from "./types";

export class TasksResource {
  constructor(private readonly http: HttpClient) {}

  async create(params: CreateTaskParams): Promise<Task> {
    const res = await this.http.post<{ task: Task }>("/tasks", params);
    return res.task;
  }

  async list(
    params?: ListTasksParams
  ): Promise<{ tasks: Task[]; pagination: Pagination }> {
    return this.http.get("/tasks", params);
  }

  async get(taskId: string): Promise<{ task: Task; events: TaskEvent[] }> {
    return this.http.get(`/tasks/${taskId}`);
  }

  async start(taskId: string): Promise<Task> {
    const res = await this.http.post<{ task: Task }>(`/tasks/${taskId}/start`);
    return res.task;
  }

  async complete(
    taskId: string,
    output: Record<string, unknown>
  ): Promise<Task> {
    const res = await this.http.post<{ task: Task }>(`/tasks/${taskId}/complete`, {
      output,
    });
    return res.task;
  }

  async fail(taskId: string, errorMessage: string): Promise<Task> {
    const res = await this.http.post<{ task: Task }>(`/tasks/${taskId}/fail`, {
      error_message: errorMessage,
    });
    return res.task;
  }

  async cancel(taskId: string): Promise<Task> {
    const res = await this.http.post<{ task: Task }>(`/tasks/${taskId}/cancel`);
    return res.task;
  }

  async assign(taskId: string, assignedToAgentId: number): Promise<Task> {
    const res = await this.http.post<{ task: Task }>(`/tasks/${taskId}/assign`, {
      assigned_to_agent_id: assignedToAgentId,
    });
    return res.task;
  }

  async listEvents(
    taskId: string,
    params?: ListTaskEventsParams
  ): Promise<{ events: TaskEvent[]; pagination: Pagination }> {
    return this.http.get(`/tasks/${taskId}/events`, params);
  }
}
