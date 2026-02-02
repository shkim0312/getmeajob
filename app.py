import requests
import streamlit as st

st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬", layout="centered")

# -----------------------------
# Sidebar: TMDB API Key 입력
# -----------------------------
st.sidebar.header("TMDB 설정")
api_key = st.sidebar.text_input("TMDB API Key", type="password", placeholder="여기에 붙여넣기")

st.title("🎬 나와 어울리는 영화는?")
st.write(
    "5개의 질문에 답하면, 당신의 영화 취향(로맨스/드라마 · 액션/어드벤처 · SF/판타지 · 코미디)을 바탕으로 "
    "TMDB 인기 영화 5편을 추천해줘요."
)

st.divider()

# -----------------------------
# 질문/선택지 데이터
# -----------------------------
questions = [
    {
        "q": "1) 시험 끝나고 갑자기 하루가 비었어. 너는?",
        "options": [
            "A. 잔잔한 카페에 앉아 오늘 하루를 정리한다 (로맨스/드라마)",
            "B. 즉흥으로 당일치기 여행이나 드라이브를 떠난다 (액션/어드벤처)",
            "C. 집에서 세계관 큰 작품을 몰아본다 (SF/판타지)",
            "D. 친구랑 만나서 웃긴 썰 풀며 스트레스 푼다 (코미디)",
        ],
    },
    {
        "q": "2) 단톡방에서 “오늘 뭐 할래?” 했을 때 네 반응은?",
        "options": [
            "A. 둘이 조용히 산책하면서 깊은 얘기하고 싶어 (로맨스/드라마)",
            "B. 방탈출/서바이벌 게임/스포츠처럼 활동적인 거 콜! (액션/어드벤처)",
            "C. 전시·우주/테크 체험·보드게임처럼 신기한 걸 하고 싶어 (SF/판타지)",
            "D. 스탠드업/코미디 영화/예능 보면서 깔깔대고 싶어 (코미디)",
        ],
    },
    {
        "q": "3) 팀플에서 네가 주로 맡는 역할은?",
        "options": [
            "A. 분위기 조율하고 서로 감정 상하지 않게 챙기는 편 (로맨스/드라마)",
            "B. “내가 이끈다!” 일정/역할 분배 확실히 밀어붙이는 편 (액션/어드벤처)",
            "C. 자료 조사·기획 설계·새로운 아이디어 내는 데 강함 (SF/판타지)",
            "D. 발표나 회의 때 센스 있는 한마디로 긴장 푸는 편 (코미디)",
        ],
    },
    {
        "q": "4) 낯선 과제/상황이 생겼을 때 너의 첫 반응은?",
        "options": [
            "A. 의미를 찾고 내 감정부터 정리해본다 (로맨스/드라마)",
            "B. 일단 부딪혀 보고 해결하면서 배우는 타입 (액션/어드벤처)",
            "C. “이건 시스템을 바꾸면 되겠는데?” 구조부터 분석한다 (SF/판타지)",
            "D. “이거 완전 밈 각인데?” 가볍게 넘기며 웃음 포인트 찾는다 (코미디)",
        ],
    },
    {
        "q": "5) 네 휴대폰 갤러리/최근 저장 목록에 가장 가까운 건?",
        "options": [
            "A. 하늘·노을·감성 사진, 가사 캡처, 기록들 (로맨스/드라마)",
            "B. 운동/여행/활동 사진, 지도 캡처, 도전 인증샷 (액션/어드벤처)",
            "C. 세계관 설정, 과학/기술 영상, 신기한 정보 저장 (SF/판타지)",
            "D. 짤·릴스·웃긴 영상, 친구 놀릴(?) 밈 모음 (코미디)",
        ],
    },
]

# -----------------------------
# 유틸: 선택지 -> 성향 카테고리
# -----------------------------
CATEGORY_LABELS = {
    "romance_drama": "(로맨스/드라마)",
    "action_adventure": "(액션/어드벤처)",
    "sf_fantasy": "(SF/판타지)",
    "comedy": "(코미디)",
}

CATEGORY_NAME_KO = {
    "romance_drama": "로맨스/드라마",
    "action_adventure": "액션/어드벤처",
    "sf_fantasy": "SF/판타지",
    "comedy": "코미디",
}

# TMDB 장르 ID (요구사항 기반)
CATEGORY_TO_GENRE_IDS = {
    "romance_drama": [18, 10749],   # 드라마, 로맨스 (둘 다 섞어서 추천)
    "action_adventure": [28],       # 액션
    "sf_fantasy": [878, 14],        # SF, 판타지 (둘 다 섞어서 추천)
    "comedy": [35],                 # 코미디
}

def infer_category_from_choice(choice_text: str) -> str:
    for cat, label in CATEGORY_LABELS.items():
        if label in choice_text:
            return cat
    return "romance_drama"  # fallback

