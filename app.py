import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 기본 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Pool Ver", layout="wide")

# 텔레그램 메시지 전송
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": msg}
            requests.post(url, data=data)
            st.toast("✅ 텔레그램 전송 성공!", icon="✈️")
        else:
            st.warning("텔레그램 설정이 없습니다. (secrets.toml 확인)")
    except Exception as e:
        st.error(f"텔레그램 전송 오류: {e}")

# 데이터 가져오기
@st.cache_data(ttl=300)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1400.0, "dd": 0.0, "fng": 50.0, "error": None}
    try:
        # TQQQ 가격
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        if not t_hist.empty: 
            data["price"] = round(t_hist['Close'].iloc[-1], 2)
        else:
            data["error"] = "TQQQ 데이터 로드 실패"
        
        # 나스닥 DD (참고용으로 유지)
        n_hist = yf.Ticker("^NDX").history(period="2y")
        if not n_hist.empty:
            ndx_high = n_hist['Close'].max()
            curr_ndx = n_hist['Close'].iloc[-1]
            data["dd"] = round((curr_ndx / ndx_high - 1) * 100, 2)
        
        # 환율
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: 
            data["fx"] = round(fx_hist['Close'].iloc[-1], 2)

        # 공포지수 (참고용으로 유지)
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/static/history", headers=headers, timeout=3)
            if r.status_code == 200: 
                data["fng"] = float(r.json()['fear_and_greed']['score'])
        except: pass
        
        return data
    except Exception as e: 
        data["error"] = str(e)
        return data

m = get_market_intelligence()

# --- [UI 타이틀] ---
st.title("🌊 TQQQ VR 5.0 (Pool Version)")

if m["price"] == 0 or m["error"]:
    st.warning(f"⚠️ 시장 데이터 로드 실패 ({m.get('error')}). 수동 입력을 사용하세요.")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("⚙️ 전략 설정")
    
    # 투자 성향 (Pool 한도 결정)
    invest_type = st.radio("투자 성향 (Pool 사용 한도)", ["적립식 (월급형, 75%)", "거치식 (목돈형, 50%)"])
    pool_cap_ratio = 0.75 if "적립식" in invest_type else 0.50
    
    st.divider()

    # G값
    g_factor = st.number_input("G값 (나누기 변수)", value=10, min_value=1, help="기본값 10. Pool을 이 값으로 나눈 만큼 V가 성장함.")

    st.divider()

    # 시장 데이터 수동 입력
    st.subheader("📝 시장 데이터 (수동)")
    price_val = m["price"] if m["price"] > 0 else 0.0
    current_price = st.number_input("TQQQ 현재가 ($)", value=price_val, format="%.2f")
    
    # 참고용 지표 (로직엔 영향 X)
    mdd_val = st.number_input("나스닥 MDD (%)", value=m["dd"], format="%.2f")
    fng_val = st.number_input("FnG 지수", value=float(m["fng"]))
    fx_val = st.number_input("환율 (원/$)", value=m["fx"])
    
    m["price"] = current_price
    m["fx"] = fx_val

    st.divider()
    
    # 구글 시트 로드
    st.subheader("📂 자산 데이터")
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    df = pd.DataFrame()
    default_qty, default_pool, default_v, default_principal = 100, 2000.0, m["price"]*100, 5000.0
    last_date = "없음"

    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty and len(df.columns) >= 4:
            last_row = df.iloc[-1]
            try: default_qty = int(float(str(last_row.iloc[0]).replace(',','')))
            except: pass
            try: default_pool = float(str(last_row.iloc[1]).replace(',',''))
            except: pass
            try: default_v = float(str(last_row.iloc[2]).replace(',',''))
            except: pass
            try: default_principal = float(str(last_row.iloc[3]).replace(',',''))
            except: pass
            if len(df.columns) > 4: last_date = str(last_row.iloc[4])
            st.success(f"✅ 로드됨 ({last_date})")
        else:
            st.info("ℹ️ 데이터 없음 (신규)")
    except:
        st.warning("⚠️ 시트 연결 실패")

    mode = st.radio("모드 선택", ["사이클 업데이트 (2주 1회)", "최초 시작"])
    
    qty = st.number_input("보유 수량 (주)", value=default_qty, min_value=0)
    pool = st.number_input("현금 Pool ($)", value=default_pool)

    # --- [핵심 계산 로직: VR 5.0 Pool형] ---
    v_final = 0.0
    principal_final = default_principal
    
    if mode == "최초 시작":
        principal_final = st.number_input("총 투입 원금 ($)", value=default_principal)
        if current_price > 0:
            v_final = current_price * qty
        else:
            v_final = 0
            
    else: # 사이클 업데이트
        v_old = default_v
        st.markdown(f"**직전 V: ${v_old:,.2f}**")
        
        # 적립금 추가
        cur = st.radio("적립금 리필", ["없음", "원화", "달러"], horizontal=True)
        add_val = 0.0
        if cur == "원화":
            add_krw = st.number_input("입금액 (원)", value=0)
            add_val = add_krw / fx_val if fx_val > 0 else 0
            principal_final += (add_krw / fx_val) # 원금 $환산 합산
        elif cur == "달러":
            add_usd = st.number_input("입금액 ($)", value=0.0)
            add_val = add_usd
            principal_final += add_usd
        
        # [NEW] 성장 로직: V_new = V_old + (Pool / G) + 적립금
        growth_amt = 0.0
        if pool > 0:
            growth_amt = pool / g_factor
        
        v_final = v_old + growth_amt + add_val
        st.info(f"📈 성장분(Pool/{g_factor}): +${growth_amt:.2f}")

    # 저장 버튼
    if st.button("💾 시트 저장"):
        new_row = pd.DataFrame([{
            "Qty": qty, "Pool": pool, "V_old": v_final, 
            "Principal": principal_final, 
            "Date": datetime.now().strftime('%Y-%m-%d'), 
            "FnG": fng_val
        }])
        
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        final_df = final_df.fillna("")
        conn.update(worksheet="Sheet1", data=final_df)
        st.success("✅ 저장 완료!")
        st.rerun()

