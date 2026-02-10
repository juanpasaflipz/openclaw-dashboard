const links = {
  Product: [
    { label: "Features", href: "#features" },
    { label: "Channels", href: "#channels" },
    { label: "Providers", href: "#providers" },
    { label: "Pricing", href: "#pricing" },
  ],
  Resources: [
    { label: "Documentation", href: "https://docs.greenmonkey.dev" },
    { label: "API Reference", href: "https://docs.greenmonkey.dev" },
    { label: "Status", href: "https://app.greenmonkey.dev" },
  ],
  Company: [
    { label: "Dashboard", href: "https://app.greenmonkey.dev" },
    { label: "GitHub", href: "https://github.com/openclaw" },
    { label: "Contact", href: "mailto:hello@greenmonkey.dev" },
  ],
};

export default function Footer() {
  return (
    <footer className="border-t border-border py-16 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <div className="text-xl font-bold mb-2">
              <img src="/logo.webp" alt="" className="inline-block w-7 h-7 mr-1.5 align-middle" />Green Monkey
            </div>
            <p className="text-sm text-text-tertiary">
              AI agent management, simplified.
            </p>
          </div>

          {/* Link columns */}
          {Object.entries(links).map(([heading, items]) => (
            <div key={heading}>
              <h4 className="font-semibold text-sm mb-3 text-text-secondary">
                {heading}
              </h4>
              <ul className="space-y-2">
                {items.map((item) => (
                  <li key={item.label}>
                    <a
                      href={item.href}
                      className="text-sm text-text-tertiary hover:text-text-primary transition-colors"
                    >
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="border-t border-border pt-8 text-center text-sm text-text-tertiary">
          &copy; {new Date().getFullYear()} Green Monkey. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
