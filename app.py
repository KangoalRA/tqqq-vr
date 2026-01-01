import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 페이지 설정 및 데이터 엔진] ---
st.set_page_config(page_title="TQQQ VR 5.0 투자 가이드", layout="wide")

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

# --- [2. 메인 화면 상단] ---
st.title("🚀 TQQQ VR 5.0 투자 가이드")

with st.expander("🚨 필독: VR 5.0 시작 및 운영 매뉴얼", expanded=True):
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("""
        ### 1. 최초 시작 (0일차)
        * **50% 선매수:** 전체 투자금 절반 매수 / 나머지 절반 현금 Pool 입력
        * **모드 설정:** 반드시 **'최초 시작'** 모드 선택
        """)
    with col_m2:
        st.markdown("""
        ### 2. 2주 1회 (격주) 루틴
        * **돈 넣는 날:** (기존Pool + 입금액) 합쳐서 Pool에 적고, 입금액만 리필에 적음.
        * **평소:** 현재 Pool 적고, 리필은 0원.
        * **저장:** 입력 후 반드시 **[구글 시트에 저장]** 버튼 클릭.
        """)

# --- [3. 사이드바 및 입력부: 구글 시트 연동] ---
if m and m["price"] > 0:
    with st.sidebar:
        st.header("⚙️ 시장 지표 및 설정")
        st.metric("나스닥 낙폭", f"{m['dd']}%")
        fng_input = st.number_input("FnG Index", value=float(m['fng']))
        
        st.divider()
        st.subheader("💾 자산 데이터 (Google Cloud)")
        
        # 구글 시트 연결
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 데이터 불러오기
        try:
            existing_data = conn.read(worksheet="Sheet1", usecols=[0, 1, 2], ttl=0)
            existing_data = existing_data.dropna()
            if not existing_data.empty:
                last_row = existing_data.iloc[-1]
                default_qty = int(last_row.iloc[0])
                default_pool = float(last_row.iloc[1])
                default_v = float(last_row.iloc[2])
                st.success(f"☁️ 클라우드 데이터 로드 완료")
            else:
                default_qty, default_pool, default_v = 100, 2000.0, m['price']*100
        except:
            default_qty, default_pool, default_v = 100, 2000.0, m['price']*100
            st.warning("⚠️ 구글 시트 연결 필요 (Secrets 설정)")

        mode = st.radio("운용 모드", ["최초 시작", "사이클 업데이트"])
        qty = st.number_input("보유 수량 (주)", value=default_qty, min_value=1)
        pool = st.number_input("현금 Pool ($)", value=default_pool)
        
        if mode == "최초 시작":
            v1 = m['price'] * qty
            v_to_save = v1 
        else:
            v_old = st.number_input("직전 V1 ($)", value=default_v)
            v_to_save = v_old
            v1 = v_old 
            cur = st.radio("리필 통화", ["원화", "달러"], horizontal=True)
            add = (st.number_input("리필(원)", value=0)/m['fx']) if cur=="원화" else st.number_input("리필($)", value=0.0)
            v1 += add

        # 저장 버튼
        if st.button("💾 구글 시트에 저장"):
            new_data = pd.DataFrame([{"Qty": qty, "Pool": pool, "V_old": v_to_save}])
            # 기존 데이터 날리고 덮어쓰기 (히스토리 원하면 append 모드로 변경 가능하지만 단순화 위해 덮어쓰기)
            conn.update(worksheet="Sheet1", data=new_data)
            st.success("✅ 클라우드 저장 완료!")

        st.divider()
        rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
        st.info(rec_msg)
        band_pct = st.slider("밴드 설정 (%)", 5, 30, rec_val) / 100

    # 계산 데이터
    v_l, v_u = v1 * (1-band_pct), v1 * (1+band_pct)
    ok, qta, msg, m_type = check_safety(m['dd'], fng_input)

    # --- [4. 화면 구성] ---
    st.subheader(f"📈 실시간 가이드 (TQQQ: ${m['price']})")
    
    tab1, tab2 = st.tabs(["📊 메인 대시보드", "📘 안전장치/로직 설명서"])

    with tab1:
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
                        if p < m['price'] * 1.05: st.code(f"LOC 매수 {p:.2f}$ ({t_q}주)")
                else: st.error("🚫 FnG 안전장치 작동: 매수 금지")
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

        st.divider()
        fig = go.Figure()
        dr_range = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
        fig.add_trace(go.Scatter(x=dr_range, y=[v_l, v_l], name='매수선', line=dict(color='red', dash='dash')))
        fig.add_trace(go.Scatter(x=dr_range, y=[v_u, v_u], name='매도선', line=dict(color='green', dash='dash')))
        fig.add_trace(go.Scatter(x=dr_range, y=[v1, v1], name='목표V', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=[datetime.now().date()], y=[m['price']*qty], marker=dict(color='orange', size=15), name='현재자산'))
        fig.update_layout(height=400, title="밸류 리밸런싱 추적 그래프", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown("### 🛡️ VR 5.0 지능형 로직 상세 명세")
        st.info("이 탭은 과거의 내가 설계한 안전장치 로직을 까먹지 않기 위해 기록한 페이지입니다.")
        st.markdown("---")
        st.markdown("#### 1. 🚦 상황별 밴드폭 자동 조절 (Bull/Bear 판독기)")
        st.markdown("* **🟩 상승장 (20%):** 나스닥 낙폭 -10% 이내 & 200일선 위.")
        st.markdown("* **🟧 조정장 (15%):** 나스닥 -10% ~ -20%.")
        st.markdown("* **🟥 하락장 (10%):** 나스닥 -20% 이하 or 200일선 붕괴.")
        st.markdown("---")
        st.markdown("#### 2. 💰 현금 쿼터(Quota) 제한 시스템")
        st.markdown("* **일반:** 100% 사용 가능.")
        st.markdown("* **경고:** 나스닥 -10%~-20% 시 현금 50%만 사용 (FnG 15 이하).")
        st.markdown("* **위험:** 나스닥 -20% 이하 시 현금 30%만 사용 (FnG 10 이하).")
        st.markdown("---")
        st.markdown("#### 3. 🧠 공포/탐욕 지수(FnG) 퓨즈")
        st.markdown("* 하락장(-20% 이하)에서는 FnG가 10 이하일 때만 매수 허용.")

else:
    st.error("데이터 로드 중... 잠시만 기다려주세요.")
