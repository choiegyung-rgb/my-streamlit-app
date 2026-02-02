import time
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

import requests
import streamlit as st


# =========================
# Page config
# =========================
st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬")


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

# 질문/선택지 → 장르 점수 매핑(휴리스틱)
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
def score_genres(answers: List[str]) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
    scores = defaultdict(int)
    evidence = defaultdict(list)
    for a in answers:
        mapping = ANSWER_TO_GENRE_SCORES.get(a, {})
        for g, s in mapping.items():
            scores[g] += s
            evidence[g].append(a)
    return dict(scores), dict(evidence)


def pick_genre_strategy(scores: Dict[str, int]) -> Tuple[List[str], str]:
    """
    Returns:
      - selected_genres: [best] or [best, second] (top2 조합)
      - label: 표시용 설명
    """
    if not scores:
        return ["드라마"], "기본값(드라마)"

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best, best_score = ranked[0]
    second, second_score = ranked[1] if len(ranked) > 1 else (None, None)

    # 점수 차가 작으면(예: 2점 이하) Top2 조합 추천
    if second and (best_score - second_score) <= 2:
        return [best, second], f"복합 장르({best} + {second})"
    return [best], f"단일 장르({best})"


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


def per_movie_reason(selected_genres: List[str]) -> str:
    # 영화별 이유는 너무 길어지지 않게 1줄로
    if len(selected_genres) == 1:
        g = selected_genres[0]
        return f"당신의 성향과 가장 잘 맞는 **{g}** 장르의 인기작이라 추천해요."
    g1, g2 = selected_genres[0], selected_genres[1]
    return f"당신의 성향(**{g1}+{g2}**)에 맞는 톤을 가진 인기작이라 추천해요."


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
    """
    - 429/네트워크 오류 등에 대해 아주 가벼운 재시도
    - Streamlit 앱에서 과도한 복잡성 없이 안정성만 보강
    """
    last_exc = None
    for i in range(max_retries + 1):
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code == 429:
                # 간단 백오프 후 재시도
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
    page: int = 1,
) -> List[Dict[str, Any]]:
    session = requests.Session()
    url = f"{TMDB_BASE}/discover/movie"
    params = {
        "api_key": api_key,
        "with_genres": ",".join(map(str, genre_ids)),
        "language": language,
        "region": region,
        "include_adult": "false",
        "sort_by": "popularity.desc",
        "vote_count.gte": min_vote_count,
        "page": page,
    }
    data = _tmdb_get(session, url, params)
    return data.get("results", [])


@st.cache_data(show_spinner=False, ttl=60 * 60)
def movie_details_with_videos(
    api_key: str,
    movie_id: int,
    language: str,
) -> Dict[str, Any]:
    """
    append_to_response=videos 로 상세+예고편을 한 번에 가져옴
    """
    session = requests.Session()
    url = f"{TMDB_BASE}/movie/{movie_id}"
    params = {
        "api_key": api_key,
        "language": language,
        "append_to_response": "videos",
    }
    return _tmdb_get(session, url, params)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def movie_details_basic(
    api_key: str,
    movie_id: int,
    language: str,
) -> Dict[str, Any]:
    session = requests.Session()
    url = f"{TMDB_BASE}/movie/{movie_id}"
    params = {"api_key": api_key, "language": language}
    return _tmdb_get(session, url, params)


def pick_trailer_url(details: Dict[str, Any]) -> Optional[str]:
    """
    videos.results 에서 YouTube trailer 하나를 고름
    """
    videos = (details.get("videos") or {}).get("results") or []
    for v in videos:
        if v.get("site") == "YouTube" and (v.get("type") in ["Trailer", "Teaser"]):
            key = v.get("key")
            if key:
                return f"https://www.youtube.com/watch?v={key}"
    return None


def poster_url(poster_path: Optional[str]) -> Optional[str]:
    if poster_path:
        return POSTER_BASE + poster_path
    return None


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
    st.subheader("추천 옵션")
    language = st.selectbox("언어(language)", ["ko-KR", "en-US"], index=0)
    region = st.selectbox("지역(region)", ["KR", "US", "JP", "GB"], index=0)
    min_vote_count = st.slider("최소 투표 수(vote_count.gte)", 0, 5000, 200, step=50)
    st.caption("투표 수를 올리면 덜 알려진 작품이 줄고, 더 ‘검증된’ 작품 위주로 나와요.")


st.divider()

