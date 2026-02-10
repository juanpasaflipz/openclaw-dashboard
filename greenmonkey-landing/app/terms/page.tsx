import type { Metadata } from "next";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "Terms of Service — Green Monkey",
  description: "Green Monkey terms of service.",
};

export default function TermsOfService() {
  return (
    <main>
      <article className="max-w-3xl mx-auto px-4 py-24">
        <a
          href="/"
          className="text-sm text-text-tertiary hover:text-text-primary transition-colors mb-8 inline-block"
        >
          &larr; Back to Home
        </a>

        <h1 className="text-4xl font-bold mb-2">Terms of Service</h1>
        <p className="text-text-tertiary mb-12">
          Last updated: February 10, 2026
        </p>

        <div className="space-y-8 text-text-secondary leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              1. Acceptance of Terms
            </h2>
            <p>
              By accessing or using Green Monkey (&ldquo;the Service&rdquo;), you
              agree to be bound by these Terms of Service. If you do not agree,
              do not use the Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              2. Description of Service
            </h2>
            <p>
              Green Monkey is a platform for configuring, deploying, and managing
              autonomous AI agents. The Service allows you to connect external
              services (such as Google Gmail, Calendar, and Drive), configure AI
              agents with various LLM providers, and manage agent actions through
              a human-in-the-loop approval system.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              3. Accounts
            </h2>
            <p>
              You must provide a valid email address to create an account. You are
              responsible for maintaining the security of your account. You are
              responsible for all activity that occurs under your account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              4. Your API Keys &amp; Connected Services
            </h2>
            <p>
              You are responsible for any API keys you provide to the Service. You
              must ensure you have the right to use those keys and that your usage
              complies with the respective provider&apos;s terms. When you connect
              external services (Google, Binance, etc.), you authorize Green
              Monkey to access those services on your behalf within the scopes you
              grant.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              5. Agent Actions &amp; Approvals
            </h2>
            <p>
              AI agents may propose actions that affect your connected services.
              You are responsible for reviewing and approving or rejecting
              proposed actions. Once you approve an action, it will be executed
              on your behalf. Green Monkey is not liable for the consequences of
              actions you approve.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              6. Subscriptions &amp; Payments
            </h2>
            <p>
              Some features require a paid subscription. Payments are processed
              through Stripe. Subscriptions renew automatically unless cancelled.
              You may cancel at any time from the dashboard. Refunds are handled
              on a case-by-case basis.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              7. Acceptable Use
            </h2>
            <p>You agree not to:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>Use the Service for any unlawful purpose</li>
              <li>Attempt to gain unauthorized access to other users&apos; data</li>
              <li>Use the Service to send spam or unsolicited messages</li>
              <li>Interfere with or disrupt the Service</li>
              <li>Reverse engineer or attempt to extract the source code of the Service (excluding the open-source components)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              8. AI &amp; LLM Disclaimer
            </h2>
            <p>
              AI agents powered by large language models may produce inaccurate,
              incomplete, or inappropriate outputs. The Service provides tools to
              review and approve actions before execution, but you are ultimately
              responsible for the actions you approve. Green Monkey does not
              guarantee the accuracy of AI-generated content.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              9. Limitation of Liability
            </h2>
            <p>
              The Service is provided &ldquo;as is&rdquo; without warranties of
              any kind. Green Monkey shall not be liable for any indirect,
              incidental, special, or consequential damages arising from your use
              of the Service, including any actions executed by AI agents on your
              behalf.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              10. Beta Service
            </h2>
            <p>
              The Service is currently in beta. Features may change, break, or be
              removed without notice. We appreciate your feedback and patience as
              we improve the platform.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              11. Termination
            </h2>
            <p>
              We may terminate or suspend your account at any time for violation
              of these terms. You may delete your account at any time by
              contacting us. Upon termination, your data will be deleted in
              accordance with our Privacy Policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              12. Changes to Terms
            </h2>
            <p>
              We may update these terms from time to time. Continued use of the
              Service after changes constitutes acceptance of the new terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              13. Contact
            </h2>
            <p>
              For questions about these terms, contact us at{" "}
              <a
                href="mailto:hello@greenmonkey.dev"
                className="text-primary hover:underline"
              >
                hello@greenmonkey.dev
              </a>
              .
            </p>
          </section>
        </div>
      </article>
      <Footer />
    </main>
  );
}
