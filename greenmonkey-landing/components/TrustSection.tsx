const trustPoints = [
  {
    icon: "🔑",
    title: "Explicit permissions",
    description:
      "Agents only access what you grant. Scoped credentials, no ambient authority.",
  },
  {
    icon: "✅",
    title: "Action-level approvals",
    description:
      "Every side-effect requires human sign-off before execution. Nothing runs silently.",
  },
  {
    icon: "📜",
    title: "Full audit trails",
    description:
      "Every decision, plan, and execution is logged and reviewable. Complete transparency.",
  },
  {
    icon: "💻",
    title: "Local-first option",
    description:
      "Run entirely on your infrastructure. Your data never has to leave your network.",
  },
];

export default function TrustSection() {
  return (
    <section className="py-24 px-4" id="trust">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
          Why You Can Trust It
        </h2>
        <p className="text-text-secondary text-center mb-16 max-w-xl mx-auto">
          Safety isn&apos;t a feature. It&apos;s the architecture.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-12">
          {trustPoints.map((point) => (
            <div key={point.title} className="glass-card p-6">
              <div className="text-3xl mb-3">{point.icon}</div>
              <h3 className="text-lg font-semibold mb-2">{point.title}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">
                {point.description}
              </p>
            </div>
          ))}
        </div>

        <p className="text-center text-xl font-semibold text-text-primary">
          Autonomy is{" "}
          <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
            earned
          </span>
          , not assumed.
        </p>
      </div>
    </section>
  );
}
