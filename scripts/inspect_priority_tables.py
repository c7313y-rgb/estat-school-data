import os
import json
import csv
import time
import requests
from pathlib import Path

APP_ID = os.environ.get("ESTAT_APP_ID")

if not APP_ID:
    raise RuntimeError("ESTAT_APP_ID が設定されていません。GitHub Secretsを確認してください。")

DATA_DIR = Path("data")
OUT_DIR = DATA_DIR / "priority_table_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)

META_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo"
DATA_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

PRIORITY_IDS = [
    "0003011817",
    "0003011819",
    "0003013750",
    "0003011368",
    "0003013680",
    "0003013387",
    "0003015662",
    "0003015720",
    "0003059636",
    "0003059639",
]


def to_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def request_with_retry(url, params, max_retries=5, wait_seconds=10):
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Request {attempt}/{max_retries}: {params.get('statsDataId')}")

            response = requests.get(url, params=params, timeout=90)

            print("status:", response.status_code)
            print("head:", response.text[:150])

            if response.status_code in [429, 502, 503, 504]:
                if attempt < max_retries:
                    print(f"一時エラーです。{wait_seconds}秒待って再試行します。")
                    time.sleep(wait_seconds)
                    continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            last_error = e
            print("通信エラー:", e)
            if attempt < max_retries:
                time.sleep(wait_seconds)
            else:
                raise

    raise RuntimeError(f"API取得に失敗しました: {last_error}")


def extract_class_summary(meta):
    try:
        class_objs = meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    except Exception:
        return []

    class_objs = to_list(class_objs)
    rows = []

    for obj in class_objs:
        class_id = obj.get("@id", "")
        class_name = obj.get("@name", "")
        classes = to_list(obj.get("CLASS", []))

        sample_names = []
        for c in classes[:30]:
            sample_names.append(c.get("@name", ""))

        rows.append({
            "class_id": class_id,
            "class_name": class_name,
            "class_count": len(classes),
            "sample_names": " / ".join(sample_names),
        })

    return rows


summary_rows = []

for stats_data_id in PRIORITY_IDS:
    print("=" * 80)
    print(f"Inspecting {stats_data_id}")

    try:
        meta = request_with_retry(
            META_URL,
            {
                "appId": APP_ID,
                "statsDataId": stats_data_id,
            }
        )

        sample = request_with_retry(
            DATA_URL,
            {
                "appId": APP_ID,
                "statsDataId": stats_data_id,
                "limit": 50,
            }
        )

        title = ""
        try:
            title = meta["GET_META_INFO"]["METADATA_INF"]["TABLE_INF"]["TITLE"]
        except Exception:
            title = ""

        class_summary = extract_class_summary(meta)

        json_path = OUT_DIR / f"{stats_data_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "statsDataId": stats_data_id,
                    "title": title,
                    "class_summary": class_summary,
                    "meta": meta,
                    "sample": sample,
                },
                f,
                ensure_ascii=False,
                indent=2
            )

        class_names = " / ".join(
            [f'{r["class_id"]}:{r["class_name"]}({r["class_count"]})' for r in class_summary]
        )

        class_samples = " || ".join(
            [f'{r["class_name"]}: {r["sample_names"]}' for r in class_summary]
        )

        summary_rows.append({
            "statsDataId": stats_data_id,
            "title": str(title),
            "class_names": class_names,
            "class_samples": class_samples,
            "json_path": str(json_path),
            "status": "ok",
        })

        time.sleep(0.5)

    except Exception as e:
        summary_rows.append({
            "statsDataId": stats_data_id,
            "title": "",
            "class_names": "",
            "class_samples": "",
            "json_path": "",
            "status": f"error: {e}",
        })


out_csv = DATA_DIR / "priority_table_inspection.csv"

with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "statsDataId",
            "title",
            "class_names",
            "class_samples",
            "json_path",
            "status",
        ]
    )
    writer.writeheader()
    writer.writerows(summary_rows)

print(f"保存しました: {out_csv}")
