import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정: 컴팩트한 레이아웃] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")

st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .stTabs [data-baseweb="tab-list"] {gap: 8px;}
        .stTabs [data-baseweb="tab"] {padding: 8px 16px; border-radius: 4px;}
    </style>
""", unsafe_allow_html=True)

# 텔레그램 전송 함수
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg})
            st.toast("✅ 가이드 전송 완료", icon="✈️")
        else: st.error("Secrets에 텔레그램 설정이 없습니다.")
    except Exception as e: st.error(f"전송 실패: {e}")

# 데이터 로드 (실시간 가격/환율)
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 0.0, "fx": 1400.0}
    try:
        t = yf.Ticker("TQQQ").history(period="1d")
        if not t.empty: data["price"] = round(t['Close'].iloc[-1], 2)
        f = yf.Ticker("USDKRW=X").history(period="1d")
        if not f.empty: data["fx"] = round(f['Close'].iloc[-1], 2)
    except: pass
    return data

m = get_market_data()

# --- [사이드바: 불필요한 지표 제거 및 핵심 설정] ---
with st.sidebar:
    st.header("📊 VR 5.0 설정")
    
    invest_type = st.radio("투자 성향", ["적립식 (Limit 75%)", "거치식 (Limit 50%)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("G값", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드(%)", value=15, min_value=5) / 100.0
    
    st.divider()
    
    # 구글 시트 연결 및 데이터 로드
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_pool, last_qty, last_princ = 0.0, 0.0, 0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            last_qty = int(float(str(row.get("Qty", 0)).replace(',','')))
            last_pool = float(str(row.get("Pool", 0)).replace(',',''))
            last_v = float(str(row.get("V_old", 0)).replace(',',''))
            last_princ = float(str(row.get("Principal", 0)).replace(',',''))
            st.success(f"최근 데이터: {row.get('Date')}")
    except: st.info("데이터 로딩 대기 중...")

    # 입력 섹션
    mode = st.radio("작업 모드", ["사이클 업데이트", "최초 시작"], horizontal=True)
    
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"] if m["price"]>0 else 0.0, format="%.2f")
    curr_fx = st.number_input("환율(￦/$)", value=m["fx"])
    
    qty = st.number_input("보유 수량(주)", value=last_qty)
    pool = st.number_input("현금 Pool($)", value=last_pool)
    
    # --- [V값 성장 공식 적용] ---
    v_final, princ_final, growth = 0.0, last_princ, 0.0
    
    if mode == "최초 시작":
        princ_final = st.number_input("초기 원금($)", value=last_princ)
        v_final = curr_p * qty
    else:
        add_usd = st.number_input("추가 투입($)", value=0.0)
        princ_final += add_usd
        if pool > 0: growth = pool / g_val
        v_final = last_v + growth + add_usd # 매뉴얼 공식

    if st.button("💾 시트 데이터 저장", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, "Pool": pool, "V_old": v_final, "Principal": princ_final,
            "Price": curr_p, "Band": int(b_pct*100)
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장 완료!")
        st.rerun()

# --- [메인 대시보드] ---
if curr_p <= 0: st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + pool
roi = ((total_usd - princ_final)/princ_final*100) if princ_final>0 else 0

st.title("🚀 TQQQ VR 5.0 (Pool Type)")

# 상단 핵심 지표
m1, m2, m3, m4 = st.columns(4)
m1.metric("New V (목표)", f"${v_final:,.0f}", f"+${growth:,.0f}")
m2.metric("총 자산 (E+P)", f"${total_usd:,.0f}")
m3.metric("가용 Pool", f"${pool:,.0f}")
m4.metric("수익률", f"{roi:.2f}%")

tab1, tab2 = st.tabs(["📋 매매 실전 가이드", "📈 자산 성장 차트"])

with tab1:
    col_buy, col_sell = st.columns(2)
    
    with col_buy:
        st.subheader("🔵 매수 그물 (LOC)")
        limit_amt = pool * pool_cap
        st.caption(f"예산 한도: ${limit_amt:,.0f} ({int(pool_cap*100)}%)")
        
        buy_table = []
        steps = [0.98, 0.96, 0.94, 0.92, 0.90] # -2% 간격
        used = 0
        for i, r in enumerate(steps):
            p_loc = curr_p * r
            q_loc = int((limit_amt / 5) / p_loc)
            if q_loc < 1: q_loc = 1
            cost = p_loc * q_loc
            if used + cost <= limit_amt:
                buy_table.append({"단계": f"LOC {i+1}", "가격": f"${p_loc:.2f}", "수량": f"{q_loc}주", "금액": f"${cost:.0f}"})
                used += cost
            else: break
        st.table(pd.DataFrame(buy_table))

    with col_sell:
        st.subheader("🔴 리밸런싱 매도 (지정가)")
        v_max = v_final * (1 + b_pct)
        st.caption(f"밴드 상단 기준: ${v_max:,.0f}")
        
        if qty > 0:
            target_p = v_max / qty
            if curr_p >= target_p:
                excess = eval_usd - v_final
                sell_q = int(excess / curr_p)
                st.error(f"🚨 **밴드 상단 돌파!** {sell_q}주 즉시 매도하여 V값으로 복귀하세요.")
            else:
                excess_at_target = v_max - v_final
                sell_q_at_target = int(excess_at_target / target_p)
                st.success("✅ 현재 밴드 내부에서 안전하게 운용 중입니다.")
                st.markdown(f"**매도 목표가:** :red[${target_p:.2f}]")
                st.write(f"도달 시 예상 매도량: {sell_q_at_target}주")
        else: st.info("보유 중인 주식이 없습니다.")

    if st.button("✈️ 텔레그램 가이드 전송", type="primary", use_container_width=True):
        msg = f"[VR 5.0 가이드]\nTQQQ: ${curr_p}\n목표V: ${v_final:,.0f}\n총자산: ${total_usd:,.0f}\n\n*매수(LOC) 1차: ${curr_p*0.98:.2f}\n*매도(지정가): ${v_max/qty:.2f}"
        send_telegram_msg(msg)

with tab2:
    if not df.empty and "V_old" in df.columns:
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date'])
        
        # 현재 시점 데이터 추가하여 그래프 끝까지 연결
        now_df = pd.DataFrame([{
            "Date": datetime.now(), "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)
        }])
        c_df = pd.concat([c_df, now_df], ignore_index=True)
        
        # 밴드 및 자산 계산
        c_df["High"] = c_df["V_old"] * (1 + c_df["Band"]/100.0)
        c_df["Low"] = c_df["V_old"] * (1 - c_df["Band"]/100.0)
        c_df["Eval"] = c_df["Qty"] * c_df["Price"]
        
        fig = go.Figure()
        # 밴드 라인 (노란색 실선)
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['High'], line=dict(color='yellow', width=1.5), name='Band Upper'))
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['Low'], line=dict(color='yellow', width=1.5), fill='tonexty', fillcolor='rgba(255, 255, 0, 0.05)', name='Band Lower'))
        # V값 (빨간색)
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['V_old'], line=dict(color='red', width=2.5), name='Target(V)'))
        # 자산 평가액 (하늘색)
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['Eval'], mode='lines+markers', line=dict(color='#00E5FF', width=3), name='Evaluation(E)'))

        fig.update_layout(
            height=450, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("기록된 데이터가 없습니다.")
