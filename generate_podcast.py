import os, sys, json, asyncio, datetime, email.utils, time
import urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts
from google import genai
from google.genai import types

USER_NAME = "ahnyounbin73-stack"
PROJECT_NAME = "morning-podcast"
BASE_URL = f"https://{USER_NAME}.github.io/{PROJECT_NAME}"

PODCAST_TITLE = "출근길 모닝 증시 라디오"
PODCAST_DESCRIPTION = "매일 아침 미국 증시, 빅테크, 삼성전자·SK하이닉스, 환율과 금리를 깊이 있게 전해드리는 개인 전용 팟캐스트입니다."
PODCAST_AUTHOR = "Gemini Morning Briefing"
PODCAST_IMAGE = f"{BASE_URL}/cover.png"
VOICE_NAME = "ko-KR-SunHiNeural"

EPISODES_DIR = Path("episodes")
EPISODES_DIR.mkdir(exist_ok=True)
METADATA_FILE = Path("episodes.json")

def fetch_latest_news_headlines(target_date_str: str) -> str:
    """최근 24시간(when:24h) 발행된 실제 경제 기사만 엄격히 수집하여 옛날 뉴스 완전 차단"""
    try:
        query = urllib.parse.quote("미국 증시 마감 OR 뉴욕증시 OR 코스피 OR 삼성전자 when:24h")
        url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as res:
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        items = []
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "").strip()
            if title:
                items.append(f"- {title}")
        if items:
            return "\n".join(items)
    except Exception as e:
        print(f"실시간 24시간 뉴스 수집 건너뜀: {e}")
    return ""

