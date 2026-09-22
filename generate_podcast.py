import os, sys, json, asyncio, datetime, email.utils
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
VOICE_NAME = "ko-KR-InJoonNeural"

EPISODES_DIR = Path("episodes")
EPISODES_DIR.mkdir(exist_ok=True)
METADATA_FILE = Path("episodes.json")

def fetch_latest_news_headlines() -> str:
    """최근 24시간 실제 경제 헤드라인을 수집하여 프롬프트에 직접 주입"""
    try:
        query = urllib.parse.quote("미국 증시 마감 OR 뉴욕증시 OR 코스피 OR 삼성전자")
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
        print(f"실시간 뉴스 RSS 수집 건너뜀: {e}")
    return ""

def generate_podcast_script() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 없습니다.")
    client = genai.Client(api_key=api_key)

    kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    today_str = kst_now.strftime("%Y년 %m월 %d일")
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][kst_now.weekday()]
    display_today = f"{today_str} ({weekday_kr}요일)"

    # 미국 및 국내 증시 직전 거래일 자동 계산 (주말/월요일 처리)
    if kst_now.weekday() == 0:  # 월요일 아침이면 지난주 금요일 마감분
        target_dt = kst_now - datetime.timedelta(days=3)
        target_desc = f"지난 금요일({target_dt.strftime('%m월 %d일')})"
    elif kst_now.weekday() == 6:  # 일요일 아침이면 지난주 금요일 마감분
        target_dt = kst_now - datetime.timedelta(days=2)
        target_desc = f"지난 금요일({target_dt.strftime('%m월 %d일')})"
    else:  # 화, 수, 목, 금, 토요일 아침이면 바로 어제 마감분
        target_dt = kst_now - datetime.timedelta(days=1)
        target_desc = f"어제({target_dt.strftime('%m월 %d일')})"

    target_date_str = target_dt.strftime("%Y년 %m월 %d일")
    print(f"방송일: {display_today} | 마감 기준 거래일: {target_date_str} ({target_desc})")
    
    realtime_news = fetch_latest_news_headlines()

    prompt = f"""당신은 대한민국 최고의 경제 전문 라디오 진행자입니다.
오늘 방송 날짜는 {display_today} 아침입니다.

[★ 핵심 기준일 원칙 - 최신 뉴스 보장 필독]
오늘은 {display_today} 아침이므로, 오늘의 정규장 거래는 아직 시작하지 않았습니다.
따라서 오늘 아침 방송에서 청취자에게 전달할 핵심 마감 시황은 반드시 **{target_desc}인 {target_date_str}의 최신 마감 데이터와 이슈**여야 합니다:
1. 미국 뉴욕 증시: 현지시간 {target_date_str}에 진행되어 오늘({display_today}) 새벽에 최종 마감된 최신 3대 지수(다우, S&P 500, 나스닥)와 주요 시장 요인
2. 거시 경제 지표: {target_date_str} 미국 10년물 국채 금리, WTI 유가, 원/달러 환율의 최신 수치와 등락 원인
3. 빅테크 & AI 섹터: {target_date_str} 시장을 주도한 주요 빅테크 및 AI 기업 핵심 뉴스(화제 사건, 52주 고/저가 및 PER 분석)
4. 국내 증시 및 종목: {target_desc}인 {target_date_str} 마감한 코스피·코스닥 지수 및 삼성전자·SK하이닉스 주요 이슈, 오늘 장 개장 체크포인트

[절대 금지사항]
- 과거 오래된 지난 뉴스를 언급하지 마세요.
- 제목 기호(#), 불릿포인트(*), 괄호 지문((음악), (웃음) 등), 소제목 없이 첫 문장부터 끝 문장까지 바로 낭독할 수 있는 자연스러운 구어체 대본만 출력하세요.
- 분량: 3분~5분 분량 (약 1,200자 ~ 1,800자 내외)

[최근 24시간 실제 주요 헤드라인 참고자료]
{realtime_news}
"""

    models_to_try = ["gemini-3.6-pro", "gemini-3.6-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    last_err = None
    
    for m in models_to_try:
        try:
            print(f"-> 모델 시도 중: {m}...")
            # 1. 실시간 검색 포함 호출 시도
            try:
                cfg = types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.3)
                res = client.models.generate_content(model=m, contents=prompt, config=cfg)
                if res and hasattr(res, "text") and res.text:
                    print(f"✓ {m} (검색 포함) 대본 생성 성공!")
                    return res.text.strip()
            except Exception as search_e:
                print(f"검색 포함 호출 실패 ({search_e}), 일반 텍스트 생성으로 재시도...")

            # 2. 일반 텍스트 생성 호출 시도 (참고자료 헤드라인 활용)
            cfg_plain = types.GenerateContentConfig(temperature=0.3)
            res = client.models.generate_content(model=m, contents=prompt, config=cfg_plain)
            if res and hasattr(res, "text") and res.text:
                print(f"✓ {m} (헤드라인 기반) 대본 생성 성공!")
                return res.text.strip()

        except Exception as e:
            print(f"경고: {m} 전체 호출 실패 ({e}). 다음 후보 모델로 전환합니다.")
            last_err = e
            continue

    raise RuntimeError(f"모든 후보 모델 호출에 실패했습니다. 마지막 오류: {last_err}")

async def synthesize_speech(text: str, out_path: str):
    comm = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+3%")
    await comm.save(out_path)

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
    asyncio.run(synthesize_speech(text, str(mp3_path)))

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
