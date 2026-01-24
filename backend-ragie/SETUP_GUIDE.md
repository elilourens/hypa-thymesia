# Ragie Backend Setup Guide

This guide walks you through setting up the leaner Ragie-based backend from scratch.

## Step 1: Prepare Your Environment

### Install Required Software
```bash
# Install Python 3.12+
# Download from https://www.python.org/downloads/

# Install Poetry (Python package manager)
curl -sSL https://install.python-poetry.org | python3 -
```

### Navigate to Backend Directory
```bash
cd backend-ragie
```

## Step 2: Configure Environment Variables

### Create .env File
```bash
cp .env.example .env
```

### Edit .env and Add Your Credentials

#### Supabase Configuration
1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Select your project
3. Go to Settings → API
4. Copy your project URL and service role key

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=sb_secret_your_service_role_key_here
```

#### Ragie Configuration
1. Go to [Ragie Dashboard](https://dashboard.ragie.ai)
2. Navigate to API Keys
3. Copy your API key

```bash
RAGIE_API_KEY=tnt_your_ragie_api_key_here
```

#### Stripe Configuration
1. Go to [Stripe Dashboard](https://dashboard.stripe.com)
2. Navigate to Developers → API Keys
3. Copy your Secret Key

```bash
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
```

For webhook secret:
1. Go to Developers → Webhooks
2. Create a new webhook endpoint (you'll get the URL later)
3. Copy the signing secret

```bash
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
STRIPE_PRICE_ID=price_your_price_id
```

#### JWT Configuration
Create a strong secret key (at least 32 characters):
```bash
JWT_ALGORITHM=HS256
JWT_SECRET_KEY=your_secret_key_here_min_32_chars_long_very_secure
```

#### App Configuration
```bash
API_PREFIX=/api/v1
DEBUG=false
```

## Step 3: Set Up Supabase Database

### Create app_groups Table (if not exists)
Go to Supabase SQL Editor and run:

```sql
CREATE TABLE IF NOT EXISTS app_groups (
    group_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_index INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE app_groups ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own groups"
    ON app_groups FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own groups"
    ON app_groups FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own groups"
    ON app_groups FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own groups"
    ON app_groups FOR DELETE
    USING (auth.uid() = user_id);
```

### Create user_settings Table (if not exists)
```sql
CREATE TABLE IF NOT EXISTS user_settings (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    stripe_subscription_status TEXT,
    stripe_current_period_end BIGINT,
    stripe_cancel_at_period_end BOOLEAN DEFAULT FALSE,
    max_files INTEGER DEFAULT 50,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own settings"
    ON user_settings FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update their own settings"
    ON user_settings FOR UPDATE
    USING (auth.uid() = user_id);
```

### Create ragie_documents Table
Copy the entire SQL from `migrations/001_create_ragie_documents_table.sql` and run it in Supabase SQL Editor.

## Step 4: Install Python Dependencies

```bash
poetry install
```

This installs all required packages from `pyproject.toml`:
- FastAPI
- Supabase client
- Ragie SDK
- Stripe library
- And more...

## Step 5: Test the Setup

### Start the Development Server
```bash
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Test Health Check
```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{"status":"ok","message":"Ragie backend is running"}
```

## Step 6: Set Up Stripe Webhook

### Create Webhook Endpoint in Stripe

1. Go to [Stripe Dashboard](https://dashboard.stripe.com)
2. Navigate to Developers → Webhooks
3. Click "Add endpoint"
4. Enter endpoint URL: `https://yourdomain.com/api/v1/stripe/webhook`
   - For local testing, use ngrok: `https://your-ngrok-url.ngrok.io/api/v1/stripe/webhook`
5. Select events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
6. Create endpoint
7. Copy the signing secret and add to .env as `STRIPE_WEBHOOK_SECRET`

### Test Webhook (Local Development)

Install ngrok:
```bash
# From https://ngrok.com/download
ngrok http 8000
```

This gives you a public URL like `https://abc123.ngrok.io`. Update your Stripe webhook URL to:
```
https://abc123.ngrok.io/api/v1/stripe/webhook
```

## Step 7: Verify All Components

### Check Supabase Connection
```bash
curl -X GET http://localhost:8000/api/v1/user-settings \
  -H "Authorization: Bearer your_jwt_token_here"
```

### Check Ragie Connection
Upload a test document to verify Ragie integration works:
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer your_jwt_token_here" \
  -F "file=@test_document.pdf"
```

### Check Stripe Integration
Create a checkout session:
```bash
curl -X POST http://localhost:8000/api/v1/stripe/create-checkout-session \
  -H "Authorization: Bearer your_jwt_token_here" \
  -H "Content-Type: application/json" \
  -d '{
    "success_url": "https://example.com/success",
    "cancel_url": "https://example.com/cancel"
  }'
```

## Step 8: Create a Test User

### Sign Up in Your Frontend
Use your frontend application to create a test account through Supabase Authentication.

This automatically creates a `user_id` in Supabase Auth.

### Manually Create User Settings (Optional)
If needed, you can manually create settings in Supabase:

```sql
INSERT INTO user_settings (user_id, max_files)
VALUES ('your_user_id', 50)
ON CONFLICT DO NOTHING;
```

## Step 9: Test Core Functionality

### 1. Upload a Document
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@sample.pdf"
```

Response should include:
- Document ID
- Ragie Document ID
- Status (should be "pending" initially)

### 2. Check Processing Status
```bash
curl -X GET http://localhost:8000/api/v1/documents/{doc_id}/status \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Wait for status to become "ready" (this may take a few seconds to minutes depending on file size).

### 3. Search Documents
```bash
curl -X POST http://localhost:8000/api/v1/search/retrieve \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "your search query here"
  }'
```

### 4. Create a Group
```bash
curl -X POST http://localhost:8000/api/v1/groups/create \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Important Documents",
    "sort_index": 0
  }'
