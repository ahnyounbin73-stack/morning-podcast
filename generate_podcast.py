import os
import sys
import json
import asyncio
import datetime
import email.utils
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts
from google import genai
from google.genai import types

# ----------------------------------------------------
# 1. 설정 및 기본 정보
# ----------------------------------------------------
REPO_NAME = os.environ.get("GITHUB_REPOSITORY", "ahnyounbin73-stack/morning-podcast")
USER_NAME = REPO_NAME.split("/")[0]
PROJECT_NAME = REPO_NAME.split("/")

# GitHub Pages 기본 배포 주소
BASE_URL = f"https://{USER_NAME}.github.io/{PROJECT_NAME}"

PODCAST_TITLE = "출근길 모닝 증시 라디오"
PODCAST_DESCRIPTION = "매일 아침 출근길, 미국 증시와 빅테크, 삼성전자·SK하이닉스, 환율과 금리를 깊이 있게 정리해 드리는 개인 전용 증시 팟캐스트입니다."
PODCAST_AUTHOR = "Gemini Morning Briefing"
PODCAST_IMAGE = f"{BASE_URL}/cover.png"

# 고음질 한국어 라디오 아나운서 음성
VOICE_NAME = "ko-KR-InJoonNeural"

EPISODES_DIR = Path("episodes")
EPISODES_DIR.mkdir(exist_ok=True)
METADATA_FILE = Path("episodes.json")

# ----------------------------------------------------
# 2. 최신 뉴스 기반 대본 생성 (Pro 모델 우선 + 자동 업그레이드 대비)
# ----------------------------------------------------
def generate_podcast_script() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y년 %m월 %d일")

    prompt = f"""
당신은 대한민국 최고의 경제 전문 라디오 진행자입니다.
오늘은 {today_str} 아침입니다. 출근길 청취자를 위한 '모닝 증시 라디오 브리핑' 대본을 작성해 주세요.

[필수 요구사항]
1. 분량: 출근길에 차분하고 깊이 있게 들을 수 있는 3분~6분 분량 (약 1,200자 ~ 2,000자 내외).
2. 어조: 전문적이면서도 청취자에게 조곤조곤 설명해 주는 부드럽고 자연스러운 구어체 라디오 톤.
3. 금지사항: 
   - 제목 기호(#), 불릿포인트(*), 괄호 지문((음악), (웃음) 등), UI 안내 문구 일절 작성 금지.
   - 첫 문장부터 끝 문장까지 아나운서가 바로 낭독할 수 있는 순수 스크립트 본문만 출력할 것.

[대본 구성 순서]
1. [오프닝]: 상쾌한 아침 인사와 오늘 날짜, 오늘 시장을 관통하는 한 줄 테마 소개.
2. [미국 증시 3대 지수 & 매크로 환경]:
   - 다우, S&P 500, 나스닥 마감 수치 및 변동 요인.
   - 미국 10년물 국채 금리, WTI 유가, 원/달러 환율 수치와 등락 원인.
3. [빅테크 & AI 섹터 심층 뉴스]:
   - 시장을 주도한 빅테크 기업의 구체적 화제 사건(실적, 모델/제품 출시, 규제/소송, 대형 투자 등).
   - 52주 신고가 또는 신저가를 기록한 기업이 있다면 주요 배경과 밸류에이션(PER) 평가.
4. [국내 증시 및 삼성전자·SK하이닉스]:
   - 삼성전자와 SK하이닉스의 HBM, 파운드리, 설비투자, 공급망 관련 최신 이슈.
   - 오늘 개장 전 투자자들이 눈여겨볼 국내 시장 핵심 체크포인트.
5. [클로징]: 오늘 하루 투자와 안전한 출근길을 응원하는 따뜻한 마무리 멘트.
"""

    # Pro 모델 1순위 시도 -> 실패 시 차기 최신 모델로 자동 전환 (영구 유지 관리 대비)
    CANDIDATE_MODELS = [
        "gemini-3.6-pro",     # 1순위: 최신 고성능 Pro 모델
        "gemini-3.6-flash",   # 2순위: 최신 고속 Flash 모델
        "gemini-2.0-flash",   # 3순위: 안정적인 표준 모델
        "gemini-1.5-pro",     # 4순위: 이전 세대 Pro 모델
        "gemini-1.5-flash"    # 5순위: 표준 모델
    ]

    last_error = None
    for model_name in CANDIDATE_MODELS:
        try:
            print(f"-> 모델 시도 중: {model_name}...")
            try:
                # 실시간 웹 검색 도구 활성화
                config_with_search = types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=0.7,
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config_with_search,
                )
            except Exception:
                # 검색 도구 미지원 모델일 경우 일반 생성으로 안전 전환
                config_basic = types.GenerateContentConfig(temperature=0.7)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config_basic,
                )

            if response and response.text:
                print(f"✓ {model_name} 모델로 대본 생성 성공!")
                return response.text.strip()
        except Exception as e:
            print(f"경고: {model_name} 호출 실패 ({e}). 다음 후보 모델로 전환합니다.")
            last_error = e
            continue

    raise RuntimeError(f"모든 후보 모델 호출에 실패했습니다. 마지막 오류: {last_error}")

