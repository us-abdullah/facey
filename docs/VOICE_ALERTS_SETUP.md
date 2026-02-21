# Voice Alerts: ElevenLabs + Twilio (Unknown person in Analyst Zone)

When an **Unknown** person is detected in a zone whose name contains **"Analyst"** (e.g. "Analyst Zone"), the app:

1. **Logs** the security alert as usual.
2. **Generates TTS** with **ElevenLabs**:  
   *"Security violation detected in Analyst Zone, please check the dashboard for the security footage."*
3. **Calls** configured C-level phone numbers via **Twilio** and plays that message when they answer.

**Yes, you need Twilio** to place the actual phone call. ElevenLabs only produces the spoken audio; Twilio handles dialing and playing the audio to the phone.

---

## 1. ElevenLabs

- Sign up at [elevenlabs.io](https://elevenlabs.io) and get an API key.
- Set in your environment:
  - `ELEVENLABS_API_KEY` (or `XI_API_KEY`)

Optional: `ELEVENLABS_VOICE_ID` to use a different voice (default is Rachel).

---

## 2. Twilio

- Sign up at [twilio.com](https://www.twilio.com) and get:
  - **Account SID**
  - **Auth Token**
  - A **Twilio phone number** (used as caller ID for the outbound call)
- Set in your environment:
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_PHONE_NUMBER` (e.g. `+15551234567`)

---

## 3. C-level phone numbers

- Set who gets the call when the violation fires:
  - `C_LEVEL_PHONE_NUMBERS` — comma-separated E.164 numbers, e.g.  
    `+15551234567,+15559876543`

---

## 4. Public URL (required for Twilio)

Twilio must be able to reach your backend over the internet to:

- Fetch **TwiML** (instructions for the call).
- Fetch the **MP3** (the ElevenLabs message) to play to the caller.

So your backend must be exposed at a **public HTTPS URL**. Options:

- **ngrok**: run `ngrok http 8000`, then set `PUBLIC_BASE_URL=https://xxxx.ngrok.io` (or your ngrok URL).
- **Deployed app**: set `PUBLIC_BASE_URL` to your production URL (e.g. `https://api.yourapp.com`).

Set in your environment:

- `PUBLIC_BASE_URL` (or `BASE_URL`) — e.g. `https://abc123.ngrok.io` (no trailing slash).

---

## 5. Example `.env` (backend)

Create a `.env` in `facey/backend/` (or export these in the shell before starting the server):

```bash
# ElevenLabs (TTS)
ELEVENLABS_API_KEY=your_elevenlabs_api_key

# Twilio (outbound call)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+15551234567

# Who to call on Analyst Zone violation
C_LEVEL_PHONE_NUMBERS=+15559876543,+15555555555

# Public URL so Twilio can fetch TwiML and MP3 (e.g. ngrok or production)
PUBLIC_BASE_URL=https://your-ngrok-or-domain.com
```

Load `.env` in the backend (e.g. `python-dotenv` in your run script or at the top of `main.py`) so these variables are set when uvicorn starts.

---

## 6. C-level actions on the dashboard

On each security alert, a C-level user can:

- **Acknowledge** — mark as seen.
- **Problem fixed** — mark as resolved.

Both actions are available on the Security Alerts panel and call the `/api/security/alerts/{id}/resolve` endpoint.
