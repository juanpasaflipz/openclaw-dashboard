import type { HttpClient } from "./client";
import type {
  Message,
  SendMessageParams,
  ListMessagesParams,
  Pagination,
} from "./types";

export class MessagesResource {
  constructor(private readonly http: HttpClient) {}

  async send(params: SendMessageParams): Promise<Message> {
    const res = await this.http.post<{ message: Message }>(
      "/messages",
      params
    );
    return res.message;
  }

  async list(
    params: ListMessagesParams
  ): Promise<{ messages: Message[]; pagination: Pagination }> {
    return this.http.get("/messages", params);
  }
}
