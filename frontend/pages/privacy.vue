<script setup lang="ts">
useSeoMeta({
  title: 'Privacy Policy - SmartQuery',
  description: 'Privacy Policy for SmartQuery application'
})
</script>

<template>
  <div class="min-h-screen">
    <UContainer class="py-12">
      <UCard>
        <template #header>
          <div class="space-y-2">
            <h1 class="text-4xl font-bold">Privacy Policy</h1>
            <p class="text-muted">
              Last updated: January 14, 2026
            </p>
          </div>
        </template>

        <div class="max-w-none space-y-8 prose prose-slate dark:prose-invert">
          <section>
            <h2>Introduction</h2>
            <p>
              Welcome to SmartQuery, operated by <strong>SmartQuery Ltd</strong>, a company registered in England and Wales with company number [SC873991] and registered office at [REDACTED].
            </p>
            <p>
              We respect your privacy and are committed to protecting your personal data in accordance with the UK General Data Protection Regulation (UK GDPR), the Data Protection Act 2018, and other applicable data protection laws.
            </p>
            <p>
              This Privacy Policy explains how we collect, use, disclose, store, and protect your personal data when you use our website and SmartQuery service (the “Service”).
            </p>
            <p>
              If you have any questions about this policy or our data practices, please contact us at <a href="mailto:privacy@smartquery.co.uk">privacy@smartquery.co.uk</a>.
            </p>
          </section>

          <USeparator />

          <section>
            <h2>Information We Collect</h2>
            <p>We collect and process the following categories of personal data:</p>
            <ul>
              <li><strong>Account & Contact Information:</strong> name, email address, password (hashed), and any other details you provide during registration or account updates.</li>
              <li><strong>User Content:</strong> documents, text, images, PDFs, or other files you upload, together with any metadata associated with them.</li>
              <li><strong>AI Interaction Data:</strong> search queries, prompts you submit to our semantic/AI features, and the results/responses generated (we do not use your content to train third-party foundation models unless you explicitly opt in).</li>
              <li><strong>Usage & Analytics Data:</strong> how you interact with the Service (features used, time spent, navigation paths, etc.).</li>
              <li><strong>Technical & Device Data:</strong> IP address, browser type & version, operating system, device identifiers, approximate location (derived from IP), access times and dates.</li>
              <li><strong>Payment Information (if applicable):</strong> processed securely by our payment provider — we do not store full card details.</li>
            </ul>
            <p>We do not intentionally collect special category data (e.g. health, racial or ethnic origin, religious beliefs) unless you deliberately include it in uploaded content — in which case you remain the controller for that processing.</p>
          </section>

          <USeparator />

          <section>
            <h2>How We Use Your Information</h2>
            <p>We process your personal data for the following purposes and on the following legal bases:</p>
            <ul>
              <li>To provide, maintain, and improve the Service</li>
              <li>To process and store your uploaded content via Ragie and enable semantic search & AI-powered features</li>
              <li>To extract, chunk, and index content from your documents for search and retrieval</li>
              <li>To personalise your experience and develop new features</li>
              <li>To communicate service updates, security notices, or respond to support requests</li>
              <li>To detect, prevent and investigate fraud, abuse, or security incidents</li>
              <li>To comply with legal obligations (e.g. responding to data subject rights requests)</li>
            </ul>
          </section>

          <USeparator />

          <section>
            <h2>Data Storage and Security</h2>
            <p>We implement appropriate technical and organisational measures to protect your data, including:</p>
            <ul>
              <li>Encryption of data at rest and in transit (TLS 1.3+)</li>
              <li>Secure authentication & authorisation via Supabase</li>
              <li>Strict access controls and multi-factor authentication for our team</li>
              <li>Data minimisation and pseudonymisation where possible</li>
            </ul>
            <p>Your relational data and authentication information are primarily hosted in Supabase projects configured in EU regions where available. Uploaded documents are processed by Ragie for content extraction and chunking. Vector embeddings are stored with Pinecone. Some AI processing (e.g. LLM inference) occurs with providers in the United States or other jurisdictions.</p>
          </section>

          <USeparator />

          <section>
            <h2>Third-Party Services & International Transfers</h2>
            <p>We share data with the following subprocessors (acting as data processors on our instructions):</p>
            <ul>
              <li><strong>Supabase</strong> – Authentication, PostgreSQL database → <a href="https://supabase.com/privacy" target="_blank" rel="noopener">Privacy Policy</a> | <a href="https://supabase.com/legal/dpa" target="_blank" rel="noopener">DPA</a></li>
              <li><strong>Ragie</strong> – Document processing, content extraction, and chunking for semantic search → <a href="https://www.ragie.ai/privacy-policy" target="_blank" rel="noopener">Privacy Policy</a></li>
              <li>Cloudflare – Edge caching, DDoS protection → <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener">Privacy Policy</a></li>
              <li>Stripe – Payment processing (card data never reaches our servers) → <a href="https://stripe.com/gb/privacy" target="_blank" rel="noopener">Privacy Policy</a></li>
            </ul>
            <p>Some providers are located outside the UK/EEA (mainly United States). We only make restricted transfers when necessary and ensure appropriate safeguards are in place, such as:</p>
            <ul>
              <li>UK International Data Transfer Agreement (IDTA) or UK Addendum to EU SCCs</li>
              <li>Processor’s Data Processing Addendum incorporating standard clauses</li>
              <li>Transfer Impact Assessments where required</li>
            </ul>
            <p>You can request our current subprocessor list or copies of relevant DPAs/SCCs by emailing <a href="mailto:elilourens123@gmail.com">elilourens123@gmail.com</a> (subject to redaction of confidential information).</p>
          </section>

          <USeparator />

          <section>
            <h2>Data Retention</h2>
            <p>We keep personal data only for as long as necessary:</p>
            <ul>
              <li>Account data — while your account is active + 90 days after deletion (for recovery/legal reasons)</li>
              <li>User-uploaded content & vectors — until you delete it or your account is deleted (subject to backups)</li>
              <li>Usage logs & technical data — up to 12–24 months for security & product improvement</li>
              <li>Legal / billing records — 7 years as required by UK law</li>
            </ul>
            <p>After these periods, data is securely deleted or irreversibly anonymised.</p>
          </section>

          <USeparator />

          <section>
            <h2>Your Rights (UK GDPR)</h2>
            <p>Under UK GDPR you have the right to:</p>
            <ul>
              <li>Access your personal data (right of access)</li>
              <li>Correct inaccurate or incomplete data</li>
              <li>Request erasure (“right to be forgotten”)</li>
              <li>Restrict processing in certain circumstances</li>
              <li>Data portability (receive data in structured format)</li>
              <li>Object to processing based on legitimate interests or for direct marketing</li>
              <li>Withdraw consent (where we rely on consent)</li>
              <li>Lodge a complaint with the UK Information Commissioner’s Office (<a href="https://ico.org.uk" target="_blank" rel="noopener">ico.org.uk</a>)</li>
            </ul>
            <p>To exercise these rights, email <a href="mailto:privacy@smartquery.co.uk">privacy@smartquery.co.uk</a> or use the account settings / deletion options in the Service. We usually respond within one month (free of charge unless requests are excessive or manifestly unfounded).</p>
          </section>

          <USeparator />

          <section>
            <h2>Cookies and Similar Technologies</h2>
            <p>We use essential cookies for authentication and session management. Optional analytics cookies may be used to understand usage patterns (via privacy-friendly tools). You can manage preferences via our cookie banner or your browser settings.</p>
            <p>We do not use cookies for behavioural advertising.</p>
          </section>

          <USeparator />

          <section>
            <h2>Children's Privacy</h2>
            <p>Our Service is not directed at children under 16. We do not knowingly collect personal data from anyone under 16. If we become aware that we have collected such data, we will delete it promptly.</p>
          </section>

          <USeparator />

          <section>
            <h2>Changes to This Policy</h2>
            <p>We may update this policy from time to time. Material changes will be notified via email or in-app notice. The “Last updated” date at the top shows when it was last revised.</p>
          </section>

          <USeparator />

          <section>
            <h2>Contact Us</h2>
            <p>Questions, requests or complaints should be sent to:</p>
            <p>
              <strong>SmartQuery Ltd</strong><br>
              Email: <a href="mailto:elilourens123@gmail.com">elilourens123@gmail.com</a><br>
            </p>
            <p>(We have not appointed a formal Data Protection Officer as we are not legally required to do so, but all privacy matters are handled via the above contact.)</p>
          </section>
        </div>

        <template #footer>
          <NuxtLink to="/">
            <UButton variant="ghost" icon="i-lucide-arrow-left">
              Back to Home
            </UButton>
          </NuxtLink>
        </template>
      </UCard>
    </UContainer>
  </div>
</template>