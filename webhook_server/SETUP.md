# Front-Tech — Complete Setup Guide

## Files Overview

| File | Location | Purpose |
|---|---|---|
| index.html | landing/ | Your public sales page |
| webhook_server.py | webhook_server/ | Auto-provisions clients after payment |
| clients.py | repo root (next to app.py) | Loads Stripe clients into the dashboard |
| .env.example | webhook_server/ | Template for your secret keys |

---

## STEP 1 — Host the Landing Page (5 mins, FREE)

1. Go to **netlify.com** → sign up free
2. Click **"Add new site" → "Deploy manually"**
3. Drag the `landing/` folder onto the page
4. Your page is live at `yourname.netlify.app`

**Before publishing** — open `index.html` and replace:
- `YOUR_STREAMLIT_APP_URL` → your Streamlit Cloud URL
- `YOUR_STRIPE_STARTER_LINK` → Stripe payment link for $49 plan
- `YOUR_STRIPE_PRO_LINK` → Stripe payment link for $149 plan
- `YOUR_STRIPE_ENTERPRISE_LINK` → Stripe payment link for $299 plan

---

## STEP 2 — Create Stripe Products (10 mins)

1. Go to **stripe.com** → sign up → Dashboard
2. Products → **Add product** → create 3 products:
   - "Starter Plan" — $49/month recurring
   - "Pro Plan" — $149/month recurring
   - "Enterprise Plan" — $299/month recurring
3. For each product → **Payment Links** → Create → copy the link
4. Paste links into `index.html` (Step 1 above)
5. Copy each **Price ID** (looks like `price_1ABC...`)
6. Paste Price IDs into `webhook_server.py` in the `PLAN_MAP` dict

---

## STEP 3 — Set Up Gmail App Password (5 mins)

1. Go to **myaccount.google.com**
2. Security → 2-Step Verification → enable
3. Security → **App passwords** → create one called "Front-Tech"
4. Copy the 16-character password
5. Paste into `.env` file as `SMTP_PASS`

---

## STEP 4 — Deploy Webhook to Railway (10 mins, FREE)

1. Push your repo to GitHub (include `webhook_server/` folder)
2. Go to **railway.app** → sign up with GitHub
3. **New Project** → Deploy from GitHub repo
4. Select your repo → Railway auto-detects Python
5. Go to **Variables** tab → add all values from `.env.example`
6. Railway gives you a URL like `https://fronttech-webhook.up.railway.app`

---

## STEP 5 — Connect Stripe to Railway (5 mins)

1. **Stripe Dashboard** → Developers → **Webhooks**
2. **Add endpoint** → paste your Railway URL + `/webhook`:
   `https://fronttech-webhook.up.railway.app/webhook`
3. Select these events:
   - `checkout.session.completed`
   - `invoice.payment_succeeded`
   - `customer.subscription.deleted`
4. Click **Add endpoint**
5. Copy the **Signing secret** (starts with `whsec_`)
6. Paste into Railway Variables as `STRIPE_WEBHOOK_SECRET`

---

## STEP 6 — Add clients.py to Your Streamlit App

1. Copy `clients.py` into your GitHub repo **root** (next to `app.py`)
2. Create empty `clients.json` in repo root with content: `{}`
3. Your `app.py` already calls `load_all_clients()` — no changes needed

---

## How the Full Flow Works

```
Client visits index.html (Netlify)
         ↓
Clicks "Get Pro" → Stripe payment page
         ↓
Pays $149 → Stripe fires webhook
         ↓
webhook_server.py (Railway) receives it
  → creates username + password
  → saves to clients.json
  → emails credentials to client
         ↓
Client logs into Streamlit dashboard
within 2 minutes — fully automatic!
```

---

## Test Your Webhook

Visit: `https://your-railway-url.up.railway.app/health`

You should see: `{"status": "ok", "clients": 0}`

---

## Adding a Client Manually (if needed)

Edit `clients.json` in your GitHub repo:
```json
{
  "their_username": {
    "password": "their_password",
    "name": "Client Name",
    "email": "client@email.com",
    "plan": "Pro",
    "created": "2025-01-01T00:00:00"
  }
}
```
Commit and push → client can log in immediately.

---

## Revenue Potential

| Clients | Plan | Monthly Revenue |
|---|---|---|
| 5 | Starter ($49) | $245/mo |
| 5 | Pro ($149) | $745/mo |
| 3 | Enterprise ($299) | $897/mo |
| 10 | Mixed | $1,500+/mo |

Stripe fee: 2.9% + $0.30 per transaction.
