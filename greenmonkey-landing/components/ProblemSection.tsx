const problems = [
  {
    icon: "💬",
    text: "Chatbots don't execute",
  },
  {
    icon: "🔧",
    text: "Automation tools break silently",
  },
  {
    icon: "🤖",
    text: "Autonomous agents feel risky",
  },
  {
    icon: "🛡️",
    text: "Guardrails are bolted on too late",
  },
];

export default function ProblemSection() {
  return (
    <section className="py-24 px-4">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-3xl sm:text-4xl font-bold text-center mb-12">
          AI can think. It just can&apos;t act &mdash;{" "}
          <span className="text-text-tertiary">safely.</span>
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-12">
          {problems.map((problem) => (
            <div
              key={problem.text}
              className="glass-card p-5 flex items-center gap-4"
            >
              <span className="text-2xl flex-shrink-0">{problem.icon}</span>
              <span className="text-text-secondary font-medium">
                {problem.text}
              </span>
            </div>
          ))}
        </div>

        <p className="text-center text-xl font-semibold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
          Green Monkey was built to fix this.
        </p>
      </div>
    </section>
  );
}
