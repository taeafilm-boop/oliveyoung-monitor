# ╔══════════════════════════════════════════════════════════╗
# ║ 올리브영 전체 베스트 TOP10 → 전일 비교 → 구글시트 적재 ║
# ║ oliveyoung_crawler.py                                   ║
# ╚══════════════════════════════════════════════════════════╝

import re, datetime, os
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import gspread
from google.oauth2.service_account import Credentials


# ══════════════════════════════════════════════════════
# ▶ 설정값 — 로컬 / GitHub Actions 자동 분기
# ══════════════════════════════════════════════════════
CREDENTIALS_FILE = os.environ.get(
    "CREDENTIALS_FILE",
    r"C:\Users\11ST\Desktop\모니터링\credentials.json"
)
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID",
    "1nmLGooCid37AjWGglNVLIosG9Kxr8reTuAhAtyu7Jvw"
)
WORKSHEET_NAME   = "베스트TOP10"
EXCLUDE_KEYWORDS = ["칩", "과자", "음료", "커피", "쿠키", "초코", "캔디", "젤리", "껌", "사탕"]


# ══════════════════════════════════════════════════════
# ▶ 유틸 함수
# ══════════════════════════════════════════════════════
def is_beauty(name):
    for kw in EXCLUDE_KEYWORDS:
        if kw in name:
            return False
    return True


# ══════════════════════════════════════════════════════
# ▶ 공통 변수
# ══════════════════════════════════════════════════════
data = []
now  = datetime.datetime.now()

REQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.oliveyoung.co.kr",
}
BEST_URL = (
    "https://www.oliveyoung.co.kr/store/main/getBestList.do"
    "?dispCatNo=900000100100001&fltDispCatNo=&pageIdx=1&rowsPerPage=20"
)


# ══════════════════════════════════════════════════════
# ▶ STEP 1: 랭킹 페이지 — requests 방식으로 기본 정보 수집
# ══════════════════════════════════════════════════════
print("=" * 58)
print("  STEP 1. 올리브영 전체 베스트 TOP10 수집 중...")
print("=" * 58)

res  = requests.get(BEST_URL, headers=REQ_HEADERS, timeout=15)
soup = BeautifulSoup(res.text, "html.parser")
cards = soup.select("ul.best_list > li")
if not cards:
    cards = soup.select("ul.cate_prd_list > li")

rank = 1
for card in cards:
    if rank > 10:
        break

    brand_el = card.select_one(".tx_brand")
    name_el  = card.select_one(".tx_name")
    brand = brand_el.text.strip() if brand_el else ""
    name  = name_el.text.strip() if name_el else ""

    if not name or not is_beauty(name):
        print(f"  → 제외: {name[:20]}")
        continue

    org_el = card.select_one(".tx_org .tx_num")
    cur_el = card.select_one(".tx_cur .tx_num")
    original = re.sub(r"[^\d]", "", org_el.text if org_el else "")
    discount = re.sub(r"[^\d]", "", cur_el.text if cur_el else "")

    if original and discount and int(original) > 0:
        rate_str = f"{round((1 - int(discount)/int(original)) * 100)}%"
    else:
        rate_str = ""

    card_text = card.text
    promo_parts = []
    if "1+1" in card_text:
        promo_parts.append("1+1")
    if "2+1" in card_text:
        promo_parts.append("2+1")
    if "증정" in card_text:
        promo_parts.append("🎁")
    if "오늘드림" in card_text:
        promo_parts.append("🚀")
    if "쿠폰" in card_text:
        promo_parts.append("🎟️")

    a_tag = card.select_one("a.prd_thumb") or card.select_one("a")
    detail_url = a_tag["href"] if a_tag and a_tag.get("href") else ""
    if detail_url and detail_url.startswith("/"):
        detail_url = "https://www.oliveyoung.co.kr" + detail_url

    data.append({
        "rank": rank,
        "brand": brand,
        "name": name,
        "original": original,
        "discount": discount,
        "rate": rate_str,
        "reviews": "",
        "promo": " ".join(promo_parts),
        "url": detail_url,
    })
    print(f"  {rank:>2}위 수집 | {brand} {name[:28]}")
    rank += 1

