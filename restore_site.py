#!/usr/bin/env python3
import os, sys, glob, zipfile, tempfile, requests

CF_TOKEN      = os.environ.get("CF_TOKEN", "")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_PROJECT    = "grupoestrategika"

print("Restaurando sitio completo...")
site_files = glob.glob("site/*.html")
print(f"Archivos: {len(site_files)}")

with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
    tmp_path = tmp.name

with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for filepath in site_files:
        zf.write(filepath, os.path.basename(filepath))
        print("  + " + os.path.basename(filepath))

url = "https://api.cloudflare.com/client/v4/accounts/" + CF_ACCOUNT_ID + "/pages/projects/" + CF_PROJECT + "/deployments"
cf_headers = {"Authorization": "Bearer " + CF_TOKEN}

with open(tmp_path, "rb") as f:
    r = requests.post(url, headers=cf_headers, files={"file": ("deployment.zip", f, "application/zip")})
os.unlink(tmp_path)

try:
    data = r.json()
    if data.get("success"):
        print("Sitio restaurado: grupoestrategika.com")
    else:
        print("Error: " + str(data.get("errors")))
        sys.exit(1)
except Exception as e:
    print("HTTP " + str(r.status_code) + ": " + r.text[:200])
    sys.exit(1)
