# 메일 메시지 구성 및 Gmail 임시보관함 주입
msg = MIMEMultipart("alternative")
msg["Subject"] = f"[실시간 모니터링] H&B 뷰티 랭킹 급상승 트렌드 리포트 ({now.month}/{now.day})"
msg["From"] = GMAIL_USER
msg["To"] = TO_EMAIL
msg.attach(MIMEText(html_content, "html"))

if not GMAIL_PASS:
    raise ValueError("GMAIL_APP_PASSWORD가 설정되지 않았습니다.")

imap = imaplib.IMAP4_SSL("imap.gmail.com")
imap.login(GMAIL_USER, GMAIL_PASS)

# 실제 임시보관함 폴더명 탐색
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