print(f"\n  → 총 {len(data)}개 기본 정보 수집 완료")


# ══════════════════════════════════════════════════════
# ▶ STEP 2: 상세 페이지 — 셀레니움으로 리뷰수 추출
# ══════════════════════════════════════════════════════
print("\n" + "=" * 58)
print("  STEP 2. 리뷰수 수집 중 (상품별 상세 페이지)")
print("=" * 58)

options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--lang=ko-KR,ko;q=0.9")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])

driver = webdriver.Chrome(options=options)

try:
    for row in data:
        if not row["url"]:
            continue
        try:
            driver.get(row["url"])
            time.sleep(3)

            reviews = ""
            for sel in [
                ".review_count", ".prd_review strong",
                "[class*='review'] strong", "[class*='review'] em",
                ".review_num", "#reviewCount",
                ".count_area em", ".goods_review .num",
                "a[href*='review'] em", "a[href*='review'] strong",
            ]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    t = re.sub(r"[^\d]", "", el.text)
                    if t:
                        reviews = t
                        break
                if reviews:
                    break

            if not reviews:
                src = driver.page_source
                for pat in [
                    r'reviewCount["\s:]+(\d+)',
                    r'"totalCount"\s*:\s*(\d+)',
                    r'리뷰\s*[\(（](\d[\d,]+)',
                ]:
                    m = re.search(pat, src)
                    if m:
                        reviews = re.sub(r"[^\d]", "", m.group(1))
                        break

            row["reviews"] = reviews
            rv_disp = f"{int(reviews):,}개" if reviews else "-"
            print(f"  {row['rank']:>2}위 {row['brand']:<10} → 리뷰 {rv_disp}")
            time.sleep(1.2)

        except Exception as e:
            print(f"  {row['rank']}위 리뷰 수집 오류: {e}")
finally:
    driver.quit()


# ══════════════════════════════════════════════════════
# ▶ STEP 3: 전일 데이터 비교 분석
# ══════════════════════════════════════════════════════
print("\n" + "=" * 58)
print("  STEP 3. 전일 데이터 비교 분석 중...")
print("=" * 58)


def get_previous_data(gc):
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)
        rows = ws.get_all_records()
        if not rows:
            return {}

        today_str = now.strftime("%Y-%m-%d")
        dates = sorted(
            set(r["수집일자"] for r in rows if r["수집일자"] != today_str),
            reverse=True
        )
        if not dates:
            print("  → 비교할 전일 데이터 없음 (첫 실행)")
            return {}

        prev_date = dates[0]
        print(f"  → 전일 기준: {prev_date}")

        lookup = {}
        for r in rows:
            if r["수집일자"] == prev_date:
                key = f"{r['브랜드']}::{r['제품명']}"
                lookup[key] = {
                    "rank": int(r["순위"]) if str(r["순위"]).isdigit() else 0,
                    "discount": int(r["할인가"]) if str(r["할인가"]).isdigit() else 0,
                    "reviews": int(r["리뷰수"]) if str(r["리뷰수"]).isdigit() else 0,
                    "promo": r["프로모션"],
                }
        return lookup

    except Exception as e:
        print(f"  → 전일 데이터 로드 실패: {e}")
        return {}


