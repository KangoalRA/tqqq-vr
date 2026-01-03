import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 페이지 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 투자 가이드", layout="wide")

# 텔레그램 메시지 전송 함수
def send_telegram_msg(msg):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 완료!", icon="✈️")
    except Exception as e:
        st.error(f"텔레그램 설정 오류: {e}")

@st.cache_data(ttl=600)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1350.0, "dd": 0.0, "fng": 25.0, "bull": True}
    try:
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        if not t_hist.empty: data["price"] = round(t_hist['Close'].iloc[-1], 2)
        
        n_hist = yf.Ticker("^NDX").history(period="2y")
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

# VR 5.0 안전장치
def check_safety(dd, fng):
    if dd > -10: return True, 1.0, "🟩 정상장: 쿼터 100%", "normal"
    elif -20 < dd <= -10:
        if fng <= 15: return True, 0.5, "🟧 조정장: 쿼터 50% (FnG 15↓)", "warning"
        else: return False, 0.0, f"🚫 매수 보류 (FnG {fng} > 15)", "error"
    else:
        if fng <= 10: return True, 0.3, "🟥 하락장: 쿼터 30% (FnG 10↓)", "critical"
        else: return False, 0.0, f"🚫 하락장 방어 (FnG {fng} > 10)", "error"

def get_recommended_band(dd, is_bull):
    if not is_bull or dd < -20: return 10, "🟥 하락/공포장 (추천: 10%)"
    elif -20 <= dd < -10: return 15, "🟧 조정장 (추천: 15%)"
    elif dd >= -10 and is_bull: return 20, "🟩 상승장 (추천: 20%)"
    return 15, "⬜ 일반 (추천: 15%)"

# --- [UI 시작] ---
st.title("🚀 TQQQ VR 5.0 가이드")

