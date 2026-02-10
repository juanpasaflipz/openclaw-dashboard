import type { Metadata } from "next";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "Privacy Policy — Green Monkey",
  description: "Green Monkey privacy policy. How we handle your data.",
};

export default function PrivacyPolicy() {
  return (
    <main>
      <article className="max-w-3xl mx-auto px-4 py-24">
        <a
          href="/"
          className="text-sm text-text-tertiary hover:text-text-primary transition-colors mb-8 inline-block"
        >
          &larr; Back to Home
        </a>

        <h1 className="text-4xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-text-tertiary mb-12">
          Last updated: February 10, 2026
        </p>

        <div className="space-y-8 text-text-secondary leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              1. Introduction
            </h2>
            <p>
              Green Monkey (&ldquo;we&rdquo;, &ldquo;our&rdquo;, &ldquo;us&rdquo;)
              operates the Green Monkey platform at{" "}
              <a href="https://app.greenmonkey.dev" className="text-primary hover:underline">
                app.greenmonkey.dev
              </a>
              . This Privacy Policy explains how we collect, use, and protect your
              information when you use our service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              2. Information We Collect
            </h2>
            <h3 className="text-lg font-medium text-text-primary mb-2 mt-4">
              Account Information
            </h3>
            <p>
              When you create an account, we collect your email address for
              authentication purposes. We use magic link email authentication
              &mdash; we do not store passwords.
            </p>

            <h3 className="text-lg font-medium text-text-primary mb-2 mt-4">
              Connected Services (Google APIs)
            </h3>
            <p className="mb-3">
              When you connect Google services (Gmail, Google Calendar, Google
              Drive), we request access through Google&apos;s OAuth 2.0 system.
              We store:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>OAuth access tokens and refresh tokens (encrypted at rest)</li>
              <li>Token expiration timestamps</li>
              <li>The list of scopes you granted</li>
            </ul>
            <p className="mt-3">
              We access your Google data <strong className="text-text-primary">only</strong> to
              perform actions you explicitly request or approve through the
              dashboard. Specifically:
            </p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>
                <strong className="text-text-primary">Gmail:</strong> Reading
                recent emails, sending emails on your behalf (only when you
                approve an agent action)
              </li>
              <li>
                <strong className="text-text-primary">Google Calendar:</strong>{" "}
                Reading calendar events, creating or modifying events (only when
                you approve an agent action)
              </li>
              <li>
                <strong className="text-text-primary">Google Drive:</strong>{" "}
                Reading file metadata, searching files, uploading or downloading
                files (only when you approve an agent action)
              </li>
            </ul>

            <h3 className="text-lg font-medium text-text-primary mb-2 mt-4">
              AI Agent Configuration
            </h3>
            <p>
              We store your agent configurations, including identity settings,
              system prompts, tool configurations, and conversation history. This
              data is associated with your account and used solely to operate your
              agents.
            </p>

            <h3 className="text-lg font-medium text-text-primary mb-2 mt-4">
              LLM Provider API Keys
            </h3>
            <p>
              If you connect LLM providers (OpenAI, Anthropic, etc.), your API
              keys are stored encrypted. We use them only to make API calls on
              your behalf. We never share your API keys with third parties.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              3. How We Use Your Information
            </h2>
            <p>We use your information to:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>Authenticate you and maintain your session</li>
              <li>Operate your AI agents as configured by you</li>
              <li>Execute approved actions on connected services</li>
              <li>Display relevant data in your dashboard</li>
              <li>Process subscription payments via Stripe</li>
            </ul>
            <p className="mt-3">
              We do <strong className="text-text-primary">not</strong> use your
              connected service data (emails, calendar events, files) for
              advertising, training AI models, or any purpose other than providing
              the service you requested.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              4. Human-in-the-Loop &amp; Action Approvals
            </h2>
            <p>
              Green Monkey uses a human-in-the-loop approval system. When an AI
              agent proposes an action that affects your connected services
              (sending an email, creating a calendar event, etc.), the action is
              queued for your explicit approval. No action is executed on your
              connected accounts without your consent.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              5. Data Storage &amp; Security
            </h2>
            <ul className="list-disc pl-6 space-y-1">
              <li>
                Data is stored in a PostgreSQL database hosted on Neon with SSL
                encryption in transit
              </li>
              <li>OAuth tokens and API keys are encrypted at rest</li>
              <li>Sessions are server-side and secured</li>
              <li>The application is served over HTTPS</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              6. Data Sharing
            </h2>
            <p>
              We do not sell, rent, or share your personal data with third parties
              except:
            </p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>
                <strong className="text-text-primary">Stripe:</strong> For
                payment processing (email and subscription data only)
              </li>
              <li>
                <strong className="text-text-primary">LLM Providers:</strong>{" "}
                Your prompts and conversation data are sent to whichever LLM
                provider you configure (using your own API key)
              </li>
              <li>
                <strong className="text-text-primary">Vercel:</strong> Our
                hosting provider processes web requests
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              7. Data Retention &amp; Deletion
            </h2>
            <p>
              You can disconnect any connected service at any time from the
              dashboard, which deletes the stored tokens. You can request full
              account deletion by contacting us at{" "}
              <a
                href="mailto:privacy@greenmonkey.dev"
                className="text-primary hover:underline"
              >
                privacy@greenmonkey.dev
              </a>
              . We will delete all your data within 30 days of the request.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              8. Google API Services User Data Policy
            </h2>
            <p>
              Green Monkey&apos;s use and transfer of information received from
              Google APIs adheres to the{" "}
              <a
                href="https://developers.google.com/terms/api-services-user-data-policy"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                Google API Services User Data Policy
              </a>
              , including the Limited Use requirements. We only use Google user
              data to provide and improve user-facing features that are visible
              and prominent in the application&apos;s user interface.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              9. Your Rights
            </h2>
            <p>You have the right to:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>Access the data we hold about you</li>
              <li>Disconnect any connected service at any time</li>
              <li>Export your agent configurations</li>
              <li>Request deletion of your account and all associated data</li>
              <li>
                Revoke Google access at any time via{" "}
                <a
                  href="https://myaccount.google.com/permissions"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Google Account Permissions
                </a>
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              10. Changes to This Policy
            </h2>
            <p>
              We may update this policy from time to time. We will notify users of
              significant changes via email or a notice in the dashboard.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-3">
              11. Contact
            </h2>
            <p>
              For privacy questions or data requests, contact us at{" "}
              <a
                href="mailto:privacy@greenmonkey.dev"
                className="text-primary hover:underline"
              >
                privacy@greenmonkey.dev
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