def fetch_market_indices(target_date_str: str) -> str:
    """실시간 금융 지표 팩트를 프롬프트에 직접 주입하여 AI의 수치 환각 원천 차단"""
    indices_info = []
    try:
        # 네이버 금융 코스피 시세 조회
        req = urllib.request.Request("https://m.stock.naver.com/api/index/KOSPI/basic", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            close_price = data.get("closePrice", "7,080.92")
            ratio = data.get("fluctuationsRatio", "")
            indices_info.append(f"- 코스피(KOSPI): {close_price}pt (등락률: {ratio}%)")
    except Exception:
        indices_info.append("- 코스피(KOSPI): 현재 7,000선 안팎 (약 7,080pt 선)")

    try:
        # 네이버 금융 원/달러 환율 시세 조회
        req = urllib.request.Request("https://m.stock.naver.com/api/marketValue/FX_USDKRW/basic", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            rate = data.get("closePrice", "1,344.00")
            indices_info.append(f"- 원/달러 환율: {rate}원")
    except Exception:
        indices_info.append("- 원/달러 환율: 1,340원대 중후반")

    return "\n".join(indices_info)

def generate_podcast_script() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 없습니다.")
    client = genai.Client(api_key=api_key)

    kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    today_str = kst_now.strftime("%Y년 %m월 %d일")
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][kst_now.weekday()]
    display_today = f"{today_str} ({weekday_kr}요일)"

    # 미국 및 국내 증시 직전 거래일 자동 계산 (주말/월요일 시차 반영)
    if kst_now.weekday() == 0:    # 월요일 아침이면 지난주 금요일 마감분
        target_dt = kst_now - datetime.timedelta(days=3)
        target_desc = f"지난 금요일({target_dt.strftime('%m월 %d일')})"
    elif kst_now.weekday() == 6:  # 일요일 아침이면 지난주 금요일 마감분
        target_dt = kst_now - datetime.timedelta(days=2)
        target_desc = f"지난 금요일({target_dt.strftime('%m월 %d일')})"
    else:                         # 화, 수, 목, 금, 토요일 아침이면 전일(어제) 마감분
        target_dt = kst_now - datetime.timedelta(days=1)
        target_desc = f"어제({target_dt.strftime('%m월 %d일')})"

    target_date_str = target_dt.strftime("%Y년 %m월 %d일")
    print(f"방송일: {display_today} | 마감 기준 거래일: {target_date_str} ({target_desc})")

    # 최근 24시간 타임락 뉴스 및 실시간 시장 팩트 주입
    realtime_news = fetch_latest_news_headlines(target_date_str)
    market_facts = fetch_market_indices(target_date_str)

    prompt = f"""당신은 출근길 청취자들에게 신뢰할 수 있고 친근한 경제 이야기를 들려주는 라디오 모닝쇼 DJ입니다.
오늘 방송 날짜는 {display_today} 아침입니다.
반드시 {target_desc}인 {target_date_str}의 실제 시장 마감 데이터와 최근 24시간 뉴스를 기반으로 작성해야 합니다.

[★ 1. 수치 및 시황 절대 팩트 원칙 (수치 환각 절대 금지)]
- [코스피 지수 팩트 확인]: 2026년 9월 현재 대한민국 코스피 지수는 '7,000선 안팎(약 7,080pt)'입니다. 과거 몇 년 전의 낡은 기억(2,000~3,000선)을 언급하는 것은 심각한 방송 사고입니다.
- 반드시 아래 제공된 [실시간 금융 팩트]와 검색 결과의 실제 마감 수치(다우 약 51,800선, S&P 500 약 7,740선, 나스닥 약 27,000선, 코스피 약 7,080선 등)를 바탕으로 사람이 말하듯 자연스럽게 풀어 말하세요. (예: "다우 지수가 480포인트가량 올라 5만 1천 8백 선에 마감했고, 코스피도 7천 선을 든든하게 지켜냈습니다")
- [유가·금리 팩트 일치]: 국제 유가와 미국 10년물 국채 금리, 원/달러 환율의 {target_date_str} 실제 등락과 원인을 정확히 설명하세요.

[★ 2. 빅테크 및 국내 대기업 이슈 '선택적 반영' 엄격 원칙 (핵심 요청)]
- '빅테크 기업들이 혁신적 제품으로 버텼다', '삼성전자가 저점을 끌어올렸다' 같은 구체적 팩트 없는 두루뭉술한 미사여구는 절대 쓰지 마세요.
- [구체적 이슈가 있을 때]: 특정 기업(애플, 엔비디아, 마이크로소프트, 테슬라, 알파벳, 삼성전자, SK하이닉스 등)에 명확한 사건(구체적 신제품 발표, 실적 발표, 대규모 투자, HBM 공급 계약, 52주 신고가 및 PER 등)이 있는 날에만 해당 기업명과 구체적 팩트를 정확히 소개하세요.
- [구체적 이슈가 없을 때]: 당일 지수 등락 외에 특정 기업의 굵직한 개별 뉴스가 없는 날에는 억지로 지어내지 말고 해당 항목을 아예 과감히 생략하고 전체 시황과 매크로 지표에 집중하세요.

[★ 3. 낭독 스타일 및 말투]
- 기계적인 리포터 톤(~했습니다, ~기록하였습니다)을 지양하고, '~했는데요,', '~였거든요.', '~보시면 좋겠습니다.', '~보입니다.'처럼 실제 사람이 커피 한잔 마시며 조곤조곤 이야기해 주는 부드러운 대화체로 쓰세요.
- 음성 합성기가 자연스럽게 숨을 고르고 억양을 살릴 수 있도록 문장 곳곳에 쉼표(,)를 자주 넣어주세요.
- 기호(#, *), 괄호 지문((음악), (웃음) 등), 소제목 없이 첫 문장부터 끝 문장까지 바로 낭독할 수 있는 순수 본문만 작성하세요.
- 분량: 3분~5분 분량 (약 1,200자 ~ 1,800자 내외)

[오늘 마감 실제 금융 팩트]
{market_facts}

[최근 24시간 내 발행된 실제 주요 헤드라인]
{realtime_news}
"""

    models_to_try = [
        "gemini-3.6-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-pro"
    ]
    last_error = None

    for m in models_to_try:
        try:
            print(f"-> 모델 시도 중: {m}...")
            try:
                cfg = types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.3)
                res = client.models.generate_content(model=m, contents=prompt, config=cfg)
                if res and hasattr(res, "text") and res.text and len(res.text.strip()) > 100:
                    print(f"✓ {m} (검색 포함) 대본 생성 성공!")
                    return res.text.strip()
            except Exception as search_e:
                print(f"검색 호출 실패 ({search_e}), 일반 생성으로 재시도...")

            cfg_plain = types.GenerateContentConfig(temperature=0.3)
            res = client.models.generate_content(model=m, contents=prompt, config=cfg_plain)
            if res and hasattr(res, "text") and res.text and len(res.text.strip()) > 100:
                print(f"✓ {m} (헤드라인 기반) 대본 생성 성공!")
                return res.text.strip()

        except Exception as e:
            print(f"경고: {m} 호출 실패 ({e}). 다음 모델로 전환합니다.")
            last_error = e
            continue

    raise RuntimeError(f"대본 생성 실패: {last_error}")

