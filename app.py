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
        # Secrets에서 정보 가져오기 (streamlit/secrets.toml 설정 필요)
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 완료!", icon="✈️")
    except Exception as e:
        st.error(f"텔레그램 전송 실패: Secrets 설정을 확인하세요.\n에러: {e}")

@st.cache_data(ttl=600)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1350.0, "dd": 0.0, "fng": 25.0, "bull": True}
    try:
        # 야후 파이낸스 데이터
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

# VR 5.0 핵심: 하락장/조정장 시 FnG 수치에 따른 쿼터 제한
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

# --- [UI 시작] ---
st.title("🚀 TQQQ VR 5.0 투자 가이드")

with st.expander("🚨 필독: VR 5.0 시작 및 운영 매뉴얼", expanded=False):
    st.markdown("""
    * **최초 시작:** 50% 매수 / 50% 현금 입력. (모드: 최초 시작)
    * **격주 루틴:** 돈 넣는 날은 (Pool+입금액) 합산, 리필란에 입금액 기입. 평소엔 리필 0원.
    * **저장:** 입력 후 [구글 시트에 저장] 필수. (FnG값도 함께 저장됩니다)
    * **알림:** 매매 가이드 확인 후 [텔레그램 전송] 버튼 클릭.
    """)

if m and m["price"] > 0:
    with st.sidebar:
        # 1. 시장 지표
        st.header("⚙️ 시장 지표")
        st.metric("나스닥 낙폭", f"{m['dd']}%")
        st.markdown("[👉 FnG 지수 공식 사이트 (CNN)](https://edition.cnn.com/markets/fear-and-greed)")
        
        # FnG 입력칸
        fng_input = st.number_input("FnG Index", value=float(m['fng']))
        
        st.divider()
        
        # 2. 밴드폭 추천 (10~40% 범위로 수정됨)
        st.subheader("🛠️ 밴드폭 설정")
        rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
        st.info(rec_msg)
        
        # 기본 추천값이 10보다 작거나 40보다 클 경우 조정
        default_band = max(10, min(40, rec_val))
        band_pct = st.slider("밴드 설정 (%)", 10, 40, default_band) / 100
        
        st.divider()
        
        # 3. 자산 데이터 (Google Cloud)
        st.subheader("💾 자산 데이터 관리")
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 기본값 설정
        default_qty, default_pool, default_v, default_principal, default_saved_fng = 100, 2000.0, m['price']*100, 5000.0, 0.0
        
        try:
            # 시트에서 데이터 읽어오기 (E열까지 읽음: A, B, C, D, E)
            existing_data = conn.read(worksheet="Sheet1", usecols=[0, 1, 2, 3, 4], ttl=0).dropna()
            if not existing_data.empty:
                last_row = existing_data.iloc[-1]
                default_qty = int(last_row.iloc[0])
                default_pool = float(last_row.iloc[1])
                default_v = float(last_row.iloc[2])
                if len(last_row) > 3: default_principal = float(last_row.iloc[3])
                if len(last_row) > 4: default_saved_fng = float(last_row.iloc[4]) # 저장된 FnG 불러오기
                
                st.success(f"☁️ 데이터 로드 완료 (Last FnG: {default_saved_fng})")
        except:
            st.warning("⚠️ 신규 시작 또는 시트 포맷 확인 필요")

        mode = st.radio("운용 모드", ["최초 시작", "사이클 업데이트"])
        
        # 입력 필드들
        principal = st.number_input("총 투입 원금 ($)", value=default_principal)
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
            if cur == "원화" and add > 0: principal += (add * m['fx'] / m['fx']) 
            elif add > 0: principal += add

        # 저장 버튼 (E열 FnG 추가)
        if st.button("💾 구글 시트에 저장"):
            new_data = pd.DataFrame([{
                "Qty": qty, 
                "Pool": pool, 
                "V_old": v_to_save, 
                "Principal": principal,
                "FnG": fng_input # FnG 값 저장
            }])
            conn.update(worksheet="Sheet1", data=new_data)
            st.success("✅ 클라우드 저장 완료!")

    # 계산 로직
    v_l, v_u = v1 * (1-band_pct), v1 * (1+band_pct)
    ok, qta, msg, m_type = check_safety(m['dd'], fng_input)
    
    # 수익률 계산
    current_asset = (m['price'] * qty) + pool
    roi_val = current_asset - principal
    roi_pct = (roi_val / principal) * 100 if principal > 0 else 0

    # --- [메인 대시보드] ---
    st.subheader(f"📈 실시간 가이드 (TQQQ: ${m['price']})")
    
    col_roi1, col_roi2, col_roi3 = st.columns(3)
    col_roi1.metric("총 투입 원금", f"${principal:,.0f}")
    col_roi2.metric("현재 총 자산", f"${current_asset:,.0f}", delta=f"{roi_val:,.0f} $")
    col_roi3.metric("누적 수익률 (ROI)", f"{roi_pct:.2f}%", delta_color="normal")
    
    st.divider()

    tab1, tab2 = st.tabs(["📊 메인 대시보드", "📘 안전장치 설명서"])

    telegram_msg = "" 

    with tab1:
        if m_type == "normal": st.success(msg)
        elif m_type == "warning": st.warning(msg)
        else: st.error(msg)
        
        # 텔레그램 리포트 내용 작성
        telegram_msg += f"[VR 5.0 리포트]\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"
        telegram_msg += f"TQQQ: ${m['price']} (FnG: {int(fng_input)})\n"
        telegram_msg += f"상태: {msg}\n"
        telegram_msg += f"밴드폭: {int(band_pct*100)}%\n"
        telegram_msg += f"수익률: {roi_pct:.2f}% (${roi_val:.0f})\n\n"

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
                    telegram_msg += "📉 [매수 추천]\n"
                    for i in range(1, 10):
                        t_q = qty + i
                        p = v_l / t_q
                        if p < m['price'] * 1.05:
                            guide_text = f"LOC 매수: {p:.2f}$ ({t_q}주)"
                            st.code(guide_text)
                            telegram_msg += f"{guide_text}\n"
                else: 
                    st.error("🚫 FnG 안전장치 작동: 매수 금지")
                    telegram_msg += "🚫 FnG 경고: 매수 금지\n"
            else: 
                st.success("✅ 관망 (현금 보유)")
                telegram_msg += "😴 매수 없음 (관망)\n"

        with r:
            st.markdown("#### 📈 매도 가이드")
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
                st.success("✅ 관망 (주식 보유)")
                telegram_msg += "😴 매도 없음 (관망)\n"

        st.divider()
        # 텔레그램 전송 버튼
        if st.button("✈️ 텔레그램으로 이 리포트 전송하기"):
            send_telegram_msg(telegram_msg)

        # 그래프
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
        st.markdown("""
        #### 1. 🚦 상황별 밴드폭 (Bull/Bear)
        * **🟩 상승장 (20%):** 나스닥 -10% 이내 & 200일선 위
        * **🟧 조정장 (15%):** 나스닥 -10% ~ -20%
        * **🟥 하락장 (10%):** 나스닥 -20% 이하
        * *사용자 설정 가능 범위: 10% ~ 40%*
        
        #### 2. 💰 현금 쿼터(Quota)
        * **경고:** (-10%~-20%) 현금 50% 사용 (FnG 15 이하)
        * **위험:** (-20% 이하) 현금 30% 사용 (FnG 10 이하)
        """)

else:
    st.error("데이터 로드 중... 잠시만 기다려주세요.")
