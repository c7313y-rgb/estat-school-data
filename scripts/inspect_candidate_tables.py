import os
import csv
import json
import time
import requests
from pathlib import Path

APP_ID = os.environ.get("ESTAT_APP_ID")

if not APP_ID:
    raise RuntimeError("ESTAT_APP_ID が設定されていません。GitHub Secretsを確認してください。")

DATA_DIR = Path("data")
INPUT_CSV = DATA_DIR / "latest_school_table_candidates.csv"
OUTPUT_CSV = DATA_DIR / "inspected_school_table_candidates.csv"
OUTPUT_JSON_DIR = DATA_DIR / "candidate_samples"
OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)

META_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo"
DATA_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

TARGET_KEYWORDS = [
    "都道府県別",
    "学校数",
    "園数",
    "児童数",
    "生徒数",
    "学生数",
    "在学者数",
    "設置者別",
    "幼稚園",
    "小学校",
    "中学校",
    "高等学校",
    "高等専門学校",
    "大学",
]

EXCLUDE_KEYWORDS = [
    "卒業",
    "進学",
    "就職",
    "転入",
    "転出",
    "教員",
    "職員",
    "学級",
    "帰国",
    "収入",
    "支出",
    "休学",
    "理由",
    "年齢",
    "入学状況",
    "通学状況",
]


def request_with_retry(url, params, max_retries=5, wait_seconds=10):
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Request attempt {attempt}/{max_retries}: {params.get('statsDataId', '')}")

            response = requests.get(url, params=params, timeout=60)

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


def text_score(title):
    title = str(title)
    include_score = sum(1 for kw in TARGET_KEYWORDS if kw in title)
    exclude_score = sum(1 for kw in EXCLUDE_KEYWORDS if kw in title)
    return include_score - exclude_score


def flatten_meta_classes(meta_json):
    result = []

    try:
        class_objs = meta_json["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    except Exception:
        return result

    if isinstance(class_objs, dict):
        class_objs = [class_objs]

    for obj in class_objs:
        class_id = obj.get("@id", "")
        class_name = obj.get("@name", "")
        classes = obj.get("CLASS", [])

        if isinstance(classes, dict):
            classes = [classes]

        values = []

        for c in classes[:20]:
            values.append({
                "code": c.get("@code", ""),
                "name": c.get("@name", ""),
                "level": c.get("@level", ""),
                "unit": c.get("@unit", ""),
            })

        result.append({
            "class_id": class_id,
            "class_name": class_name,
            "sample_values": values,
        })

    return result


if not INPUT_CSV.exists():
    raise FileNotFoundError(f"{INPUT_CSV} が見つかりません")

with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# 使えそうな候補を上位に絞る
for r in rows:
    r["title_score"] = text_score(r.get("title", ""))

filtered = [
    r for r in rows
    if int(r.get("title_score", 0)) > 0
]

filtered = sorted(
    filtered,
    key=lambda x: (
        int(x.get("title_score", 0)),
        str(x.get("updated_date", ""))
    ),
    reverse=True
)

# 最初は上位80件だけ確認
filtered = filtered[:80]

out_rows = []

for idx, r in enumerate(filtered, start=1):
    stats_data_id = str(r.get("statsDataId", ""))
    title = str(r.get("title", ""))

    print("=" * 80)
    print(f"{idx}/{len(filtered)}")
    print(stats_data_id, title)

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
                "limit": 20,
            }
        )

        meta_classes = flatten_meta_classes(meta)

        json_path = OUTPUT_JSON_DIR / f"{stats_data_id}.json"

        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(
                {
                    "candidate": r,
                    "meta_classes": meta_classes,
                    "sample_data": sample,
                },
                jf,
                ensure_ascii=False,
                indent=2
            )

        class_names = " / ".join([m["class_name"] for m in meta_classes])

        out_rows.append({
            "statsDataId": stats_data_id,
            "title": title,
            "updated_date": r.get("updated_date", ""),
            "survey_date": r.get("survey_date", ""),
            "matched_search_word": r.get("matched_search_word", ""),
            "title_score": r.get("title_score", ""),
            "class_names": class_names,
            "sample_json": str(json_path),
            "status": "ok",
        })

        time.sleep(0.5)

    except Exception as e:
        out_rows.append({
            "statsDataId": stats_data_id,
            "title": title,
            "updated_date": r.get("updated_date", ""),
            "survey_date": r.get("survey_date", ""),
            "matched_search_word": r.get("matched_search_word", ""),
            "title_score": r.get("title_score", ""),
            "class_names": "",
            "sample_json": "",
            "status": f"error: {e}",
        })

with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "statsDataId",
            "title",
            "updated_date",
            "survey_date",
            "matched_search_word",
            "title_score",
            "class_names",
            "sample_json",
            "status",
        ]
    )
    writer.writeheader()
    writer.writerows(out_rows)

print(f"保存しました: {OUTPUT_CSV}")
print(f"確認件数: {len(out_rows)}")
