import type { HttpClient } from "./client";
import type {
  PolicyChangeRequest,
  CreatePolicyChangeRequestParams,
  ListGovernanceRequestsParams,
  ApproveRequestParams,
  DelegationGrant,
  ApplyDelegationParams,
  ListDelegationsParams,
  AuditEntry,
  ListAuditParams,
  Pagination,
} from "./types";

export class GovernanceResource {
  constructor(private readonly http: HttpClient) {}

  // ── Policy Change Requests ──────────────────────────────────────────────

  async createRequest(
    params: CreatePolicyChangeRequestParams
  ): Promise<PolicyChangeRequest> {
    const res = await this.http.post<{ request: PolicyChangeRequest }>(
      "/governance/requests",
      params
    );
    return res.request;
  }

  async listRequests(
    params?: ListGovernanceRequestsParams
  ): Promise<{ requests: PolicyChangeRequest[]; pagination: Pagination }> {
    return this.http.get("/governance/requests", params);
  }

  async approve(
    requestId: number,
    params: ApproveRequestParams
  ): Promise<{
    request: PolicyChangeRequest;
    delegation_grant: DelegationGrant | null;
  }> {
    return this.http.post(
      `/governance/requests/${requestId}/approve`,
      params
    );
  }

  async deny(
    requestId: number,
    reason?: string
  ): Promise<PolicyChangeRequest> {
    const res = await this.http.post<{ request: PolicyChangeRequest }>(
      `/governance/requests/${requestId}/deny`,
      reason ? { reason } : undefined
    );
    return res.request;
  }

  // ── Delegations ─────────────────────────────────────────────────────────

  async listDelegations(
    params?: ListDelegationsParams
  ): Promise<{ delegations: DelegationGrant[]; pagination: Pagination }> {
    return this.http.get("/governance/delegations", params);
  }

  async revokeDelegation(
    grantId: number
  ): Promise<DelegationGrant> {
    const res = await this.http.post<{ grant: DelegationGrant } | DelegationGrant>(
      `/governance/delegations/${grantId}/revoke`
    );
    return "grant" in res ? res.grant : res;
  }

  async applyDelegation(
    params: ApplyDelegationParams
  ): Promise<Record<string, unknown>> {
    return this.http.post("/governance/delegations/apply", params);
  }

  // ── Audit Trail ─────────────────────────────────────────────────────────

  async listAudit(
    params?: ListAuditParams
  ): Promise<{ entries: AuditEntry[]; pagination: Pagination }> {
    return this.http.get("/governance/audit", params);
  }
}
