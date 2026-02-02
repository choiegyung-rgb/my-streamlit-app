import streamlit as st

st.set_page_config(page_title="나와 어울리는 영화는?", page_icon="🎬")

# 제목 & 소개
st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 질문 5개로 당신의 영화 취향을 알아보는 심리테스트예요! 아래 질문에 가장 가까운 답을 골라주세요 🙂")

st.divider()

# 질문/선택지
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

st.divider()

# 버튼 클릭 시 "분석 중..." 표시
if st.button("결과 보기", type="primary"):
    st.info("분석 중...")
