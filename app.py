import re
import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import streamlit as st

# =============================
# Page config
# =============================
st.set_page_config(page_title="대학생 진로 추천", page_icon="🧭", layout="centered")

# =============================
# Work24 API constants
# =============================
WORK24_LIST_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo212L01.do"
WORK24_DETAIL_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo212D01.do"

# 212L01 필수 파라미터: returnType=XML, target=JOBCD :contentReference[oaicite:3]{index=3}
WORK24_LIST_RETURN_TYPE = "XML"
WORK24_LIST_TARGET = "JOBCD"

# 212D01 필수 파라미터: returnType=XML, target=JOBDTL, jobGb=1, dtlGb(1~7) :contentReference[oaicite:4]{index=4}
WORK24_DETAIL_RETURN_TYPE = "XML"
WORK24_DETAIL_TARGET = "JOBDTL"
WORK24_DETAIL_JOBGB = "1"

# =============================
# Sidebar: Work24 authKey
# =============================
st.sidebar.header("🔑 고용24(Work24) API 설정")
work24_key = st.sidebar.text_input("Work24 authKey", type="password", placeholder="발급받은 인증키 입력")

st.title("🧭 대학생 진로 추천 웹사이트")
st.write(
    "필수 정보(연령·학력·관심분야)와 선택 정보(성격·전공)를 입력하면, "
    "**입력 패턴 기반으로 분야 키워드를 뽑아** 고용24 직업정보 API에서 **직업 4개**를 가져와 추천합니다."
)
st.divider()

# =============================
# Input options
# =============================
MBTI_LIST = [
    "INTJ","INTP","ENTJ","ENTP",
    "INFJ","INFP","ENFJ","ENFP",
    "ISTJ","ISFJ","ESTJ","ESFJ",
    "ISTP","ISFP","ESTP","ESFP",
]

# =============================
# Helpers
# =============================
def tokenize_ko(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z가-힣0-9]+", text.strip().lower())

def build_field_keyword(interest_field: str, major_text: str) -> str:
    """
    관심분야/전공을 바탕으로 Work24 '직업명 키워드(keyword)'를 구성.
    Work24 212L01은 srchType=K(키워드) + keyword(직업명 키워드 검색) :contentReference[oaicite:5]{index=5}
    """
    # 분야별 기본 키워드(직업명에 자주 들어가는 단어 중심으로)
    base_map = {
        "인문": ["작가", "편집", "출판", "기획", "연구"],
        "사회": ["상담", "행정", "경찰", "회계", "노무"],
        "교육": ["교사", "강사", "교육", "지도"],
        "공학": ["개발", "엔지니어", "기술", "설계", "로봇"],
        "자연": ["연구원", "분석", "실험", "데이터"],
        "의학": ["의사", "간호", "약사", "치과", "치료"],
        "예체능": ["디자인", "작가", "아티스트", "콘텐츠", "음악"],
    }

    parts = []
    parts.extend(base_map.get(interest_field, []))

    # 전공에서 힌트가 되는 토큰 1~2개만 추가(너무 길면 검색 품질 저하)
    tokens = tokenize_ko(major_text)
    # 흔한 접미사 제거(가벼운 정리)
    cleaned = []
    for t in tokens:
        t = t.replace("학과", "").replace("공학", "공학")  # 유지
        if len(t) >= 2:
            cleaned.append(t)
    cleaned = cleaned[:2]
    parts.extend(cleaned)

    # 중복 제거 + 너무 일반적인 단어 최소화
    uniq = []
    for p in parts:
        if p and p not in uniq:
            uniq.append(p)

    # Work24 keyword는 "컨설턴트 , 환경" 같은 형태 예시가 있으나, 공백 구분도 일반적으로 동작 :contentReference[oaicite:6]{index=6}
    return " ".join(uniq[:4]) if uniq else interest_field

