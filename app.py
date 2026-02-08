import json
import re
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import streamlit as st
from openai import OpenAI

# =============================
# Page
# =============================
st.set_page_config(page_title="대학생 진로 추천", page_icon="🧭", layout="wide")

# =============================
# Work24(고용24) API
# =============================
WORK24_LIST_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo212L01.do"
WORK24_DETAIL_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo212D01.do"

LIST_FIXED_PARAMS = {"returnType": "XML", "target": "JOBCD"}                     # 목록(직업코드)
DETAIL_FIXED_PARAMS = {"returnType": "XML", "target": "JOBDTL", "jobGb": "1"}    # 상세

# =============================
# Sidebar
# =============================
st.sidebar.header("🔑 API 설정")
work24_key = st.sidebar.text_input("고용24 authKey", type="password", placeholder="고용24 인증키 입력")

st.sidebar.divider()
st.sidebar.subheader("🤖 OpenAI 설정")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", placeholder="sk-...")
openai_model = st.sidebar.text_input("모델명(선택)", value="gpt-5.2")

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

    candidates = []
    if majors:
        for m in majors:
            candidates.append(m)
            for b in base[:3]:
                candidates.append(f"{m} {b}")
    for b in base[:5]:
        candidates.append(b)

    uniq = []
    for c in candidates:
        if c and c not in uniq:
            uniq.append(c)
    return uniq[:8]

def safe_text(parent: Optional[ET.Element], tag: str) -> str:
    if parent is None:
        return ""
    child = parent.find(tag)
    return (child.text or "").strip() if child is not None else ""

def parse_job_list(xml_text: str) -> List[Dict[str, str]]:
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
    root = ET.fromstring(xml_text)
    job_sum = root.find(".//jobSum")
    if job_sum is None:
        return {}
    return {
        "jobSum": safe_text(job_sum, "jobSum"),
        "way": safe_text(job_sum, "way"),
        "jobProspect": safe_text(job_sum, "jobProspect"),
        "jobSatis": safe_text(job_sum, "jobSatis"),
        "sal": safe_text(job_sum, "sal"),
        "jobEnv": safe_text(job_sum, "jobEnv"),
    }

