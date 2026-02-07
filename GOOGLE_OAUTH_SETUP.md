# Google OAuth Setup for Gmail Integration

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click **Select a project** → **New Project**
3. Name: **GreenMonkey**
4. Click **Create**

## Step 2: Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search and enable these APIs:
   - ✅ **Gmail API**
   - ✅ **Google Calendar API** (for future)
   - ✅ **Google Drive API** (for future)

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **External** user type
3. Fill in the form:
   - **App name**: GreenMonkey
   - **User support email**: juan@injupe.com
   - **Developer contact**: juan@injupe.com
4. Click **Save and Continue**
5. **Scopes** page:
   - Click **Add or Remove Scopes**
   - Add these Gmail scopes:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.send`
     - `https://www.googleapis.com/auth/gmail.labels`
   - Click **Update**
   - Click **Save and Continue**
6. **Test users** page:
   - Click **Add Users**
   - Add: `d.chosen.juan.1@gmail.com`
   - Click **Save and Continue**
7. Click **Back to Dashboard**

## Step 4: Create OAuth Client ID

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Name: **GreenMonkey Dashboard**
5. **Authorized redirect URIs** - Add both:
   ```
   https://www.greenmonkey.dev/api/oauth/google/callback
   http://localhost:5000/api/oauth/google/callback
   ```
6. Click **Create**
7. **COPY THESE VALUES** (you'll need them next):
   - Client ID: `something.apps.googleusercontent.com`
   - Client Secret: `GOCSPX-something`

## Step 5: Add Environment Variables to Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Select your **openclaw-dashboard** project
3. Go to **Settings** → **Environment Variables**
4. Add these three variables (for Production, Preview, Development):

   **Variable 1:**
   - Key: `GOOGLE_CLIENT_ID`
   - Value: `[paste your Client ID]`

   **Variable 2:**
   - Key: `GOOGLE_CLIENT_SECRET`
   - Value: `[paste your Client Secret]`

   **Variable 3:**
   - Key: `GOOGLE_REDIRECT_URI`
   - Value: `https://www.greenmonkey.dev/api/oauth/google/callback`

5. Click **Save** for each

## Step 6: Redeploy on Vercel

After adding the environment variables, trigger a new deployment:

```bash
cd /Users/juanmac/Public/clawd
vercel --prod
```

Or just push to GitHub and Vercel will auto-deploy.

## Step 7: Test Gmail Connection

1. Go to https://www.greenmonkey.dev
2. Login with your email
3. Click **Connect** tab
4. Click **Connect Gmail**
5. Authorize in the popup window
6. You should see "Connection Successful! ✅"

## Troubleshooting

### "Error 400: redirect_uri_mismatch"
- Make sure the redirect URI in Google Cloud Console exactly matches:
  `https://www.greenmonkey.dev/api/oauth/google/callback`

### "Access blocked: This app's request is invalid"
- Make sure you added your email as a test user in OAuth consent screen

### "The OAuth client was not found"
- Check that GOOGLE_CLIENT_ID environment variable is set correctly in Vercel

## Next Steps

Once Gmail is working:
- ✅ Read your recent emails via API
- ✅ Send emails via API
- ✅ Let your AI agent draft email replies
- 🔜 Add Google Calendar integration
- 🔜 Add Google Drive integration

---

**You're almost there! Just follow these steps and Gmail integration will be live! 🚀**