def compare_with_previous(data, previous_lookup):
    results = []
    for r in data:
        key = f"{r['brand']}::{r['name']}"
        today_reviews = int(r["reviews"]) if r["reviews"] else 0
        today_discount = int(r["discount"]) if r["discount"] else 0

        if key in previous_lookup:
            prev = previous_lookup[key]
            rank_change = prev["rank"] - r["rank"]
            review_inc = today_reviews - prev["reviews"]
            review_growth = round((review_inc / prev["reviews"]) * 100, 1) if prev["reviews"] > 0 else 0
            price_change = today_discount - prev["discount"]
            is_new = False

            events = []
            if rank_change >= 3:
                events.append(f"🔺 순위 {rank_change}단계 급상승")
            elif rank_change <= -3:
                events.append(f"🔻 순위 {abs(rank_change)}단계 하락")

            if review_inc >= 50:
                events.append(f"💬 리뷰 +{review_inc}개 급증")
            elif review_inc >= 20:
                events.append(f"💬 리뷰 +{review_inc}개 증가")

            if prev["promo"] == "" and r["promo"] != "":
                events.append(f"🎯 신규 프로모션 ({r['promo']})")
            elif prev["promo"] != "" and r["promo"] == "":
                events.append("📤 프로모션 종료")

            if price_change < -1000:
                events.append(f"💸 가격 {abs(price_change):,}원 인하")
            elif price_change > 1000:
                events.append(f"📈 가격 {price_change:,}원 인상")

        else:
            rank_change = None
            review_inc = None
            review_growth = None
            price_change = None
            is_new = True
            events = ["🆕 신규 진입"]

        results.append({
            **r,
            "rank_change": rank_change,
            "review_inc": review_inc,
            "review_growth": review_growth,
            "price_change": price_change,
            "is_new": is_new,
            "events": " / ".join(events) if events else "-",
        })
    return results


# ══════════════════════════════════════════════════════
# ▶ STEP 4: 구글시트 연결 + 전일 비교 + 적재
# ══════════════════════════════════════════════════════
print("\n" + "=" * 58)
print("  STEP 4. 구글시트 적재 중...")
print("=" * 58)

try:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)

    previous_lookup = get_previous_data(gc)
    data_with_change = compare_with_previous(data, previous_lookup)

    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=3000, cols=20)

    if not ws.get_all_values():
        ws.append_row([
            "수집일자", "수집시간", "순위", "전일대비순위",
            "브랜드", "제품명", "정가", "할인가", "할인율",
            "리뷰수", "리뷰증감", "리뷰증감률(%)",
            "가격변화", "프로모션", "이벤트", "신규여부", "URL"
        ])

    rows = [[
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        r["rank"],
        r["rank_change"] if r["rank_change"] is not None else "NEW",
        r["brand"],
        r["name"],
        int(r["original"]) if r["original"] else "",
        int(r["discount"]) if r["discount"] else "",
        r["rate"],
        int(r["reviews"]) if r["reviews"] else "",
        r["review_inc"] if r["review_inc"] is not None else "",
        r["review_growth"] if r["review_growth"] is not None else "",
        r["price_change"] if r["price_change"] is not None else "",
        r["promo"],
        r["events"],
        "Y" if r["is_new"] else "N",
        r["url"],
    ] for r in data_with_change]

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    print("\n  [전일 대비 변화 리포트]")
    print(f"  {'순위':<4} {'변화':<8} {'브랜드':<10} {'제품명':<25} {'리뷰증감':<10} 이벤트")
    print("  " + "-" * 80)
    for r in data_with_change:
        if r["rank_change"] is None:
            rank_disp = "🆕NEW "
        elif r["rank_change"] > 0:
            rank_disp = f"🔺+{r['rank_change']:<4}"
        elif r["rank_change"] < 0:
            rank_disp = f"🔻{r['rank_change']:<5}"
        else:
            rank_disp = "➡️ 유지"

        rv_disp = f"+{r['review_inc']}개" if r["review_inc"] is not None else "-"
        print(f"  {r['rank']:>2}위  {rank_disp} {r['brand']:<10} {r['name'][:24]:<25} {rv_disp:<10} {r['events']}")

    print(f"\n  ✅ 구글시트 적재 완료! {len(rows)}행 추가")
    print(f"  🔗 https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")

except FileNotFoundError:
    print(f"  ❌ credentials.json 없음 → {CREDENTIALS_FILE} 확인")
except gspread.exceptions.APIError as e:
    print(f"  ❌ 구글 API 오류: {e}")
    print("  → 서비스 계정 이메일이 시트에 편집자로 공유되어 있는지 확인")
except Exception as e:
    print(f"  ❌ 오류: {e}")
