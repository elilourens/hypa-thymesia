# Production Webhook Setup Guide

## Current Status
✅ **Stripe**: Configured (has `whsec_...` secret)
⚠️ **Ragie**: Not configured (optional but recommended for production)

---

## Quick Setup (5 minutes)

### 1. Ragie Webhooks

1. **Get webhook secret:**
   - Visit https://dashboard.ragie.ai → Settings → Webhooks
   - Copy the **Signing Secret**

2. **Update `.env`:**
   ```env
   RAGIE_WEBHOOK_SECRET=your_secret_here
   APP_ENV=production
   ```

3. **Configure endpoint in Ragie dashboard:**
   - URL: `https://your-domain.com/api/v1/ragie-webhooks/webhook`

### 2. Stripe Webhooks (Already Setup ✅)

1. **Verify in Stripe dashboard:**
   - Go to Developers → Webhooks
   - Find: `https://your-domain.com/api/v1/stripe/webhook`
   - Confirm it's **Enabled** with recent **✓ Success** events

### 3. Application Configuration

```env
APP_ENV=production
DEBUG=false
STRIPE_WEBHOOK_SECRET=whsec_...  # Already set ✓
RAGIE_WEBHOOK_SECRET=...         # Add this
```

4. **Restart application:**
   ```bash
   docker-compose restart backend-ragie
   # or
   systemctl restart backend-ragie
   ```

5. **Verify startup logs:**
   ```
   ✓ STRIPE_WEBHOOK_SECRET configured
   ✓ RAGIE_WEBHOOK_SECRET configured
   ```

---

## Webhook Endpoints

Once live:
```
POST https://your-domain.com/api/v1/ragie-webhooks/webhook
POST https://your-domain.com/api/v1/stripe/webhook
```

Requirements:
- ✅ Publicly accessible (no auth)
- ✅ HTTPS only
- ✅ Configured in both dashboards

---

## What Each Webhook Does

### Ragie Webhook
- **Triggered**: When document processing completes
- **Updates**: `ragie_documents.status`, stores chunks in `video_chunks`
- **Rate limit**: 100/min per IP
- **Security**: HMAC-SHA256 signature verification

### Stripe Webhook
- **Triggered**: On subscription/payment events
- **Updates**: `user_settings` with subscription tier and limits
- **Security**: Stripe's native signature verification
- **Idempotent**: Tracks processed events to prevent duplicates

---

## Testing

### Test Stripe (2 minutes)
1. Stripe Dashboard → Developers → Webhooks
2. Click your endpoint → "Send test webhook"
3. Select event (e.g., `customer.subscription.created`)
4. Check "Recent events" - should show ✓

### Test Ragie (requires secret)
```bash
DOMAIN="your-domain.com"
SECRET="your_ragie_webhook_secret"
BODY='{"type":"document_status_updated","nonce":"test-123","payload":{"document_id":"test","status":"ready"}}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | cut -d' ' -f2)

curl -X POST https://$DOMAIN/api/v1/ragie-webhooks/webhook \
  -H "x-signature: $SIGNATURE" \
  -H "Content-Type: application/json" \
  -d "$BODY"
# Response: {"status":"success"}
```

---

## Monitoring

### Database Queries
```sql
-- Stripe events processed (last hour)
SELECT COUNT(*) FROM webhook_events
WHERE created_at > NOW() - INTERVAL 1 HOUR;

-- Document processing updates (last hour)
SELECT COUNT(*) FROM ragie_documents
WHERE updated_at > NOW() - INTERVAL 1 HOUR;
```

### Logs to Monitor
```bash
# Check startup
docker logs backend-ragie | grep -i webhook

# Real-time logs
docker logs -f backend-ragie | grep -i webhook
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Stripe returns 401** | Verify `STRIPE_WEBHOOK_SECRET` matches Stripe dashboard (starts with `whsec_`) |
| **Ragie returns 500** | Ensure `RAGIE_WEBHOOK_SECRET` is set and matches Ragie dashboard |
| **No webhook events showing** | 1) Check endpoints are publicly accessible 2) Verify HTTPS 3) Check logs for errors |
| **Events not in database** | Verify database connection, check logs for processing errors |

---

## Deployment Checklist

- [ ] Set `RAGIE_WEBHOOK_SECRET` from Ragie dashboard
- [ ] Verify `STRIPE_WEBHOOK_SECRET` matches Stripe dashboard
- [ ] Set `APP_ENV=production` and `DEBUG=false`
- [ ] Ensure webhook endpoints are HTTPS and publicly accessible
- [ ] Configure endpoints in Ragie and Stripe dashboards
- [ ] Restart application
- [ ] Test Stripe webhook with "Send test webhook"
- [ ] Monitor logs for `✓ configured` messages
- [ ] Check recent events in Stripe/Ragie dashboards show success

---

## Reference

**Status Checks:**
```bash
# Health check
curl https://your-domain.com/api/v1/health

# Check if endpoints are accessible
curl -X OPTIONS https://your-domain.com/api/v1/stripe/webhook
curl -X OPTIONS https://your-domain.com/api/v1/ragie-webhooks/webhook
```

**Documentation:**
- Ragie: https://docs.ragie.ai/webhooks
- Stripe: https://stripe.com/docs/webhooks