# ----------------------------------------------------
# 3. 고음질 음성 변환 (Edge TTS)
# ----------------------------------------------------
async def synthesize_speech(text: str, output_path: str):
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+3%")
    await communicate.save(output_path)

# ----------------------------------------------------
# 4. 애플 팟캐스트 표준 RSS XML 생성
# ----------------------------------------------------
def build_rss_xml(episodes: list) -> str:
    items_xml = []
    for ep in episodes:
        items_xml.append(f"""    <item>
      <title><![CDATA[{ep['title']}]]></title>
      <description><![CDATA[{ep['description']}]]></description>
      <pubDate>{ep['pubDate']}</pubDate>
      <enclosure url="{ep['url']}" length="{ep['length']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{ep['guid']}</guid>
      <itunes:duration>{ep['duration']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    items_joined = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" 
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title><![CDATA[{PODCAST_TITLE}]]></title>
    <link>{BASE_URL}/</link>
    <language>ko-KR</language>
    <itunes:author><![CDATA[{PODCAST_AUTHOR}]]></itunes:author>
    <description><![CDATA[{PODCAST_DESCRIPTION}]]></description>
    <itunes:image href="{PODCAST_IMAGE}"/>
    <itunes:category text="Business">
      <itunes:category text="Investing"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>
{items_joined}
  </channel>
</rss>"""

# ----------------------------------------------------
# 5. 메인 실행 함수
# ----------------------------------------------------
def main():
    kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = kst_now.strftime("%Y-%m-%d")
    display_date = kst_now.strftime("%Y년 %m월 %d일")

    print(f"[{date_str}] 1. 최신 증시 대본 작성 시작...")
    script_text = generate_podcast_script()
    print("대본 생성 완료. 글자 수:", len(script_text))

    mp3_filename = f"briefing_{date_str}.mp3"
    mp3_path = EPISODES_DIR / mp3_filename

    print(f"2. TTS 음성 변환 중 ({mp3_filename})...")
    asyncio.run(synthesize_speech(script_text, str(mp3_path)))
    print("음성 파일 생성 완료.")

    # 오디오 길이 및 파일 크기 측정
    audio = MP3(str(mp3_path))
    duration_sec = int(audio.info.length)
    duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    file_size = os.path.getsize(mp3_path)

    # 에피소드 메타데이터 갱신
    episodes = []
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                episodes = json.load(f)
        except Exception:
            episodes = []

    new_episode = {
        "title": f"[{display_date}] 모닝 증시 브리핑",
        "description": script_text[:200] + "...",
        "pubDate": email.utils.formatdate(kst_now.timestamp(), usegmt=True),
        "url": f"{BASE_URL}/episodes/{mp3_filename}",
        "length": str(file_size),
        "guid": f"briefing-{date_str}",
        "duration": duration_str,
        "filename": mp3_filename
    }

    # 최신 에피소드 반영 및 최근 14일치만 보관
    episodes = [ep for ep in episodes if ep.get("guid") != new_episode["guid"]]
    episodes.insert(0, new_episode)
    episodes = episodes[:14]

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)

    # 오래된 파일 정리 (용량 절약)
    valid_filenames = {ep
