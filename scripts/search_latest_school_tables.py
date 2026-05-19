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
    # 令和7年度
    "令和7年度 学校基本調査 幼稚園 都道府県別",
    "令和7年度 学校基本調査 小学校 都道府県別",
    "令和7年度 学校基本調査 中学校 都道府県別",
    "令和7年度 学校基本調査 高等学校 都道府県別",
    "令和7年度 学校基本調査 高等専門学校 都道府県別",
    "令和7年度 学校基本調査 大学 都道府県別",

    # 令和6年度
    "令和6年度 学校基本調査 幼稚園 都道府県別",
    "令和6年度 学校基本調査 小学校 都道府県別",
    "令和6年度 学校基本調査 中学校 都道府県別",
    "令和6年度 学校基本調査 高等学校 都道府県別",
    "令和6年度 学校基本調査 高等専門学校 都道府県別",
    "令和6年度 学校基本調査 大学 都道府県別",

    # 令和5年度
    "令和5年度 学校基本調査 幼稚園 都道府県別",
    "令和5年度 学校基本調査 小学校 都道府県別",
    "令和5年度 学校基本調査 中学校 都道府県別",
    "令和5年度 学校基本調査 高等学校 都道府県別",
    "令和5年度 学校基本調査 高等専門学校 都道府県別",
    "令和5年度 学校基本調査 大学 都道府県別",

    # 表タイトルが年度名を含まない場合に備えた補助検索
    "学校基本調査 都道府県別 幼稚園 園数 園児数",
    "学校基本調査 都道府県別 小学校 学校数 児童数",
    "学校基本調査 都道府県別 中学校 学校数 生徒数",
    "学校基本調査 都道府県別 高等学校 学校数 生徒数",
    "学校基本調査 都道府県別 高等専門学校 学校数 学生数",
    "学校基本調査 都道府県別 大学 学校数 学生数",
]

IMPORTANT_WORDS = [
    "幼稚園",
    "小学校",
    "中学校",
    "高等学校",
    "高等専門学校",
    "大学",
    "都道府県",
    "都道府県別",
    "設置者別",
    "国立",
    "公立",
    "私立",
    "学校数",
    "園数",
    "園児数",
    "児童数",
    "生徒数",
    "学生数",
    "在学者数",
]

EXCLUDE_WORDS = [
    "卒業",
    "進学",
    "就職",
    "教員",
    "職員",
    "学級",
    "収入",
    "支出",
    "理由",
    "休学",
    "年齢",
    "転入",
    "転出",
    "帰国",
    "専修学校",
    "各種学校",
]

OLD_YEAR_WORDS = [
    "平成20年度",
    "平成２０年度",
    "平成19年度",
    "平成１９年度",
    "平成18年度",
    "平成１８年度",
    "平成17年度",
    "平成１７年度",
    "平成16年度",
    "平成１６年度",
]


def normalize_title(title):
    if isinstance(title, dict):
        no = title.get("@no", "")
        value = title.get("$", "")
        return f"{no} {value}".strip()
    return str(title)


def to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def fetch_stats_list(search_word, start_position=1, limit=100):
    params = {
        "appId": APP_ID,
        "statsCode": "00400001",
        "searchWord": search_word,
        "limit": limit,
        "startPosition": start_position,
    }

    max_retries = 5
    wait_seconds = 10

    for attempt in range(1, max_retries + 1):
        print("=" * 80)
        print(f"searchWord: {search_word}")
        print(f"attempt: {attempt}/{max_retries}")

        response = requests.get(API_URL, params=params, timeout=90)

        print("status:", response.status_code)
        print("head:", response.text[:200])

        if response.status_code in [429, 502, 503, 504]:
            if attempt < max_retries:
                print(f"一時的なAPIエラーです。{wait_seconds}秒待って再試行します。")
                time.sleep(wait_seconds)
                continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError(f"e-Stat API取得に失敗しました: {search_word}")


def title_score(title):
    title = str(title)

    score = 0

    for word in IMPORTANT_WORDS:
        if word in title:
            score += 1

    for word in EXCLUDE_WORDS:
        if word in title:
            score -= 3

    # 令和年度を優先
    if "令和7年度" in title or "令和７年度" in title:
        score += 10
    if "令和6年度" in title or "令和６年度" in title:
        score += 8
    if "令和5年度" in title or "令和５年度" in title:
        score += 6

    # 古い平成年度は除外寄り
    for old in OLD_YEAR_WORDS:
        if old in title:
            score -= 20

    return score


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

            # 明確に古い平成年度は除外
            if any(old in title for old in OLD_YEAR_WORDS):
                continue

            score = title_score(title)

            # 低スコアは保存しない
            if score <= 0:
                continue

            rows_by_id[stats_data_id] = {
                "score": score,
                "statsDataId": stats_data_id,
                "title": title,
                "survey_date": survey_date,
                "updated_date": updated_date,
                "gov_org": str(gov_org),
                "matched_search_word": word,
            }

        if len(tables) < limit:
            break

        start += limit
        time.sleep(0.5)

rows = list(rows_by_id.values())

rows = sorted(
    rows,
    key=lambda x: (
        int(x["score"]),
        str(x["updated_date"]),
        str(x["survey_date"]),
    ),
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