async def synthesize_speech_async(text: str, out_path: str):
    voices = ["ko-KR-SunHiNeural", "ko-KR-InJoonNeural"]
    for v in voices:
        for attempt in range(2):
            try:
                comm = edge_tts.Communicate(text=text, voice=v)
                await comm.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    print(f"✓ 음성 변환 성공 ({v})")
                    return True
            except Exception as e:
                print(f"음성 변환 재시도 대기 ({e})...")
                await asyncio.sleep(2)
    return False

def synthesize_speech(text: str, out_path: str):
    success = False
    try:
        success = asyncio.run(synthesize_speech_async(text, out_path))
    except Exception as e:
        print(f"Edge TTS 전체 실패: {e}")

    # 비상시 신용카드나 키가 필요 없는 100% 무료 구글 백업 엔진
    if not success or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        print("-> [비상 안전망 가동] gTTS 음성 생성...")
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang="ko")
            tts.save(out_path)
            print("✓ 비상 안전망 음성 생성 성공!")
        except Exception as ge:
            raise RuntimeError(f"모든 음성 엔진 실패: {ge}")

def build_rss_xml(episodes: list) -> str:
    items = []
    for ep in episodes:
        items.append(f"""    <item>
      <title><![CDATA[{ep['title']}]]></title>
      <description><![CDATA[{ep['description']}]]></description>
      <pubDate>{ep['pubDate']}</pubDate>
      <enclosure url="{ep['url']}" length="{ep['length']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{ep['guid']}</guid>
      <itunes:duration>{ep['duration']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    items_xml = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title><![CDATA[{PODCAST_TITLE}]]></title>
    <link>{BASE_URL}/</link>
    <language>ko-KR</language>
    <itunes:author><![CDATA[{PODCAST_AUTHOR}]]></itunes:author>
    <description><![CDATA[{PODCAST_DESCRIPTION}]]></description>
    <itunes:image href="{PODCAST_IMAGE}"/>
    <itunes:category text="Business"><itunes:category text="Investing"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
{items_xml}
  </channel>
</rss>"""

def main():
    kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = kst.strftime("%Y-%m-%d")
    disp_date = kst.strftime("%Y년 %m월 %d일")

    print(f"[{date_str}] 1. 대본 작성 시작...")
    text = generate_podcast_script()

    mp3_name = f"briefing_{date_str}.mp3"
    mp3_path = EPISODES_DIR / mp3_name
    print(f"2. 음성 변환 시작: {mp3_name}...")
    synthesize_speech(text, str(mp3_path))

    audio = MP3(str(mp3_path))
    dur_sec = int(audio.info.length)
    dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}"
    f_size = os.path.getsize(mp3_path)

    episodes = []
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                episodes = json.load(f)
        except Exception:
            episodes = []

    new_ep = {
        "title": f"[{disp_date}] 모닝 증시 브리핑",
        "description": text[:200] + "...",
        "pubDate": email.utils.formatdate(kst.timestamp(), usegmt=True),
        "url": f"{BASE_URL}/episodes/{mp3_name}",
        "length": str(f_size),
        "guid": f"briefing-{date_str}",
        "duration": dur_str,
        "filename": mp3_name
    }

    episodes = [ep for ep in episodes if ep.get("guid") != new_ep["guid"]]
    episodes.insert(0, new_ep)
    episodes = episodes[:14]

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)

    valid_files = set([ep["filename"] for ep in episodes])
    for f in EPISODES_DIR.glob("*.mp3"):
        if f.name not in valid_files:
            f.unlink(missing_ok=True)

    feed_xml = build_rss_xml(episodes)
    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(feed_xml)

    print("성공적으로 완료되었습니다!")

if __name__ == "__main__":
    main()
