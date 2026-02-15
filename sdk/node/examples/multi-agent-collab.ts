/**
 * Multi-Agent Collaboration Example
 *
 * Demonstrates a research pipeline where:
 *  1. A "Coordinator" agent creates tasks
 *  2. A "Researcher" agent performs research
 *  3. A "Writer" agent produces the final report
 *  4. Agents communicate via messages
 *  5. Observability events are emitted throughout
 *  6. A governance request is submitted when budget is exceeded
 *
 * Usage:
 *   export GM_API_KEY="gm_your_key_here"
 *   export GM_BASE_URL="http://localhost:5000"   # or your deployed URL
 *   npx tsx examples/multi-agent-collab.ts
 */

import { GreenMonkeyClient, ApiRequestError } from "../src";

const API_KEY = process.env.GM_API_KEY ?? "gm_test_key";
const BASE_URL = process.env.GM_BASE_URL ?? "http://localhost:5000";

const gm = new GreenMonkeyClient({ apiKey: API_KEY, baseUrl: BASE_URL });

function log(label: string, data: unknown) {
  console.log(`\n[$${label}]`, JSON.stringify(data, null, 2));
}

async function main() {
  console.log("=== Green Monkey Multi-Agent Collaboration Demo ===\n");

  // ── Step 1: Register agents ───────────────────────────────────────────

  console.log("--- Registering agents ---");

  const coordinator = await gm.registerAgent({
    name: "Coordinator",
    description: "Orchestrates research tasks and distributes work",
    agent_type: "external",
    personality: "Efficient project manager who breaks down complex work",
  });
  log("Coordinator registered", { id: coordinator.id, name: coordinator.name });

  const researcher = await gm.registerAgent({
    name: "Researcher",
    description: "Performs deep research and gathers data",
    agent_type: "external",
    personality: "Thorough and methodical researcher",
  });
  log("Researcher registered", { id: researcher.id, name: researcher.name });

  const writer = await gm.registerAgent({
    name: "Writer",
    description: "Synthesizes research into polished reports",
    agent_type: "external",
    personality: "Clear and concise technical writer",
  });
  log("Writer registered", { id: writer.id, name: writer.name });

  // ── Step 2: Start an observability run ────────────────────────────────

  console.log("\n--- Starting observability run ---");

  const run = await gm.observability.startRun({
    agent_id: coordinator.id,
    model: "gpt-4o",
    metadata: { pipeline: "quarterly-report" },
  });
  log("Run started", { run_id: run.run_id });

  // ── Step 3: Coordinator creates a research task ───────────────────────

  console.log("\n--- Creating research task ---");

  const researchTask = await gm.createTask({
    title: "Research Q4 2025 earnings for top 5 tech companies",
    assigned_to_agent_id: researcher.id,
    created_by_agent_id: coordinator.id,
    input: {
      companies: ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
      focus_areas: ["revenue", "operating_income", "guidance"],
    },
    priority: 1,
  });
  log("Research task created", {
    id: researchTask.id,
    status: researchTask.status,
  });

  // Emit an event for the task creation
  await gm.emitEvent({
    event_type: "action_started",
    status: "info",
    agent_id: coordinator.id,
    run_id: run.run_id,
    payload: { action: "create_research_task", task_id: researchTask.id },
  });

  // ── Step 4: Coordinator sends instructions to the researcher ──────────

  console.log("\n--- Sending instructions to researcher ---");

  const msg1 = await gm.sendMessage({
    from_agent_id: coordinator.id,
    to_agent_id: researcher.id,
    task_id: researchTask.id,
    content:
      "Please focus on YoY growth rates and any forward guidance changes. " +
      "Deliver results as structured JSON with one entry per company.",
  });
  log("Message sent", { id: msg1.id, to: researcher.id });

  // ── Step 5: Researcher starts and completes the task ──────────────────

  console.log("\n--- Researcher starts task ---");

  const startedTask = await gm.tasks.start(researchTask.id);
  log("Task started", { status: startedTask.status });

  await gm.emitEvent({
    event_type: "llm_call",
    status: "success",
    agent_id: researcher.id,
    run_id: run.run_id,
    model: "gpt-4o",
    tokens_in: 2500,
    tokens_out: 4200,
    cost_usd: 0.08,
    latency_ms: 3200,
    payload: { task_id: researchTask.id, step: "research" },
  });

  // Researcher replies with findings
  await gm.sendMessage({
    from_agent_id: researcher.id,
    to_agent_id: coordinator.id,
    task_id: researchTask.id,
    content: JSON.stringify({
      AAPL: { revenue_yoy: "+8%", guidance: "strong" },
      MSFT: { revenue_yoy: "+12%", guidance: "raised" },
      GOOGL: { revenue_yoy: "+14%", guidance: "maintained" },
      AMZN: { revenue_yoy: "+11%", guidance: "raised" },
      META: { revenue_yoy: "+22%", guidance: "raised" },
    }),
  });

  const completedResearch = await gm.tasks.complete(researchTask.id, {
    summary: "All 5 companies showed positive YoY revenue growth (8-22%)",
    companies_analyzed: 5,
  });
  log("Research task completed", { status: completedResearch.status });

  // ── Step 6: Coordinator creates a writing task ────────────────────────

  console.log("\n--- Creating writing task ---");

  const writeTask = await gm.createTask({
    title: "Write Q4 2025 tech earnings summary report",
    assigned_to_agent_id: writer.id,
    created_by_agent_id: coordinator.id,
    parent_task_id: researchTask.id,
    input: {
      research_task_id: researchTask.id,
      format: "markdown",
      max_words: 1500,
    },
  });
  log("Writing task created", { id: writeTask.id });

  await gm.sendMessage({
    from_agent_id: coordinator.id,
    to_agent_id: writer.id,
    task_id: writeTask.id,
    content:
      "Synthesize the research findings into a concise executive summary. " +
      "Include a comparison table and highlight any standout performers.",
  });

  // Writer completes the task
  await gm.tasks.start(writeTask.id);
  await gm.emitEvent({
    event_type: "llm_call",
    status: "success",
    agent_id: writer.id,
    run_id: run.run_id,
    model: "gpt-4o",
    tokens_in: 3000,
    tokens_out: 2800,
    cost_usd: 0.07,
    latency_ms: 2800,
  });

  await gm.tasks.complete(writeTask.id, {
    report:
      "# Q4 2025 Tech Earnings Summary\n\n" +
      "All five major tech companies reported positive YoY revenue growth...\n" +
      "META led with +22% growth, while AAPL showed the most modest gains at +8%.",
    word_count: 1200,
  });

  console.log("\n--- Writing task completed ---");

  // ── Step 7: Submit a governance request ───────────────────────────────

  console.log("\n--- Submitting governance request ---");

  const policyRequest = await gm.requestPolicyChange({
    agent_id: researcher.id,
    requested_changes: {
      daily_spend_cap: "25.00",
    },
    reason:
      "Need higher daily spend cap for upcoming quarterly deep-dive analysis " +
      "covering 20+ companies instead of the usual 5.",
  });
  log("Policy change request submitted", {
    id: policyRequest.id,
    status: policyRequest.status,
  });

  // ── Step 8: Finish the observability run ──────────────────────────────

  console.log("\n--- Finishing observability run ---");

  const finishedRun = await gm.observability.finishRun(run.run_id, {
    status: "success",
    tokens_in: 5500,
    tokens_out: 7000,
    cost_usd: 0.15,
    latency_ms: 6000,
    tool_calls_count: 0,
  });
  log("Run finished", {
    run_id: finishedRun.run_id,
    status: finishedRun.status,
  });

  // ── Step 9: Query the results ─────────────────────────────────────────

  console.log("\n--- Querying task history ---");

  const { tasks } = await gm.tasks.list({
    created_by_agent_id: coordinator.id,
  });
  log(
    "Tasks created by coordinator",
    tasks.map((t) => ({ id: t.id, title: t.title, status: t.status }))
  );

  const { messages } = await gm.messages.list({
    task_id: researchTask.id,
  });
  log(
    "Messages on research task",
    messages.map((m) => ({
      from: m.from_agent_id,
      to: m.to_agent_id,
      preview: m.content.slice(0, 80),
    }))
  );

  // ── Done ──────────────────────────────────────────────────────────────

  console.log("\n=== Demo complete! ===\n");
  console.log(
    "This example demonstrated:\n" +
      "  - Agent registration (3 agents)\n" +
      "  - Task creation and lifecycle (queued -> running -> completed)\n" +
      "  - Inter-agent messaging\n" +
      "  - Observability event ingestion and run tracking\n" +
      "  - Governance policy change requests\n" +
      "  - Idempotency keys on all write operations\n" +
      "  - Automatic retries with backoff (built into the client)\n"
  );
}

main().catch((err) => {
  if (err instanceof ApiRequestError) {
    console.error(`\nAPI Error [${err.status}] ${err.code}: ${err.message}`);
    if (err.details) console.error("Details:", err.details);
  } else {
    console.error("\nUnexpected error:", err);
  }
  process.exit(1);
});
