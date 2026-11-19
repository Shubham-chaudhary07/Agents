# linkedin_api.py
import os

import requests

API = "https://api.linkedin.com"
# LinkedIn needs a recent API version in YYYYMM form. If you get a version error, check LinkedIn's docs
# for the current one and set LINKEDIN_VERSION in your .env.
VERSION = os.environ.get("LINKEDIN_VERSION", "202608")


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['LINKEDIN_ACCESS_TOKEN']}",
        "LinkedIn-Version": VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


def _escape(text):
    # LinkedIn treats some characters as formatting codes, so escape them (# is left alone for hashtags)
    for ch in "\\|{}@[]()<>*_~":
        text = text.replace(ch, "\\" + ch)
    return text


def _upload_image(author, path):
    # 1) ask LinkedIn for an upload address
    init = requests.post(
        f"{API}/rest/images?action=initializeUpload",
        headers=_headers(),
        json={"initializeUploadRequest": {"owner": author}},
        timeout=30,
    )
    if init.status_code >= 400:
        raise RuntimeError(f"Image init failed {init.status_code}: {init.text[:300]}")
    value = init.json()["value"]

    # 2) upload the image bytes
    with open(path, "rb") as f:
        up = requests.put(
            value["uploadUrl"],
            data=f.read(),
            headers={"Authorization": f"Bearer {os.environ['LINKEDIN_ACCESS_TOKEN']}"},
            timeout=120,
        )
    if up.status_code >= 400:
        raise RuntimeError(f"Image upload failed {up.status_code}: {up.text[:300]}")

    return value["image"]  # an id like urn:li:image:...


def post_to_linkedin(text, image_path=""):
    author = os.environ["LINKEDIN_AUTHOR_URN"]
    body = {
        "author": author,
        "commentary": _escape(text),
        "visibility": os.environ.get("LINKEDIN_VISIBILITY", "CONNECTIONS"),
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    # 3) attach the photo if there is one
    if image_path and os.path.isfile(image_path):
        body["content"] = {"media": {"id": _upload_image(author, image_path)}}

    # 4) create the post
    r = requests.post(f"{API}/rest/posts", headers=_headers(), json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Post failed {r.status_code}: {r.text[:300]}")

    post_id = r.headers.get("x-restli-id", "")
    return f"https://www.linkedin.com/feed/update/{post_id}/"