q1 = st.radio(
    "1. 주말에 가장 하고 싶은 것은?",
    ["집에서 휴식", "친구와 놀기", "새로운 곳 탐험", "혼자 취미생활"],
    index=None,
)
q2 = st.radio(
    "2. 스트레스 받으면?",
    ["혼자 있기", "수다 떨기", "운동하기", "맛있는 거 먹기"],
    index=None,
)
q3 = st.radio(
    "3. 영화에서 중요한 것은?",
    ["감동 스토리", "시각적 영상미", "깊은 메시지", "웃는 재미"],
    index=None,
)
q4 = st.radio(
    "4. 여행 스타일?",
    ["계획적", "즉흥적", "액티비티", "힐링"],
    index=None,
)
q5 = st.radio(
    "5. 친구 사이에서 나는?",
    ["듣는 역할", "주도하기", "분위기 메이커", "필요할 때 나타남"],
    index=None,
)

answers = [q1, q2, q3, q4, q5]

st.divider()

if st.button("결과 보기", type="primary"):
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해주세요.")
        st.stop()
    if any(a is None for a in answers):
        st.warning("모든 질문에 답변을 선택해주세요!")
        st.stop()

    with st.spinner("분석 중..."):
        scores, evidence = score_genres(answers)
        selected_genres, strategy_label = pick_genre_strategy(scores)
        selected_genre_ids = [GENRES[g] for g in selected_genres]

        # Discover 결과를 넉넉히 가져온 뒤(최소 20개),
        # 포스터/줄거리 있는 것 위주로 5개를 뽑는 방식
        raw = discover_movies(
            api_key=api_key,
            genre_ids=selected_genre_ids,
            language=language,
            region=region,
            min_vote_count=min_vote_count,
            page=1,
        )

        # 후보 필터링 + 중복 제거
        picked = []
        seen = set()
        for m in raw:
            mid = m.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            picked.append(m)
            if len(picked) >= 10:  # 5개 뽑기 위한 예비 후보
                break

        if not picked:
            st.info("추천할 영화를 찾지 못했어요. (조건을 완화해보세요: 최소 투표 수 낮추기 등)")
            st.stop()

    # ===== 결과 표시 =====
    best_label = " + ".join(selected_genres)
    st.subheader(f"✅ 당신에게 어울리는 장르: **{best_label}**")
    st.caption(f"선정 방식: {strategy_label}")

    st.markdown("#### 왜 이렇게 추천했나요?")
    st.write(make_overall_reason(selected_genres, evidence))

    with st.expander("장르 점수 보기(디버그)"):
        st.json(scores)

    st.divider()
    st.subheader("🎥 인기 영화 추천 5편")

    # 실제로 5개만 출력 (상세는 append_to_response=videos로 가져오고,
    # overview가 비어 있으면 en-US 폴백)
    shown = 0
    for m in picked:
        if shown >= 5:
            break

        movie_id = m.get("id")
        if not movie_id:
            continue

        # 1) 상세+videos(예고편)
        try:
            details = movie_details_with_videos(api_key, int(movie_id), language=language)
        except requests.RequestException:
            # 상세 실패 시 discover 데이터로라도 표시
            details = m

        title = details.get("title") or "제목 없음"
        rating = details.get("vote_average", 0.0)
        overview = details.get("overview") or ""

        # 2) 줄거리 폴백: ko-KR에서 비어 있으면 en-US로 한번 더
        if not overview and language != "en-US":
            try:
                d2 = movie_details_basic(api_key, int(movie_id), language="en-US")
                overview = d2.get("overview") or overview
            except requests.RequestException:
                pass

        if not overview:
            overview = "줄거리 정보가 없어요."

        poster = poster_url(details.get("poster_path"))
        trailer = None
        if isinstance(details, dict) and details.get("videos"):
            trailer = pick_trailer_url(details)

        cols = st.columns([1, 2], vertical_alignment="top")
        with cols[0]:
            if poster:
                st.image(poster, use_container_width=True)
            else:
                st.image("https://via.placeholder.com/500x750?text=No+Poster", use_container_width=True)

        with cols[1]:
            st.markdown(f"### {title}")
            st.write(f"⭐ 평점: **{float(rating):.1f}** / 10")
            st.write(overview)

            st.caption("이 영화를 추천하는 이유: " + per_movie_reason(selected_genres))

            if trailer:
                st.link_button("예고편 보기(YouTube)", trailer)

        st.divider()
        shown += 1
