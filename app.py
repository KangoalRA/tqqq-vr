import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 기본 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Pool", layout="wide")

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
            st.warning("텔레그램 설정이 없습니다.")
    except Exception as e:
        st.error(f"텔레그램 오류: {e}")

# 데이터 가져오기 (가격, 환율만)
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 0.0, "fx": 1400.0, "error": None}
    try:
        # TQQQ
        t_hist = yf.Ticker("TQQQ").history(period="1d")
        if not t_hist.empty: 
            data["price"] = round(t_hist['Close'].iloc[-1], 2)
        else:
            data["error"] = "TQQQ 로드 실패"
        
        # 환율
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: 
            data["fx"] = round(fx_hist['Close'].iloc[-1], 2)
            
        return data
    except Exception as e: 
        data["error"] = str(e)
        return data

m = get_market_data()

# --- [UI 타이틀] ---
st.title("🌊 TQQQ VR 5.0 (Pool Growth)")

if m["price"] == 0 or m["error"]:
    st.warning(f"⚠️ 데이터 로드 실패. 수동 입력 필요.")

# --- [사이드바: 핵심 변수만 남김] ---
with st.sidebar:
    st.header("⚙️ 전략 컨트롤")
    
    # 1. 투자 성향
    invest_type = st.radio("투자 성향", ["적립식 (Limit 75%)", "거치식 (Limit 50%)"])
    pool_cap_ratio = 0.75 if "적립식" in invest_type else 0.50
    
    st.divider()

    # 2. VR 변수 (G, Band)
    c1, c2 = st.columns(2)
    with c1:
        g_factor = st.number_input("G값 (나누기)", value=10, min_value=1, help="Pool / G 만큼 V가 성장")
    with c2:
        band_val = st.number_input("밴드폭 (%)", value=15, min_value=5)
        band_pct = band_val / 100.0

    st.divider()

    # 3. 시장 데이터 (수동 보정)
    st.subheader("📝 현재 데이터")
    price_val = m["price"] if m["price"] > 0 else 0.0
    current_price = st.number_input("TQQQ 현재가 ($)", value=price_val, format="%.2f")
    fx_val = st.number_input("환율 (원/$)", value=m["fx"])
    
    st.divider()
    
    # 4. 자산 데이터 로드
    st.subheader("📂 히스토리")
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    df = pd.DataFrame()
    # 기본값 설정
    default_qty, default_pool, default_v, default_principal = 0, 0.0, 0.0, 0.0
    last_date = "기록 없음"

    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            # 마지막 기록 불러오기
            last_row = df.iloc[-1]
            try: default_qty = int(str(last_row["Qty"]).replace(',',''))
            except: pass
            try: default_pool = float(str(last_row["Pool"]).replace(',',''))
            except: pass
            try: default_v = float(str(last_row["V_old"]).replace(',',''))
            except: pass
            try: default_principal = float(str(last_row["Principal"]).replace(',',''))
            except: pass
            try: last_date = str(last_row["Date"])
            except: pass
            
            st.success(f"✅ 로드 완료 ({last_date})")
        else:
            st.info("ℹ️ 신규 시작")
    except Exception as e:
        st.warning(f"⚠️ 시트 연결 대기중")

    # 모드 선택
    mode = st.radio("작업 선택", ["사이클 갱신 (2주 1회)", "초기 세팅"])
    
    # 입력 폼
    qty = st.number_input("보유 수량 (주)", value=default_qty)
    pool = st.number_input("현금 Pool ($)", value=default_pool)

    # --- [계산 로직] ---
    v_final = 0.0
    principal_final = default_principal
    growth_amt = 0.0
    
    if mode == "초기 세팅":
        principal_final = st.number_input("총 투입 원금 ($)", value=default_principal)
        if current_price > 0:
            v_final = current_price * qty # 초기 V는 현재 평가금
            
    else: # 사이클 갱신
        v_old = default_v
        st.markdown(f":gray[이전 V: ${v_old:,.0f}]")
        
        # 적립금 입력
        cur_type = st.radio("추가 입금", ["없음", "원화", "달러"], horizontal=True)
        add_val = 0.0
        
        if cur_type == "원화":
            add_krw = st.number_input("입금액 (KRW)", value=0)
            if fx_val > 0:
                add_val = add_krw / fx_val
                principal_final += add_val
        elif cur_type == "달러":
            add_usd = st.number_input("입금액 (USD)", value=0.0)
            add_val = add_usd
            principal_final += add_usd
        
        # [핵심] V값 성장 로직 (Pool / G)
        if pool > 0:
            growth_amt = pool / g_factor
        
        v_final = v_old + growth_amt + add_val
        
        if growth_amt > 0:
            st.info(f"📈 성장: +${growth_amt:,.2f}")

    # 저장 버튼
    if st.button("💾 기록 저장 (Save)"):
        # 저장할 데이터 (Price 열 추가됨)
        new_data = {
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty,
            "Pool": pool,
            "V_old": v_final, # 이번에 확정된 V
            "Principal": principal_final,
            "Price": current_price, # 차트용 주가 저장
            "Band": band_val # 차트용 밴드 저장
        }
        
        new_row = pd.DataFrame([new_data])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        final_df = final_df.fillna(0)
        
        conn.update(worksheet="Sheet1", data=final_df)
        st.success("✅ 저장되었습니다.")
        st.rerun()