@st.cache_data(ttl=600)
def work24_search(auth_key: str, keyword: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
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
    job_nm = (job.get("jobNm") or "").lower()
    cl_nm = (job.get("jobClcdNM") or "").lower()
    tokens = tokenize(major_text)

    score = 0
    reasons = []

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
        reasons.append(f"관심분야가 {interest_field}이고, 이 직업이 관련 키워드와 연결돼요.")

    hit_tokens = []
    for t in tokens:
        if t and (t in job_nm or t in cl_nm):
            hit_tokens.append(t)
    if hit_tokens:
        score += 35 + min(len(hit_tokens), 2) * 5
        reasons.append(f"전공/키워드({', '.join(hit_tokens[:2])})와 직무 연관성이 있어 보여요.")

    if mbti:
        score += 5
        reasons.append("MBTI는 참고로만 두고, 경험을 통해 적합도를 확인하면 좋아요.")

    if not reasons:
        score += 10
        reasons = [
            f"관심분야({interest_field})를 바탕으로 관련 직업군을 우선 추천했어요.",
            "키워드를 더 입력하면 더 정교한 매칭이 가능해요."
        ]

    return score, reasons[:2]

def shorten(text: str, max_len: int = 140) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    return t if len(t) <= max_len else t[:max_len].rstrip() + "…"

# =============================
# OpenAI: AI 요약/추천 이유 생성
# =============================
def generate_ai_insights(
    api_key: str,
    model: str,
    user_profile: Dict[str, str],
    jobs: List[Dict[str, str]],
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    client = OpenAI(api_key=api_key)

    jobs_payload = [
        {
            "jobCd": j.get("jobCd"),
            "jobNm": j.get("jobNm"),
            "one_liner": j.get("one_liner", ""),
            "jobClcdNM": j.get("jobClcdNM", ""),
        }
        for j in jobs
    ]

    prompt = f"""
너는 대학생 진로 상담사야. 아래 사용자 입력 패턴을 바탕으로:
1) 사용자 성향 설명: 1~2문장
2) 추천 직업 3개 각각에 대해:
   - AI 직무 요약: 1문장
   - 왜 추천하는지: 2~3문장
을 작성해줘.

[사용자 입력]
- 연령: {user_profile.get("age_group")}
- 학력: {user_profile.get("education")}
- 관심분야: {user_profile.get("interest_field")}
- MBTI: {user_profile.get("mbti")}
- 전공(자유입력): {user_profile.get("major_text")}

[추천 직업 3개(고용24 기반)]
{json.dumps(jobs_payload, ensure_ascii=False)}

반드시 JSON만 출력해.
스키마:
{{
  "user_trait": "1~2문장(한국어)",
  "jobs": [
    {{
      "jobCd": "고용24 jobCd(그대로)",
      "ai_summary": "1문장(한국어)",
      "ai_reason": "2~3문장(한국어)"
    }},
    {{
      "jobCd": "고용24 jobCd(그대로)",
      "ai_summary": "1문장(한국어)",
      "ai_reason": "2~3문장(한국어)"
    }},
    {{
      "jobCd": "고용24 jobCd(그대로)",
      "ai_summary": "1문장(한국어)",
      "ai_reason": "2~3문장(한국어)"
    }}
  ]
}}

제약:
- jobs는 반드시 3개
- jobCd는 입력에 있는 jobCd와 정확히 일치
- 과장/단정 금지, 현실적인 표현
""".strip()

    resp = client.responses.create(model=model, input=prompt)
    text = (resp.output_text or "").strip()

    user_trait = ""
    job_ai: Dict[str, Dict[str, str]] = {}

    try:
        data = json.loads(text)
        user_trait = (data.get("user_trait") or "").strip()

        items = data.get("jobs", []) or []
        for it in items:
            cd = str(it.get("jobCd", "")).strip()
            if not cd:
                continue
            job_ai[cd] = {
                "ai_summary": (it.get("ai_summary") or "").strip(),
                "ai_reason": (it.get("ai_reason") or "").strip(),
            }

        for j in jobs:
            cd = j.get("jobCd", "")
            if cd and cd not in job_ai:
                job_ai[cd] = {
                    "ai_summary": "이 직무는 관심 분야와 전공 힌트를 바탕으로 탐색하기 좋은 선택지예요.",
                    "ai_reason": "입력한 관심 방향과 직무 특성이 연결될 가능성이 있어 추천했어요. 관련 경험으로 적합도를 확인해보면 좋아요.",
                }

        if not user_trait:
            user_trait = (
                "관심 분야와 선택 정보(전공/성격)를 종합하면, 흥미가 지속될 수 있는 영역을 중심으로 탐색해보는 게 좋아 보여요. "
                "작은 경험으로 빠르게 적합도를 확인하는 방식이 잘 맞아요."
            )

        return user_trait, job_ai

    except Exception:
        user_trait = (
            "관심 분야와 전공 키워드가 비교적 뚜렷해서, 관련 직무를 폭넓게 탐색해보면 좋겠어요. "
            "작은 프로젝트로 경험을 쌓는 방식이 잘 맞아요."
        )
        for j in jobs:
            cd = j.get("jobCd", "")
            job_ai[cd] = {
                "ai_summary": "이 직무는 관심 분야와 전공 힌트로 볼 때 탐색 가치가 높은 분야예요.",
                "ai_reason": "입력한 관심 방향과 직무 요구 역량이 맞닿아 있어 추천했어요. 관련 경험을 만들어보면 적합도를 더 정확히 판단할 수 있어요.",
            }
        return user_trait, job_ai

# =============================
# Card UI (horizontal columns)
# =============================
def render_job_card_in_column(
    col,
    idx: int,
    interest_field: str,
    major_text: str,
    mbti: Optional[str],
    job: Dict[str, str],
    ai_summary: str,
    ai_reason: str,
):
    with col:
        with st.container(border=True):
            st.markdown(f"### {idx}. {job['jobNm']}")

            meta = [f"관심분야: {interest_field}"]
            if job.get("jobClcdNM"):
                meta.append(f"분류: {job['jobClcdNM']}")
            if major_text.strip():
                meta.append("전공: 입력됨")
            if mbti:
                meta.append(f"MBTI: {mbti}")
            st.caption(" | ".join(meta))

            st.markdown("**한 줄 설명**")
            st.write(job["one_liner"])

            st.markdown("**AI 직무 요약**")
            st.write(ai_summary)

            st.markdown("**왜 추천했나요?**")
            st.write(ai_reason)

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
    missing = []
    if age_group == "선택":
        missing.append("연령")
    if education == "선택":
        missing.append("학력")
    if interest_field == "선택":
        missing.append("관심분야")

    if missing:
        st.error(f"제출하지 않은 항목이 있어요: {', '.join(missing)}")
        st.stop()

    if not work24_key.strip():
        st.error("사이드바에 고용24 authKey(API Key)를 입력해야 직업 정보를 불러올 수 있어요.")
        st.stop()

    keywords = build_search_keywords(interest_field, major_text)

    with st.spinner("고용24에서 직업 정보를 검색하는 중..."):
        pool: List[Dict[str, str]] = []
        errors = []
        for kw in keywords:
            jobs, err = work24_search(work24_key.strip(), kw)
            if err:
                errors.append(err)
                continue
            pool.extend(jobs)
            if len(pool) >= 40:
                break

    if not pool:
        st.warning("직업 검색 결과가 없어요. 전공을 더 일반적인 단어로 바꿔보거나 전공을 비워두고 다시 시도해보세요.")
        if errors:
            st.caption(f"(참고) 마지막 오류: {errors[-1]}")
        st.stop()

    uniq = {j["jobCd"]: j for j in pool}
    pool = list(uniq.values())

    scored: List[Tuple[int, Dict[str, str], List[str]]] = []
    for j in pool:
        s, reasons = score_job(j, interest_field, major_text, mbti)
        scored.append((s, j, reasons))
    top3_scored = sorted(scored, key=lambda x: (x[0], x[1].get("jobNm", "")), reverse=True)[:3]

    with st.spinner("추천 직업의 한 줄 설명을 불러오는 중..."):
        enriched: List[Dict[str, str]] = []
        for s, j, reasons in top3_scored:
            detail, _ = work24_detail(work24_key.strip(), j["jobCd"], dtl_gb="1")
            one_liner_raw = (detail.get("jobSum") or "").strip()
            one_liner = shorten(one_liner_raw, 140) if one_liner_raw else ""
            enriched.append({
                **j,
                "one_liner": one_liner or "직무 요약 정보를 불러오지 못했어요. (고용24 응답에 요약이 없을 수 있어요.)",
                "fallback_reasons": reasons,
            })

    user_trait = ""
    job_ai_map: Dict[str, Dict[str, str]] = {}

    if openai_api_key.strip():
        with st.spinner("AI가 사용자 성향과 추천 이유를 작성하는 중..."):
            try:
                user_profile = {
                    "age_group": age_group,
                    "education": education,
                    "interest_field": interest_field,
                    "mbti": mbti or "선택 안 함",
                    "major_text": major_text.strip() if major_text else "(미입력)",
                }
                user_trait, job_ai_map = generate_ai_insights(
                    api_key=openai_api_key.strip(),
                    model=openai_model.strip(),
                    user_profile=user_profile,
                    jobs=enriched,
                )
            except Exception as e:
                st.warning(f"AI 요약 생성에 실패했어요. 오류: {e}")
                user_trait = ""
                job_ai_map = {}
    else:
        st.info("사이드바에 OpenAI API Key를 입력하면 AI 직무 요약/추천 이유가 추가로 표시돼요.")

    st.divider()
    st.subheader("✨ 추천 결과 (직업 3개)")

    if user_trait:
        st.markdown("#### 🧠 사용자 성향")
        st.write(user_trait)

    # ✅ 가로(3열)로 카드 배치
    cols = st.columns(3, gap="large")

    for idx, job in enumerate(enriched, start=1):
        ai = job_ai_map.get(job["jobCd"], {})
        ai_summary = (ai.get("ai_summary") or "").strip() or (
            job.get("one_liner", "") or "이 직무는 관심 분야와 전공 힌트를 바탕으로 탐색하기 좋은 선택지예요."
        )

        ai_reason = (ai.get("ai_reason") or "").strip()
        if not ai_reason:
            fallback = job.get("fallback_reasons", []) or []
            ai_reason = " ".join([re.sub(r"\*\*(.*?)\*\*", r"\1", r) for r in fallback]).strip()
            if not ai_reason:
                ai_reason = "관심 분야와 입력한 키워드를 바탕으로 관련 직업군을 추천했어요. 실제 경험을 통해 적합도를 확인해보면 좋아요."

        render_job_card_in_column(
            col=cols[idx - 1],
            idx=idx,
            interest_field=interest_field,
            major_text=major_text,
            mbti=mbti,
            job=job,
            ai_summary=ai_summary,
            ai_reason=ai_reason,
        )

st.caption("※ 본 추천은 키워드 매칭 기반 데모이며, 직업 정보는 고용24 OPEN-API를 활용합니다. AI 설명은 참고용이에요.")
