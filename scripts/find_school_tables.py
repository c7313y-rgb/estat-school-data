import json
from pathlib import Path

INPUT_PATH = Path("data/estat_school_basic_stats_list.json")
OUTPUT_PATH = Path("data/school_basic_table_candidates.csv")

if not INPUT_PATH.exists():
    raise FileNotFoundError(f"{INPUT_PATH} が見つかりません")

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

tables = data.get("GET_STATS_LIST", {}).get("DATALIST_INF", {}).get("TABLE_INF", [])

if isinstance(tables, dict):
    tables = [tables]

keywords = [
    "幼稚園",
    "小学校",
    "中学校",
    "高等学校",
    "高等専門学校",
    "大学",
    "都道府県",
    "学校数",
    "学生数",
    "児童数",
    "生徒数",
    "在学者数",
]

rows = []

for t in tables:
    stats_data_id = t.get("@id", "")
    title = t.get("TITLE", "")
    survey_date = t.get("SURVEY_DATE", "")
    updated_date = t.get("UPDATED_DATE", "")
    government_statistics_name = t.get("GOV_ORG", {}).get("$", "")

    title_text = str(title)

    score = sum(1 for kw in keywords if kw in title_text)

    if score > 0:
        rows.append({
            "score": score,
            "statsDataId": stats_data_id,
            "title": title_text,
            "survey_date": survey_date,
            "updated_date": updated_date,
            "gov_org": government_statistics_name,
        })

rows = sorted(rows, key=lambda x: x["score"], reverse=True)

OUTPUT_PATH.parent.mkdir(exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8-sig") as f:
    f.write("score,statsDataId,title,survey_date,updated_date,gov_org\n")
    for r in rows:
        line = [
            str(r["score"]),
            r["statsDataId"],
            r["title"].replace(",", "、").replace("\n", " "),
            str(r["survey_date"]),
            str(r["updated_date"]),
            str(r["gov_org"]).replace(",", "、"),
        ]
        f.write(",".join(line) + "\n")

print(f"候補表を保存しました: {OUTPUT_PATH}")
print(f"候補数: {len(rows)}")
