import type { HttpClient } from "./client";
import type {
  Agent,
  CreateAgentParams,
  UpdateAgentParams,
  ListAgentsParams,
  Pagination,
} from "./types";

export class AgentsResource {
  constructor(private readonly http: HttpClient) {}

  async list(
    params?: ListAgentsParams
  ): Promise<{ agents: Agent[]; pagination: Pagination }> {
    return this.http.get("/agents", params);
  }

  async get(agentId: number): Promise<Agent> {
    const res = await this.http.get<{ agent: Agent }>(`/agents/${agentId}`);
    return res.agent ?? (res as unknown as Agent);
  }

  async create(params: CreateAgentParams): Promise<Agent> {
    const res = await this.http.post<{ agent: Agent } | Agent>(
      "/agents",
      params
    );
    return "agent" in res ? res.agent : res;
  }

  async update(agentId: number, params: UpdateAgentParams): Promise<Agent> {
    const res = await this.http.post<{ agent: Agent } | Agent>(
      `/agents/${agentId}`,
      params
    );
    return "agent" in res ? res.agent : res;
  }

  async delete(agentId: number): Promise<{ deleted: boolean; agent_id: number }> {
    return this.http.post(`/agents/${agentId}/delete`);
  }
}
