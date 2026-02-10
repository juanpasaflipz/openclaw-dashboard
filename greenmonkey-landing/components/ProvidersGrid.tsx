import { PROVIDERS } from "@/lib/constants";

export default function ProvidersGrid() {
  return (
    <section className="py-24 px-4" id="providers">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
          9 LLM Providers
        </h2>
        <p className="text-text-secondary text-center mb-16 max-w-2xl mx-auto">
          Bring your own API keys. Switch between providers anytime — no
          lock-in.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {PROVIDERS.map((provider) => (
            <div key={provider.name} className="glass-card p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="text-2xl">{provider.icon}</span>
                <span className="font-semibold">{provider.name}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {provider.models.map((model) => (
                  <span
                    key={model}
                    className="text-xs px-2 py-1 rounded-md bg-surface-light text-text-tertiary"
                  >
                    {model}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
