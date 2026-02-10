const offerings = [
  {
    icon: "📦",
    title: "Open-source core",
    description:
      "The agent framework, planning engine, and approval system are fully open-source. Inspect every line.",
  },
  {
    icon: "☁️",
    title: "Hosted SaaS for teams",
    description:
      "Don't want to manage infrastructure? Our hosted version handles deployment, scaling, and updates.",
  },
  {
    icon: "🔓",
    title: "No lock-in",
    description:
      "Export your data, switch providers, or self-host anytime. Your agents and configs are portable.",
  },
];

export default function OpenCore() {
  return (
    <section className="py-24 px-4" id="open-core">
      <div className="max-w-4xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-bold mb-4">
          Run it yourself. Or let us run it better.
        </h2>
        <p className="text-text-secondary mb-16 max-w-xl mx-auto">
          Open-core means you always have a way out. And a reason to stay.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-12">
          {offerings.map((item) => (
            <div key={item.title} className="glass-card p-6 text-left">
              <div className="text-3xl mb-3">{item.icon}</div>
              <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">
                {item.description}
              </p>
            </div>
          ))}
        </div>

        <a
          href="https://app.greenmonkey.dev"
          className="btn-primary text-lg px-10 py-4"
        >
          Get Started
        </a>
      </div>
    </section>
  );
}
