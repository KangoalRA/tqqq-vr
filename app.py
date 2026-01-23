import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
try:
    from streamlit_gsheets import GSheetsConnection
    gsheets_available = True
except ImportError:
    gsheets_available = False

# --- [0. 화면 설정 및 CSS] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        .metric-box {
            background-color: #ffffff;
            border-left: 8px solid #ffcc00; 
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        .header-text { font-size: 1.4rem; font-weight: 900; color: #000000 !important; display: block; }
        .sub-text { font-size: 1.1rem; color: #111111 !important; font-weight: 700; }
        .manual-step { background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-bottom: 12px; border-left: 5px solid #2196f3; color: #000 !important; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)

# --- [1. 텔레그램 전송 함수 (사용자 원본)] ---
def send_telegram_msg(msg):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 완료!", icon="✈️")
    except:
        st.error("텔레그램 전송 실패: secrets 설정을 확인하세요.")

# --- [2. 데이터 및 사이드바 설정] ---
@st.cache_data(ttl=300)
def get_price():
    try:
        t = yf.Ticker("TQQQ").history(period="1d")
        return round(t['Close'].iloc[-1], 2) if not t.empty else 50.0
    except: return 50.0

curr_p = get_price()

with st.sidebar:
    st.header("⚙️ VR 5.0 전략 세팅")
    invest_type = st.radio("투자 성향", ["적립식 (Pool 75%)", "거치식 (Pool 50%)", "인출식 (Pool 25%)"])
    p_cap = 0.75 if "적립" in invest_type else (0.5 if "거치" in invest_type else 0.25)
    
    c1, c2 = st.columns(2)
    g_val = c1.number_input("기울기(G)", value=10, min_value=1)
    b_pct = c2.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    conn = None
    last_v = last_pool = last_princ = 0.0
    if gsheets_available:
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_gs = conn.read(worksheet="Sheet1", ttl=0)
            if not df_gs.empty:
                row = df_gs.iloc[-1]
                last_v = float(str(row.get("V_old", 0)).replace(',',''))
                last_pool = float(str(row.get("Pool", 0)).replace(',',''))
                last_princ = float(str(row.get("Principal", 0)).replace(',',''))
        except: conn = None

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p_input = st.number_input("현재가 ($)", value=curr_p, format="%.2f")
    qty_input = st.number_input("보유 수량 (주)", value=0)
    
    if mode == "최초 시작":
        princ_f = st.number_input("총 원금 ($)", value=5000.0)
        qty_init = int((princ_f * 0.5) / curr_p_input)
        final_pool = princ_f - (qty_init * curr_p_input)
        v_final = curr_p_input * qty_init
        qty = qty_init
    else:
        base_p = st.number_input("현재 현금 ($)", value=last_pool)
        add_usd = st.number_input("신규 입금 ($)", value=0.0)
        final_pool = base_p + add_usd
        princ_f = last_princ + add_usd
        v_final = last_v + (final_pool / g_val) + add_usd if final_pool > 0 else last_v + add_usd
        qty = qty_input

    # [분리] 데이터 저장 버튼
    if st.button("💾 이 사이클 데이터 저장", use_container_width=True):
        if conn:
            new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_f, "Price": curr_p_input, "Band": int(b_pct*100)}])
            conn.update(worksheet="Sheet1", data=pd.concat([df_gs, new_row], ignore_index=True).fillna(0))
            st.success("구글 시트 저장 완료!")
            st.rerun()

# --- [3. 매매 가이드 계산] ---
min_val, max_val = v_final * (1 - b_pct), v_final * (1 + b_pct)
start_s_p = max_val / qty if qty > 0 else 0
base_s_p = max(curr_p_input, start_s_p)

buy_guide, b_step, t_q, t_p = [], (final_pool * p_cap) / 10, qty, final_pool
for i in range(10):
    p = curr_p_input * (1 - (0.015 * (i+1)))
    q = int(b_step / p) if p > 0 else 0
    if q >= 1 and t_p >= p * q:
        t_q += q; t_p -= (p * q)
        buy_guide.append({"잔여개수": f"{t_q}개", "매수가격": f"${p:.2f}", "Pool": f"${t_p:,.2f}"})

