import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# --- [0. 페이지 설정 및 데이터 엔진] ---
st.set_page_config(page_title="TQQQ VR 5.0 지능형 관제탑", layout="wide")

# 세션 상태 초기화
if 'v_target' not in st.session_state:
    st.session_state['v_target'] = 0.0

@st.cache_data(ttl=600)
def get_market_intelligence():
    # 기본값 설정
    data = {"price": 0.0, "fx": 1400.0, "dd": 0.0, "fng": 50.0, "bull": True, "fng_err": False}
    
    try:
        # 1. TQQQ 및 나스닥 데이터
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        n_hist = yf.Ticker("^NDX").history(period="2y") # 나스닥 100
        
        if not t_hist.empty: 
            data["price"] = round(t_hist['Close'].iloc[-1], 2)
        
        if not n_hist.empty:
            ndx_high = n_hist['Close'].max()
            curr_ndx = n_hist['Close'].iloc[-1]
            data["dd"] = round((curr_ndx / ndx_high - 1) * 100, 2)
            # 200일 이동평균선 돌파 여부
            ma200 = n_hist['Close'].rolling(window=200).mean().iloc[-1]
            data["bull"] = curr_ndx > ma200
        
        # 2. 환율 데이터
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: 
            data["fx"] = round(fx_hist['Close'].iloc[-1], 2)

        # 3. Fear & Greed (불안정하므로 예외처리 강화)
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            # API 주소가 자주 바뀌므로 타임아웃 짧게 설정
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers=headers, timeout=2)
            if r.status_code == 200:
                fng_data = r.json()
                data["fng"] = float(fng_data['fear_and_greed']['score'])
            else:
                data["fng_err"] = True
        except:
            data["fng_err"] = True
            
        return data
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return data

m = get_market_intelligence()

# --- [1. 지능형 로직 함수] ---
def check_safety(dd, fng):
    # VR 5.0 핵심: 하락장에서는 FnG 수치가 낮아야만 매수 허용
    if dd > -10: 
        return True, 1.0, "🟩 정상장 (Normal): 쿼터 100% 가동", "normal"
    elif -20 < dd <= -10:
        if fng <= 20: # 기준 완화 (사용자 성향에 따라 조절)
            return True, 0.5, "🟧 조정장 (Correction): 쿼터 50% (FnG 20 충족)", "warning"
        else: 
            return False, 0.0, f"🚫 조정장 매수 보류: 현재 FnG {fng} (20 이하 필요)", "error"
    else: # 대세 하락장 (-20% 이하)
        if fng <= 10: 
            return True, 0.3, "🟥 폭락장 (Crash): 쿼터 30% (FnG 10 충족)", "critical"
        else: 
            return False, 0.0, f"🚫 폭락장 방어 모드: 현재 FnG {fng} (10 이하 필요)", "error"

def get_recommended_band(dd, is_bull):
    if not is_bull or dd < -20: 
        return 10, "🛡️ 하락세/공포장: 방어력 위해 10% 추천"
    elif -20 <= dd < -10: 
        return 15, "⚖️ 조정 구간: 표준 15% 추천"
    elif dd >= -10 and is_bull: 
        return 20, "🚀 상승 추세: 수익 극대화 20% 추천"
    return 15, "⚖️ 일반 상황: 표준 15% 추천"

# --- [2. 메인 UI 구성] ---
st.title("🚀 TQQQ VR 5.0 지능형 관제탑")
st.markdown(f"**기준 환율:** {m['fx']}원/$ | **TQQQ 현재가:** ${m['price']}")

if m["fng_err"]:
    st.caption("⚠️ CNN FnG 데이터 로드 지연으로 기본값(50)이 적용되었습니다. 수동으로 수정해주세요.")

# --- [3. 사이드바 컨트롤 패널] ---
with st.sidebar:
    st.header("⚙️ VR 운용 설정")
    
    # 1. 시장 지표 수동 보정
    with st.expander("📊 시장 지표 확인/수정", expanded=True):
        st.metric("나스닥 낙폭 (MDD)", f"{m['dd']}%", delta_color="inverse")
        fng_input = st.number_input("Fear & Greed Index", min_value=0.0, max_value=100.0, value=float(m['fng']))
        st.caption("[🔗 CNN FnG 공식확인](https://edition.cnn.com/markets/fear-and-greed)")

    st.divider()
    
    # 2. 밴드 설정
    rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
    st.info(rec_msg)
    band_pct = st.slider("밴드폭 설정 (%)", 5, 30, rec_val, step=1) / 100
    
    st.divider()
    
    # 3. 자산 데이터 입력
    mode = st.radio("운용 모드", ["🏁 최초 시작 / 리셋", "🔄 2주차 사이클 업데이트"])
    
    qty = st.number_input("현재 보유 수량 (주)", value=100, min_value=0)
    current_asset_val = m['price'] * qty
    
    if mode == "🏁 최초 시작 / 리셋":
        st.caption("현재 평가금을 기준으로 V(목표값)를 새로 설정합니다.")
        v1 = current_asset_val
        pool = st.number_input("시작 현금 Pool ($)", value=2000.0)
        
    else: # 사이클 업데이트
        st.caption("이전 V값에 적립금을 더해 목표를 상향합니다.")
        v_old = st.number_input("직전 사이클의 V값 ($)", value=current_asset_val)
        
        col_input1, col_input2 = st.columns(2)
        with col_input1:
            add_type = st.selectbox("적립 통화", ["KRW(원)", "USD($)"])
        with col_input2:
            add_amt = st.number_input("추가 적립금", value=0)
            
        real_add = (add_amt / m['fx']) if add_type == "KRW(원)" else add_amt
        v1 = v_old + real_add
        pool = st.number_input("현재 잔여 현금 Pool ($)", value=2000.0) + real_add