def safe_get_text(elem: Optional[ET.Element], tag: str) -> str:
    if elem is None:
        return ""
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""

def parse_work24_list_xml(xml_text: str) -> List[Dict[str, str]]:
    """
    212L01 출력: <jobsList><total>...<jobList>... :contentReference[oaicite:7]{index=7}
    """
    root = ET.fromstring(xml_text)
    jobs = []

    # 문서 구조가 바뀌거나 wrapper가 있어도 잡기 위해 findall을 유연하게
    for job in root.findall(".//jobList"):
        jobs.append({
            "jobClcd": safe_get_text(job, "jobClcd"),
            "jobClcdNM": safe_get_text(job, "jobClcdNM"),
            "jobCd": safe_get_text(job, "jobCd"),
            "jobNm": safe_get_text(job, "jobNm"),
        })

    # jobCd 없는 항목 제거
    jobs = [j for j in jobs if j.get("jobCd") and j.get("jobNm")]
    return jobs

def parse_work24_detail_xml(xml_text: str) -> Dict[str, object]:
    """
    212D01 출력(요약 기준): <jobSum> 아래 다양한 필드 :contentReference[oaicite:8]{index=8}
    dtlGb에 따라 내용이 달라질 수 있어, 존재하는 것만 유연하게 파싱.
    """
    root = ET.fromstring(xml_text)
    job_sum = root.find(".//jobSum")  # 문서 내 첫 jobSum

    if job_sum is None:
        return {}

    # 공통적으로 유용한 필드(문서에 제시된 요약 섹션 중심) :contentReference[oaicite:9]{index=9}
    data = {
        "jobCd": safe_get_text(job_sum, "jobCd"),
        "jobLrclNm": safe_get_text(job_sum, "jobLrclNm"),
        "jobMdclNm": safe_get_text(job_sum, "jobMdclNm"),
        "jobSmclNm": safe_get_text(job_sum, "jobSmclNm"),
        "jobSum": safe_get_text(job_sum, "jobSum"),    # 하는 일(요약)
        "way": safe_get_text(job_sum, "way"),          # 되는 길
        "sal": safe_get_text(job_sum, "sal"),
        "jobSatis": safe_get_text(job_sum, "jobSatis"),
        "jobProspect": safe_get_text(job_sum, "jobProspect"),
        "jobEnv": safe_get_text(job_sum, "jobEnv"),
        "jobChr": safe_get_text(job_sum, "jobChr"),
        "jobIntrst": safe_get_text(job_sum, "jobIntrst"),
        "jobVals": safe_get_text(job_sum, "jobVals"),
    }

    # 관련전공/자격증(있을 때만)
    rel_majors = []
    for m in root.findall(".//relMajorList"):
        rel_majors.append({
            "majorCd": safe_get_text(m, "majorCd"),
            "majorNm": safe_get_text(m, "majorNm"),
        })
    rel_majors = [m for m in rel_majors if m.get("majorNm")]
    data["relMajors"] = rel_majors

    rel_certs = []
    for c in root.findall(".//relCertList"):
        name = safe_get_text(c, "certNm")
        if name:
            rel_certs.append(name)
    data["relCerts"] = rel_certs

    return data

def make_reason(interest_field: str, major_text: str, mbti: Optional[str], job_nm: str, job_clcd_nm: str) -> str:
    """
    간단한 추천 이유(1~2문장) 생성: 사용자 입력과 직업명/분류명 매칭 기반.
    """
    tokens = tokenize_ko(major_text)
    hit_major = None
    for t in tokens:
        if t and (t in job_nm.lower() or t in job_clcd_nm.lower()):
            hit_major = t
            break

    parts = []
    parts.append(f"관심분야가 **{interest_field}**라서 관련 직업군을 우선 추천했어요.")
    if hit_major:
        parts.append(f"전공/키워드(**{hit_major}**)와 직업 정보가 연결될 가능성이 있어요.")
    if mbti:
        parts.append(f"MBTI(**{mbti}**)는 참고로만 두고, 실제 흥미·경험으로 적합도를 확인해보면 좋아요.")
    return " ".join(parts[:2])  # 너무 길어지지 않게 2문장 정도