sell_guide, weights, t_qs, t_ps = [], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5], qty, final_pool
unit = qty / sum(weights) if qty > 0 else 0
for i in range(10):
    q = max(1, int(unit * weights[i]))
    if t_qs >= q:
        p = base_s_p * (1 + (0.015 * i))
        t_qs -= q; t_ps += (p * q)
        sell_guide.append({"잔여개수": f"{t_qs}개", "매도가격": f"${p:.2f}", "수량": f"🔻{q}주", "Pool": f"${t_ps:,.2f}"})

# --- [4. 메인 화면 출력 (TAB)] ---
st.title("🚀 TQQQ VR 5.0 Dashboard")
t1, t2, t3 = st.tabs(["📋 매매 가이드", "📈 성장 차트", "📖 필승 매뉴얼"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        # [분리] 매수 알림 버튼
        if st.button("✈️ 매수 가이드 텔레그램 전송"):
            m_msg = f"🔵 [VR 5.0 매수 가이드]\n하단가: ${min_val:,.2f}\n" + "\n".join([f"{d['매수가격']} / {d['잔여개수']}" for d in buy_guide[:5]])
            send_telegram_msg(m_msg)
        
        st.markdown(f'<div class="metric-box"><span class="header-text">📉 하단(최소): ${min_val:,.2f}</span><span class="sub-text">잔여:{qty}개 │ Pool:${final_pool:,.2f}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(buy_guide), use_container_width=True, hide_index=True)

    with c2:
        # [분리] 매도 알림 버튼
        if st.button("✈️ 매도 가이드 텔레그램 전송"):
            s_msg = f"🔴 [VR 5.0 매도 가이드]\n상단가: ${start_s_p:,.2f}\n" + "\n".join([f"{d['매도가격']} / {d['수량']}" for d in sell_guide[:5]])
            send_telegram_msg(s_msg)

        st.markdown(f'<div class="metric-box"><span class="header-text">📈 상단가: ${start_s_p:,.2f}</span><span class="sub-text">최대 가치: ${max_val:,.2f}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(sell_guide), use_container_width=True, hide_index=True)

with t2:
    if conn:
        df_p = conn.read(worksheet="Sheet1", ttl=0)
        if not df_p.empty:
            df_p['Date'] = pd.to_datetime(df_p['Date'])
            df_p["상단"] = df_p["V_old"] * (1 + b_pct); df_p["하단"] = df_p["V_old"] * (1 - b_pct); df_p["자산"] = df_p["Qty"] * df_p["Price"]
            fig = go.Figure()
            # [수정] 밴드 초록색으로 설정
            fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['상단'], line=dict(color='green', width=1), name='매도 한계'))
            fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['하단'], line=dict(color='green', width=1), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.1)', name='안전 밴드(V)'))
            fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['V_old'], line=dict(color='#00BFFF', dash='dot'), name='목표 가치'))
            fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['자산'], line=dict(color='#FFFF00', width=3), name='내 자산(E)'))
            fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

with t3:
    st.markdown("### 📖 VR 5.0 필승 매뉴얼")
    st.markdown('<div class="manual-step"><b>1. 데이터 저장:</b> 사이드바에서 정보를 입력하고 [이 사이클 데이터 저장]을 누르세요. 2주에 한 번만 합니다.</div>', unsafe_allow_html=True)
    st.markdown('<div class="manual-step"><b>2. 가이드 전송:</b> 표 위에 있는 [텔레그램 전송] 버튼을 눌러 폰으로 숙제를 보내세요. 필요할 때 언제든 다시 보낼 수 있습니다.</div>', unsafe_allow_html=True)
    st.markdown('<div class="manual-step"><b>3. 차트 확인:</b> 차트의 초록색 영역 안에 내 자산(노란선)이 있으면 안전합니다. 영역 밖으로 나가면 즉시 매매 대응하세요.</div>', unsafe_allow_html=True)
