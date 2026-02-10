export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden px-4">
      {/* Background gradient orbs */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-[128px] animate-glow" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-secondary/20 rounded-full blur-[128px] animate-glow [animation-delay:1.5s]" />
      </div>

      <div className="max-w-4xl mx-auto text-center animate-fade-in">
        {/* Beta badge */}
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-primary/40 bg-primary/10 text-sm text-primary-light mb-8">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          BETA
        </div>

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold mb-6 tracking-tight leading-tight">
          <span className="text-text-primary">Autonomous AI agents that </span>
          <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
            actually do work
          </span>
          <span className="text-text-primary"> &mdash; safely.</span>
        </h1>

        {/* Subheadline */}
        <p className="text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto mb-10 leading-relaxed">
          Green Monkey lets you deploy AI agents that plan, execute approved
          actions, and report back transparently. No black boxes. No runaway
          automation.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <a
            href="https://app.greenmonkey.dev"
            className="btn-primary text-lg px-8 py-3.5"
          >
            Try the GitHub Agent Demo
          </a>
          <a
            href="https://github.com/juanpasaflipz/openclaw-dashboard"
            className="btn-secondary text-lg px-8 py-3.5"
          >
            Run Locally
          </a>
        </div>
      </div>
    </section>
  );
}
