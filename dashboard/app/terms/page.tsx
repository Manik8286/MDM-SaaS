import Link from "next/link";
import { Shield } from "lucide-react";

export const metadata = { title: "Terms of Service — MDM Console" };

export default function TermsPage() {
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
        <h1 className="text-3xl font-bold text-zinc-900 mb-2">Terms of Service</h1>
        <p className="text-sm text-zinc-400 mb-12">Last updated: [DATE]</p>

        <div className="space-y-10 text-sm leading-relaxed text-zinc-600">
          <p>
            These Terms of Service (&quot;Terms&quot;) govern access to and use of MDM Console
            (the &quot;Service&quot;), operated by [YOUR COMPANY LEGAL NAME] (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;).
            By creating an account or using the Service, you agree to be bound by these Terms.
            If you are entering into these Terms on behalf of an organization, you represent
            that you have authority to bind that organization.
          </p>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">1. The Service</h2>
            <p>
              MDM Console is a mobile device management platform that lets organizations
              enroll, configure, monitor, and remotely manage Mac and Windows computers,
              including pushing configuration profiles, enforcing compliance policies, and
              integrating with Microsoft Entra ID for single sign-on.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">2. Trial &amp; Billing</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>
                New accounts begin with a 5-day free trial. A valid payment card is required
                at signup, processed securely by our payment processor, Stripe — we never see
                or store your full card number.
              </li>
              <li>
                Unless you cancel before the trial ends, your card will be charged
                automatically at the start of your selected plan and on each billing cycle
                thereafter until you cancel.
              </li>
              <li>
                You can cancel or change your subscription at any time from Settings →
                Plan &amp; Billing. Cancellation takes effect at the end of the current billing
                period; we do not provide partial-period refunds except where required by law.
              </li>
              <li>Fees are exclusive of applicable taxes, which may be added to your invoice.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">3. Your Account</h2>
            <p>
              You are responsible for maintaining the confidentiality of your account
              credentials and for all activity under your account. Notify us immediately of
              any unauthorized use. We recommend enabling two-factor authentication, available
              under Settings.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">4. Acceptable Use</h2>
            <p>You agree not to use the Service to:</p>
            <ul className="list-disc pl-5 space-y-2 mt-2">
              <li>Enroll or manage devices you do not own or lack authorization to manage;</li>
              <li>Attempt to access another tenant&apos;s data or bypass account isolation;</li>
              <li>Reverse-engineer, resell, or white-label the Service without written consent;</li>
              <li>Interfere with the security or availability of the Service or other tenants&apos; use of it.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">5. Device Management Authorization</h2>
            <p>
              By enrolling a device, you represent that you (or your organization) own the
              device or have the device owner&apos;s consent to install management profiles and
              issue remote commands to it, including configuration changes, lock, and wipe.
              We are not responsible for data loss resulting from remote commands you or your
              administrators initiate.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">6. Third-Party Services</h2>
            <p>
              The Service relies on third parties to function, including Stripe (payments),
              Apple&apos;s Push Notification service (device commands), and Microsoft Entra ID
              (optional SSO integration). Your use of those integrations is also subject to
              those providers&apos; own terms.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">7. Disclaimer &amp; Limitation of Liability</h2>
            <p>
              The Service is provided &quot;as is&quot; without warranties of any kind, express or
              implied. To the maximum extent permitted by law, we are not liable for indirect,
              incidental, or consequential damages, or for any loss of data, revenue, or
              devices arising from use of the Service.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">8. Termination</h2>
            <p>
              You may stop using the Service and cancel your subscription at any time. We may
              suspend or terminate accounts that violate these Terms or where required by law.
              Upon termination, your right to access the Service ends; we retain data per our{" "}
              <Link href="/privacy" className="text-zinc-900 underline">Privacy Policy</Link>.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">9. Changes to These Terms</h2>
            <p>
              We may update these Terms from time to time. Material changes will be
              communicated by email or in-app notice. Continued use of the Service after
              changes take effect constitutes acceptance.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">10. Governing Law</h2>
            <p>
              These Terms are governed by the laws of [GOVERNING JURISDICTION], without regard
              to its conflict-of-law principles.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-zinc-900 mb-3">11. Contact</h2>
            <p>
              Questions about these Terms? Contact us at{" "}
              <a href="mailto:legal@strativon.click" className="text-zinc-900 underline">
                legal@strativon.click
              </a>.
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
