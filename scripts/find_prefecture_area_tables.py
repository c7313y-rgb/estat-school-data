import os
import csv
import time
import requests
from pathlib import Path

APP_ID = os.environ.get("ESTAT_APP_ID")

if not APP_ID:
    raise RuntimeError("ESTAT_APP_ID が設定されていません。GitHub Secretsを確認してください。")

DATA_DIR = Path("data")
INPUT_CSV = DATA_DIR / "latest_school_table_candidates.csv"
OUTPUT_CSV = DATA_DIR / "prefecture_area_table_candidates.csv"

META_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo"

PREF_NAMES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府",
    "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県",
    "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県",
    "鹿児島県", "沖縄県"
]

IMPORTANT_WORDS = [
    "幼稚園", "小学校", "中学校", "高等学校", "高等専門学校", "大学",
    "学校数", "園数", "児童数", "生徒数", "学生数", "在学者数",
    "設置者別", "都道府県別"
]

EXCLUDE_WORDS = [
    "卒業", "進学", "就職", "教員", "職員", "学級", "転入", "転出",
    "理由", "休学", "収入", "支出", "年齢", "帰国"
]


def to_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def request_with_retry(url, params, max_retries=5, wait_seconds=10):
    for attempt in range(1, max_retries + 1):
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

    raise RuntimeError("API取得に失敗しました")


def extract_area_names(meta):
    try:
        class_objs = meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    except Exception:
        return []

    class_objs = to_list(class_objs)

    area_names = []

    for obj in class_objs:
        class_id = obj.get("@id", "")
        class_name = obj.get("@name", "")

        if class_id != "area" and "都道府県" not in class_name and "地域" not in class_name:
            continue

        classes = to_list(obj.get("CLASS", []))

        for c in classes:
            name = c.get("@name", "")
            if name:
                area_names.append(name)

    return area_names


def title_score(title):
    title = str(title)
    score = sum(1 for w in IMPORTANT_WORDS if w in title)
    score -= sum(2 for w in EXCLUDE_WORDS if w in title)
    return score


if not INPUT_CSV.exists():
    raise FileNotFoundError(f"{INPUT_CSV} が見つかりません")

with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

for r in rows:
    r["title_score"] = title_score(r.get("title", ""))

rows = sorted(rows, key=lambda x: int(x["title_score"]), reverse=True)

# 上位300件を確認
rows = rows[:300]

out_rows = []

for i, r in enumerate(rows, start=1):
    stats_data_id = r.get("statsDataId", "")
    title = r.get("title", "")

    print("=" * 80)
    print(f"{i}/{len(rows)} {stats_data_id} {title}")

    try:
        meta = request_with_retry(
            META_URL,
            {
                "appId": APP_ID,
                "statsDataId": stats_data_id,
            }
        )

        area_names = extract_area_names(meta)
        pref_hit_count = sum(1 for p in PREF_NAMES if p in area_names)

        if pref_hit_count >= 40:
            out_rows.append({
                "statsDataId": stats_data_id,
                "title": title,
                "updated_date": r.get("updated_date", ""),
                "survey_date": r.get("survey_date", ""),
                "matched_search_word": r.get("matched_search_word", ""),
                "title_score": r.get("title_score", ""),
                "pref_hit_count": pref_hit_count,
                "area_sample": " / ".join(area_names[:20]),
                "status": "prefecture_area_found",
            })

        time.sleep(0.3)

    except Exception as e:
        print("error:", e)
        continue

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
            "pref_hit_count",
            "area_sample",
            "status",
        ]
    )
    writer.writeheader()
    writer.writerows(out_rows)

print(f"保存しました: {OUTPUT_CSV}")
print(f"都道府県エリア候補数: {len(out_rows)}")
