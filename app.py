import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
# gsheets 라이브러리 예외처리
try:
    from streamlit_gsheets import GSheetsConnection
    gsheets_available = True
except ImportError:
    gsheets_available = False

# --- [0. 화면 설정 및 CSS (글자색 검정 고정)] ---
st.set_page_config(page_title="TQQQ VR 5.0 Final", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        
        .metric-box {
            background-color: #ffffff;
            border-left: 6px solid #ffcc00; 
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }
        
        .header-text {
            font-size: 1.3rem;
            font-weight: 900;
            color: #000000 !important;
            display: block;
            margin-bottom: 5px;
        }
        .sub-text {
            font-size: 1.0rem;
            color: #222222 !important;
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
    data = {"price": 50.0, "fx": 1450.0}
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
    
    # 구글 시트 연결
    conn = None
    if gsheets_available:
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
        except: pass

    df = pd.DataFrame()
    last_v, last_pool, last_princ = 0.0, 0.0, 0.0
    
    if conn:
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
        if conn:
            new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
            final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
            try:
                conn.update(worksheet="Sheet1", data=final_df.fillna(0))
                st.success("저장 완료")
                st.rerun()
            except: st.error("구글 시트 저장 실패")
        else:
            st.warning("구글 시트 연결 안됨")

# --- [3. 메인 화면] ---
if curr_p <= 0:
    st.error("왼쪽 사이드바에 현재가를 입력해주세요.")
    st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + final_pool
min_val = v_final * (1 - b_pct)  # 밴드 하단
max_val = v_final * (1 + b_pct)  # 밴드 상단

st.title("📊 TQQQ VR 5.0 Dashboard")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드 (표)", "📈 성장 차트", "📖 운용 매뉴얼"])

# --- [TAB 1: 매매 가이드] ---
with tab1:
    col_buy, col_sell = st.columns(2)

    # === [매수점: 10단계 균등 분할] ===
    with col_buy:
        st.subheader("🔵 매수점 (Buying Point)")
        buy_limit = final_pool * pool_cap
        
        total_buy_qty = int(buy_limit / (curr_p * 0.9)) if curr_p > 0 else 0
        step_buy_qty = max(1, int(total_buy_qty / 10))

        st.markdown(f"""
        <div class="metric-box">
            <span class="header-text">📉 최소값(밴드하단): ${min_val:,.2f}</span>
            <span class="sub-text">현재 잔여개수: <b>{qty}개</b> │ 현재 Pool: <b>${final_pool:,.2f}</b></span>
        </div>
        """, unsafe_allow_html=True)
        
        st.info(f"💡 **가이드:** 주가가 떨어지면 **{step_buy_qty}개씩** 똑같이 사모으세요.")

        buy_data = []
        cur_pool = final_pool
        cur_qty = qty
        
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

    # === [매도점 수정: 피라미드 분할 매도] ===
    with col_sell:
        st.subheader("🔴 매도점 (Selling Point)")
        
        # 1. 매도 시작점 잡기
        start_sell_price = max_val / qty if qty > 0 else 0
        base_sell_price = max(curr_p, start_sell_price)

        # 2. 피라미드 매도 가중치 (갈수록 많이 팜)
        # 총 10단계, 가중치: 1,1,2,2,3,3,4,4,5,5 (총합 30)
        # 내 보유 수량을 30등분 하여 1단위로 설정
        sell_weights = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
        total_weight = sum(sell_weights)
        unit_share = qty / total_weight if qty > 0 else 0

        st.markdown(f"""
        <div class="metric-box">
            <span class="header-text">📈 최대값(밴드상단): ${max_val:,.2f}</span>
            <span class="sub-text">상단 도달 가격: <b>${start_sell_price:,.2f}</b></span>
        </div>
        """, unsafe_allow_html=True)

        if curr_p < start_sell_price:
             st.info(f"💡 **대기:** 주가가 **${start_sell_price:.2f}** 근처에 가야 조금씩 팔기 시작합니다.")
        else:
             st.error(f"🚨 **구간 진입:** 상승세입니다! 위로 갈수록 더 많이 파세요.")

        sell_data = []
        cur_pool_s = final_pool
        cur_qty_s = qty
        
        for i in range(10):
            # 단계별 매도 수량 (소량 -> 대량)
            # 최소 1주 이상은 팔리게 max(1, ...) 처리
            sell_q_now = max(1, int(unit_share * sell_weights[i]))
            
            if cur_qty_s >= sell_q_now:
                target_p = base_sell_price * (1 + (0.015 * i)) 
                revenue = target_p * sell_q_now
                cur_qty_s -= sell_q_now
                cur_pool_s += revenue
                
                sell_data.append({
                    "잔여 개수": f"{cur_qty_s}개",
                    "매도 가격": f"${target_p:.2f}",
                    "매도 수량": f"🔻 {sell_q_now}주",
                    "예상 Pool": f"${cur_pool_s:,.2f}"
                })
                
        st.dataframe(pd.DataFrame(sell_data), use_container_width=True, hide_index=True)

# --- [TAB 2: 차트] ---
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

# --- [TAB 3: 운용 매뉴얼] ---
with tab3:
    st.markdown("### 📘 VR 5.0 필승 운용 가이드")
    
    with st.expander("STEP 1: 처음 시작할 때", expanded=True):
        st.markdown("""
        <div class="manual-step">
        <b>1. 모드 선택:</b> [최초 시작] 클릭<br>
        <b>2. 입력:</b> 총 원금(달러) 입력<br>
        <b>3. 실행:</b> 계산된 수량만큼 즉시 매수 후 저장
        </div>
        """, unsafe_allow_html=True)

    with st.expander("STEP 2: 2주마다 업데이트", expanded=True):
        st.markdown("""
        <div class="manual-step">
        <b>1. 모드 선택:</b> [사이클 업데이트] 클릭<br>
        <b>2. 입력:</b> 현재 주식 수, 남은 현금 입력<br>
        <b>3. 확인:</b> [매매 가이드] 탭의 표 확인
        </div>
        """, unsafe_allow_html=True)

    with st.expander("STEP 3: 예약 주문 (핵심)", expanded=True):
        st.markdown("""
        <div class="manual-step">
        <b>🔵 매수 (그물치기)</b><br>
        - 가이드 표에 나온대로 가격/수량을 <b>지정가+잔량</b>으로 예약.<br>
        - 주가가 떨어지면 알아서 사집니다.<br><br>
        <b>🔴 매도 (피라미드)</b><br>
        - 가이드 표를 보세요. <b>위로 갈수록 매도 수량이 늘어납니다.</b><br>
        - 밴드 상단 근처에선 조금 팔고, 폭등하면 많이 팔아서 수익을 극대화하세요.
        </div>
        """, unsafe_allow_html=True)
