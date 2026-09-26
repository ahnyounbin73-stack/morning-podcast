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

# 자연스럽고 따뜻한 여성 라디오 DJ 음성
VOICE_NAME = "ko-KR-SunHiNeural"

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

    # 직전 거래일 자동 계산 (주말/월요일 처리)
    if kst_now.weekday() == 0:
        target_dt = kst_now - datetime.timedelta(days=3)
        target_desc = f"지난 금요일({target_dt.strftime('%m월 %d일')})"
    elif kst_now.weekday() == 6:
        target_dt = kst_now - datetime.timedelta(days=2)
        target_desc = f"지난 금요일({target_dt.strftime('%m월 %d일')})"
    else:
        target_dt = kst_now - datetime.timedelta(days=1)
        target_desc = f"어제({target_dt.strftime('%m월 %d일')})"

    target_date_str = target_dt.strftime("%Y년 %m월 %d일")
    realtime_news = fetch_latest_news_headlines()

    prompt = f"""당신은 출근길 청취자들에게 다정하고 따뜻하게 경제 이야기를 들려주는 라디오 모닝쇼 DJ입니다.
오늘 방송 날짜는 {display_today} 아침입니다.

[★ 사람처럼 들리게 하는 핵심 낭독 지침]
1. [구어체 대화체 필수]: 
   - 기계적인 '~했습니다', '~기록하였습니다' 문체를 절대 쓰지 마세요.
   - '~했는데요,', '~였거든요.', '~보시면 좋겠습니다.', '~보입니다.'처럼 실제 사람이 커피 한잔 마시며 조곤조곤 이야기해 주는 부드러운 대화체로 쓰세요.
2. [숫자 발음 입말화]:
   - '52,093.11pt'처럼 적으면 기계가 이상하게 읽습니다.
   - 반드시 '5만 2천 선으로 3백 포인트가량 내리면서', '0.6% 정도 밀리면서', '1,348원 선'처럼 사람이 실제로 말하는 자연스러운 발음 형태로 풀어 쓰세요.
3. [자연스러운 호흡(숨소리) 유도]:
   - 음성 합성기가 적절히 숨을 고르고 억양을 살릴 수 있도록, 문장 곳곳에 쉼표(,)를 자연스럽게 자주 넣어주세요.
   - '그런데요,', '한편,', '오늘 아침 가장 눈길을 끄는 건,', '어제 장 보신 분들은 아시겠지만,' 같은 자연스러운 연결 멘트를 넣어주세요.
4. [금지 사항]:
   - 기호(#, *), 괄호 지문((음악), (웃음) 등), 소제목 없이 첫 문장부터 끝 문장까지 바로 읽을 수 있는 순수 본문만 작성하세요.
   - 분량: 3분~5분 분량 (약 1,200자 ~ 1,800자 내외)

[다룰 핵심 내용 ({target_desc}인 {target_date_str} 마감 기준)]
- 상쾌한 아침 인사 및 오늘 시장을 관통하는 한 줄 테마
- 미국 3대 지수(다우, S&P 500, 나스닥) 마감 상황과 10년물 금리, 유가, 환율 동향
- 글로벌 빅테크 및 AI 기업들의 화제 사건(실적, 모델/제품 출시, 52주 고/저가 분석)
- 국내 시장 코스피·코스닥 마감 및 삼성전자·SK하이닉스 핵심 소식, 오늘 장 개장 체크포인트
- 따뜻한 하루 응원 클로징 멘트

[최근 24시간 실제 주요 헤드라인 참고자료]
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
                cfg = types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.4)
                res = client.models.generate_content(model=m, contents=prompt, config=cfg)
                if res and hasattr(res, "text") and res.text and len(res.text.strip()) > 100:
                    print(f"✓ {m} (검색 포함) 대본 생성 성공!")
                    return res.text.strip()
            except Exception as search_e:
                print(f"검색 호출 실패 ({search_e}), 일반 생성으로 재시도...")

            cfg_plain = types.GenerateContentConfig(temperature=0.4)
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
    """1순위: 자연스러운 고음질 Edge TTS 음성 합성"""
    voices = ["ko-KR-SunHiNeural", "ko-KR-InJoonNeural"]
    for v in voices:
        for attempt in range(2):
            try:
                comm = edge_tts.Communicate(text=text, voice=v, rate="+0%")
                await comm.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    print(f"✓ 고음질 음성 생성 완료 ({v})")
                    return True
            except Exception as e:
                print(f"고음질 음성 일시 지연 ({e})...")
                await asyncio.sleep(2)
    return False

def synthesize_speech(text: str, out_path: str):
    """음성 합성 통합 관리: 고음질 Edge TTS 우선 + 비상시 100% 무료 구글 백업 엔진"""
    success = False
    try:
        success = asyncio.run(synthesize_speech_async(text, out_path))
    except Exception as e:
        print(f"Edge TTS 전체 실패: {e}")

    # 만에 하나 Edge TTS가 모두 실패할 경우, 100% 무료 구글 백업 엔진으로 즉시 대체
    if not success or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        print("-> [비상 안전망 가동] 100% 무료 구글 백업 엔진(gTTS)으로 음성 생성...")
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
