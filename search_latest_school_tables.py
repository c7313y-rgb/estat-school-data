import os
import csv
import time
import requests
from pathlib import Path

APP_ID = os.environ.get("ESTAT_APP_ID")

if not APP_ID:
    raise RuntimeError("ESTAT_APP_ID が設定されていません。GitHub Secretsを確認してください。")

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)

API_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList"

SEARCH_WORDS = [
    "学校基本調査 幼稚園 都道府県",
    "学校基本調査 小学校 都道府県",
    "学校基本調査 中学校 都道府県",
    "学校基本調査 高等学校 都道府県",
    "学校基本調査 高等専門学校 都道府県",
    "学校基本調査 大学 都道府県",
    "学校基本調査 都道府県 学校数",
    "学校基本調査 都道府県 園児数",
    "学校基本調査 都道府県 児童数",
    "学校基本調査 都道府県 生徒数",
    "学校基本調査 都道府県 学生数",
    "令和7年度 学校基本調査 都道府県",
    "令和6年度 学校基本調査 都道府県",
    "令和5年度 学校基本調査 都道府県",
]

KEYWORDS = [
    "幼稚園",
    "小学校",
    "中学校",
    "高等学校",
    "高等専門学校",
    "大学",
    "都道府県",
    "学校数",
    "園数",
    "学生数",
    "児童数",
    "生徒数",
    "園児数",
    "在学者数",
    "設置者別",
]


def normalize_title(title):
    if isinstance(title, dict):
        no = title.get("@no", "")
        value = title.get("$", "")
        return f"{no} {value}".strip()
    return str(title)


def fetch_stats_list(search_word, start_position=1, limit=100):
    params = {
        "appId": APP_ID,
        "statsCode": "00400001",
        "searchWord": search_word,
        "limit": limit,
        "startPosition": start_position,
    }

    response = requests.get(API_URL, params=params, timeout=60)
    print("searchWord:", search_word)
    print("status:", response.status_code)

    response.raise_for_status()
    return response.json()


def to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


rows_by_id = {}

for word in SEARCH_WORDS:
    start = 1
    limit = 100

    for _ in range(10):
        data = fetch_stats_list(word, start_position=start, limit=limit)

        root = data.get("GET_STATS_LIST", {})
        datalist = root.get("DATALIST_INF", {})
        tables = to_list(datalist.get("TABLE_INF", []))

        if not tables:
            break

        for t in tables:
            stats_data_id = str(t.get("@id", ""))
            title = normalize_title(t.get("TITLE", ""))
            survey_date = str(t.get("SURVEY_DATE", ""))
            updated_date = str(t.get("UPDATED_DATE", ""))
            gov_org = t.get("GOV_ORG", "")
            if isinstance(gov_org, dict):
                gov_org = gov_org.get("$", "")

            score = sum(1 for kw in KEYWORDS if kw in title)

            # 学校基本調査らしいものだけ残す
            if score == 0:
                continue

            # 同じstatsDataIdは重複保存しない
            rows_by_id[stats_data_id] = {
                "score": score,
                "statsDataId": stats_data_id,
                "title": title,
                "survey_date": survey_date,
                "updated_date": updated_date,
                "gov_org": str(gov_org),
                "matched_search_word": word,
            }

        # 次ページへ
        if len(tables) < limit:
            break

        start += limit
        time.sleep(0.5)

rows = list(rows_by_id.values())

# 新しい更新日を上に、次にスコア順
rows = sorted(
    rows,
    key=lambda x: (x["updated_date"], x["score"]),
    reverse=True
)

out_path = OUT_DIR / "latest_school_table_candidates.csv"

with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "score",
            "statsDataId",
            "title",
            "survey_date",
            "updated_date",
            "gov_org",
            "matched_search_word",
        ]
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"保存しました: {out_path}")
print(f"候補数: {len(rows)}")
