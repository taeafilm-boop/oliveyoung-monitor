import re
import datetime
import time
import os
import gspread
import imaplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
except ImportError:
    def stealth_sync(page):
        pass

CREDENTIALS_FILE = os.environ.get("CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = "1nmLGooCid37AjWGglNVLIosG9Kxr8reTuAhAtyu7Jvw"
WORKSHEET_NAME = "베스트TOP10"

GMAIL_USER = "taeafilm@gmail.com"
GMAIL_PASS = (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_PASS") or "").replace(" ", "")
TO_EMAIL = "7467@11stcorp.com"

EXCLUDE_KEYWORDS = ["칩", "과자", "음료", "커피", "쿠키", "초코", "캔디", "젤리", "껌", "사탕"]
BEST_URL = (
    "https://www.oliveyoung.co.kr/store/main/getBestList.do"
    "?dispCatNo=900000100100001&fltDispCatNo=&pageIdx=1&rowsPerPage=20"
)

def is_beauty(name):
    for kw in EXCLUDE_KEYWORDS:
        if kw in name:
            return False
    return True

data = []
now = datetime.datetime.now()
weekdays = ["월", "화", "수", "목", "금", "토", "일"]
date_str = f"{now.year}년 {now.month:02d}월 {now.day:02d}일 ({weekdays[now.weekday()]})"

print("=" * 58)
print("  STEP 1. 올리브영 전체 베스트 TOP10 수집 중...")
print("=" * 58)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = context.new_page()
        stealth_sync(page)

        try:
            page.goto(BEST_URL, wait_until="domcontentloaded", timeout=30000)
            # 빈 뼈대 대신, 실제 '상품명'이 화면에 확실히 렌더링 될 때까지 대기
            page.wait_for_selector(".tx_name", timeout=15000)
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"⚠️ 메인 페이지 로딩 지연 또는 봇 차단 발생: {e}")
            pass 

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("ul.best_list > li")
        if not cards:
            cards = soup.select("ul.cate_prd_list > li")

        rank = 1
        for card in cards:
            if rank > 10:
                break

            brand_el = card.select_one(".tx_brand")
            name_el = card.select_one(".tx_name")
            brand = brand_el.text.strip() if brand_el else ""
            name = name_el.text.strip() if name_el else ""

            if not name or not is_beauty(name):
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
            if "1+1" in card_text: promo_parts.append("1+1")
            if "2+1" in card_text: promo_parts.append("2+1")
            if "증정" in card_text: promo_parts.append("🎁")
            if "오늘드림" in card_text: promo_parts.append("🚀")
            if "쿠폰" in card_text: promo_parts.append("🎟️")

            a_tag = card.select_one("a.prd_thumb") or card.select_one("a")
            detail_url = a_tag["href"] if a_tag and a_tag.get("href") else ""
            if detail_url and detail_url.startswith("/"):
                detail_url = "https://www.oliveyoung.co.kr" + detail_url

            data.append({
                "rank": rank, "brand": brand, "name": name,
                "original": original, "discount": discount,
                "rate": rate_str, "reviews": "",
                "promo": " ".join(promo_parts), "url": detail_url,
            })
            rank += 1

        print("\n" + "=" * 58)
        print("  STEP 2. 리뷰수 수집 중 (상품별 상세 페이지)")
        print("=" * 58)

        for row in data:
            if not row["url"]: continue
            try:
                page.goto(row["url"], wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("#reviewInfo span, .review_count", timeout=5000)
            except Exception:
                pass
                
            try:
                reviews = ""
                selectors = [
                    "#reviewInfo span", ".review_count", ".prd_review strong", 
                    "[class*='review'] strong", ".review_num", "#reviewCount",
                    ".area-review-tally strong", "a#reviewList span.tx_num"
                ]
                for sel in selectors:
                    el = page.query_selector(sel)
                    if el:
                        t = re.sub(r"[^\d]", "", el.inner_text())
                        if t and int(t) > 0:
                            reviews = t
                            break

                if not reviews:
                    src = page.content()
                    patterns = [
                        r'reviewCount["\s:]+(\d+)', 
                        r'"totalCount"\s*:\s*(\d+)', 
                        r'리뷰\s*[\(（](\d[\d,]+)',
                        r'<span[^>]*class="[^"]*review[^"]*"[^>]*>.*?(\d+).*?</span>'
                    ]
                    for pat in patterns:
                        m = re.search(pat, src)
                        if m:
                            val = re.sub(r"[^\d]", "", m.group(1))
                            if val and int(val) > 0:
                                reviews = val
                                break

                row["reviews"] = reviews
                print(f"  {row['rank']:>2}위 {row['brand']:<10} 리뷰수: {reviews or '없음'} 수집 완료")
            except Exception as e:
                print(f"  {row['rank']}위 {row['brand']} 리뷰 수집 오류(Pass): {e}")

        browser.close()

except Exception as e:
    print(f"❌ 크롤링 치명적 오류 발생: {e}")

if not data:
    print("⚠️ 수집된 데이터가 없어 리포트 생성을 종료합니다.")
    exit(0)

data_with_change = []

try:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=3000, cols=20)

    rows = ws.get_all_records()
    today_str = now.strftime("%Y-%m-%d")
    dates = sorted(set(r["수집일자"] for r in rows if r["수집일자"] != today_str), reverse=True)
    
    previous_lookup = {}
    if dates:
        prev_date = dates[0]
        for r in rows:
            if r["수집일자"] == prev_date:
                key = f"{r['브랜드']}::{r['제품명']}"
                previous_lookup[key] = {
                    "rank": int(r["순위"]) if str(r["순위"]).isdigit() else 0,
                    "discount": int(r["할인가"]) if str(r["할인가"]).isdigit() else 0,
                    "reviews": int(r["리뷰수"]) if str(r["리뷰수"]).isdigit() else 0,
                    "promo": r["프로모션"],
                }

    for r in data:
        key = f"{r['brand']}::{r['name']}"
        today_reviews = int(r["reviews"]) if r["reviews"] and str(r["reviews"]).isdigit() else 0
        today_discount = int(r["discount"]) if r["discount"] and str(r["discount"]).isdigit() else 0

        if key in previous_lookup:
            prev = previous_lookup[key]
            rank_change = prev["rank"] - r["rank"]
            review_inc = today_reviews - prev["reviews"]
            review_growth = round((review_inc / prev["reviews"]) * 100, 1) if prev["reviews"] > 0 else 0
            price_change = today_discount - prev["discount"]
            events = []
            
            if rank_change >= 3: events.append(f"🔺순위 {rank_change}단계 급상승")
            elif rank_change <= -3: events.append(f"🔻순위 {abs(rank_change)}단계 하락")
            if review_inc >= 50: events.append(f"💬리뷰 +{review_inc}개 급증")
            
            if prev["promo"] == "" and r["promo"] != "": events.append(f"🎯신규 프로모션 ({r['promo']})")
            if price_change < -1000: events.append(f"💸가격 {abs(price_change):,}원 인하")
        else:
            rank_change = review_inc = None
            events = ["🆕 신규 진입"]

        data_with_change.append({
            **r,
            "rank_change": rank_change, "review_inc": review_inc,
            "events": " / ".join(events) if events else "-"
        })

    sheet_rows = []
    for r in data_with_change:
        org_val = int(r["original"]) if r["original"] and str(r["original"]).isdigit() else ""
        disc_val = int(r["discount"]) if r["discount"] and str(r["discount"]).isdigit() else ""
        rev_val = int(r["reviews"]) if r["reviews"] and str(r["reviews"]).isdigit() else ""
        
        sheet_rows.append([
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
            r["rank"], r["rank_change"] if r["rank_change"] is not None else "NEW",
            r["brand"], r["name"], org_val, disc_val, r["rate"],
            rev_val, r["review_inc"] if r["review_inc"] is not None else "",
            r["events"], r["url"]
        ])
    
    ws.append_rows(sheet_rows, value_input_option="USER_ENTERED")
    print("\n✅ 구글시트 적재 완료")

except Exception as e:
    print(f"\n❌ 구글시트 연동 실패(메일 초안 생성은 계속 진행): {e}")
    if not data_with_change:
        for r in data:
            data_with_change.append({**r, "rank_change": None, "review_inc": None, "events": "-"})

print("\n" + "=" * 58)
print("  STEP 4. 이메일 HTML 생성 및 임시보관함 저장 중...")
print("=" * 58)

cards_html = ""
for idx, r in enumerate(data_with_change):
    if r["rank_change"] is None:
        rank_badge = '<span style="color:#00C73C; font-weight:bold; font-size:12px;">🆕 NEW</span>'
    elif r["rank_change"] > 0:
        rank_badge = f'<span style="color:#FA2828; font-weight:bold; font-size:12px;">🔺 {r["rank_change"]}계단 상승</span>'
    elif r["rank_change"] < 0:
        rank_badge = f'<span style="color:#111111; font-weight:bold; font-size:12px;">🔻 {abs(r["rank_change"])}계단 하락</span>'
    else:
        rank_badge = '<span style="color:#999999; font-weight:bold; font-size:12px;">➖ 순위 유지</span>'

    rv_disp = f" (+{r['review_inc']})" if r.get("review_inc") else ""
    reviews_formatted = f"{int(r['reviews']):,}개" if r.get('reviews') and str(r['reviews']).isdigit() else "리뷰 정보 없음"

    event_html = ""
    if r.get('events') and r['events'] != "-":
        event_html = f"""
        <div style="background-color:#fff5f5; border-radius:6px; padding:10px 12px; font-size:12px; color:#FA2828; font-weight:700; margin-top:8px;">
            🚨 모니터링 이벤트: {r['events']}
        </div>
        """

    is_last = (idx == len(data_with_change) - 1)
    border_style = "padding-bottom:15px;" if is_last else "padding-bottom:20px; margin-bottom:20px; border-bottom:1px solid #eeeeee;"

    url_button_html = ""
    if r.get('url'):
        url_button_html = f"""
        <div style="margin-top:10px; text-align:right;">
            <a href="{r['url']}" target="_blank" style="background-color:#9BD728; color:#111111; padding:6px 12px; border-radius:4px; font-size:12px; font-weight:bold; text-decoration:none; display:inline-block;">🔗 올리브영에서 상품 보기 &gt;</a>
        </div>
        """
        
    disc_html = f"{int(r['discount']):,}원" if r.get('discount') and str(r['discount']).isdigit() else "표시 안됨"
    org_html = f"(정가 {int(r['original']):,}원 / {r['rate']} 할인)" if r.get('original') and str(r['original']).isdigit() else ""

    cards_html += f"""
        <div style="{border_style}">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="font-size:18px; font-weight:900; color:#111111;">{r['rank']}위 {rank_badge}</div>
            <div style="font-size:12px; font-weight:700; color:#444444;">[{r['brand']}]</div>
          </div>
          <div style="font-size:15px; font-weight:700; color:#222222; margin-bottom:6px; line-height:1.4;">
            <a href="{r.get('url', '#')}" target="_blank" style="color:#222222; text-decoration:none;">{r['name']}</a>
          </div>
          <div style="font-size:13px; color:#666666; line-height:1.6;">
            • 할인가: <b style="color:#FA2828;">{disc_html}</b> {org_html} <br>
            • 누적 리뷰: {reviews_formatted} <span style="color:#FA2828; font-weight:bold;">{rv_disp}</span> <br>
            • 프로모션 현황: {r.get('promo') if r.get('promo') else '없음'}
          </div>
          {event_html}
          {url_button_html}
        </div>
    """

html_content = f"""
<div style="background-color:#ffffff; padding:20px 10px; font-family:'Pretendard', '11STREET Gothic', -apple-system, sans-serif;">
  <table width="100%" border="0" cellpadding="0" cellspacing="0" style="max-width:680px; margin:0 auto; background-color:#ffffff; border:1px solid #eaeaea; border-radius:12px; overflow:hidden;">
    <tr>
      <td align="center" style="background-color:#9BD728; padding:28px 20px; color:#ffffff;">
        <div style="font-size:12px; font-weight:bold; letter-spacing:1px; opacity:0.9; margin-bottom:6px; color:#111;">COMPETITIVE MONITORING</div>
        <h2 style="margin:0; font-size:23px; font-weight:800; line-height:1.3; letter-spacing:-0.5px; color:#111;">H&B 채널 뷰티 랭킹 실시간 리포트</h2>
        <div style="font-size:13px; margin-top:8px; font-weight:600; opacity:0.95; color:#333;">{date_str} 기준 TOP 10</div>
      </td>
    </tr>
    <tr>
      <td style="padding:24px 20px; background-color:#ffffff;">
        {cards_html}
      </td>
    </tr>
    <tr>
      <td align="center" style="background-color:#f9f9f9; padding:18px; font-size:12px; color:#999999; border-top:1px solid #eeeeee;">
        본 리포트는 타겟 H&B 채널의 랭킹 및 리뷰 데이터를 Playwright를 통해 실시간 크롤링하여 자동 작성되었습니다.
      </td>
    </tr>
  </table>
</div>
"""

msg = MIMEMultipart("alternative")
msg["Subject"] = f"[실시간 모니터링] H&B 뷰티 랭킹 급상승 트렌드 리포트 ({now.month}/{now.day})"
msg["From"] = GMAIL_USER
msg["To"] = TO_EMAIL
msg.attach(MIMEText(html_content, "html"))

if not GMAIL_PASS:
    raise ValueError("GMAIL_APP_PASSWORD가 설정되지 않았습니다.")

imap = imaplib.IMAP4_SSL("imap.gmail.com")
imap.login(GMAIL_USER, GMAIL_PASS)

draft_folder = None
typ, mailboxes = imap.list()
if typ == 'OK':
    for mb in mailboxes:
        if b'\\Drafts' in mb:
            draft_folder = mb.split(b' "/" ')[-1].strip().decode('latin1').strip('"')
            break

candidate_folders = [draft_folder, "[Gmail]/&x4TC3Lz0rQDVaA-", "[Gmail]/Drafts", "Drafts"]
success = False

for folder in candidate_folders:
    if not folder: 
        continue
    status, _ = imap.append(folder, "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    if status == 'OK':
        print(f"✅ 성공: [{folder}] 폴더에 올리브영 모니터링 리포트 초안이 정상 생성되었습니다.")
        success = True
        break

if not success:
    raise Exception("임시보관함 폴더를 찾지 못해 초안 생성에 실패했습니다.")

imap.logout()
