import os
import json
import csv
import time
import requests
from pathlib import Path

APP_ID = os.environ.get("ESTAT_APP_ID")

if not APP_ID:
    raise RuntimeError("ESTAT_APP_ID が設定されていません。GitHub Secretsを確認してください。")

STATS_DATA_ID = "0003147060"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

META_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo"
DATA_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"


def request_with_retry(url, params, max_retries=5, wait_seconds=10):
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Request attempt {attempt}/{max_retries}")
            response = requests.get(url, params=params, timeout=90)

            print("status:", response.status_code)
            print("head:", response.text[:200])

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


def to_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def extract_classes(meta):
    class_objs = meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    class_objs = to_list(class_objs)

    rows = []

    for obj in class_objs:
        class_id = obj.get("@id", "")
        class_name = obj.get("@name", "")
        classes = to_list(obj.get("CLASS", []))

        for c in classes:
            rows.append({
                "class_id": class_id,
                "class_name": class_name,
                "code": c.get("@code", ""),
                "name": c.get("@name", ""),
                "level": c.get("@level", ""),
                "unit": c.get("@unit", ""),
            })

    return rows


def extract_values(data):
    stat_data = data["GET_STATS_DATA"]["STATISTICAL_DATA"]

    class_objs = to_list(stat_data["CLASS_INF"]["CLASS_OBJ"])

    code_maps = {}

    for obj in class_objs:
        class_id = obj.get("@id", "")
        classes = to_list(obj.get("CLASS", []))
        code_maps[class_id] = {}

        for c in classes:
            code_maps[class_id][c.get("@code", "")] = c.get("@name", "")

    values = to_list(stat_data["DATA_INF"]["VALUE"])

    rows = []

    for v in values:
        row = {}
        for key, value in v.items():
            if key.startswith("@"):
                dim = key[1:]
                row[f"{dim}_code"] = value
                row[f"{dim}_name"] = code_maps.get(dim, {}).get(value, "")

        row["value"] = v.get("$", "")
        rows.append(row)

    return rows


print("3147060 のメタ情報を取得します")
meta = request_with_retry(
    META_URL,
    {
        "appId": APP_ID,
        "statsDataId": STATS_DATA_ID,
    }
)

meta_path = DATA_DIR / "target_3147060_meta.json"
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"保存しました: {meta_path}")

class_rows = extract_classes(meta)

class_csv_path = DATA_DIR / "target_3147060_classes.csv"
with open(class_csv_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["class_id", "class_name", "code", "name", "level", "unit"]
    )
    writer.writeheader()
    writer.writerows(class_rows)

print(f"保存しました: {class_csv_path}")


print("3147060 のデータを取得します")

all_values = []
start = 1
limit = 100000

while True:
    data = request_with_retry(
        DATA_URL,
        {
            "appId": APP_ID,
            "statsDataId": STATS_DATA_ID,
            "startPosition": start,
            "limit": limit,
        }
    )

    stat_data = data["GET_STATS_DATA"]["STATISTICAL_DATA"]
    result_inf = stat_data["RESULT_INF"]

    rows = extract_values(data)
    all_values.extend(rows)

    total = int(result_inf["TOTAL_NUMBER"])
    to_number = int(result_inf["TO_NUMBER"])

    print(f"取得済み: {to_number} / {total}")

    if to_number >= total:
        break

    start = to_number + 1
    time.sleep(0.5)


raw_csv_path = DATA_DIR / "target_3147060_values_long.csv"

# 全カラムを集める
fieldnames = []
for r in all_values:
    for k in r.keys():
        if k not in fieldnames:
            fieldnames.append(k)

with open(raw_csv_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_values)

print(f"保存しました: {raw_csv_path}")
print(f"行数: {len(all_values)}")
