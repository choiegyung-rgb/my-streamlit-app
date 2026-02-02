import time
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple, Any, Optional

import requests
import streamlit as st


# =========================
# Page config
# =========================
st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬", layout="wide")


# =========================
# Constants
# =========================
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_BASE = "https://api.themoviedb.org/3"

GENRES = {
    "액션": 28,
    "코미디": 35,
    "드라마": 18,
    "SF": 878,
    "로맨스": 10749,
    "판타지": 14,
}

GENRE_REASON = {
    "액션": "에너지 넘치고 몰입감 있는 전개를 좋아하는 성향이 보여서, 박진감 있는 액션 영화가 잘 맞아요.",
    "코미디": "일상 속 스트레스를 웃음으로 풀고 싶어 하는 성향이 보여서, 가볍게 즐길 수 있는 코미디가 잘 맞아요.",
    "드라마": "이야기의 감정선과 여운을 중요하게 여기는 성향이 보여서, 깊이 있는 드라마가 잘 맞아요.",
    "SF": "새로운 아이디어와 ‘왜?’라는 질문을 즐기는 성향이 보여서, 상상력을 자극하는 SF가 잘 맞아요.",
    "로맨스": "관계와 감정의 디테일에 끌리는 성향이 보여서, 설렘과 공감이 있는 로맨스가 잘 맞아요.",
    "판타지": "현실을 잠시 벗어나 세계관에 푹 빠지는 걸 좋아하는 성향이 보여서, 모험적인 판타지가 잘 맞아요.",
}

# 질문별 가중치 (우선순위 개선점 #1)
QUESTION_WEIGHTS = {
    "q1": 1.0,
    "q2": 1.0,
    "q3": 1.8,  # '영화에서 중요한 것'은 장르 성향에 가장 직접적
    "q4": 1.1,
    "q5": 1.0,
}

ANSWER_TO_GENRE_SCORES: Dict[str, Dict[str, int]] = {
    # Q1
    "집에서 휴식": {"드라마": 2, "로맨스": 1},
    "친구와 놀기": {"코미디": 2, "로맨스": 1},
    "새로운 곳 탐험": {"액션": 2, "판타지": 1},
    "혼자 취미생활": {"SF": 2, "드라마": 1},
    # Q2
    "혼자 있기": {"드라마": 2, "SF": 1},
    "수다 떨기": {"로맨스": 2, "코미디": 1},
    "운동하기": {"액션": 2, "판타지": 1},
    "맛있는 거 먹기": {"코미디": 2, "로맨스": 1},
    # Q3
    "감동 스토리": {"드라마": 2, "로맨스": 1},
    "시각적 영상미": {"판타지": 2, "SF": 1},
    "깊은 메시지": {"SF": 2, "드라마": 1},
    "웃는 재미": {"코미디": 3},
    # Q4
    "계획적": {"드라마": 2, "SF": 1},
    "즉흥적": {"로맨스": 1, "코미디": 2},
    "액티비티": {"액션": 3},
    "힐링": {"로맨스": 2, "드라마": 1},
    # Q5
    "듣는 역할": {"드라마": 2, "로맨스": 1},
    "주도하기": {"액션": 2, "SF": 1},
    "분위기 메이커": {"코미디": 3},
    "필요할 때 나타남": {"판타지": 2, "액션": 1},
}


# =========================
# Helpers: scoring / reasons
# =========================
def score_genres_weighted(answers_by_q: Dict[str, str]) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    """
    우선순위 개선점 #1
    - 질문별 가중치 반영
    - evidence(근거 답변)도 같이 모음
    """
    scores = defaultdict(float)
    evidence = defaultdict(list)

    for qkey, ans in answers_by_q.items():
        w = QUESTION_WEIGHTS.get(qkey, 1.0)
        mapping = ANSWER_TO_GENRE_SCORES.get(ans, {})
        for g, s in mapping.items():
            scores[g] += s * w
            evidence[g].append(ans)

    return dict(scores), dict(evidence)