# --- [메인 화면] ---
if current_price <= 0:
    st.error("👈 사이드바에서 현재가를 입력해주세요.")
    st.stop()

# 자산 현황 계산
curr_eval = current_price * qty
curr_total_usd = curr_eval + pool
curr_total_krw = curr_total_usd * fx_val
roi_val_usd = curr_total_usd - principal_final
roi_pct = (roi_val_usd / principal_final * 100) if principal_final > 0 else 0

st.subheader(f"📊 자산 현황 (TQQQ ${current_price})")
c1, c2, c3, c4 = st.columns(4)
c1.metric("목표값 (V)", f"${v_final:,.0f}")
c2.metric("총 자산 (현금포함)", f"${curr_total_usd:,.0f}")
c3.metric("현재 Pool", f"${pool:,.0f}")
c4.metric("수익률", f"{roi_pct:.2f}%")

st.divider()

# 탭 구성
tab1, tab2 = st.tabs(["📢 매매 가이드 (LOC/지정가)", "📈 차트"])

with tab1:
    # 텔레그램 전송용 텍스트 빌더
    report_lines = []
    report_lines.append(f"🌊 VR 5.0 (Pool) 가이드")
    report_lines.append(f"TQQQ: ${current_price} / V: ${v_final:,.0f}")
    report_lines.append(f"성향: {invest_type} (Limit {int(pool_cap_ratio*100)}%)")
    
    col_buy, col_sell = st.columns(2)
    
    # --- [매수 로직: LOC 그물망] ---
    with col_buy:
        st.markdown("#### 🔵 매수 (LOC 주문)")
        st.caption("주가가 떨어질 때 체결되도록 그물을 칩니다.")
        
        # Pool 한도 계산
        max_pool_use = pool * pool_cap_ratio
        st.markdown(f"**가용 Pool 한도:** :blue[${max_pool_use:,.0f}]")
        
        # LOC 테이블 생성 (현재가 기준 -2% 씩 5단계 or 한도까지)
        st.markdown("| 종류 | 가격 (LOC) | 수량 | 금액 |")
        st.markdown("|---|---|---|---|")
        
        used_pool = 0.0
        # 예시: 현재가에서 -1.5% 간격으로 촘촘하게
        steps = [0.985, 0.97, 0.955, 0.94, 0.925] 
        
        for i, factor in enumerate(steps):
            buy_price = current_price * factor
            # 1회 주문 금액 (대략 Pool 한도의 1/N 등분 혹은 1주씩)
            # 여기서는 간단하게 1주씩 혹은 금액 비례로 설정 가능. 
            # 매뉴얼상 '촘촘하게'이므로 1주~2주 단위로 제안
            buy_qty = max(1, int((max_pool_use / 5) / buy_price)) # 한도를 5분할해서 투입
            
            cost = buy_price * buy_qty
            
            if used_pool + cost <= max_pool_use:
                line = f"| LOC {i+1}차 | ${buy_price:.2f} | {buy_qty}주 | ${cost:.0f} |"
                st.markdown(line)
                report_lines.append(f"매수 LOC: ${buy_price:.2f} ({buy_qty}주)")
                used_pool += cost
            else:
                break
        
        st.markdown(f"**총 투입 예정:** ${used_pool:,.0f} / (잔여 한도 ${max_pool_use - used_pool:,.0f})")

    # --- [매도 로직: 지정가 목표] ---
    with col_sell:
        st.markdown("#### 🔴 매도 (지정가 주문)")
        st.caption("자산이 V를 초과하는 구간에 미리 걸어둡니다.")
        
        # 목표 구간별 필요 주가 계산
        # 총자산(Price*Qty + Pool) >= V * Target_Ratio
        # Price * Qty >= (V * Target_Ratio) - Pool
        # Price >= ((V * Target_Ratio) - Pool) / Qty
        
        targets = [1.05, 1.15, 1.25]
        labels = ["1차 (5%↑)", "2차 (15%↑)", "졸업 (25%↑)"]
        
        st.markdown("| 단계 | 목표가 (지정가) | 실행 |")
        st.markdown("|---|---|---|")
        
        sell_msg_added = False
        
        for t, lbl in zip(targets, labels):
            target_asset = v_final * t
            
            # (목표자산 - 현재풀) / 수량 = 목표주가
            if qty > 0:
                target_price = (target_asset - pool) / qty
                
                # 이미 목표 달성했는지 체크
                is_reached = "✅ 도달" if curr_total_usd >= target_asset else ""
                if is_reached:
                    act_msg = "**지금 즉시 매도**"
                else:
                    act_msg = "예약 매도"

                st.markdown(f"| {lbl} | **${target_price:.2f}** | {is_reached} |")
                
                if curr_total_usd < target_asset:
                    report_lines.append(f"매도 예약({lbl}): ${target_price:.2f}")
                else:
                    report_lines.append(f"🚨 매도 신호({lbl}): 현재가(${current_price}) > 목표가(${target_price:.2f})")
                    sell_msg_added = True
            else:
                st.write("보유 수량 0주")

    # 텔레그램 버튼
    st.write("")
    if st.button("✈️ 텔레그램으로 가이드 전송"):
        full_msg = "\n".join(report_lines)
        send_telegram_msg(full_msg)

with tab2:
    fig = go.Figure()
    # 차트에는 V값과 밴드구간(매도구간)을 시각화
    dates = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
    
    # 1.05배, 1.15배 라인
    v_105 = v_final * 1.05
    v_115 = v_final * 1.15
    
    fig.add_trace(go.Scatter(x=dates, y=[v_final, v_final], name="V (기준선)", line=dict(color='blue', width=2)))
    fig.add_trace(go.Scatter(x=dates, y=[v_105, v_105], name="매도 1차(105%)", line=dict(color='orange', dash='dot')))
    fig.add_trace(go.Scatter(x=dates, y=[v_115, v_115], name="매도 2차(115%)", line=dict(color='red', dash='dot')))
    
    # 내 자산 점 찍기
    fig.add_trace(go.Scatter(x=[dates[0]], y=[curr_total_usd], name="내 총자산", marker=dict(size=14, color='green', symbol='star')))
    
    fig.update_layout(title="V값 vs 내 자산 위치", height=400)
    st.plotly_chart(fig, use_container_width=True)