if m and m["price"] > 0:
    with st.sidebar:
        st.header("⚙️ VR 설정")
        
        # 1. 밴드폭 설정 (수정됨: G값 오기 수정)
        st.subheader("1. 밴드폭(Band) 설정")
        rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
        st.caption(rec_msg)
        # 용어 수정: G값 -> 밴드폭
        band_pct = st.slider("밴드폭 설정 (%)", 10, 40, rec_val) / 100

        st.divider()

        # 2. 시장 데이터
        st.subheader("2. 시장 데이터")
        st.metric("나스닥 낙폭", f"{m['dd']}%")
        st.markdown("[👉 FnG 확인 (CNN)](https://edition.cnn.com/markets/fear-and-greed)")
        fng_input = st.number_input("FnG Index 입력", value=float(m['fng']))
        
        st.divider()
        
        # 3. 내 자산 데이터 (자동 로드)
        st.subheader("3. 자산 데이터")
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 변수 초기화
        loaded = False
        default_qty, default_pool, default_v, default_principal = 100, 2000.0, m['price']*100, 5000.0
        
        try:
            # E열(FnG)까지 읽기
            existing_data = conn.read(worksheet="Sheet1", usecols=[0, 1, 2, 3, 4], ttl=0).dropna()
            if not existing_data.empty:
                last_row = existing_data.iloc[-1]
                default_qty = int(last_row.iloc[0])
                default_pool = float(last_row.iloc[1])
                default_v = float(last_row.iloc[2]) # 시트의 V값
                if len(last_row) > 3: default_principal = float(last_row.iloc[3])
                loaded = True
                st.success(f"✅ 최근 데이터 로드됨 (V: ${default_v:,.0f})")
        except:
            st.warning("⚠️ 시트 연결 안됨")

        mode = st.radio("모드 선택", ["사이클 업데이트", "최초 시작"])
        
        # 공통 입력
        qty = st.number_input("현재 보유 수량 (주)", value=default_qty, min_value=1)
        pool = st.number_input("현재 현금 Pool ($)", value=default_pool)
        
        # 모드별 V값 처리
        if mode == "최초 시작":
            principal = st.number_input("총 투입 원금 ($)", value=default_principal)
            v1 = m['price'] * qty
            v_to_save = v1 
        else:
            # [수정된 부분] V값은 시트에서 가져온 값으로 고정
            st.markdown(f"**직전 V값: ${default_v:,.2f}** (자동 적용)")
            v_old = default_v 
            
            # 원금 업데이트 로직
            principal = default_principal
            cur = st.radio("추가 적립금(리필)", ["없음", "원화", "달러"], horizontal=True)
            
            add_val = 0.0
            if cur == "원화":
                add_krw = st.number_input("입금액 (원)", value=0)
                add_val = add_krw / m['fx']
                principal += add_krw
            elif cur == "달러":
                add_usd = st.number_input("입금액 ($)", value=0.0)
                add_val = add_usd
                principal += (add_usd * m['fx'])

            # 여기서 G값(성장)은 사실 숨겨져 있습니다. 
            # (V_new = V_old + 리필액 + G성장분) 인데, 
            # 편의상 리필액만 더하는 구조로 되어있습니다. (순수 VR은 이 부분 로직이 더 복잡함)
            v1 = v_old + add_val 
            v_to_save = v1
            
            if add_val > 0:
                st.info(f"💡 리필액 ${add_val:,.2f}이 V값에 반영되었습니다.")

        # 저장 버튼
        if st.button("💾 이 상태를 구글 시트에 저장"):
            new_data = pd.DataFrame([{
                "Qty": qty, 
                "Pool": pool, 
                "V_old": v_to_save, 
                "Principal": principal,
                "FnG": fng_input
            }])
            conn.update(worksheet="Sheet1", data=new_data)
            st.success("✅ 저장 완료!")

    # 계산 로직
    v_l, v_u = v1 * (1-band_pct), v1 * (1+band_pct)
    ok, qta, msg, m_type = check_safety(m['dd'], fng_input)
    
    # 수익률
    current_asset_usd = (m['price'] * qty) + pool
    current_asset_krw = current_asset_usd * m['fx']
    roi_val_krw = current_asset_krw - principal
    roi_pct = (roi_val_krw / principal) * 100 if principal > 0 else 0

    # --- [메인 대시보드] ---
    st.subheader(f"📈 TQQQ: ${m['price']} (FnG: {int(fng_input)})")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 투입 원금 (KRW)", f"{principal:,.0f}원")
    c2.metric("현재 자산 평가 (KRW)", f"{current_asset_krw:,.0f}원", delta=f"{roi_val_krw:,.0f}원")
    c3.metric("수익률 (ROI)", f"{roi_pct:.2f}%", delta_color="normal")
    
    st.divider()

    tab1, tab2 = st.tabs(["📊 매매 가이드", "📘 로직 설명"])

    telegram_msg = "" 

    with tab1:
        if m_type == "normal": st.success(msg)
        elif m_type == "warning": st.warning(msg)
        else: st.error(msg)
        
        # 텔레그램 리포트 내용
        telegram_msg += f"[VR 5.0 리포트]\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"
        telegram_msg += f"TQQQ: ${m['price']} (FnG: {int(fng_input)})\n"
        telegram_msg += f"상태: {msg}\n"
        telegram_msg += f"밴드폭: {int(band_pct*100)}%\n" # 용어 수정
        telegram_msg += f"수익률: {roi_pct:.2f}% ({roi_val_krw/10000:.0f}만원)\n\n"

        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("현재 평가금", f"${m['price']*qty:,.1f}")
        col_v2.metric("목표 V값", f"${v1:,.1f}")
        col_v3.metric("하단 매수선", f"${v_l:,.1f}")

        st.divider()
        l, r = st.columns(2)
        
        with l:
            st.markdown("#### 📉 매수 (Buy)")
            if m['price']*qty < v_l:
                if ok:
                    st.write(f"✅ 가용 현금 쿼터: {qta*100:.0f}%")
                    telegram_msg += "📉 [매수 추천]\n"
                    for i in range(1, 10):
                        t_q = qty + i
                        p = v_l / t_q
                        if p < m['price'] * 1.05:
                            guide_text = f"LOC 매수: {p:.2f}$ ({t_q}주)"
                            st.code(guide_text)
                            telegram_msg += f"{guide_text}\n"
                else: 
                    st.error("🚫 FnG 위험: 매수 금지")
                    telegram_msg += "🚫 FnG 경고: 매수 금지\n"
            else: 
                st.info("😴 관망 (매수 구간 아님)")
                telegram_msg += "😴 매수 없음 (관망)\n"

        with r:
            st.markdown("#### 📈 매도 (Sell)")
            if m['price']*qty > v_u:
                telegram_msg += "📈 [매도 추천]\n"
                for i in range(1, 5):
                    t_q = qty - i
                    if t_q > 0:
                        p = v1 / t_q
                        if p > m['price']: 
                            guide_text = f"LOC 매도: {p:.2f}$ ({qty-t_q}주 판매)"
                            st.code(guide_text)
                            telegram_msg += f"{guide_text}\n"
            else: 
                st.info("😴 관망 (매도 구간 아님)")
                telegram_msg += "😴 매도 없음 (관망)\n"

        st.divider()
        if st.button("✈️ 텔레그램 전송"):
            send_telegram_msg(telegram_msg)

        fig = go.Figure()
        dr_range = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
        fig.add_trace(go.Scatter(x=dr_range, y=[v_l, v_l], name='매수선(Min)', line=dict(color='red', dash='dash')))
        fig.add_trace(go.Scatter(x=dr_range, y=[v_u, v_u], name='매도선(Max)', line=dict(color='green', dash='dash')))
        fig.add_trace(go.Scatter(x=dr_range, y=[v1, v1], name='목표 V', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=[datetime.now().date()], y=[m['price']*qty], marker=dict(color='orange', size=15), name='현재자산'))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10), template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown("""
        ### 🛡️ VR 5.0 로직
        **1. 밴드폭 (Bandwidth)**
        * V값을 기준으로 위아래 벌어지는 폭을 의미합니다. (이 폭을 뚫어야 매매가 일어남)
        * 평시: 15%, 상승장: 20%, 하락장: 10% 추천
        
        **2. FnG 안전장치**
        * 조정장(-10%~): FnG 15 이하시 매수
        * 하락장(-20%~): FnG 10 이하시 매수
        """)

else:
    st.error("데이터 로드 중... 잠시만 기다려주세요.")
