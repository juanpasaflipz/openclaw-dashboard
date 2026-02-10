import { PRICING } from "@/lib/constants";

export default function PricingTable() {
  return (
    <section className="py-24 px-4" id="pricing">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
          Simple Pricing
        </h2>
        <p className="text-text-secondary text-center mb-16 max-w-2xl mx-auto">
          Start free, upgrade when you need more power.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Free tier */}
          <div className="glass-card p-8 flex flex-col">
            <h3 className="text-xl font-bold mb-1">{PRICING.free.name}</h3>
            <div className="mb-6">
              <span className="text-4xl font-bold">{PRICING.free.price}</span>
              <span className="text-text-tertiary ml-1">
                {PRICING.free.period}
              </span>
            </div>
            <ul className="space-y-3 mb-8 flex-1">
              {PRICING.free.features.map((f) => (
                <li
                  key={f}
                  className="flex items-start gap-2 text-sm text-text-secondary"
                >
                  <span className="text-success mt-0.5">&#10003;</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href={PRICING.free.ctaLink} className="btn-secondary w-full text-center">
              {PRICING.free.cta}
            </a>
          </div>

          {/* Pro tier */}
          <div className="glass-card p-8 flex flex-col border-primary/50 shadow-[0_0_30px_rgba(124,115,255,0.15)]">
            <div className="flex items-center gap-3 mb-1">
              <h3 className="text-xl font-bold">{PRICING.pro.name}</h3>
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary-light font-medium">
                {PRICING.pro.badge}
              </span>
            </div>
            <div className="mb-6">
              <span className="text-4xl font-bold">{PRICING.pro.price}</span>
              <span className="text-text-tertiary ml-1">
                {PRICING.pro.period}
              </span>
            </div>
            <ul className="space-y-3 mb-8 flex-1">
              {PRICING.pro.features.map((f) => (
                <li
                  key={f}
                  className="flex items-start gap-2 text-sm text-text-secondary"
                >
                  <span className="text-primary mt-0.5">&#10003;</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href={PRICING.pro.ctaLink} className="btn-primary w-full text-center">
              {PRICING.pro.cta}
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
