import json
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="대학생 진로 추천", page_icon="🧭", layout="centered")

# =============================
# Sidebar: OpenAI API Key
# =============================
st.sidebar.header("🔑 OpenAI 설정")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", placeholder="sk-...")

# (선택) 모델명
model_name = st.sidebar.text_input("모델명(선택)", value="gpt-5.2")

st.title("🧭 대학생 진로 추천 웹사이트")
st.write(
    "필수 정보(연령·학력·관심분야)와 선택 정보(성격·전공)를 입력하면, "
    "키워드 매칭으로 **직업 3개**를 추천하고, OpenAI가 **사용자 성향 해석 + 직업 추천 이유(각 2문장)**를 제공해요."
)
st.divider()

# =============================
# Data Model
# =============================
@dataclass
class Job:
    name: str
    one_liner: str
    fields: List[str]
    keywords: List[str]
    mbti_hints: List[str]
    major_hints: List[str]


# =============================
# Jobs Database (요청 직업 목록 포함)
# =============================
JOBS: List[Job] = [
    Job("선장", "선박을 지휘하고 항해·안전을 총괄하는 해양 리더.", ["공학", "자연", "사회"],
        ["바다", "항해", "선박", "해양", "운항", "안전", "리더십"], ["ESTJ","ENTJ","ISTJ"], ["해양", "조선", "항해", "물류"]),
    Job("제과사", "빵·디저트를 기획하고 만드는 푸드 크리에이터.", ["예체능", "사회"],
        ["디저트", "빵", "베이킹", "레시피", "위생", "매장"], ["ISFP","ESFP","ENFP"], ["식품", "조리", "호텔", "외식"]),
    Job("반도체공학기술자", "반도체 소자·공정·설계를 연구·개발하는 엔지니어.", ["공학", "자연"],
        ["반도체", "회로", "공정", "칩", "설계", "클린룸"], ["INTJ","ISTJ","ENTJ"], ["전자", "전기", "반도체", "재료"]),
    Job("운동선수", "훈련과 경기로 기록과 성과를 만드는 퍼포머.", ["예체능"],
        ["훈련", "경기", "체력", "대회", "기록", "팀"], ["ESTP","ESFP","ISTP"], ["체육", "스포츠"]),
    Job("초등학교교사", "초등학생의 학습·성장을 돕는 교육 전문가.", ["교육", "인문", "사회"],
        ["교육", "아동", "수업", "학급", "생활지도"], ["ENFJ","ESFJ","ISFJ"], ["교육", "아동", "초등"]),
    Job("프로게이머", "게임 실력과 전략으로 경쟁하는 e스포츠 선수.", ["예체능", "공학"],
        ["게임", "대회", "전략", "팀", "연습", "피드백"], ["ISTP","INTP","ESTP"], ["게임", "컴퓨터", "e스포츠"]),
    Job("수의사", "동물의 질병을 진단·치료하고 건강을 관리하는 의료인.", ["의학", "자연"],
        ["동물", "진료", "치료", "수술", "예방", "보호자"], ["ISFJ","INFJ","ISTJ"], ["수의", "생명", "바이오"]),
    Job("배우", "캐릭터를 해석해 연기와 표현으로 이야기를 전달하는 아티스트.", ["예체능", "인문"],
        ["연기", "무대", "촬영", "캐릭터", "표현", "오디션"], ["ENFP","ESFP","INFJ"], ["연극", "영화", "방송"]),
    Job("비행기조종사", "항공기를 안전하게 운항하며 항로·상황을 통제하는 전문가.", ["공학", "자연"],
        ["항공", "조종", "안전", "운항", "기상", "관제"], ["ISTJ","ESTJ","INTJ"], ["항공", "기계", "운항"]),
    Job("웹툰작가", "스토리와 그림으로 연재 콘텐츠를 만드는 크리에이터.", ["예체능", "인문"],
        ["웹툰", "스토리", "작화", "연재", "캐릭터", "콘티"], ["INFP","ISFP","INTP"], ["만화", "디자인", "일러스트"]),
    Job("경찰관", "치안 유지와 범죄 예방·대응을 담당하는 공공안전 직무.", ["사회"],
        ["치안", "범죄", "현장", "수사", "안전", "공공"], ["ESTJ","ISTJ","ESFJ"], ["경찰", "행정", "법"]),
    Job("범죄심리분석관", "범죄자 행동·심리를 분석해 수사 전략을 돕는 전문가.", ["사회", "인문"],
        ["범죄", "심리", "프로파일링", "분석", "수사", "행동"], ["INTJ","INFJ","INTP"], ["심리", "범죄", "사회"]),
    Job("상담전문가", "개인의 고민을 듣고 해결을 돕는 심리·상담 전문가.", ["사회", "교육", "인문"],
        ["상담", "공감", "심리", "치유", "코칭", "관계"], ["INFJ","ENFJ","ISFJ"], ["상담", "심리", "교육"]),
    Job("약사", "약을 조제·복약지도하며 약물 안전을 관리하는 전문가.", ["의학", "자연"],
        ["약", "조제", "복약지도", "약물", "안전", "약국"], ["ISTJ","ISFJ","INTJ"], ["약학", "생명", "화학"]),
    Job("한의사", "한방 진단과 치료로 건강을 관리하는 의료 전문가.", ["의학"],
        ["한의학", "진단", "치료", "침", "한약", "건강"], ["INFJ","ISFJ","ISTJ"], ["한의", "보건"]),
    Job("간호사", "환자 케어와 임상 지원을 수행하는 의료 현장 핵심 인력.", ["의학"],
        ["간호", "환자", "병원", "케어", "협업", "임상"], ["ESFJ","ISFJ","ENFJ"], ["간호", "보건"]),
    Job("가수", "노래와 무대 퍼포먼스로 감정을 전달하는 뮤지션.", ["예체능"],
        ["음악", "보컬", "무대", "연습", "공연", "팬"], ["ENFP","ESFP","ISFP"], ["실용음악", "보컬", "음악"]),
    Job("회계사", "재무제표·감사·세무로 기업의 숫자를 책임지는 전문가.", ["사회"],
        ["회계", "감사", "세무", "재무", "분석", "자격"], ["ISTJ","INTJ","ESTJ"], ["회계", "경영", "경제"]),
    Job("성우", "목소리 연기로 캐릭터를 살리는 보이스 아티스트.", ["예체능", "인문"],
        ["목소리", "더빙", "연기", "녹음", "발성", "캐릭터"], ["INFP","ENFP","ISFP"], ["방송", "연기", "미디어"]),
    Job("천문학연구원", "우주 현상을 관측·분석해 과학 지식을 확장하는 연구자.", ["자연"],
        ["우주", "천문", "관측", "연구", "데이터", "물리"], ["INTP","INTJ","INFJ"], ["천문", "물리", "수학"]),
    Job("직업군인", "국방 임무를 수행하며 조직 운영과 훈련을 담당하는 직무.", ["사회"],
        ["국방", "훈련", "작전", "규율", "조직", "리더십"], ["ISTJ","ESTJ","ENTJ"], ["군사", "행정", "체육"]),
    Job("소설가", "이야기와 문장으로 세계를 창조하는 작가.", ["인문"],
        ["글쓰기", "서사", "창작", "출판", "아이디어", "문학"], ["INFP","INFJ","INTP"], ["문예", "국문", "창작"]),
    Job("중학교교사", "청소년 학습과 진로 성장을 돕는 교육 전문가.", ["교육", "인문", "사회"],
        ["교육", "수업", "청소년", "생활지도", "평가"], ["ENFJ","ESFJ","INFJ"], ["교육", "사범", "전공교과"]),
    Job("비행기승무원", "기내 안전과 서비스를 책임지는 항공 서비스 전문가.", ["사회"],
        ["서비스", "기내", "안전", "응대", "항공", "여행"], ["ESFJ","ENFJ","ISFJ"], ["항공", "관광", "서비스"]),
    Job("건축사", "공간을 설계하고 프로젝트를 총괄하는 건축 전문가.", ["공학", "예체능"],
        ["건축", "설계", "도면", "공간", "프로젝트", "현장"], ["INTJ","ENTJ","ISTJ"], ["건축", "도시", "디자인"]),
    Job("기계공학 연구원", "기계 시스템을 연구·개발해 성능을 개선하는 연구자.", ["공학"],
        ["기계", "설계", "해석", "실험", "연구", "제조"], ["INTJ","ISTJ","INTP"], ["기계", "항공", "자동차"]),
    Job("크리에이터", "콘텐츠를 기획·제작해 팬과 소통하는 1인 미디어.", ["예체능", "사회"],
        ["콘텐츠", "영상", "기획", "편집", "SNS", "브랜딩"], ["ENFP","ESFP","ENTP"], ["미디어", "광고", "방송"]),
    Job("유치원교사", "유아의 놀이·발달을 돕는 유아교육 전문가.", ["교육"],
        ["유아", "놀이", "교육", "발달", "돌봄", "관찰"], ["ESFJ","ISFJ","ENFJ"], ["유아", "아동", "교육"]),
    Job("변호사", "법률 문제를 해결하고 권리를 보호하는 전문가.", ["사회"],
        ["법", "소송", "자문", "논리", "증거", "권리"], ["ENTJ","INTJ","ESTJ"], ["법학", "정치", "행정"]),
    Job("물리학연구원", "자연 법칙을 탐구하고 기술 기반을 만드는 연구자.", ["자연", "공학"],
        ["물리", "연구", "실험", "이론", "데이터", "수학"], ["INTP","INTJ","INFJ"], ["물리", "수학", "전자"]),
    Job("의사", "질병을 진단·치료하며 환자의 건강을 책임지는 의료인.", ["의학"],
        ["진단", "치료", "환자", "병원", "의학", "수술"], ["ISTJ","INFJ","ESTJ"], ["의학", "생명", "보건"]),
    Job("소방관", "재난·화재 현장에서 구조와 안전을 수행하는 공공안전 직무.", ["사회"],
        ["재난", "구조", "화재", "안전", "현장", "대응"], ["ESTP","ISTP","ESTJ"], ["소방", "안전", "응급"]),
    Job("생물학연구원", "생명 현상과 생물 시스템을 연구하는 과학자.", ["자연", "의학"],
        ["생물", "연구", "실험", "세포", "생명", "데이터"], ["INTP","INFJ","INTJ"], ["생명", "바이오", "생물"]),
    Job("심리학연구원", "인간 행동·마음을 연구해 근거 기반 지식을 만드는 연구자.", ["사회", "인문"],
        ["심리", "연구", "실험", "통계", "행동", "데이터"], ["INTP","INFJ","INTJ"], ["심리", "인지", "통계"]),
    Job("일러스트레이터", "그림으로 메시지와 감성을 시각화하는 창작자.", ["예체능"],
        ["일러스트", "그림", "디자인", "콘셉트", "의뢰"], ["INFP","ISFP","INTP"], ["디자인", "미술", "일러스트"]),
    Job("조리사", "조리 기술로 메뉴를 만들고 주방을 운영하는 전문가.", ["예체능", "사회"],
        ["요리", "주방", "메뉴", "위생", "식재료", "서비스"], ["ESFP","ISFP","ESTP"], ["조리", "외식", "호텔"]),
    Job("메이크업아티스트", "메이크업으로 이미지·분위기를 연출하는 뷰티 전문가.", ["예체능"],
        ["메이크업", "뷰티", "촬영", "트렌드", "연출"], ["ESFP","ENFP","ISFP"], ["뷰티", "미용", "디자인"]),
    Job("패션디자이너", "의상을 기획·디자인해 컬렉션을 만드는 디자이너.", ["예체능"],
        ["패션", "의상", "트렌드", "디자인", "브랜드"], ["ENFP","INFP","ENTP"], ["패션", "디자인", "의류"]),
    Job("외교관", "국가 간 협상·외교를 수행하는 국제 관계 전문가.", ["사회", "인문"],
        ["외교", "국제", "협상", "정책", "언어", "문화"], ["ENTJ","ENFJ","INTJ"], ["국제", "정치", "외교"]),
    Job("화학공학기술자", "화학 공정으로 소재·제품을 대량 생산하는 엔지니어.", ["공학", "자연"],
        ["화학", "공정", "소재", "플랜트", "안전", "생산"], ["ISTJ","INTJ","ENTJ"], ["화공", "화학", "재료"]),
    Job("배터리기술자", "이차전지 소재·셀·공정을 개발하는 에너지 엔지니어.", ["공학", "자연"],
        ["배터리", "이차전지", "에너지", "소재", "공정", "전기차"], ["INTJ","ISTJ","ENTJ"], ["재료", "화공", "전기"]),
    Job("유전자 재조합 식품 전문가", "유전공학 기반 식품 기술을 연구·검증하는 전문가.", ["자연", "의학"],
        ["유전자", "GMO", "식품", "바이오", "안전", "연구"], ["INTP","INTJ","INFJ"], ["식품", "생명", "바이오"]),
    Job("게임기획자", "게임의 규칙·레벨·경제를 설계하는 기획자.", ["공학", "예체능"],
        ["게임", "기획", "레벨", "밸런스", "스토리", "UX"], ["ENTP","INTP","ENFP"], ["게임", "컴퓨터", "기획"]),
    Job("동물조련사", "동물 훈련과 행동 교정으로 안전한 교감을 돕는 전문가.", ["자연", "예체능"],
        ["동물", "훈련", "행동", "교감", "안전"], ["ESFP","ISFP","ENFP"], ["동물", "생명", "수의"]),
    Job("통역가", "언어를 실시간으로 전환해 소통을 돕는 전문가.", ["인문", "사회"],
        ["통역", "언어", "회의", "동시", "문화", "커뮤니케이션"], ["ENFJ","ENTP","INFJ"], ["영어", "통번역", "언어"]),
    Job("스마트공장 기술자", "자동화·데이터로 공정을 최적화하는 제조 혁신 기술자.", ["공학"],
        ["스마트공장", "자동화", "센서", "데이터", "PLC", "제조"], ["ISTJ","INTJ","ENTJ"], ["산업", "자동화", "메카트로닉스"]),
    Job("만화가", "스토리와 그림으로 만화를 만드는 창작자.", ["예체능", "인문"],
        ["만화", "작화", "스토리", "연재", "캐릭터", "콘티"], ["INFP","ISFP","INTP"], ["만화", "디자인", "일러스트"]),
    Job("로봇연구원", "로봇 하드웨어·제어·AI를 연구하는 엔지니어.", ["공학", "자연"],
        ["로봇", "제어", "AI", "센서", "연구", "자동화"], ["INTJ","INTP","ISTJ"], ["로봇", "기계", "전기"]),
    Job("캐릭터디자이너", "캐릭터의 형태·성격을 시각적으로 설계하는 디자이너.", ["예체능"],
        ["캐릭터", "디자인", "설정", "콘셉트", "IP"], ["INFP","ISFP","ENFP"], ["디자인", "애니", "일러스트"]),
    Job("신약개발연구원", "신약 후보를 발굴·검증해 치료제를 만드는 연구자.", ["의학", "자연"],
        ["신약", "바이오", "임상", "연구", "화합물", "실험"], ["INTJ","INTP","INFJ"], ["약학", "생명", "화학"]),
    Job("바리스타", "커피를 추출·설계하고 매장을 운영하는 음료 전문가.", ["사회", "예체능"],
        ["커피", "추출", "원두", "라떼", "서비스", "매장"], ["ESFP","ISFP","ENFP"], ["호텔", "외식", "식음료"]),
    Job("화가", "회화로 감정과 메시지를 표현하는 순수예술가.", ["예체능"],
        ["회화", "미술", "작품", "전시", "표현", "창작"], ["INFP","ISFP","INFJ"], ["미술", "회화", "디자인"]),
    Job("비디오게임디자이너", "게임의 시각·레벨·경험을 디자인하는 디자이너.", ["공학", "예체능"],
        ["게임", "디자인", "레벨", "아트", "UX", "인터랙션"], ["ENTP","INFP","INTP"], ["게임", "디자인", "컴퓨터"]),
    Job("치과의사", "구강 건강을 진단·치료하는 의료 전문가.", ["의학"],
        ["치과", "구강", "치료", "교정", "진단", "시술"], ["ISTJ","ISFJ","INTJ"], ["치의", "보건"]),
    Job("판사", "법과 증거로 판단을 내리는 사법부 핵심 직무.", ["사회"],
        ["재판", "판결", "법", "논리", "공정", "증거"], ["INTJ","ISTJ","ENTJ"], ["법학", "정치"]),
    Job("노무사", "노동법·인사 이슈를 해결하는 노동·HR 전문가.", ["사회"],
        ["노동", "인사", "노무", "법", "분쟁", "자문"], ["ISTJ","ENTJ","INTJ"], ["노무", "경영", "법"]),
    Job("항공우주공학기술자", "항공기·우주체 시스템을 설계·해석하는 엔지니어.", ["공학", "자연"],
        ["항공우주", "로켓", "위성", "설계", "해석", "추진"], ["INTJ","ISTJ","ENTJ"], ["항공우주", "기계", "전기"]),
    Job("감성인식기술전문가", "감정·표현 데이터를 분석해 인식 기술을 만드는 전문가.", ["공학", "자연", "사회"],
        ["감성", "AI", "인식", "데이터", "음성", "표정"], ["INTP","INTJ","ENTP"], ["AI", "컴퓨터", "심리"]),
    Job("애니메이터", "움직임으로 캐릭터에 생명을 불어넣는 창작자.", ["예체능"],
        ["애니", "움직임", "작화", "연출", "캐릭터", "영상"], ["INFP","ISFP","ENFP"], ["애니", "영상", "디자인"]),
    Job("스포츠트레이너", "운동 프로그램과 재활로 몸 상태를 관리하는 전문가.", ["예체능", "의학"],
        ["트레이닝", "재활", "운동", "체력", "코칭", "근골격"], ["ESTP","ESFP","ISFJ"], ["스포츠", "재활", "체육"]),
]