# --- [메인 화면] ---
if current_price <= 0:
    st.error("👈 왼쪽 사이드바에서 현재가를 확인해주세요.")
    st.stop()

# 현재 상태 계산
curr_eval = current_price * qty
curr_total_usd = curr_eval + pool
roi_val = curr_total_usd - principal_final
roi_pct = (roi_val / principal_final * 100) if principal_final > 0 else 0

# 상단 메트릭
c1, c2, c3, c4 = st.columns(4)
c1.metric("New 목표값 (V)", f"${v_final:,.0f}", delta=f"+${growth_amt:,.0f} (성장)")
c2.metric("총 자산", f"${curr_total_usd:,.0f}")
c3.metric("현재 Pool", f"${pool:,.0f}")
c4.metric("수익률", f"{roi_pct:.2f}%", delta_color="normal")

st.divider()

# 탭 구성
tab1, tab2 = st.tabs(["📢 매매 가이드", "📈 히스토리 차트"])

with tab1:
    report_lines = []
    report_lines.append(f"🌊 VR 5.0 가이드 ({datetime.now().strftime('%m/%d')})")
    report_lines.append(f"TQQQ: ${current_price} / V: ${v_final:,.0f}")
    report_lines.append(f"Pool Limit: {int(pool_cap_ratio*100)}% (${pool*pool_cap_ratio:,.0f})")
    
    col_buy, col_sell = st.columns(2)
    
    # [매수] LOC 그물망
    with col_buy:
        st.subheader("🔵 매수 (LOC)")
        limit_amt = pool * pool_cap_ratio
        
        if limit_amt < 10:
            st.warning("매수 가능 Pool이 부족합니다.")
        else:
            st.write(f"가용예산: ${limit_amt:,.0f}")
            # 테이블 헤더
            st.markdown("""
            | 구분 | 가격 (LOC) | 수량 | 금액 |
            | :--- | :--- | :--- | :--- |
            """)
            
            # -2% 간격 5분할
            steps = [0.98, 0.96, 0.94, 0.92, 0.90]
            used = 0
            
            for i, rate in enumerate(steps):
                p_loc = current_price * rate
                # 예산 균등 분배 (최소 1주)
                q_loc = int((limit_amt / 5) / p_loc)
                if q_loc < 1: q_loc = 1
                
                cost = p_loc * q_loc
                if used + cost <= limit_amt:
                    st.markdown(f"| LOC {i+1} | **${p_loc:.2f}** | {q_loc}주 | ${cost:.0f} |")
                    report_lines.append(f"매수 LOC: ${p_loc:.2f} ({q_loc}주)")
                    used += cost
                else:
                    break

    # [매도] 밴드 리밸런싱
    with col_sell:
        st.subheader("🔴 매도 (지정가)")
        v_upper = v_final * (1 + band_pct)
        
        # 현재가 vs 밴드 상단 비교
        if qty > 0:
            target_price = v_upper / qty # (V * 1.15) / Qty 가 아니라, 평가금이 V*1.15가 되는 주가
            # 정확히는: Price * Qty = V * 1.15 => Price = (V * 1.15) / Qty
            
            st.markdown(f"**밴드 상단(기준):** :red[${target_price:.2f}]")
            
            if current_price >= target_price:
                # 밴드 돌파 -> 즉시 리밸런싱
                # 목표: 평가금을 V로 맞춤 (혹은 V*1.05 등 성향따라 다르나 기본은 초과분 컷)
                # 여기서는 '밴드 안쪽으로 밀어넣기' 위해 초과분 매도
                excess = (current_price * qty) - v_final
                sell_q = int(excess / current_price)
                if sell_q > 0:
                    st.error(f"🚨 **즉시 매도 신호**")
                    st.write(f"초과분(${excess:,.0f}) 정리 필요")
                    st.code(f"매도: {sell_q}주 (현재가)")
                    report_lines.append(f"🚨 매도 신호: {sell_q}주 (즉시)")
            else:
                # 예약 매도
                # 목표가에 도달했을 때 팔아야 할 수량 (V값 유지 가정)
                # (Target * Q) - V = Excess
                excess_at_target = v_upper - v_final
                sell_q_at_target = int(excess_at_target / target_price)
                
                st.success("✅ 밴드 내부 (관망)")
                st.markdown(f"""
                | 구분 | 목표가 | 예상매도 |
                | :--- | :--- | :--- |
                | 밴드상단 | **${target_price:.2f}** | {sell_q_at_target}주 |
                """)
                report_lines.append(f"매도 예약: ${target_price:.2f} ({sell_q_at_target}주)")
        else:
            st.info("보유 주식이 없습니다.")

    st.write("")
    if st.button("텔레그램 전송", type="primary"):
        send_telegram_msg("\n".join(report_lines))

