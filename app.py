import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정 및 CSS (글자색 완전 고정)] ---
st.set_page_config(page_title="TQQQ VR 5.0 Final", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        
        /* 박스 스타일: 배경색 밝게, 글자색 검정 강제 */
        .metric-box {
            background-color: #ffffff; /* 완전 흰색 배경 */
            border-left: 6px solid #ffcc00; 
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }
        
        .header-text {
            font-size: 1.3rem;
            font-weight: 900;
            color: #000000 !important; /* 무조건 검은색 */
            display: block;
            margin-bottom: 5px;
        }
        .sub-text {
            font-size: 1.0rem;
            color: #222222 !important; /* 진한 검은색 */
            font-weight: 600;
        }
        
        .manual-step {
            background-color: #e3f2fd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 10px;
            border-left: 5px solid #2196f3;
            color: #000000 !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- [1. 데이터 가져오기] ---
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 0.0, "fx": 1450.0}
    try:
        t = yf.Ticker("TQQQ").history(period="1d")
        if not t.empty: data["price"] = round(t['Close'].iloc[-1], 2)
        f = yf.Ticker("USDKRW=X").history(period="1d")
        if not f.empty: data["fx"] = round(f['Close'].iloc[-1], 2)
    except: pass
    return data

m = get_market_data()

# --- [2. 사이드바 설정] ---
with st.sidebar:
    st.header("⚙️ VR 5.0 설정")
    
    invest_type = st.radio(
        "투자 성향", 
        ["적립식 (Pool 75%)", "거치식 (Pool 50%)", "인출식 (Pool 25%)"]
    )
    if "적립식" in invest_type: pool_cap = 0.75
    elif "거치식" in invest_type: pool_cap = 0.50
    else: pool_cap = 0.25

    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_pool, last_princ = 0.0, 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            def safe_float(x):
                try: return float(str(x).replace(',',''))
                except: return 0.0
            last_v = safe_float(row.get("V_old", 0))
            last_pool = safe_float(row.get("Pool", 0))
            last_princ = safe_float(row.get("Principal", 0))
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가 ($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율 (원)", value=m["fx"])
    qty = st.number_input("현재 보유 수량 (주)", value=0)
    
    final_pool, v_final, princ_final, growth, add_usd = 0.0, 0.0, 0.0, 0.0, 0.0

    if mode == "최초 시작":
        princ_final = st.number_input("총 원금 ($)", value=5000.0)
        qty_init = int((princ_final * 0.5) / curr_p) if curr_p > 0 else 0
        final_pool = princ_final - (qty_init * curr_p)
        v_final = curr_p * qty_init
        qty = qty_init 
    else:
        base_pool = st.number_input("기존 계좌 현금 ($)", value=last_pool)
        add_usd = st.number_input("신규 입금액 ($)", value=0.0)
        final_pool = base_pool + add_usd
        princ_final = last_princ + add_usd
        if final_pool > 0: growth = final_pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장"):
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장 완료")
        st.rerun()

# --- [3. 메인 화면] ---
if curr_p <= 0: st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + final_pool
min_val = v_final * (1 - b_pct)  # 밴드 하단
max_val = v_final * (1 + b_pct)  # 밴드 상단

st.title("📊 TQQQ VR 5.0 Dashboard")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드 (표)", "📈 성장 차트", "📖 운용 매뉴얼"])

# --- [TAB 1: 매매 가이드] ---
with tab1:
    col_buy, col_sell = st.columns(2)

    # === [매수점 로직: 하단부터 시작] ===
    with col_buy:
        st.subheader("🔵 매수점 (Buying Point)")
        buy_limit = final_pool * pool_cap
        
        # 10단계 분할 매수 수량
        total_buy_qty = int(buy_limit / (curr_p * 0.9)) if curr_p > 0 else 0
        step_buy_qty = max(1, int(total_buy_qty / 10))

        st.markdown(f"""
        <div class="metric-box">
            <span class="header-text">📉 최소값(밴드하단): ${min_val:,.2f}</span>
            <span class="sub-text">현재 잔여개수: <b>{qty}개</b> │ 현재 Pool: <b>${final_pool:,.2f}</b></span>
        </div>
        """, unsafe_allow_html=True)
        
        st.info(f"💡 **가이드:** {step_buy_qty}개씩 지정가 매수 (잔량 주문)")

        buy_data = []
        cur_pool = final_pool
        cur_qty = qty
        
        # 매수: 현재가에서 -1.5%씩 내려가며 그물망
        for i in range(10):
            target_p = curr_p * (1 - (0.015 * (i+1))) 
            cost = target_p * step_buy_qty
            if cur_pool >= cost:
                cur_qty += step_buy_qty
                cur_pool -= cost
                buy_data.append({
                    "잔여 개수": f"{cur_qty}개",
                    "매수 가격": f"${target_p:.2f}",
                    "예상 Pool": f"${cur_pool:,.2f}"
                })
        
        st.dataframe(pd.DataFrame(buy_data), use_container_width=True, hide_index=True)

    # === [매도점 로직 수정: 밴드 상단 가격 기준] ===
    with col_sell:
        st.subheader("🔴 매도점 (Selling Point)")
        
        # [핵심 수정] 매도 시작 가격 = 밴드 상단 가격 (Max Value / Qty)
        start_sell_price = max_val / qty if qty > 0 else 0
        
        # 만약 현재가 > 상단가격 -> '현재가'부터 매도 시작 (이미 뚫었으니까)
        # 만약 현재가 < 상단가격 -> '상단가격'부터 매도 시작 (아직 안 왔으니까 기다림)
        base_sell_price = max(curr_p, start_sell_price)

        step_sell_qty = max(1, int(qty / 10)) # 보유량의 10%씩 분할 매도

        st.markdown(f"""
        <div class="metric-box">
            <span class="header-text">📈 최대값(밴드상단): ${max_val:,.2f}</span>
            <span class="sub-text">상단 도달 가격: <b>${start_sell_price:,.2f}</b></span>
        </div>
        """, unsafe_allow_html=True)

        if curr_p < start_sell_price:
             st.info(f"💡 **대기:** 주가가 **${start_sell_price:.2f}**에 닿아야 팔립니다. 미리 예약만 해두세요.")
        else:
             st.error(f"🚨 **돌파:** 이미 밴드 상단을 넘었습니다! 즉시 매도 구간입니다.")

        sell_data = []
        cur_pool_s = final_pool
        cur_qty_s = qty
        
        # 매도: '상단 도달 가격'에서 +1.5%씩 올라가며 분할 매도
        for i in range(10):
            if cur_qty_s >= step_sell_qty:
                # 시작점(base_sell_price)에서 0%, 1.5%, 3%... 위로 설정
                target_p = base_sell_price * (1 + (0.015 * i)) 
                revenue = target_p * step_sell_qty
                cur_qty_s -= step_sell_qty
                cur_pool_s += revenue
                sell_data.append({
                    "잔여 개수": f"{cur_qty_s}개",
                    "매도 가격": f"${target_p:.2f}",
                    "예상 Pool": f"${cur_pool_s:,.2f}"
                })
                
        st.dataframe(pd.DataFrame(sell_data), use_container_width=True, hide_index=True)

# --- [TAB 2: 성장 차트] ---
with tab2:
    if not df.empty:
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date']).dt.normalize()
        now_date = pd.to_datetime(datetime.now().date())
        now_df = pd.DataFrame([{"Date": now_date, "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)}])
        plot_df = pd.concat([c_df, now_df], ignore_index=True)
        plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
        
        plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
        plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
        plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
        plot_df = plot_df[plot_df["자산"] > 0]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1), name='매도 밴드'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#FF4B4B', width=1), fill='tonexty', fillcolor='rgba(255, 75, 75, 0.05)', name='매수 밴드'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='중심선(V)'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], line=dict(color='#FFFF00', width=3), mode='lines+markers', name='내 자산(E)'))
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

# --- [TAB 3: 운용 매뉴얼 (초심자용 상세)] ---
with tab3:
    st.markdown("### 📘 VR 5.0 필승 운용 가이드")
    
    with st.expander("STEP 1: 처음 시작할 때 (최초 세팅)", expanded=True):
        st.markdown("""
        <div class="manual-step">
        <b>1. 모드 선택:</b> 왼쪽 사이드바에서 [최초 시작]을 누르세요.<br>
        <b>2. 원금 입력:</b> 투자할 총 금액(예: $5000)을 입력하세요.<br>
        <b>3. 즉시 매수:</b> 화면에 "23주 사세요"라고 뜨면, 증권사 앱에서 <b>지금 당장 시장가</b>로 23주를 사세요.<br>
        <b>4. 저장:</b> 매수 후 '데이터 저장' 버튼을 꾹 누르세요.
        </div>
        """, unsafe_allow_html=True)

    with st.expander("STEP 2: 2주마다 업데이트 (반복 루틴)", expanded=True):
        st.markdown("""
        <div class="manual-step">
        <b>1. 모드 선택:</b> 왼쪽 사이드바에서 [사이클 업데이트]를 누르세요.<br>
        <b>2. 잔고 입력:</b> 내 계좌를 보고 '주식 수'와 '남은 현금(달러)'을 정확히 적으세요.<br>
        <b>3. 저장:</b> '데이터 저장'을 누르면 새로운 숙제(매매 가이드)가 나옵니다.<br>
        <b>4. 확인:</b> [매매 가이드] 탭에 나온 표를 확인하세요.
        </div>
        """, unsafe_allow_html=True)

    with st.expander("STEP 3: 증권사 예약 주문 (숙제 하기)", expanded=True):
        st.markdown("""
        <div class="manual-step">
        증권사 앱(영웅문 등)의 <b>[주식예약주문]</b> 메뉴를 켭니다.<br>
        <br>
        <b>🔵 매수 주문 (돈 버는 그물)</b><br>
        1. <b>기간:</b> 오늘 ~ 2주 뒤까지 설정<br>
        2. <b>조건:</b> <b>지정가</b>, <b>잔량(잔량유지)</b> 체크 필수!<br>
        3. <b>입력:</b> 가이드 표의 '매수 가격'과 '수량'을 그대로 입력하고 예약 전송.<br>
        (예: $50.50에 3주, $49.80에 3주... 10번 반복)<br>
        <br>
        <b>🔴 매도 주문 (수익 실현)</b><br>
        1. 가이드 표의 매도 가격이 현재가보다 훨씬 높을 겁니다. (정상)<br>
        2. 매수와 똑같이 <b>기간/지정가/잔량</b>으로 예약 매도를 걸어두세요.<br>
        3. 2주 동안 주가가 폭등하면 알아서 팔립니다.
        </div>
        """, unsafe_allow_html=True)