# =============================
# Scoring (키워드 매칭)
# =============================
def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z가-힣0-9]+", text.lower())

def score_job(job: Job, interest_field: str, mbti: Optional[str], major_text: str) -> int:
    score = 0
    score += 60 if interest_field in job.fields else 5

    if mbti and mbti in job.mbti_hints:
        score += 18

    tokens = tokenize(major_text)
    if tokens:
        hits = 0
        for hint in (job.major_hints + job.keywords):
            h = hint.lower()
            if any(h in t or t in h for t in tokens):
                hits += 1
        if hits:
            score += 24 + min(hits, 3)

    return score

# =============================
# OpenAI: AI 해석 생성
# =============================
def generate_ai_interpretation(
    api_key: str,
    model: str,
    user_profile: Dict[str, str],
    top_jobs: List[Job],
) -> Tuple[str, Dict[str, str]]:
    """
    반환:
    - profile_summary: 사용자 패턴 해석(2~4문장)
    - job_reasons: {직업명: "2문장"}
    """
    client = OpenAI(api_key=api_key)

    jobs_payload = [
        {"name": j.name, "one_liner": j.one_liner, "fields": j.fields, "keywords": j.keywords[:8]}
        for j in top_jobs
    ]

    prompt = f"""
너는 대학생 진로 상담사야. 아래 사용자 입력 패턴을 분석해서 간단한 해석을 제공하고,
추천 직업 3개 각각에 대해 '왜 추천하는지'를 정확히 2문장으로 설명해줘.

[사용자 입력]
- 연령: {user_profile.get("age_group")}
- 학력: {user_profile.get("education")}
- 관심분야: {user_profile.get("interest_field")}
- MBTI: {user_profile.get("mbti")}
- 전공(자유입력): {user_profile.get("major_text")}

[추천 직업 후보 3개]
{json.dumps(jobs_payload, ensure_ascii=False)}

출력은 반드시 JSON만.
스키마:
{{
  "profile_summary": "사용자 패턴 해석 (한국어, 2~4문장)",
  "job_reasons": [
    {{"job_name": "직업명", "reason": "추천 이유 2문장(한국어)."}},
    {{"job_name": "직업명", "reason": "추천 이유 2문장(한국어)."}},
    {{"job_name": "직업명", "reason": "추천 이유 2문장(한국어)."}}
  ]
}}

제약:
- job_reasons는 반드시 3개이며, job_name은 위 후보 3개의 name과 정확히 일치.
- reason은 문장 2개로만 작성(마침표 기준 2문장).
- 과장/단정(예: '반드시 성공') 금지. 현실적인 표현 사용.
""".strip()

    resp = client.responses.create(
        model=model,
        input=prompt,
    )

    text = (resp.output_text or "").strip()
    try:
        data = json.loads(text)
        profile_summary = str(data.get("profile_summary", "")).strip()

        job_reasons_list = data.get("job_reasons", [])
        job_reason_map: Dict[str, str] = {}
        for item in job_reasons_list:
            name = str(item.get("job_name", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if name:
                job_reason_map[name] = reason

        for j in top_jobs:
            job_reason_map.setdefault(
                j.name,
                "입력한 관심과 역량 방향이 이 직무와 잘 맞아요. 지금 단계에서 경험을 쌓아보기 좋은 선택지예요."
            )

        if not profile_summary:
            profile_summary = (
                "입력한 관심 분야와 선택 정보(성격·전공)를 종합하면, 관련 분야에서 강점을 발휘할 가능성이 보여요. "
                "특히 흥미가 오래 지속되는 영역을 중심으로 탐색하는 것이 좋아요."
            )

        return profile_summary, job_reason_map

    except Exception:
        fallback_summary = (
            "입력한 관심 분야와 선택 정보(성격·전공)를 종합해 보면, 관련 분야에서 몰입할 수 있는 방향이 보여요. "
            "아래 직업들은 그 방향성과 잘 맞는 대표 선택지예요."
        )
        fallback_map = {j.name: "관심 분야와 직무 성격이 잘 맞아요. 관련 경험을 작게라도 시작해보면 적성 확인에 도움이 돼요." for j in top_jobs}
        return fallback_summary, fallback_map

# =============================
# Form UI
# =============================
MBTI_LIST = [
    "INTJ","INTP","ENTJ","ENTP",
    "INFJ","INFP","ENFJ","ENFP",
    "ISTJ","ISFJ","ESTJ","ESFJ",
    "ISTP","ISFP","ESTP","ESFP",
]

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

    submit = st.form_submit_button("추천 받기", type="primary")

# =============================
# Validation + Result
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
        st.error(f"필수 항목을 제출해야 해요: {', '.join(missing)}")
        st.stop()

    # Top 3 추천
    scored: List[Tuple[Job, int]] = [(job, score_job(job, interest_field, mbti, major_text)) for job in JOBS]
    top3 = [j for (j, _) in sorted(scored, key=lambda x: (x[1], x[0].name), reverse=True)[:3]]

    # OpenAI 해석
    profile_summary = ""
    ai_reason_map: Dict[str, str] = {}

    if openai_api_key.strip():
        with st.spinner("AI가 답변 패턴을 해석하는 중..."):
            try:
                user_profile = {
                    "age_group": age_group,
                    "education": education,
                    "interest_field": interest_field,
                    "mbti": mbti or "선택 안 함",
                    "major_text": major_text.strip() if major_text else "(미입력)",
                }
                profile_summary, ai_reason_map = generate_ai_interpretation(
                    api_key=openai_api_key.strip(),
                    model=model_name.strip(),
                    user_profile=user_profile,
                    top_jobs=top3,
                )
            except Exception as e:
                st.warning(f"AI 해석을 불러오지 못했어요. (키/모델/네트워크 확인) 오류: {e}")
                profile_summary = ""
                ai_reason_map = {}
    else:
        st.info("사이드바에 OpenAI API Key를 입력하면, AI 해석(패턴 분석 + 2문장 추천 이유)이 추가로 표시돼요.")

    st.divider()
    st.subheader("✨ 추천 결과")

    if profile_summary:
        st.markdown("#### 🧠 AI 해석")
        st.write(profile_summary)

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
        .card h3 { margin: 10px 0 6px 0; }
        .meta {
            display:flex;
            gap:8px;
            flex-wrap:wrap;
            margin-bottom: 8px;
        }
        .pill {
            display:inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(0,0,0,0.04);
            font-size: 12px;
        }
        .reason { margin: 8px 0 0 0; line-height: 1.6; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for idx, job in enumerate(top3, start=1):
        pills = [
            f"<span class='pill'>#{idx}</span>",
            f"<span class='pill'>연령: {age_group}</span>",
            f"<span class='pill'>학력: {education}</span>",
            f"<span class='pill'>관심분야: {interest_field}</span>",
        ]
        if mbti:
            pills.append(f"<span class='pill'>MBTI: {mbti}</span>")
        if major_text.strip():
            pills.append("<span class='pill'>전공 입력됨</span>")

        ai_reason = ai_reason_map.get(job.name)
        if ai_reason:
            reason_html = f"• {ai_reason}"
        else:
            # 폴백도 2문장으로 유지
            reason_html = (
                "• 관심 분야와 직무 성격이 잘 맞고, 현재 단계에서 탐색/준비를 시작하기 좋은 선택지예요. "
                "• 관련 프로젝트·인턴·동아리로 작은 경험을 쌓아 적합도를 확인해보세요."
            )

        st.markdown(
            f"""
            <div class="card">
                <div class="meta">{' '.join(pills)}</div>
                <h3>{job.name}</h3>
                <div>{job.one_liner}</div>
                <p class="reason"><b>왜 추천했나요?</b><br/>{reason_html}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.caption("※ 본 추천은 키워드 매칭 기반 데모이며, AI 해석은 참고용이에요. 실제 진로 선택은 추가 탐색/상담을 권장해요.")
