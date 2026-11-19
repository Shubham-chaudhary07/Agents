# get_token.py  (run once)
import os
import secrets
import urllib.parse

import requests
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.environ["LINKEDIN_CLIENT_ID"]
CLIENT_SECRET = os.environ["LINKEDIN_CLIENT_SECRET"]
REDIRECT = "http://localhost:8000/callback"

state = secrets.token_urlsafe(16)
url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT,
    "state": state,
    "scope": "openid profile w_member_social",
})

print("\n1. Open this link in your browser and click Allow:\n")
print(url)
print("\n2. The next page will fail to load. That is normal.")
print("   Copy the FULL address from the browser's address bar and paste it below.\n")
returned = input("Pasted address: ").strip()

params = urllib.parse.parse_qs(urllib.parse.urlparse(returned).query)
if params.get("state", [""])[0] != state:
    raise SystemExit("State does not match. Run the script again from the start.")
if "code" not in params:
    raise SystemExit(f"No code found. LinkedIn said: {params}")

r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
    "grant_type": "authorization_code",
    "code": params["code"][0],
    "redirect_uri": REDIRECT,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
}, timeout=30)
if r.status_code >= 400:
    raise SystemExit(f"Token request failed: {r.status_code} {r.text}")
tok = r.json()

me = requests.get("https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=30)
if me.status_code >= 400:
    raise SystemExit(f"Profile request failed: {me.status_code} {me.text}")

print("\nDone. Add these two lines to your .env file:\n")
print(f"LINKEDIN_ACCESS_TOKEN={tok['access_token']}")
print(f"LINKEDIN_AUTHOR_URN=urn:li:person:{me.json()['sub']}")
print(f"\n(The token lasts about {int(tok.get('expires_in', 0)) // 86400} days. After that, run this script again.)")