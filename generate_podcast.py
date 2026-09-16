import os, sys, json, asyncio, datetime, email.utils
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts
from google import genai
from google.genai import types

REPO_NAME = os.environ.get("GITHUB_REPOSITORY", "ahnyounbin73-stack/morning-podcast")
USER_NAME = REPO_NAME.split("/")[0]
PROJECT_NAME = REPO_NAME.split("/")
BASE_URL = f"https://{USER_NAME}.github.io/{PROJECT_NAME}"

PODCAST_TITLE = "출근길 모닝 증시 라디오"
PODCAST_DESCRIPTION = "매일 아침 미국 증시, 빅테크, 삼성전자·SK하이닉스, 환율과 금리를 깊이 있게 전해드리는 개인 전용 팟캐스트입니다."
PODCAST_AUTHOR = "Gemini Morning Briefing"
PODCAST_IMAGE = f"{BASE_URL}/cover.png"
VOICE_NAME = "ko-KR-InJoonNeural"

EPISODES_DIR = Path("episodes")
EPISODES_DIR.mkdir(exist_ok=True)
METADATA_FILE = Path("episodes.json")

def generate_podcast_script() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 없습니다.")
    client = genai.Client(api_key=api_key)
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y년 %m월 %d일")

    prompt = f"""당신은 대한민국 최고의 경제 전문 라디오 진행자입니다. 오늘은 {today_str} 아침입니다.
출근길 청취자를 위한 3분~5분 분량(약 1,200~1,800자)의 모닝 증시 라디오 대본을 작성하세요.
기호(#, *)나 괄호 지문, 소제목 없이 바로 낭독할 수 있는 자연스러운 구어체 본문만 출력하세요.
[구성 순서]
1. 오프닝 인사 및 오늘 날짜, 시장 핵심 테마
2. 미국 3대 지수(다우, S&P 500, 나스닥) 마감 및 매크로(10년물 금리, 유가, 환율) 수치와 원인
3. 빅테크 및 AI 기업 핵심 뉴스(화제 사건, 52주 고/저가 및 PER 분석)
4. 국내 증시 및 삼성전자·SK하이닉스 주요 이슈, 오늘 개장 체크포인트
5. 따뜻한 출근길 클로징 인사"""

    models_to_try = ["gemini-3.6-pro", "gemini-3.6-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    last_err = None
    for m in models_to_try:
        try:
            print(f"시도 중: {m}")
            try:
                cfg = types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.7)
                res = client.models.generate_content(model=m, contents=prompt, config=cfg)
            except Exception:
                cfg = types.GenerateContentConfig(temperature=0.7)
                res = client.models.generate_content(model=m, contents=prompt, config=cfg)
            if res and res.text:
                print(f"성공: {m}")
                return res.text.strip()
        except Exception as e:
            print(f"{m} 실패: {e}")
            last_err = e
    raise RuntimeError(f"대본 생성 실패: {last_err}")

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

    print(f"[{date_str}] 대본 작성 시작...")
    text = generate_podcast_script()

    mp3_name = f"briefing_{date_str}.mp3"
    mp3_path = EPISODES_DIR / mp3_name
    print(f"음성 변환 시작: {mp3_name}...")
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