# --- [4. 계산 로직] ---
v_l = v1 * (1 - band_pct) # 매수 하단선 (Low)
v_u = v1 * (1 + band_pct) # 매도 상단선 (Up)

ok, qta, msg, m_type = check_safety(m['dd'], fng_input)

# --- [5. 대시보드 출력] ---
st.subheader("🛡️ 전략 상황판")

# 상태 메시지
if m_type == "normal": st.success(msg)
elif m_type == "warning": st.warning(msg)
else: st.error(msg)

# 핵심 지표 카드
col1, col2, col3, col4 = st.columns(4)
col1.metric("현재 평가금", f"${current_asset_val:,.0f}", f"{current_asset_val * m['fx'] / 10000:,.0f}만원")
col2.metric("목표 가치 (V)", f"${v1:,.0f}", help="이 금액을 중심으로 밴드가 형성됩니다.")
col3.metric("📉 최저 매수선", f"${v_l:,.2f}", f"-{band_pct*100}%")
col4.metric("📈 최고 매도선", f"${v_u:,.2f}", f"+{band_pct*100}%")

st.divider()

# --- [6. 매매 가이드 (LOC 계산기)] ---
l_col, r_col = st.columns(2)

with l_col:
    st.markdown("#### 🔵 매수 (Buy) 가이드")
    if current_asset_val < v_l:
        st.info(f"💡 현재가가 밴드 하단을 이탈했습니다. (가용 쿼터: {qta*100}%)")
        
        if ok:
            buy_list = []
            # 1주부터 10주까지 시뮬레이션
            for n in range(1, 11):
                target_qty = qty + n
                # LOC 공식: V_low / (현재수량 + n)
                loc_price = v_l / target_qty
                
                # 현재가보다 10% 이상 높게 사야하는 비정상 상황 제외
                if loc_price < m['price'] * 1.15: 
                    buy_list.append({
                        "추가 매수": f"+{n}주",
                        "LOC 단가 ($)": f"${loc_price:.2f}",
                        "필요 금액 ($)": f"${loc_price * n:.1f}"
                    })
            
            if buy_list:
                df_buy = pd.DataFrame(buy_list)
                st.table(df_buy)
                st.markdown(f"👉 **풀 사용 가능액:** ${(pool * qta):,.1f} (전체 풀의 {qta*100}%)")
            else:
                st.warning("계산된 LOC 가격이 너무 높습니다. 밴드 설정을 확인하세요.")
        else:
            st.error("⛔ FnG 지표가 너무 높아 매수를 금지합니다. (관망 추천)")
    else:
        dist = ((current_asset_val - v_l) / current_asset_val) * 100
        st.success(f"✅ 관망 구간 (매수선까지 {dist:.1f}% 남음)")

with r_col:
    st.markdown("#### 🔴 매도 (Sell) 가이드")
    if current_asset_val > v_u:
        st.warning("💡 현재가가 밴드 상단을 돌파했습니다. (수익 실현)")
        
        sell_list = []
        for n in range(1, 11):
            if qty - n > 0:
                target_qty = qty - n
                # LOC 공식: V_high / (현재수량 - n)
                loc_price = v_u / target_qty
                
                # 현재가보다 너무 낮게 팔아야 하는 상황 제외
                if loc_price > m['price'] * 0.85:
                    sell_list.append({
                        "매도 수량": f"-{n}주",
                        "LOC 단가 ($)": f"${loc_price:.2f}",
                        "현금 확보 ($)": f"${loc_price * n:.1f}"
                    })
        
        if sell_list:
            df_sell = pd.DataFrame(sell_list)
            st.table(df_sell)
        else:
            st.warning("매도 시뮬레이션 범위를 벗어났습니다.")
            
    else:
        dist = ((v_u - current_asset_val) / current_asset_val) * 100
        st.success(f"✅ 관망 구간 (매도선까지 {dist:.1f}% 남음)")

# --- [7. 시각화] ---
st.divider()
fig = go.Figure()
# 미래 2주 표현
dates = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]

fig.add_trace(go.Scatter(x=dates, y=[v1, v1], name='중심값 (V)', line=dict(color='gray', dash='dot')))
fig.add_trace(go.Scatter(x=dates, y=[v_u, v_u], name='매도 상한선', line=dict(color='red')))
fig.add_trace(go.Scatter(x=dates, y=[v_l, v_l], name='매수 하한선', line=dict(color='blue')))
fig.add_trace(go.Scatter(x=[datetime.now().date()], y=[current_asset_val], mode='markers+text', 
                         marker=dict(color='green', size=15), name='내 자산 위치', text=['Current'], textposition="top center"))

fig.update_layout(title="VR 밴드 위치 시각화", height=400, template="plotly_white")
st.plotly_chart(fig, use_container_width=True)
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

# --- [2. 메인 화면 상단: 빡센 사용 설명서 고정] ---
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
        st.markdown("""
        ### 2. 매일 & 매달 루틴
        * **매일 아침:** 체결 시 **수량**과 **현금 Pool**을 즉시 갱신합니다.
        * **2주 주기:** '사이클 업데이트'로 목표 V를 갱신합니다.
        * **한 달 리필:** 현금을 입금한 날 '사이클 업데이트' 모드에서 **[리필금액]**을 입력하여 V를 점프시킵니다.
        * **안전장치:** 지표가 충족되지 않아 뜨는 **매수 보류** 사인을 절대 무시하지 마십시오.
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