with tab2:
    # --- [차트 로직 개선] ---
    # 히스토리 데이터가 있어야 그림
    if not df.empty and "Date" in df.columns and "V_old" in df.columns:
        
        # 데이터 전처리
        plot_df = df.copy()
        plot_df['Date'] = pd.to_datetime(plot_df['Date'])
        plot_df = plot_df.sort_values('Date')
        
        # 'Price' 컬럼이 없으면(옛날 데이터) 0으로 처리하거나 추정해야 함
        if "Price" not in plot_df.columns:
            plot_df["Price"] = 0
        if "Band" not in plot_df.columns:
            plot_df["Band"] = 15 # 기본값
            
        # V 밴드 계산 (History)
        plot_df["V_High"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
        plot_df["V_Low"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
        plot_df["My_Eval"] = plot_df["Qty"] * plot_df["Price"] # 당시 평가금
        
        # 현재 시점 데이터 추가 (프로젝션)
        current_row = {
            "Date": datetime.now(),
            "V_old": v_final,
            "V_High": v_final * (1 + band_pct),
            "V_Low": v_final * (1 - band_pct),
            "My_Eval": current_price * qty
        }
        # 데이터프레임 합치기 (시각화용)
        # pd.concat 대신 리스트로 추가하여 DataFrame 생성 (FutureWarning 방지)
        proj_df = pd.DataFrame([current_row])
        chart_df = pd.concat([plot_df, proj_df], ignore_index=True)
        
        fig = go.Figure()

        # 1. 밴드 영역 (채우기)
        # V_High 라인
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_High'],
            mode='lines', line=dict(width=0),
            showlegend=False, hoverinfo='skip'
        ))
        # V_Low 라인 (High와 채우기)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_Low'],
            mode='lines', line=dict(width=0),
            fill='tonexty', fillcolor='rgba(0, 100, 255, 0.1)', # 파란색 반투명
            name='Band 영역'
        ))

        # 2. V값 (중심선) - 계단식(hv)이 더 어울릴 수 있음
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_old'],
            mode='lines+markers', line=dict(color='blue', width=2, shape='hv'),
            name='목표값(V)'
        ))

        # 3. 내 평가금 (자산)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['My_Eval'],
            mode='lines+markers', line=dict(color='green', width=2),
            marker=dict(size=8),
            name='내 주식가치(E)'
        ))

        fig.update_layout(
            title="자산 성장 흐름 (V vs Evaluation)",
            height=500,
            hovermode="x unified",
            xaxis_title="Date",
            yaxis_title="Value ($)"
        )
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.info("데이터가 쌓이면 이곳에 누적 차트가 표시됩니다.")
