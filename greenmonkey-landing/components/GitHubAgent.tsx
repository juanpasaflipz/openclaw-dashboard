const steps = [
  { icon: "🔍", label: "Issue analysis" },
  { icon: "📋", label: "Step-by-step plan" },
  { icon: "💻", label: "Code draft" },
  { icon: "🔀", label: "Pull request" },
  { icon: "💬", label: "Summary comment" },
];

export default function GitHubAgent() {
  return (
    <section className="py-24 px-4" id="github-agent">
      <div className="max-w-5xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Left: copy */}
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/10 text-xs text-primary-light font-medium mb-6">
              FLAGSHIP USE CASE
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Meet the Autonomous GitHub Agent
            </h2>
            <p className="text-text-secondary leading-relaxed mb-8">
              An agent that reads issues, proposes solutions, drafts PRs &mdash;
              but never merges without approval. Real work, real safety.
            </p>

            <div className="space-y-4 mb-8">
              {steps.map((step, i) => (
                <div key={step.label} className="flex items-center gap-4">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-surface-light text-sm">
                    {step.icon}
                  </span>
                  <span className="text-text-secondary font-medium">
                    {step.label}
                  </span>
                  {i < steps.length - 1 && (
                    <span className="text-border ml-auto hidden sm:block">
                      &rarr;
                    </span>
                  )}
                </div>
              ))}
            </div>

            <a
              href="https://app.greenmonkey.dev"
              className="btn-primary inline-flex"
            >
              Watch the demo (3 min)
            </a>
          </div>

          {/* Right: visual card */}
          <div className="glass-card p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center text-xl">
                🐙
              </div>
              <div>
                <div className="font-semibold text-text-primary">
                  Nautilus Agent
                </div>
                <div className="text-xs text-text-tertiary">
                  github/your-repo &middot; Issue #42
                </div>
              </div>
              <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-success/20 text-success font-medium">
                Awaiting Approval
              </span>
            </div>

            <div className="space-y-3 text-sm">
              <div className="p-3 rounded-lg bg-bg border border-border">
                <div className="text-text-tertiary text-xs mb-1">
                  Plan
                </div>
                <div className="text-text-secondary">
                  1. Parse issue requirements<br />
                  2. Create feature branch<br />
                  3. Implement auth middleware<br />
                  4. Add unit tests<br />
                  5. Open PR with summary
                </div>
              </div>

              <div className="p-3 rounded-lg bg-bg border border-border">
                <div className="text-text-tertiary text-xs mb-1">
                  Proposed Action
                </div>
                <div className="text-text-secondary">
                  Open PR <span className="text-primary">#43</span> &mdash;
                  &ldquo;Add JWT auth middleware with rate limiting&rdquo;
                </div>
              </div>

              <div className="flex gap-2 pt-2">
                <button className="flex-1 py-2 rounded-md bg-success/20 text-success text-sm font-medium border border-success/30">
                  Approve
                </button>
                <button className="flex-1 py-2 rounded-md bg-surface-light text-text-tertiary text-sm font-medium border border-border">
                  Reject
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
