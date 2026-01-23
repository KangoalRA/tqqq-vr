import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
    </style>
""", unsafe_allow_html=True)

# 텔레그램
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg})
            st.toast("✅ 전송 완료")
    except: pass

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

# --- [사이드바] ---
with st.sidebar:
    st.header("📊 VR 5.0 설정")
    invest_type = st.radio("투자 성향", ["적립식 (75%)", "거치식 (50%)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_princ = 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            # [수정] 데이터를 가져올 때 안전하게 숫자로 변환
            def safe_float(x):
                try: return float(str(x).replace(',',''))
                except: return 0.0
            
            last_v = safe_float(row.get("V_old", 0))
            last_princ = safe_float(row.get("Principal", 0))
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율", value=m["fx"])
    qty = st.number_input("보유 수량(주)", value=0)
    pool = st.number_input("현금 Pool($)", value=0.0)
    
    v_final, princ_final, growth = 0.0, last_princ, 0.0
    if mode == "최초 시작":
        princ_final = st.number_input("초기 원금($)", value=0.0)
        v_final = curr_p * qty
    else:
        add_usd = st.number_input("신규 적립($)", value=0.0)
        princ_final += add_usd
        if pool > 0: growth = pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장", use_container_width=True):
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
roi = ((total_usd - princ_final)/princ_final*100) if princ_final > 0 else 0

st.title("🚀 TQQQ VR 5.0 Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("목표값 (V)", f"${v_final:,.0f}", f"+${growth:,.0f}")
c2.metric("총 자산", f"${total_usd:,.0f}")
c3.metric("가용 Pool", f"${pool:,.0f}")
c4.metric("수익률", f"{roi:.2f}%")

tab1, tab2 = st.tabs(["📋 매매 가이드", "📈 자산 성장 차트"])

with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        st.subheader("🔵 매수 (LOC)")
        limit = pool * pool_cap
        buy_table = []
        for i, r in enumerate([0.98, 0.96, 0.94, 0.92, 0.90]):
            p = curr_p * r
            q = int((limit/5)/p)
            if q >= 1: buy_table.append({"단계": f"{i+1}차", "가격": f"${p:.2f}", "수량": f"{q}주"})
        st.table(pd.DataFrame(buy_table))

    with col_sell:
        st.subheader("🔴 매도 (지정가)")
        v_max = v_final * (1 + b_pct)
        if qty > 0:
            target_p = v_max / qty
            if curr_p >= target_p:
                st.error(f"🚨 돌파! {int((eval_usd-v_final)/curr_p)}주 매도")
            else:
                st.success(f"목표가: ${target_p:.2f}")
        else: st.info("보유량 없음")

with tab2:
    # 1. 데이터 준비
    c_df = df.copy() if not df.empty else pd.DataFrame()
    
    # [핵심 1] 날짜에서 '시간' 제거하여 날짜끼리만 비교되게 함 (중복 방지)
    if not c_df.empty: 
        c_df['Date'] = pd.to_datetime(c_df['Date']).dt.normalize()
        # 숫자 컬럼 강제 변환 (문자열 '60' 등이 섞여있을 경우 방지)
        for col in ['V_old', 'Band', 'Qty', 'Price']:
            if col in c_df.columns:
                c_df[col] = pd.to_numeric(c_df[col], errors='coerce').fillna(0)

    # 현재 데이터 생성 (시간 제거)
    now_date = pd.to_datetime(datetime.now().date())
    now_df = pd.DataFrame([{
        "Date": now_date, "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)
    }])
    
    # 합치기 및 중복 제거
    plot_df = pd.concat([c_df, now_df], ignore_index=True)
    plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
    
    # 2. 차트 변수 계산
    plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
    plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
    plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
    
    # [핵심 2] 자산이 0원인 데이터(초기값 오류 등)는 차트에서 아예 빼버림 -> 수직 상승선 방지
    plot_df = plot_df[plot_df["자산"] > 0]

    # 3. Y축 스케일 계산
    valid_vals = pd.concat([plot_df["상단"], plot_df["하단"], plot_df["자산"]])
    y_range = None
    if not valid_vals.empty:
        y_min_real, y_max_real = valid_vals.min(), valid_vals.max()
        margin = (y_max_real - y_min_real) * 0.1 if y_max_real != y_min_real else y_max_real * 0.1
        y_range = [y_min_real - margin, y_max_real + margin]

    # 4. 차트 그리기
    fig = go.Figure()

    # 미래 연장선 좌표 계산
    if not plot_df.empty:
        last_date = plot_df['Date'].max()
        last_v = plot_df['V_old'].iloc[-1]
        last_top = plot_df['상단'].iloc[-1]
        last_bottom = plot_df['하단'].iloc[-1]
        future_date = last_date + timedelta(days=60)

        # 밴드 (과거~현재)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], mode='lines', line=dict(color='#00FF00', width=1.5), name='Band Top', showlegend=True))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], mode='lines', line=dict(color='#00FF00', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='Band Bottom', showlegend=True))
        # 밴드 (미래 연장)
        fig.add_trace(go.Scatter(x=[last_date, future_date], y=[last_top, last_top], mode='lines', line=dict(color='#00FF00', width=1.5, dash='solid'), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=[last_date, future_date], y=[last_bottom, last_bottom], mode='lines', line=dict(color='#00FF00', width=1.5, dash='solid'), showlegend=False, hoverinfo='skip'))

        # 목표 V (과거~현재)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], mode='lines', line=dict(color='#00BFFF', width=2, dash='dot'), name='Target V', showlegend=True))
        # 목표 V (미래 연장)
        fig.add_trace(go.Scatter(x=[last_date, future_date], y=[last_v, last_v], mode='lines', line=dict(color='#00BFFF', width=2, dash='dot'), showlegend=False, hoverinfo='skip'))
        
        # 내 자산 (과거~현재만)
        mode_set = 'markers' if len(plot_df) == 1 else 'lines+markers'
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], 
                                 line=dict(color='#FFFF00', width=3), 
                                 marker=dict(size=8, color='#FFFF00'), 
                                 mode=mode_set, name='My Asset'))
        
        # X축 범위 설정
        min_date = plot_df['Date'].min()
        xaxis_config = dict(
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', 
            tickformat='%y-%m-%d',
            range=[min_date - timedelta(hours=12), future_date] # 시작점 딱 맞춤
        )
        
        # 오늘 처음이라 데이터가 1개뿐일 때 시각 보정
        if len(plot_df) == 1:
             xaxis_config['range'] = [min_date - timedelta(days=2), min_date + timedelta(days=30)]

        fig.update_layout(
            height=500,
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis=xaxis_config,
            yaxis=dict(
                showgrid=True, gridcolor='rgba(255,255,255,0.1)', 
                range=y_range, 
                fixedrange=False
            ),
            legend=dict(orientation="h", y=1.05, x=1, xanchor="right")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("데이터가 없습니다. 데이터를 저장해주세요.")
