const steps = [
  {
    number: "1",
    title: "Observe",
    description: "Gather inputs, context, and current state from connected services.",
    icon: "👁️",
  },
  {
    number: "2",
    title: "Reason",
    description: "Structured planning with step-by-step breakdown of what needs to happen.",
    icon: "🧠",
  },
  {
    number: "3",
    title: "Approve",
    description: "Human-in-the-loop review. Every action requires explicit approval before execution.",
    icon: "✅",
  },
  {
    number: "4",
    title: "Execute",
    description: "Permissioned actions with scoped access. Only does what you've allowed.",
    icon: "⚡",
  },
];

export default function HowItWorks() {
  return (
    <section className="py-24 px-4" id="how-it-works">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
          Think &rarr; Plan &rarr; Approve &rarr; Act &rarr; Report
        </h2>
        <p className="text-text-secondary text-center mb-16 max-w-2xl mx-auto">
          A simple mental model for safe autonomy.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step) => (
            <div key={step.title} className="glass-card p-6 relative">
              <div className="flex items-center gap-3 mb-4">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/20 text-primary text-sm font-bold">
                  {step.number}
                </span>
                <span className="text-2xl">{step.icon}</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{step.title}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
