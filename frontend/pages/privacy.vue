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
              Last updated: {{ new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}
            </p>
          </div>
        </template>

        <div class="max-w-none space-y-8">
          <section>
            <h2>Introduction</h2>
            <p>
              Welcome to SmartQuery (Hypa-Thymesia). We respect your privacy and are committed to protecting your personal data.
              This privacy policy will inform you about how we handle your personal data when you use our service.
            </p>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Add your company/organization name and contact information."
            />
          </section>

          <USeparator />

          <section>
            <h2>Information We Collect</h2>
            <p>We collect and process the following types of information:</p>
            <ul>
              <li><strong>Account Information:</strong> Email address, name, and authentication credentials</li>
              <li><strong>Content Data:</strong> Documents, text, and images you upload to our service</li>
              <li><strong>Usage Data:</strong> Information about how you interact with our service</li>
              <li><strong>Technical Data:</strong> IP address, browser type, device information</li>
            </ul>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Review and customize this list based on actual data collection practices."
            />
          </section>

          <USeparator />

          <section>
            <h2>How We Use Your Information</h2>
            <p>We use your information to:</p>
            <ul>
              <li>Provide and maintain our service</li>
              <li>Process and store your uploaded content</li>
              <li>Enable semantic search and AI-powered features</li>
              <li>Improve and personalize user experience</li>
              <li>Communicate with you about service updates</li>
              <li>Ensure security and prevent fraud</li>
            </ul>
          </section>

          <USeparator />

          <section>
            <h2>Data Storage and Security</h2>
            <p>Your data is stored securely using industry-standard practices:</p>
            <ul>
              <li>Cloud storage with encryption at rest and in transit</li>
              <li>Secure authentication through Supabase</li>
              <li>Regular security audits and updates</li>
              <li>Access controls and user data isolation</li>
            </ul>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Specify exact cloud providers and data center locations (e.g., Supabase, Pinecone, specific AWS/GCP regions)."
            />
          </section>

          <USeparator />

          <section>
            <h2>Third-Party Services</h2>
            <p>We use the following third-party services to operate our platform:</p>
            <ul>
              <li><strong>Supabase:</strong> Authentication and database services</li>
              <li><strong>Pinecone:</strong> Vector database for semantic search</li>
              <li><strong>OpenAI/Anthropic:</strong> AI and language model processing</li>
              <li><strong>Cloud Storage:</strong> File storage services</li>
            </ul>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Confirm all third-party services and add links to their privacy policies."
            />
          </section>

          <USeparator />

          <section>
            <h2>Data Retention</h2>
            <p>
              We retain your personal data only for as long as necessary to provide our services and fulfill the purposes outlined in this policy.
            </p>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Specify exact retention periods for different data types."
            />
          </section>

          <USeparator />

          <section>
            <h2>Your Rights</h2>
            <p>You have the right to:</p>
            <ul>
              <li>Access your personal data</li>
              <li>Correct inaccurate data</li>
              <li>Request deletion of your data</li>
              <li>Export your data</li>
              <li>Withdraw consent for data processing</li>
              <li>Object to certain processing activities</li>
            </ul>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Add specific instructions on how users can exercise these rights (contact email, account settings page, etc.)."
            />
          </section>

          <USeparator />

          <section>
            <h2>Cookies and Tracking</h2>
            <p>
              We use cookies and similar tracking technologies to maintain session state and improve user experience.
            </p>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Detail specific cookies used and provide opt-out options if applicable."
            />
          </section>

          <USeparator />

          <section>
            <h2>Children's Privacy</h2>
            <p>
              Our service is not intended for users under the age of 13. We do not knowingly collect personal information from children.
            </p>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Adjust age limit based on your target audience and applicable regulations (COPPA, GDPR, etc.)."
            />
          </section>

          <USeparator />

          <section>
            <h2>International Data Transfers</h2>
            <p>
              Your data may be transferred to and processed in countries other than your country of residence.
            </p>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Specify jurisdictions and safeguards for international transfers (Privacy Shield, Standard Contractual Clauses, etc.)."
            />
          </section>

          <USeparator />

          <section>
            <h2>Changes to This Policy</h2>
            <p>
              We may update this privacy policy from time to time. We will notify you of any changes by posting the new policy on this page and updating the "Last updated" date.
            </p>
          </section>

          <USeparator />

          <section>
            <h2>Contact Us</h2>
            <p>
              If you have any questions about this privacy policy or our data practices, please contact us at:
            </p>
            <UAlert
              color="warning"
              variant="soft"
              title="TODO"
              description="Add contact email, mailing address, and data protection officer (if applicable)."
            />
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