```

### 5. List Documents
```bash
curl -X GET http://localhost:8000/api/v1/documents/list \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Step 10: Production Deployment

### Using Docker

1. **Build the Docker image:**
```bash
docker build -t ragie-backend .
```

2. **Create .env file with production values**

3. **Run the container:**
```bash
docker run -d \
  --name ragie-backend \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  ragie-backend
```

### Using a Cloud Provider

#### Heroku
```bash
# Install Heroku CLI
# heroku login
# heroku create your-app-name
# git push heroku main
```

#### AWS (ECS/Fargate)
1. Create an ECR repository
2. Push Docker image to ECR
3. Create ECS task definition
4. Create ECS service

#### Google Cloud Run
```bash
gcloud run deploy ragie-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --set-env-vars SUPABASE_URL=... \
  --set-env-vars SUPABASE_KEY=... \
  # ... other env vars
```

### Production Checklist

Before deploying to production:

- [ ] Set `DEBUG=false` in environment
- [ ] Use a strong `JWT_SECRET_KEY`
- [ ] Configure proper CORS for frontend domain
- [ ] Set up Stripe webhook in production
- [ ] Enable HTTPS/TLS
- [ ] Set up logging and monitoring
- [ ] Configure backup/recovery strategy
- [ ] Test all functionality in staging
- [ ] Set up error tracking (e.g., Sentry)
- [ ] Configure rate limiting
- [ ] Review security policies
- [ ] Test with production Stripe keys
- [ ] Set up automated deployments (CI/CD)

## Troubleshooting

### Port 8000 Already in Use
```bash
# Find process using port 8000
lsof -i :8000
# Kill process
kill -9 <PID>
```

### Module Import Errors
```bash
# Reinstall dependencies
poetry install --no-cache
```

### Database Connection Errors
- Verify Supabase URL and key are correct
- Check network connectivity
- Ensure IP is whitelisted if applicable

### Ragie API Errors
- Verify Ragie API key is correct
- Check Ragie quota/limits
- Review Ragie documentation

### Stripe Errors
- Verify keys are for correct environment (test vs. live)
- Check webhook is configured
- Review Stripe logs

## Next Steps

1. **Connect your frontend** to this backend
2. **Test end-to-end** with a real user workflow
3. **Monitor logs** and metrics
4. **Implement CI/CD** for automated deployments
5. **Add monitoring** and alerting
6. **Plan scaling strategy**

## Need Help?

- Check the README.md for API documentation
- Review error logs in your application
- Check Ragie, Supabase, and Stripe documentation
- Open an issue with detailed information about your problem

## Quick Reference

**Development Server:**
```bash
poetry run uvicorn main:app --reload
```

**Production Server:**
```bash
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Check Dependencies:**
```bash
poetry show
```

**Update Dependencies:**
```bash
poetry update
```
