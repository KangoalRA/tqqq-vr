import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 및 스타일 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")

st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .manual-section { background-color: rgba(0, 191, 255, 0.05); padding: 18px; border-radius: 10px; border-left: 6px solid #00BFFF; margin-bottom: 20px; }
        .tip-box { background-color: rgba(255, 255, 0, 0.05); padding: 18px; border-radius: 10px; border-left: 6px solid #FFFF00; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    </style>
""", unsafe_allow_html=True)

# 텔레그램 알림 함수
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg})
            st.toast("✅ 가이드 전송 완료", icon="✈️")
        else: st.error("Secrets 설정에 텔레그램 정보가 없습니다.")
    except Exception as e: st.error(f"전송 오류: {e}")

# 마켓 데이터 로드
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

# --- [사이드바: 전략 설정 및 입력] ---
with st.sidebar:
    st.header("📊 VR 5.0 전략 설정")
    invest_type = st.radio("투자 성향 선택", ["적립식 (Pool 75% 사용)", "거치식 (Pool 50% 사용)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15, min_value=5) / 100.0
    
    st.divider()
    
    # 데이터 로드
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_princ = 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            def safe_float(x):
                try: return float(str(x).replace(',',''))
                except: return 0.0
            last_v = safe_float(row.get("V_old", 0))
            last_princ = safe_float(row.get("Principal", 0))
            st.success(f"이전 V값 로드: ${last_v:,.0f}")
    except: pass

    mode = st.radio("모드 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율(원)", value=m["fx"])
    qty = st.number_input("보유 수량(주)", value=0)
    pool = st.number_input("현금 Pool($)", value=0.0)
    
    v_final, princ_final, growth = 0.0, last_princ, 0.0
    if mode == "최초 시작":
        princ_final = st.number_input("투입 원금($)", value=0.0)
        v_final = curr_p * qty
        st.warning("최초 시작 시 현재 평가금이 V로 설정됩니다.")
    else:
        add_usd = st.number_input("신규 적립($)", value=0.0)
        princ_final += add_usd
        if pool > 0: growth = pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장 (Save)", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, "Pool": pool, "V_old": v_final, "Principal": princ_final,
            "Price": curr_p, "Band": int(b_pct*100)
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("데이터 저장 완료!")
        st.rerun()

# --- [메인 대시보드] ---
if curr_p <= 0: st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + pool
roi = ((total_usd - princ_final)/princ_final*100) if princ_final > 0 else 0

st.title("🚀 TQQQ VR 5.0 Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("계산된 목표값(V)", f"${v_final:,.0f}", f"+${growth:,.0f} 성장")
c2.metric("총 자산(E+P)", f"${total_usd:,.0f}")
c3.metric("가용 현금(Pool)", f"${pool:,.0f}")
c4.metric("현재 수익률", f"{roi:.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드", "📈 성장 히스토리", "📖 운용 매뉴얼"])

# --- [Tab 1: 가이드] ---
with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        st.subheader("🔵 매수 예약 (LOC)")
        limit = pool * pool_cap
        st.caption(f"가용 예산: ${limit:,.0f} (Pool의 {int(pool_cap*100)}%)")
        buy_table = []
        for i, r in enumerate([0.98, 0.96, 0.94, 0.92, 0.90]):
            p = curr_p * r
            q = int((limit/5)/p)
            if q >= 1: buy_table.append({"단계": f"{i+1}차", "가격": f"${p:.2f}", "수량": f"{q}주", "금액": f"${p*q:.0f}"})
        st.table(pd.DataFrame(buy_table))

    with col_sell:
        st.subheader("🔴 리밸런싱 매도 (지정가)")
        v_max = v_final * (1 + b_pct)
        if qty > 0:
            target_p = v_max / qty
            if curr_p >= target_p:
                excess = eval_usd - v_final
                st.error(f"🚨 **밴드 상단 돌파!** 약 {int(excess/curr_p)}주 매도하여 원금 회수 및 수익을 확정하세요.")
            else:
                st.success(f"예약 매도 목표가: **${target_p:.2f}**")
                st.write(f"도달 시 약 {int((v_max - v_final)/target_p)}주 리밸런싱 매도")
        else: st.info("보유 수량이 없어 매도 가이드를 생성할 수 없습니다.")

    if st.button("✈️ 텔레그램으로 가이드 전송", type="primary", use_container_width=True):
        msg = f"🌊 VR 5.0 가이드\n가격: ${curr_p} / V: ${v_final:,.0f}\n매수(LOC): ${curr_p*0.98:.2f}\n매도(지정): ${v_max/qty if qty>0 else 0:.2f}"
        send_telegram_msg(msg)

# --- [Tab 2: 차트] ---
with tab2:
    if not df.empty:
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date']).dt.normalize()
        now_date = pd.to_datetime(datetime.now().date())
        now_df = pd.DataFrame([{"Date": now_date, "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)}])
        plot_df = pd.concat([c_df, now_df], ignore_index=True)
        plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
        plot_df = plot_df[plot_df["V_old"] > 0]
        
        plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
        plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
        plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
        plot_df = plot_df[plot_df["자산"] > 0]
        
        fig = go.Figure()
        last_d, last_v, last_t, last_b = plot_df['Date'].max(), plot_df['V_old'].iloc[-1], plot_df['상단'].iloc[-1], plot_df['하단'].iloc[-1]
        future_d = last_d + timedelta(days=60)
        
        # 밴드(초록 실선)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1.5), name='매도 밴드(상단)'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#00FF00', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='매수 밴드(하단)'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_t, last_t], line=dict(color='#00FF00', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_b, last_b], line=dict(color='#00FF00', width=1.5), showlegend=False))
        # 목표(하늘색 점선)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='목표 가치(V)'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_v, last_v], line=dict(color='#00BFFF', width=2, dash='dot'), showlegend=False))
        # 자산(노란색)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], line=dict(color='#FFFF00', width=3), mode='lines+markers', name='내 주식 가치(E)'))
        
        y_vals = pd.concat([plot_df["상단"], plot_df["하단"], plot_df["자산"]])
        y_range = [y_vals.min()*0.9, y_vals.max()*1.1]
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(tickformat='%y-%m-%d', range=[plot_df['Date'].min() - timedelta(days=1), future_d]), yaxis=dict(range=y_range, fixedrange=False))
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("데이터를 저장하면 여기에 히스토리가 표시됩니다.")

# --- [Tab 3: 매뉴얼] ---
with tab3:
    st.markdown("### 📖 TQQQ VR 5.0 (Pool형) 공식 운용 매뉴얼")
    
    st.info("**핵심 개념:** $V$(목표 가치)는 내가 보유해야 할 주식의 기준점입니다. 주가가 떨어져 내 자산이 $V$보다 낮아지면 매수하고, 너무 올라서 밴드를 뚫으면 매도하여 수익을 확정합니다.")

    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 1️⃣ 최초 시작 (Setting Up)")
        st.markdown("""
        * **대상:** VR 투자를 오늘 처음 시작하거나, 계좌를 완전히 초기화할 때 사용합니다.
        * **자산 배분 팁:** 처음 5,000달러로 시작한다면, **현금 50% / 주식 50%** 비중으로 매수한 뒤 시작하는 것이 가장 안정적입니다.
        * **설정 방법:** 모드를 `최초 시작`으로 두고 현재 수량과 현금을 입력 후 저장하세요. 
        * **결과:** 입력한 시점의 내 주식 가치가 시스템의 **첫 번째 기준점($V$)**이 됩니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 2️⃣ 사이클 업데이트 (Cycle Update)")
        st.markdown("""
        * **대상:** 2주간의 매매가 끝난 후, 다음 주기의 계획을 수립할 때 사용합니다.
        * **적립금 투입:** 월급 등으로 추가한 자금은 `신규 적립($)` 칸에 입력하세요. 원금($Principal$)에 자동 합산됩니다.
        * **성장 공식:** $V_{new} = V_{old} + (Pool / G) + \text{신규 적립금}$
        * **원리:** 현금(Pool)이 많을수록 목표치가 높게 설정되어 더 많이 매수하게 유도하고, 현금이 적으면 보수적으로 움직입니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="tip-box">', unsafe_allow_html=True)
        st.markdown("#### 💡 실전 운용 규칙 (Rules)")
        st.markdown("""
        - **매수 한도:** 적립식 투자자는 매달 현금이 보충되므로, 하락장에서 **현금 Pool의 75%**까지 과감하게 매수 주문을 냅니다.
        - **기울기(G=10):** 적립식의 복리 효과를 극대화하기 위해 기본값 10을 권장합니다.
        - **매매 타이밍:** 2주에 한 번, 월요일 아침에 앱의 가이드를 확인하고 **LOC(매수) 및 지정가(매도)** 예약 주문을 걸어두면 본업에 집중할 수 있습니다.
        - **하락장 대응:** 현금 한도(75%)를 다 썼다면 추가 매수를 멈추고 주가가 반등하여 밴드 안으로 들어올 때까지 기다려야 합니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)
