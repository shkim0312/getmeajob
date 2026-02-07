import re
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import streamlit as st

# =============================
# Page
# =============================
st.set_page_config(page_title="대학생 진로 추천", page_icon="🧭", layout="centered")

# =============================
# Work24(고용24) API
# =============================
WORK24_LIST_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo212L01.do"
WORK24_DETAIL_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo212D01.do"

LIST_FIXED_PARAMS = {"returnType": "XML", "target": "JOBCD"}     # 목록(직업코드)
DETAIL_FIXED_PARAMS = {"returnType": "XML", "target": "JOBDTL", "jobGb": "1"}  # 상세

# =============================
# Sidebar
# =============================
st.sidebar.header("🔑 고용24 API 설정")
work24_key = st.sidebar.text_input("고용24 authKey", type="password", placeholder="발급받은 인증키 입력")

# =============================
# UI Header
# =============================
st.title("🧭 대학생 진로 추천 웹사이트")
st.write(
    "필수 정보(연령·학력·관심분야)와 선택 정보(성격·전공)를 입력하면, "
    "**키워드 매칭**으로 어울리는 **직업 3개**를 추천해드려요. (데이터: 고용24 직업정보 API)"
)
st.divider()

# =============================
# Options
# =============================
AGE_OPTIONS = ["선택", "18-19", "20-22", "23-25", "26-29", "30+"]
EDU_OPTIONS = ["선택", "고졸", "대학교 재학", "대졸"]
FIELD_OPTIONS = ["선택", "인문", "사회", "교육", "공학", "자연", "의학", "예체능"]
MBTI_LIST = [
    "INTJ","INTP","ENTJ","ENTP",
    "INFJ","INFP","ENFJ","ENFP",
    "ISTJ","ISFJ","ESTJ","ESFJ",
    "ISTP","ISFP","ESTP","ESFP",
]

# =============================
# Helpers
# =============================
def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z가-힣0-9]+", text.strip().lower())

def build_search_keywords(interest_field: str, major_text: str) -> List[str]:
    """
    고용24 목록 API는 '직업명 키워드 검색'을 지원하므로,
    관심분야 + 전공 토큰을 섞어 여러 후보 키워드를 만들어 검색 성공률을 높입니다.
    """
    base = {
        "인문": ["작가", "출판", "편집", "기획", "연구"],
        "사회": ["상담", "행정", "회계", "경찰", "노무"],
        "교육": ["교사", "교육", "강사", "지도"],
        "공학": ["엔지니어", "개발", "기술", "설계", "로봇"],
        "자연": ["연구원", "실험", "분석", "데이터", "과학"],
        "의학": ["의사", "간호", "약사", "치과", "치료"],
        "예체능": ["디자인", "아티스트", "콘텐츠", "음악", "작가"],
    }.get(interest_field, [])

    majors = tokenize(major_text)
    majors = [m.replace("학과", "") for m in majors if len(m) >= 2][:2]

    # 검색은 짧을수록 유리한 편이라 1~3단어 묶음으로 만들기
    candidates = []
    if majors:
        for m in majors:
            candidates.append(m)
            for b in base[:3]:
                candidates.append(f"{m} {b}")
    for b in base[:5]:
        candidates.append(b)

    # 중복 제거
    uniq = []
    for c in candidates:
        if c and c not in uniq:
            uniq.append(c)
    return uniq[:8]  # 너무 많이 호출하지 않도록 제한

def safe_text(parent: Optional[ET.Element], tag: str) -> str:
    if parent is None:
        return ""
    child = parent.find(tag)
    return (child.text or "").strip() if child is not None else ""

def parse_job_list(xml_text: str) -> List[Dict[str, str]]:
    """
    212L01 응답에서 jobList들을 뽑아 dict 리스트로 변환
    """
    root = ET.fromstring(xml_text)
    jobs = []
    for node in root.findall(".//jobList"):
        job = {
            "jobCd": safe_text(node, "jobCd"),
            "jobNm": safe_text(node, "jobNm"),
            "jobClcdNM": safe_text(node, "jobClcdNM"),
            "jobClcd": safe_text(node, "jobClcd"),
        }
        if job["jobCd"] and job["jobNm"]:
            jobs.append(job)
    return jobs

def parse_job_detail_summary(xml_text: str) -> Dict[str, str]:
    """
    212D01 응답에서 jobSum(요약)을 우선적으로 사용
    """
    root = ET.fromstring(xml_text)
    job_sum = root.find(".//jobSum")
    if job_sum is None:
        return {}

    return {
        "jobSum": safe_text(job_sum, "jobSum"),          # 하는 일(요약)
        "way": safe_text(job_sum, "way"),                # 되는 길
        "jobProspect": safe_text(job_sum, "jobProspect"),
        "jobSatis": safe_text(job_sum, "jobSatis"),
        "sal": safe_text(job_sum, "sal"),
        "jobEnv": safe_text(job_sum, "jobEnv"),
    }

