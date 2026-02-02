import streamlit as st
import requests
from collections import defaultdict

st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬")

# ----------------------------
# TMDB 설정
# ----------------------------
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

GENRES = {
    "액션": 28,
    "코미디": 35,
    "드라마": 18,
    "SF": 878,
    "로맨스": 10749,
    "판타지": 14,
}

# 장르별 추천 이유 템플릿
GENRE_REASON = {
    "액션": "에너지 넘치고 몰입감 있는 전개를 좋아하는 성향이 보여서, 박진감 있는 액션 영화가 잘 맞아요.",
    "코미디": "일상 속 스트레스를 웃음으로 풀고 싶어 하는 성향이 보여서, 가볍게 즐길 수 있는 코미디가 잘 맞아요.",
    "드라마": "이야기의 감정선과 여운을 중요하게 여기는 성향이 보여서, 깊이 있는 드라마가 잘 맞아요.",
    "SF": "새로운 아이디어와 ‘왜?’라는 질문을 즐기는 성향이 보여서, 상상력을 자극하는 SF가 잘 맞아요.",
    "로맨스": "관계와 감정의 디테일에 끌리는 성향이 보여서, 설렘과 공감이 있는 로맨스가 잘 맞아요.",
    "판타지": "현실을 잠시 벗어나 세계관에 푹 빠지는 걸 좋아하는 성향이 보여서, 모험적인 판타지가 잘 맞아요.",
}

# ----------------------------
# UI: 제목 / 소개
# ----------------------------
st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 질문 5개로 당신의 영화 취향을 분석하고, TMDB에서 인기 영화 5편을 추천해드려요! 🙂")

# ----------------------------
# Sidebar: API Key 입력
# ----------------------------
with st.sidebar:
    st.header("TMDB 설정")
    api_key = st.text_input("TMDB API Key", type="password", placeholder="여기에 API Key를 입력하세요")
    st.caption("키는 저장되지 않아요. (세션 동안만 사용)")

st.divider()

# ----------------------------
# 질문
# ----------------------------
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

# ----------------------------
# 답변 -> 장르 점수 매핑(휴리스틱)
# ----------------------------
ANSWER_TO_GENRE_SCORES = {
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

def decide_genre(user_answers):
    scores = defaultdict(int)
    evidence = defaultdict(list)

    for a in user_answers:
        mapping = ANSWER_TO_GENRE_SCORES.get(a, {})
        for g, s in mapping.items():
            scores[g] += s
            evidence[g].append(a)

    if not scores:
        return "드라마", {}, {}

    # 점수 높은 장르 선택, 동점이면 우선순위로 결정
    priority = ["드라마", "로맨스", "코미디", "액션", "SF", "판타지"]
    best_score = max(scores.values())
    candidates = [g for g, v in scores.items() if v == best_score]
    candidates.sort(key=lambda g: priority.index(g) if g in priority else 999)

    best = candidates[0]
    return best, dict(scores), dict(evidence)

@st.cache_data(show_spinner=False, ttl=60 * 30)
def fetch_movies(api_key: str, genre_id: int, n: int = 5):
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": api_key,
        "with_genres": genre_id,
        "language": "ko-KR",
        "sort_by": "popularity.desc",
        "page": 1,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])[:n]
    return results

def short_reason(best_genre: str, evidence_for_genre: list[str]):
    base = GENRE_REASON.get(best_genre, "당신의 선택을 바탕으로 이 장르가 잘 맞을 것 같아요.")
    if evidence_for_genre:
        # 증거(답변) 1~2개만 간단히 보여주기
        picks = " / ".join(evidence_for_genre[:2])
        return f"{base}\n\n- 당신의 선택: **{picks}**"
    return base

# ----------------------------
# 결과 보기 버튼
# ----------------------------
if st.button("결과 보기", type="primary"):
    # 필수 체크
    if not api_key:
        st.error("사이드바에 TMDB API Key를 입력해주세요.")
        st.stop()

    if any(a is None for a in answers):
        st.warning("모든 질문에 답변을 선택해주세요!")
        st.stop()

    with st.spinner("분석 중..."):
        best_genre, scores, evidence = decide_genre(answers)
        genre_id = GENRES[best_genre]

        try:
            movies = fetch_movies(api_key, genre_id, n=5)
        except requests.HTTPError as e:
            st.error("TMDB 요청에 실패했어요. API Key가 올바른지 확인해주세요.")
            st.stop()
        except requests.RequestException:
            st.error("네트워크 오류가 발생했어요. 잠시 후 다시 시도해주세요.")
            st.stop()

    st.subheader(f"✅ 당신에게 어울리는 장르: **{best_genre}**")
    st.write(short_reason(best_genre, evidence.get(best_genre, [])))

    # (선택) 점수 공개하고 싶으면 주석 해제
    # with st.expander("장르 점수 보기"):
    #     st.json(scores)

    st.divider()
    st.subheader("🎥 인기 영화 추천 5편")

    if not movies:
        st.info("추천할 영화를 찾지 못했어요. (TMDB 결과가 비어있음)")
        st.stop()

    for m in movies:
        title = m.get("title") or m.get("name") or "제목 없음"
        rating = m.get("vote_average", 0.0)
        overview = m.get("overview") or "줄거리 정보가 없어요."
        poster_path = m.get("poster_path")

        cols = st.columns([1, 2], vertical_alignment="top")

        with cols[0]:
            if poster_path:
                st.image(POSTER_BASE + poster_path, use_container_width=True)
            else:
                st.image("https://via.placeholder.com/500x750?text=No+Poster", use_container_width=True)

        with cols[1]:
            st.markdown(f"### {title}")
            st.write(f"⭐ 평점: **{rating:.1f}** / 10")
            st.write(overview)
            st.caption("이 영화를 추천하는 이유: " + GENRE_REASON.get(best_genre, "당신의 선택과 잘 맞는 장르라서 추천해요."))

        st.divider()