def decide_best_category(answers: list[str]) -> str:
    counts = {k: 0 for k in CATEGORY_LABELS.keys()}
    for a in answers:
        if not a:
            continue
        cat = infer_category_from_choice(a)
        counts[cat] += 1

    # 최다 득표 카테고리 (동점이면 고정 우선순위로 결정)
    priority = ["romance_drama", "action_adventure", "sf_fantasy", "comedy"]
    best = max(priority, key=lambda c: (counts[c], -priority.index(c)))
    return best

# -----------------------------
# TMDB 호출
# -----------------------------
TMDB_DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"

@st.cache_data(show_spinner=False, ttl=60 * 30)  # 30분 캐시
def fetch_popular_movies_by_genres(api_key: str, genre_ids: list[int], language: str = "ko-KR", limit: int = 5):
    """
    genre_ids가 여러 개인 경우, 각 장르로 discover 호출 후 합쳐서 인기순으로 상위 limit개 반환.
    """
    all_movies = []
    seen = set()

    for gid in genre_ids:
        params = {
            "api_key": api_key,
            "with_genres": gid,
            "language": language,
            "sort_by": "popularity.desc",
            "page": 1,
        }
        r = requests.get(TMDB_DISCOVER_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])

        for m in results:
            mid = m.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            all_movies.append(m)

    # popularity 기준 정렬 후 포스터 있는 것 위주로
    all_movies.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    all_movies = [m for m in all_movies if m.get("poster_path")]

    return all_movies[:limit]

def build_reason(category: str, movie: dict) -> str:
    rating = movie.get("vote_average", 0) or 0
    pop = movie.get("popularity", 0) or 0

    base = {
        "romance_drama": "당신의 답변이 감정선과 관계/성장 서사 쪽으로 기울어 있어요.",
        "action_adventure": "당신의 답변이 도전/스릴/속도감 쪽으로 강하게 나타났어요.",
        "sf_fantasy": "당신의 답변이 상상력/세계관/새로운 설정에 끌리는 편이에요.",
        "comedy": "당신의 답변이 가벼운 웃음과 분위기 전환을 중요하게 보여줘요.",
    }.get(category, "당신의 선택 성향과 잘 맞는 작품이에요.")

    # 아주 간단한 이유 템플릿
    if rating >= 7.5:
        extra = "평점도 높아서 만족도가 좋은 편이라 추천해요."
    elif pop >= 200:
        extra = "지금 많은 사람들이 보고 있는 인기작이라 추천해요."
    else:
        extra = "장르 톤이 잘 맞고 부담 없이 보기 좋아서 추천해요."

    return f"{base} {extra}"

# -----------------------------
# 질문 UI
# -----------------------------
answers = []
for i, item in enumerate(questions, start=1):
    ans = st.radio(
        item["q"],
        item["options"],
        key=f"q{i}",
        index=None,  # 처음엔 선택 안 된 상태
    )
    answers.append(ans)
    st.write("")

st.divider()

# -----------------------------
# 결과 보기 버튼
# -----------------------------
if st.button("결과 보기", type="primary"):
    # 입력 검증
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해줘!")
        st.stop()

    if any(a is None for a in answers):
        st.warning("5개 질문에 모두 답해야 결과를 볼 수 있어요.")
        st.stop()

    with st.spinner("분석 중..."):
        category = decide_best_category(answers)
        genre_ids = CATEGORY_TO_GENRE_IDS[category]

        try:
            movies = fetch_popular_movies_by_genres(api_key, genre_ids, language="ko-KR", limit=5)
        except requests.HTTPError as e:
            st.error(f"TMDB 요청에 실패했어요. (HTTP 오류) {e}")
            st.stop()
        except requests.RequestException as e:
            st.error(f"TMDB 요청 중 네트워크 오류가 발생했어요: {e}")
            st.stop()

    st.subheader(f"당신의 영화 취향: {CATEGORY_NAME_KO.get(category, category)}")
    st.write("아래는 TMDB에서 가져온 인기 영화 추천 5편이에요.")

    if not movies:
        st.info("추천할 영화를 찾지 못했어요. (포스터가 없는 작품이 많거나 응답이 비어있을 수 있어요)")
        st.stop()

    for m in movies:
        title = m.get("title") or m.get("name") or "제목 없음"
        overview = m.get("overview") or "줄거리 정보가 없어요."
        rating = m.get("vote_average", 0)
        poster_path = m.get("poster_path")
        poster_url = f"{TMDB_POSTER_BASE}{poster_path}" if poster_path else None

        reason = build_reason(category, m)

        st.markdown("---")
        cols = st.columns([1, 2])

        with cols[0]:
            if poster_url:
                st.image(poster_url, use_container_width=True)
            else:
                st.write("포스터 없음")

        with cols[1]:
            st.markdown(f"### {title}")
            st.write(f"⭐ 평점: {rating:.1f}")
            st.write(overview)
            st.caption(f"💡 이 영화를 추천하는 이유: {reason}")


