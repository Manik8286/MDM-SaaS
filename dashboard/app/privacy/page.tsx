import Link from "next/link";
import { Shield } from "lucide-react";

export const metadata = { title: "Privacy Policy — MDM Console" };

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-zinc-200">
        <div className="max-w-3xl mx-auto px-6 h-16 flex items-center gap-2">
          <Link href="/" className="flex items-center gap-2">
            <Shield size={18} className="text-zinc-900" />
            <span className="font-semibold text-zinc-900">MDM Console</span>
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-16">
        <h1 className="text-3xl font-bold text-zinc-900 mb-2">Privacy Policy</h1>
        <p className="text-sm text-zinc-400 mb-12">Last updated: [DATE]</p>

        <div className="space-y-10 text-sm leading-relaxed text-zinc-600">
          <p>
            This Privacy Policy explains what information MDM Console (&quot;we&quot;, &quot;us&quot;)
            collects when you and your organization use the Service, and how we use, share,
            and protect it.
          </p>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">1. Information We Collect</h2>
            <p className="font-medium text-zinc-800 mb-1">Account information</p>
            <p className="mb-4">Organization name, email address, and hashed password when you sign up.</p>

            <p className="font-medium text-zinc-800 mb-1">Billing information</p>
            <p className="mb-4">
              Your subscription plan and billing status. Card details are collected and
              processed directly by Stripe, our payment processor — we never receive or store
              your full card number.
            </p>

            <p className="font-medium text-zinc-800 mb-1">Device information</p>
            <p className="mb-4">
              When you enroll a device, we collect its unique device identifier (UDID), serial
              number, hostname, model, operating system version, installed configuration
              profiles, and compliance/security attributes (e.g. disk encryption status,
              supervision status). We do not collect device location.
            </p>

            <p className="font-medium text-zinc-800 mb-1">Usage &amp; audit data</p>
            <p>
              We log administrative actions (logins, profile pushes, remote commands) for
              security auditing and to power the audit log feature within your account.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">2. How We Use Information</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>To provide, operate, and maintain the Service, including device management commands you initiate;</li>
              <li>To process payments and manage your subscription;</li>
              <li>To send transactional emails (welcome, password reset, trial and billing notices);</li>
              <li>To detect, investigate, and prevent security incidents or abuse;</li>
              <li>To comply with legal obligations.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">3. Data Isolation Between Customers</h2>
            <p>
              MDM Console is multi-tenant software. Every organization&apos;s data — devices,
              users, profiles, and audit logs — is logically isolated and associated with that
              organization&apos;s account only. Access is scoped server-side based on your
              authenticated session and is never determined by URLs or client-supplied values.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">4. Third Parties We Share Data With</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li><span className="font-medium text-zinc-800">Stripe</span> — payment processing and subscription billing.</li>
              <li><span className="font-medium text-zinc-800">Apple</span> — the Apple Push Notification service, used to deliver management commands to enrolled Apple devices.</li>
              <li><span className="font-medium text-zinc-800">Microsoft Entra ID</span> — only if you choose to configure SSO / Platform SSO for your organization.</li>
              <li><span className="font-medium text-zinc-800">Cloud infrastructure providers</span> — for hosting our database and application servers.</li>
            </ul>
            <p className="mt-3">We do not sell your data or your customers&apos; data to third parties.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">5. Data Retention</h2>
            <p>
              We retain account and device data for as long as your account is active. If you
              cancel your subscription, we retain data for a limited grace period in case you
              wish to reactivate, after which it is deleted upon request or per our standard
              retention schedule.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">6. Data Security</h2>
            <p>
              Passwords are hashed with bcrypt and never stored in plaintext. Administrative
              access supports two-factor authentication (TOTP). Device communication uses
              mutual TLS. We restrict internal access to customer data to what is necessary to
              operate and support the Service.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">7. Your Rights</h2>
            <p>
              You may request access to, correction of, or deletion of your organization&apos;s
              data by contacting us at the email below. Depending on your jurisdiction, you may
              have additional rights under applicable data protection law (e.g. GDPR, CCPA).
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">8. Children&apos;s Privacy</h2>
            <p>
              The Service is intended for business use by organizations and their IT
              administrators, not for use by children, and we do not knowingly collect
              personal information from children.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">9. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. Material changes will be
              communicated by email or in-app notice.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">10. Contact</h2>
            <p>
              Questions about this policy or a data request? Contact us at{" "}
              <a href="mailto:privacy@strativon.click" className="text-zinc-900 underline">
                privacy@strativon.click
              </a>.
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