# =============================
# Work24 API calls (cached)
# =============================
@st.cache_data(ttl=600)
def work24_search_jobs(auth_key: str, keyword: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    212L01: 직업정보(목록) 키워드 검색
    - 필수: authKey, returnType=XML, target=JOBCD :contentReference[oaicite:10]{index=10}
    - 선택: srchType=K, keyword :contentReference[oaicite:11]{index=11}
    """
    params = {
        "authKey": auth_key,
        "returnType": WORK24_LIST_RETURN_TYPE,
        "target": WORK24_LIST_TARGET,
        "srchType": "K",
        "keyword": keyword,
    }
    try:
        r = requests.get(WORK24_LIST_URL, params=params, timeout=12)
        r.raise_for_status()
        jobs = parse_work24_list_xml(r.text)
        return jobs, None
    except Exception as e:
        return [], str(e)

@st.cache_data(ttl=600)
def work24_job_detail(auth_key: str, job_cd: str, dtl_gb: str = "1") -> Tuple[Dict[str, object], Optional[str]]:
    """
    212D01: 직업정보 상세
    - 필수: authKey, returnType=XML, target=JOBDTL, jobGb=1, jobCd, dtlGb :contentReference[oaicite:12]{index=12}
    dtlGb: 1(요약), 2(하는 일), ... 7(업무활동) :contentReference[oaicite:13]{index=13}
    """
    params = {
        "authKey": auth_key,
        "returnType": WORK24_DETAIL_RETURN_TYPE,
        "target": WORK24_DETAIL_TARGET,
        "jobGb": WORK24_DETAIL_JOBGB,
        "jobCd": job_cd,
        "dtlGb": dtl_gb,
    }
    try:
        r = requests.get(WORK24_DETAIL_URL, params=params, timeout=12)
        r.raise_for_status()
        data = parse_work24_detail_xml(r.text)
        return data, None
    except Exception as e:
        return {}, str(e)

# =============================
# UI: Form
# =============================
with st.form("career_form"):
    st.subheader("필수 정보")

    c1, c2, c3 = st.columns(3)
    with c1:
        age_group = st.selectbox("연령", ["선택", "18-19", "20-22", "23-25", "26-29", "30+"], index=0)
    with c2:
        education = st.selectbox("학력", ["선택", "고졸", "대학교 재학", "대졸", "대학원 졸업"], index=0)
    with c3:
        interest_field = st.selectbox("관심분야", ["선택", "인문", "사회", "교육", "공학", "자연", "의학", "예체능"], index=0)

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
# Result Flow
# =============================
if submit:
    # 필수 검증
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
        st.error("사이드바에 고용24(Work24) authKey를 입력해야 직업정보를 불러올 수 있어요.")
        st.stop()

    # 1) 사용자 입력 분석 → 분야 키워드 도출
    field_keyword = build_field_keyword(interest_field, major_text)
    st.success(f"분석된 추천 키워드: **{field_keyword}**")

    # 2) Work24 목록 API로 직업 4개 가져오기
    with st.spinner("고용24에서 직업 정보를 불러오는 중..."):
        jobs, err = work24_search_jobs(work24_key.strip(), field_keyword)

    if err:
        st.error(f"API 호출 오류: {err}")
        st.stop()

    if not jobs:
        st.warning("검색 결과가 없어요. 전공/관심 키워드를 조금 더 일반적인 단어로 바꿔보세요.")
        st.stop()

    # 상위 4개(중복 제거)
    seen = set()
    top4 = []
    for j in jobs:
        if j["jobCd"] in seen:
            continue
        seen.add(j["jobCd"])
        top4.append(j)
        if len(top4) == 4:
            break

    st.divider()
    st.subheader("✨ 고용24 기반 추천 직업 4개")

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
        .section-title { margin-top: 10px; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 3) 추천 이유 + 목록 표시
    for idx, j in enumerate(top4, start=1):
        reason = make_reason(interest_field, major_text, mbti, j["jobNm"], j["jobClcdNM"])
        pills = [
            f"<span class='pill'>#{idx}</span>",
            f"<span class='pill'>분류: {j['jobClcdNM'] or '정보 없음'}</span>",
            f"<span class='pill'>키워드: {field_keyword}</span>",
        ]
        st.markdown(
            f"""
            <div class="card">
                <div class="meta">{' '.join(pills)}</div>
                <h3 style="margin: 6px 0 6px 0;">{j['jobNm']}</h3>
                <div style="opacity: 0.8;">직업코드: {j['jobCd']}</div>
                <p class="reason"><b>왜 추천했나요?</b><br/>• {reason}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("🔎 직업 상세정보 보기")

    # 4) 리스트에서 선택하면 상세 표시
    options = {f"{j['jobNm']}  (코드: {j['jobCd']})": j for j in top4}
    selected_label = st.selectbox("상세로 볼 직업을 선택하세요", list(options.keys()))
    selected = options[selected_label]

    # 상세: 요약(dtlGb=1) + 하는 일(dtlGb=2) 같이 호출
    with st.spinner("직업 상세정보를 불러오는 중..."):
        detail_sum, err1 = work24_job_detail(work24_key.strip(), selected["jobCd"], dtl_gb="1")  # 요약 :contentReference[oaicite:14]{index=14}
        detail_work, err2 = work24_job_detail(work24_key.strip(), selected["jobCd"], dtl_gb="2")  # 하는 일 :contentReference[oaicite:15]{index=15}

    if err1 or not detail_sum:
        st.error(f"상세(요약) 호출 실패: {err1 or '응답 파싱 실패'}")
        st.stop()

    # 화면 표시(카드)
    lrcl = detail_sum.get("jobLrclNm", "")
    mdcl = detail_sum.get("jobMdclNm", "")
    smcl = detail_sum.get("jobSmclNm", "")

    job_sum_text = (detail_sum.get("jobSum") or "").strip()
    way_text = (detail_sum.get("way") or "").strip()

    # dtlGb=2도 jobSum 태그가 올 수 있어 보조로 활용
    work_text = (detail_work.get("jobSum") or "").strip() if detail_work else ""

    rel_majors = detail_sum.get("relMajors", []) or []
    rel_certs = detail_sum.get("relCerts", []) or []

    st.markdown(
        f"""
        <div class="card">
            <div class="meta">
                <span class='pill'>대분류: {lrcl or '정보 없음'}</span>
                <span class='pill'>중분류: {mdcl or '정보 없음'}</span>
                <span class='pill'>소분류: {smcl or '정보 없음'}</span>
            </div>
            <h3 style="margin: 6px 0 6px 0;">{selected['jobNm']}</h3>
            <div style="opacity: 0.8;">직업코드: {selected['jobCd']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### 🧾 요약")
    st.write(job_sum_text if job_sum_text else "요약 정보가 없습니다.")

    if work_text:
        st.markdown("#### 🛠️ 하는 일(상세)")
        st.write(work_text)

    if way_text:
        st.markdown("#### 🧭 되는 길")
        st.write(way_text)

    # 관련전공/자격증 (있으면)
    if rel_majors:
        st.markdown("#### 🎓 관련 전공")
        st.write(", ".join([m.get("majorNm", "") for m in rel_majors if m.get("majorNm")]))

    if rel_certs:
        st.markdown("#### 📜 관련 자격증")
        st.write(", ".join(rel_certs))

st.caption("※ 고용24 OPEN-API는 인증키가 필요하며, 응답은 XML 형식입니다.")
