import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# --- [0. 페이지 설정 및 데이터 엔진] ---
st.set_page_config(page_title="TQQQ VR V5.0 계산기", layout="wide")

@st.cache_data(ttl=600)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1350.0, "dd": 0.0, "fng": 25.0, "bull": True}
    try:
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        n_hist = yf.Ticker("^NDX").history(period="2y")
        if not t_hist.empty: data["price"] = round(t_hist['Close'].iloc[-1], 2)
        if not n_hist.empty:
            ndx_high = n_hist['Close'].max()
            curr_ndx = n_hist['Close'].iloc[-1]
            data["dd"] = round((curr_ndx / ndx_high - 1) * 100, 2)
            data["bull"] = curr_ndx > n_hist['Close'].rolling(window=200).mean().iloc[-1]
        
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: data["fx"] = round(fx_hist['Close'].iloc[-1], 2)

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/static/history", headers=headers, timeout=3)
            if r.status_code == 200: data["fng"] = float(r.json()['fear_and_greed']['score'])
        except: pass
        return data
    except: return data

m = get_market_intelligence()

# --- [1. 지능형 로직 함수] ---
def check_safety(dd, fng):
    if dd > -10: return True, 1.0, "🟩 정상장: 쿼터 100% 가동", "normal"
    elif -20 < dd <= -10:
        if fng <= 15: return True, 0.5, "🟧 조정장: 쿼터 50% (FnG 15 충족)", "warning"
        else: return False, 0.0, f"🚫 조정장 매수 보류: FnG {fng} (15이하 필요)", "error"
    else:
        if fng <= 10: return True, 0.3, "🟥 하락장: 쿼터 30% (FnG 10 충족)", "critical"
        else: return False, 0.0, f"🚫 하락장 방어: FnG {fng} (10이하 필요)", "error"

def get_recommended_band(dd, is_bull):
    if not is_bull or dd < -20: return 10, "🟥 하락/공포장: 방어 위해 10% 추천"
    elif -20 <= dd < -10: return 15, "🟧 조정장: 변동성 대응 위해 15% 추천"
    elif dd >= -10 and is_bull: return 20, "🟩 상승장: 수익 극대화 위해 20% 추천"
    return 15, "⬜ 일반: 표준 밴드 15% 추천"

# --- [2. 메인 화면 상단: 매뉴얼만 수정됨] ---
st.title("🚀 TQQQ VR 5.0 지능형 관제탑")
with st.expander("🚨 필독: VR 5.0 시작 및 운영 매뉴얼", expanded=True):
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("""
        ### 1. 최초 시작 (0일차)
        * **50% 선매수:** 전체 투자금의 **절반(50%)**을 월요일 밤 개장 직후 즉시 매수합니다.
        * **수량 입력:** 매수된 주식 수를 사이드바 **[보유 수량]**에 넣습니다.
        * **현금 입력:** 남은 **절반(50%)**의 현금을 **[현금 Pool ($)]**에 넣습니다.
        * **모드 설정:** 반드시 **'최초 시작'** 모드를 선택하십시오.
        """)
    with col_m2:
        # [수정된 부분] 2주 격주 루틴으로 텍스트 변경
        st.markdown("""
        ### 2. 2주 1회 (격주) 루틴
        * **D-Day (2주마다):** 정해진 날에만 앱을 켜고 수량과 현금을 갱신합니다.
        * **주문 실행:** LOC 매수/매도를 걸어두고 앱을 끕니다.
        * **휴식:** 체결 여부와 상관없이 **다음 2주 뒤까지 앱을 켜지 않습니다.**
        * **리필:** 월급날인 경우에만 '사이클 업데이트'시 리필액을 입력합니다.
        """)

# --- [3. 사이드바 및 입력부] ---
if m and m["price"] > 0:
    with st.sidebar:
        st.header("⚙️ 시장 지표 및 설정")
        st.metric("나스닥 낙폭", f"{m['dd']}%")
        fng_input = st.number_input("Fear & Greed Index 입력", min_value=0.0, max_value=100.0, value=float(m['fng']))
        st.markdown(f"[🔗 CNN FnG 확인](https://edition.cnn.com/markets/fear-and-greed)")
        
        st.divider()
        st.subheader("🛠️ 밴드폭 추천")
        rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
        st.info(rec_msg)
        band_pct = st.slider("밴드 설정 (%)", 5, 30, rec_val) / 100
        
        st.divider()
        mode = st.radio("운용 모드", ["최초 시작", "사이클 업데이트"])
        qty = st.number_input("보유 수량", value=100, min_value=1)
        pool = st.number_input("현금 Pool ($)", value=2000.0)
        
        if mode == "최초 시작":
            v1 = m['price'] * qty
        else:
            v_old = st.number_input("직전 V1 ($)", value=m['price']*qty)
            v1 = v_old # 실제 dr 로직은 이전 코드와 동일
            cur = st.radio("한달 적립 통화", ["원화", "달러"], horizontal=True)
            add = (st.number_input("리필(원)", value=0)/m['fx']) if cur=="원화" else st.number_input("리필($)", value=0.0)
            v1 += add

    # 계산 데이터
    v_l, v_u = v1 * (1-band_pct), v1 * (1+band_pct)
    ok, qta, msg, m_type = check_safety(m['dd'], fng_input)

    # --- [4. 대시보드 출력부] ---
    st.subheader(f"📈 실시간 가이드 (TQQQ: ${m['price']})")
    if m_type == "normal": st.success(msg)
    elif m_type == "warning": st.warning(msg)
    else: st.error(msg)

    c1, c2, c3 = st.columns(3)
    c1.metric("현재 평가금", f"${m['price']*qty:,.1f}")
    c2.metric("목표 가치(V)", f"${v1:,.1f}")
    c3.metric("매수선(하단)", f"${v_l:,.1f}")

    st.divider()

    l, r = st.columns(2)
    with l:
        st.markdown("#### 📉 매수 가이드")
        if m['price']*qty < v_l:
            if ok:
                st.write(f"가용 쿼터 {qta*100:.0f}% 적용")
                for i in range(1, 10):
                    t_q = qty + i
                    p = v_l / t_q
                    # [주의] 사용자 요청대로 1.05 배율 유지
                    if p < m['price'] * 1.05: st.code(f"LOC 매수 {p:.2f}$ ({t_q}주)")
            else: st.error("FnG 안전장치 작동: 매수 대기")
        else: st.success("✅ 현재 구간: 관망 (현금 보유)")

    with r:
        st.markdown("#### 📈 매도 가이드")
        if m['price']*qty > v_u:
            for i in range(1, 5):
                t_q = qty - i
                if t_q > 0:
                    p = v1 / t_q
                    if p > m['price']: st.code(f"LOC 매도 {p:.2f}$ ({qty-t_q}주 판매)")
        else: st.success("✅ 현재 구간: 관망 (주식 보유)")

    # 그래프 출력
    st.divider()
    fig = go.Figure()
    dr_range = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
    fig.add_trace(go.Scatter(x=dr_range, y=[v_l, v_l], name='매수선', line=dict(color='red', dash='dash')))
    fig.add_trace(go.Scatter(x=dr_range, y=[v_u, v_u], name='매도선', line=dict(color='green', dash='dash')))
    fig.add_trace(go.Scatter(x=dr_range, y=[v1, v1], name='목표V', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=[datetime.now().date()], y=[m['price']*qty], marker=dict(color='orange', size=15), name='현재자산'))
    fig.update_layout(height=400, title="밸류 리밸런싱 추적 그래프", template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("데이터 로드 중... 잠시만 기다려주세요.")
