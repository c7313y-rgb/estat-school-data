import os
import requests
import json
from pathlib import Path

APP_ID = os.environ.get("ESTAT_APP_ID")

if not APP_ID:
    raise RuntimeError("ESTAT_APP_ID が設定されていません。GitHub Secretsを確認してください。")

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList"

params = {
    "appId": APP_ID,
    "statsCode": "00400001",
    "searchWord": "学校基本調査",
    "limit": 100
}

print("e-Stat APIへ接続します")
print("APP_ID exists:", bool(APP_ID))

response = requests.get(url, params=params, timeout=60)

print("Response status:", response.status_code)
print("Response head:", response.text[:500])

response.raise_for_status()

data = response.json()

out_path = OUT_DIR / "estat_school_basic_stats_list.json"

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"保存しました: {out_path}")
print("File exists:", out_path.exists())