def pick_top_genres(scores: Dict[str, float], k: int = 3) -> List[str]:
    if not scores:
        return ["드라마"]
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = [g for g, _ in ranked[:k]]
    return top


def make_overall_reason(selected_genres: List[str], evidence: Dict[str, List[str]]) -> str:
    parts = []
    for g in selected_genres:
        base = GENRE_REASON.get(g, "당신의 선택과 잘 맞는 장르라서 추천해요.")
        picks = evidence.get(g, [])
        if picks:
            sample = " / ".join(picks[:2])
            parts.append(f"- **{g}**: {base} (당신의 선택: **{sample}**)")
        else:
            parts.append(f"- **{g}**: {base}")
    return "\n".join(parts)


def per_movie_reason(main_genre: str, sub_genres: List[str]) -> str:
    if not sub_genres:
        return f"당신의 메인 취향인 **{main_genre}** 장르와 잘 맞아서 추천해요."
    sub_label = "+".join(sub_genres[:2])
    return f"당신의 취향(**{main_genre}** / {sub_label})과 비슷한 톤의 인기작이라 추천해요."


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    max_v = max(scores.values())
    if max_v <= 0:
        return {k: 0.0 for k in scores}
    return {k: v / max_v for k, v in scores.items()}


# =========================
# Helpers: TMDB API (requests)
# =========================
def _tmdb_get(
    session: requests.Session,
    url: str,
    params: Dict[str, Any],
    max_retries: int = 2,
    backoff_sec: float = 0.8,
) -> Dict[str, Any]:
    last_exc = None
    for i in range(max_retries + 1):
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(backoff_sec * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last_exc = e
            time.sleep(backoff_sec * (i + 1))
    raise last_exc if last_exc else RuntimeError("TMDB 요청 실패")


@st.cache_data(show_spinner=False, ttl=60 * 30)
def discover_movies(
    api_key: str,
    genre_ids: List[int],
    language: str,
    region: str,
    min_vote_count: int,
    min_vote_average: float,
    years_back: int,
    page: int = 1,
) -> List[Dict[str, Any]]:
    """
    우선순위 개선점 #2
    - vote_average.gte + release_date.gte(최근 N년) 옵션 추가
    """
    session = requests.Session()
    url = f"{TMDB_BASE}/discover/movie"

    today = date.today()
    gte_year = max(today.year - years_back, 1900)
    release_gte = f"{gte_year}-01-01"

    params = {
        "api_key": api_key,
        "with_genres": ",".join(map(str, genre_ids)),
        "language": language,
        "region": region,
        "include_adult": "false",
        "sort_by": "popularity.desc",
        "vote_count.gte": min_vote_count,
        "vote_average.gte": min_vote_average,
        "primary_release_date.gte": release_gte,
        "page": page,
    }
    data = _tmdb_get(session, url, params)
    return data.get("results", [])


@st.cache_data(show_spinner=False, ttl=60 * 60)
def movie_details_with_videos(api_key: str, movie_id: int, language: str) -> Dict[str, Any]:
    session = requests.Session()
    url = f"{TMDB_BASE}/movie/{movie_id}"
    params = {"api_key": api_key, "language": language, "append_to_response": "videos"}
    return _tmdb_get(session, url, params)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def movie_details_basic(api_key: str, movie_id: int, language: str) -> Dict[str, Any]:
    session = requests.Session()
    url = f"{TMDB_BASE}/movie/{movie_id}"
    params = {"api_key": api_key, "language": language}
    return _tmdb_get(session, url, params)


def pick_trailer_url(details: Dict[str, Any]) -> Optional[str]:
    videos = (details.get("videos") or {}).get("results") or []
    for v in videos:
        if v.get("site") == "YouTube" and (v.get("type") in ["Trailer", "Teaser"]):
            key = v.get("key")
            if key:
                return f"https://www.youtube.com/watch?v={key}"
    return None


def poster_url(poster_path: Optional[str]) -> Optional[str]:
    return (POSTER_BASE + poster_path) if poster_path else None


# =========================
# Session state (우선순위 개선점 #3)
# =========================
if "result" not in st.session_state:
    st.session_state.result = None

if "candidates" not in st.session_state:
    st.session_state.candidates = []

if "selected" not in st.session_state:
    st.session_state.selected = []

if "scores" not in st.session_state:
    st.session_state.scores = {}


def clear_result():
    st.session_state.result = None
    st.session_state.candidates = []
    st.session_state.selected = []
    st.session_state.scores = {}


# =========================
# UI
# =========================
st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 질문 5개로 당신의 영화 취향을 분석하고, TMDB에서 인기 영화 5편을 추천해드려요! 🙂")

with st.sidebar:
    st.header("TMDB 설정")
    api_key = st.text_input("TMDB API Key", type="password", placeholder="여기에 API Key를 입력하세요")
    st.caption("키는 저장되지 않아요. (세션 동안만 사용)")

    st.divider()
    st.subheader("추천 필터 (고도화)")
    language = st.selectbox("언어(language)", ["ko-KR", "en-US"], index=0)
    region = st.selectbox("지역(region)", ["KR", "US", "JP", "GB"], index=0)

    min_vote_count = st.slider("최소 투표 수(vote_count.gte)", 0, 5000, 200, step=50)
    min_vote_average = st.slider("최소 평점(vote_average.gte)", 0.0, 10.0, 5.0, step=0.1)
    years_back = st.slider("최근 몇 년 작품 위주", 0, 30, 10, step=1)
    st.caption("필터를 올릴수록 추천이 ‘깔끔’해지지만 결과가 줄어들 수 있어요.")

st.divider()

# Questions
q1 = st.radio("1. 주말에 가장 하고 싶은 것은?", ["집에서 휴식", "친구와 놀기", "새로운 곳 탐험", "혼자 취미생활"], index=None)
q2 = st.radio("2. 스트레스 받으면?", ["혼자 있기", "수다 떨기", "운동하기", "맛있는 거 먹기"], index=None)
q3 = st.radio("3. 영화에서 중요한 것은?", ["감동 스토리", "시각적 영상미", "깊은 메시지", "웃는 재미"], index=None)
q4 = st.radio("4. 여행 스타일?", ["계획적", "즉흥적", "액티비티", "힐링"], index=None)
q5 = st.radio("5. 친구 사이에서 나는?", ["듣는 역할", "주도하기", "분위기 메이커", "필요할 때 나타남"], index=None)

answers_by_q = {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5}

st.divider()

# Actions
action_cols = st.columns([1, 1, 6])
with action_cols[0]:
    run_btn = st.button("결과 보기", type="primary")
with action_cols[1]:
    st.button("다시 하기", on_click=clear_result)

# =========================
# Run recommendation
# =========================
if run_btn:
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해주세요.")
        st.stop()
    if any(v is None for v in answers_by_q.values()):
        st.warning("모든 질문에 답변을 선택해주세요!")
        st.stop()

    with st.spinner("분석 중..."):
        scores, evidence = score_genres_weighted(answers_by_q)
        top3 = pick_top_genres(scores, k=3)
        main_genre = top3[0]
        sub_genres = top3[1:]

        # 추천은 메인+서브(Top2)로 검색하되, 결과 부족하면 메인만 fallback
        genre_ids_top2 = [GENRES[main_genre]]
        if sub_genres:
            genre_ids_top2.append(GENRES[sub_genres[0]])

        # 1) top2로 먼저 가져오기
        raw = discover_movies(
            api_key=api_key,
            genre_ids=genre_ids_top2,
            language=language,
            region=region,
            min_vote_count=min_vote_count,
            min_vote_average=min_vote_average,
            years_back=years_back,
            page=1,
        )

        # 2) 결과 부족하면 메인 장르만으로 fallback
        if len(raw) < 6:
            raw = discover_movies(
                api_key=api_key,
                genre_ids=[GENRES[main_genre]],
                language=language,
                region=region,
                min_vote_count=min_vote_count,
                min_vote_average=min_vote_average,
                years_back=years_back,
                page=1,
            )

        # 후보 최대 9개 확보(3열 카드)
        candidates = []
        seen = set()
        for m in raw:
            mid = m.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            candidates.append(m)
            if len(candidates) >= 9:
                break

        if not candidates:
            st.info("추천할 영화를 찾지 못했어요. (필터를 낮추거나 최근 연도를 늘려보세요.)")
            st.stop()

    # Session state에 저장 (우선순위 개선점 #3)
    st.session_state.result = {
        "top3": top3,
        "main_genre": main_genre,
        "sub_genres": sub_genres,
        "reason_text": make_overall_reason(top3, evidence),
    }
    st.session_state.candidates = candidates
    st.session_state.scores = scores


# =========================
# Render result (if exists)
# =========================
if st.session_state.result:
    top3 = st.session_state.result["top3"]
    main_genre = st.session_state.result["main_genre"]
    sub_genres = st.session_state.result["sub_genres"]

    label = main_genre if not sub_genres else f"{main_genre} + {sub_genres[0]}"
    st.markdown(f"## 🎉 당신에게 딱인 장르는: **{label}**!")
    st.caption(f"메인 취향: {main_genre} · 서브 취향: {', '.join(sub_genres) if sub_genres else '없음'}")

    # 우선순위 개선점 #1/2와 연결: 점수 바 차트(시각화)
    norm = normalize_scores(st.session_state.scores)
    chart_data = {g: norm.get(g, 0.0) for g in ["드라마", "로맨스", "코미디", "액션", "SF", "판타지"]}
    st.markdown("#### 🎯 당신의 장르 성향(상대 점수)")
    st.bar_chart(chart_data)

    with st.expander("왜 이렇게 추천했나요?"):
        st.write(st.session_state.result["reason_text"])

    st.divider()
    st.subheader("🎥 추천 영화")

    # 3-column cards
    cols = st.columns(3)
    for i, m in enumerate(st.session_state.candidates):
        col = cols[i % 3]
        with col:
            movie_id = m.get("id")
            title = m.get("title") or "제목 없음"
            rating = float(m.get("vote_average") or 0.0)
            p_url = poster_url(m.get("poster_path"))

            with st.container(border=True):
                if p_url:
                    st.image(p_url, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/500x750?text=No+Poster", use_container_width=True)

                st.markdown(f"**{title}**")
                st.write(f"⭐ **{rating:.1f}** / 10")

                with st.expander("상세 보기"):
                    with st.spinner("상세 정보를 불러오는 중..."):
                        details = None
                        if movie_id:
                            try:
                                details = movie_details_with_videos(api_key, int(movie_id), language=language)
                            except requests.RequestException:
                                details = None

                        d = details if isinstance(details, dict) else m
                        overview = d.get("overview") or ""

                        if not overview and language != "en-US" and movie_id:
                            try:
                                d2 = movie_details_basic(api_key, int(movie_id), language="en-US")
                                overview = d2.get("overview") or overview
                            except requests.RequestException:
                                pass

                        if not overview:
                            overview = "줄거리 정보가 없어요."

                        trailer = pick_trailer_url(d) if isinstance(d, dict) and d.get("videos") else None

                    st.write(overview)
                    st.caption("이 영화를 추천하는 이유: " + per_movie_reason(main_genre, sub_genres))
                    if trailer:
                        st.link_button("예고편 보기(YouTube)", trailer)
else:
    st.info("왼쪽에서 TMDB 키를 입력하고, 질문에 답한 뒤 **결과 보기**를 눌러주세요!")