@st.cache_data(ttl=600)
def work24_search(auth_key: str, keyword: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    고용24 직업정보 목록(212L01) 키워드 검색
    """
    params = {
        "authKey": auth_key,
        **LIST_FIXED_PARAMS,
        "srchType": "K",
        "keyword": keyword,
    }
    try:
        r = requests.get(WORK24_LIST_URL, params=params, timeout=12)
        r.raise_for_status()
        return parse_job_list(r.text), None
    except Exception as e:
        return [], str(e)

@st.cache_data(ttl=600)
def work24_detail(auth_key: str, job_cd: str, dtl_gb: str = "1") -> Tuple[Dict[str, str], Optional[str]]:
    """
    고용24 직업정보 상세(212D01) - dtlGb=1(요약) 위주
    """
    params = {
        "authKey": auth_key,
        **DETAIL_FIXED_PARAMS,
        "jobCd": job_cd,
        "dtlGb": dtl_gb,
    }
    try:
        r = requests.get(WORK24_DETAIL_URL, params=params, timeout=12)
        r.raise_for_status()
        return parse_job_detail_summary(r.text), None
    except Exception as e:
        return {}, str(e)

def score_job(job: Dict[str, str], interest_field: str, major_text: str, mbti: Optional[str]) -> Tuple[int, List[str]]:
    """
    간단 키워드 매칭 점수 + 추천 이유 생성
    """
    job_nm = (job.get("jobNm") or "").lower()
    cl_nm = (job.get("jobClcdNM") or "").lower()
    tokens = tokenize(major_text)

    score = 0
    reasons = []

    # 관심분야 가중치(분류명에 분야 느낌이 들어가기도 해서 넓게 매칭)
    field_hints = {
        "인문": ["문학", "출판", "기획", "작가", "편집", "언어"],
        "사회": ["상담", "행정", "법", "경찰", "회계", "노무", "복지"],
        "교육": ["교사", "교육", "강사", "지도", "학교"],
        "공학": ["엔지니어", "기술", "개발", "설계", "로봇", "시스템"],
        "자연": ["연구", "실험", "분석", "과학", "데이터"],
        "의학": ["의사", "간호", "약", "치과", "치료", "보건"],
        "예체능": ["디자인", "콘텐츠", "예술", "음악", "방송", "미술"],
    }.get(interest_field, [])

    if any(h.lower() in job_nm or h.lower() in cl_nm for h in field_hints):
        score += 40
        reasons.append(f"관심분야가 **{interest_field}**이고, 이 직업이 관련 키워드와 연결돼요.")

    # 전공 키워드 매칭
    hit_tokens = []
    for t in tokens:
        if t and (t in job_nm or t in cl_nm):
            hit_tokens.append(t)
    if hit_tokens:
        score += 35 + min(len(hit_tokens), 2) * 5
        reasons.append(f"전공/키워드(**{', '.join(hit_tokens[:2])}**)와 직무 연관성이 있어 보여요.")

    # MBTI는 약하게 힌트만 (과도한 단정 방지)
    if mbti:
        score += 5
        reasons.append("MBTI는 참고로만 두고, 프로젝트/동아리/인턴 경험으로 적합도를 확인하면 좋아요.")

    # 최소 이유 보장
    if not reasons:
        score += 10
        reasons = [
            f"관심분야 **{interest_field}**를 바탕으로 관련 직업군을 우선 추천했어요.",
            "추가 키워드를 더 입력하면 더 정교한 매칭이 가능해요."
        ]

    return score, reasons[:2]

# =============================
# Form
# =============================
with st.form("career_form"):
    st.subheader("필수 정보")
    c1, c2, c3 = st.columns(3)
    with c1:
        age_group = st.selectbox("연령", AGE_OPTIONS, index=0)
    with c2:
        education = st.selectbox("학력", EDU_OPTIONS, index=0)
    with c3:
        interest_field = st.selectbox("관심분야", FIELD_OPTIONS, index=0)

    st.divider()
    st.subheader("선택 정보")
    c4, c5 = st.columns([1, 2])
    with c4:
        mbti_raw = st.selectbox("성격(MBTI)", ["선택 안 함"] + MBTI_LIST, index=0)
        mbti = None if mbti_raw == "선택 안 함" else mbti_raw
    with c5:
        major_text = st.text_input("전공(자유 입력)", placeholder="예: 컴퓨터공학, 심리학, 국제관계학, 디자인 등")

    submit = st.form_submit_button("추천받기", type="primary")

# =============================
# Result
# =============================
if submit:
    # 필수 입력 검증
    missing = []
    if age_group == "선택":
        missing.append("연령")
    if education == "선택":
        missing.append("학력")
    if interest_field == "선택":
        missing.append("관심분야")

    if missing:
        st.error(f"필수 항목을 제출해야 해요: {', '.join(missing)}")
        st.stop()

    if not work24_key.strip():
        st.error("사이드바에 고용24 authKey(API Key)를 입력해야 직업 정보를 불러올 수 있어요.")
        st.stop()

    # 1) 관심분야/전공 기반 검색 키워드 만들기
    keywords = build_search_keywords(interest_field, major_text)

    # 2) 여러 키워드로 검색해서 후보 풀 만들기
    with st.spinner("고용24에서 직업 정보를 검색하는 중..."):
        pool: List[Dict[str, str]] = []
        errors = []
        for kw in keywords:
            jobs, err = work24_search(work24_key.strip(), kw)
            if err:
                errors.append(err)
                continue
            pool.extend(jobs)
            if len(pool) >= 40:  # 너무 많이 쌓지 않기
                break

    if not pool:
        st.warning("직업 검색 결과가 없어요. 전공을 더 일반적인 단어로 바꿔보거나, 전공을 비워두고 다시 시도해보세요.")
        if errors:
            st.caption(f"(참고) 마지막 오류: {errors[-1]}")
        st.stop()

    # 중복 제거
    uniq = {}
    for j in pool:
        uniq[j["jobCd"]] = j
    pool = list(uniq.values())

    # 3) 키워드 매칭으로 상위 3개 선정
    scored: List[Tuple[int, Dict[str, str], List[str]]] = []
    for j in pool:
        s, reasons = score_job(j, interest_field, major_text, mbti)
        scored.append((s, j, reasons))

    top3 = sorted(scored, key=lambda x: (x[0], x[1].get("jobNm", "")), reverse=True)[:3]

    # 4) 각 직업 한 줄 설명(상세 요약) 가져오기
    with st.spinner("추천 직업의 상세 요약을 불러오는 중..."):
        enriched = []
        for s, j, reasons in top3:
            detail, _ = work24_detail(work24_key.strip(), j["jobCd"], dtl_gb="1")
            one_liner = (detail.get("jobSum") or "").strip()
            if not one_liner:
                one_liner = "직무 요약 정보를 불러오지 못했어요. (고용24 응답에 요약이 없을 수 있어요.)"
            else:
                # 너무 길면 줄이기
                one_liner = re.sub(r"\s+", " ", one_liner)
                if len(one_liner) > 140:
                    one_liner = one_liner[:140].rstrip() + "…"
            enriched.append((j, one_liner, reasons))

    st.divider()
    st.subheader("✨ 추천 결과 (직업 3개)")

    # 카드 스타일
    st.markdown(
        """
        <style>
        .card {
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 16px;
            padding: 18px 18px 14px 18px;
            margin-bottom: 14px;
            background: #ffffff;
            box-shadow: 0 6px 18px rgba(0,0,0,0.06);
        }
        .meta { display:flex; gap:8px; flex-wrap:wrap; margin-bottom: 8px; }
        .pill {
            display:inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(0,0,0,0.04);
            font-size: 12px;
        }
        .reason { margin: 10px 0 0 0; line-height: 1.6; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for idx, (job, one_liner, reasons) in enumerate(enriched, start=1):
        pills = [
            f"<span class='pill'>#{idx}</span>",
            f"<span class='pill'>관심분야: {interest_field}</span>",
        ]
        if job.get("jobClcdNM"):
            pills.append(f"<span class='pill'>분류: {job['jobClcdNM']}</span>")
        if major_text.strip():
            pills.append("<span class='pill'>전공 입력됨</span>")
        if mbti:
            pills.append(f"<span class='pill'>MBTI: {mbti}</span>")

        reason_html = "<br/>".join([f"• {r}" for r in reasons])

        st.markdown(
            f"""
            <div class="card">
                <div class="meta">{' '.join(pills)}</div>
                <h3 style="margin: 6px 0 6px 0;">{job['jobNm']}</h3>
                <div style="opacity: 0.85;">{one_liner}</div>
                <p class="reason"><b>왜 추천했나요?</b><br/>{reason_html}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.caption("※ 본 추천은 키워드 매칭 기반 데모이며, 직업 정보는 고용24 OPEN-API를 활용합니다.")
