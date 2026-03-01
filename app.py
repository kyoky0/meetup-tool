import streamlit as st
import time
import json
import re
import os
import csv
import io
import base64
from pathlib import Path

st.set_page_config(
    page_title="名刺会メモ",
    page_icon="🤝",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ===== GLOBAL CSS =====
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

div[data-testid="stButton"] button {
    height: 72px; font-size: 20px; font-weight: 600;
    border-radius: 14px; transition: all 0.2s;
}
div[data-testid="stButton"] button[kind="primary"] {
    font-size: 22px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
    opacity: 0.9; transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(102,126,234,0.4);
}

.app-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 1.4rem 1.5rem; border-radius: 18px;
    text-align: center; margin-bottom: 1.4rem;
    box-shadow: 0 8px 32px rgba(102,126,234,0.3);
}
.app-header h2 { margin: 0 0 0.3rem 0; font-size: 1.7rem; letter-spacing: -0.5px; }
.app-header p  { margin: 0; font-size: 0.85rem; opacity: 0.8; }

.timer-wrap {
    background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
    border-radius: 20px; padding: 1.6rem 1rem;
    text-align: center; margin-bottom: 1rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
.timer-label { font-size: 0.75rem; color: #a0aec0; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 0.4rem; }
.timer-value { font-size: 64px; font-weight: 700; font-family: monospace; color: white; line-height: 1; }

.person-badge {
    background: linear-gradient(135deg, #667eea22, #764ba222);
    border: 2px solid #667eea55; border-radius: 50px;
    padding: 12px 24px; text-align: center;
    font-size: 18px; font-weight: 700; color: #4c51bf;
    margin-bottom: 1rem;
}

.done-log {
    background: #f0fff4; border-left: 3px solid #48bb78;
    padding: 8px 14px; border-radius: 0 10px 10px 0;
    margin: 4px 0; font-size: 0.85rem; color: #276749;
}

.info-banner {
    background: #ebf8ff; border: 1px solid #bee3f8; border-radius: 12px;
    padding: 12px 16px; color: #2b6cb0; font-size: 0.88rem;
    margin-bottom: 1rem; line-height: 1.6;
}

.person-card {
    background: white; border-radius: 16px; padding: 18px 20px;
    margin: 10px 0; border: 1px solid #e8ecf0;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s;
}
.person-card:hover { box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
.card-top { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.card-num {
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white; width: 34px; height: 34px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.9rem; flex-shrink: 0;
}
.card-name { font-size: 1.05rem; font-weight: 700; color: #1a202c; }
.card-company {
    font-size: 0.78rem; background: #edf2f7; color: #4a5568;
    padding: 2px 10px; border-radius: 20px; font-weight: 500;
}
.card-email {
    font-size: 0.78rem; background: #e6fffa; color: #2c7a7b;
    padding: 2px 10px; border-radius: 20px; font-weight: 500;
}
.card-summary { color: #4a5568; font-size: 0.9rem; line-height: 1.65; margin: 0; }

div[data-testid="stDownloadButton"] button {
    height: 56px; font-size: 17px; border-radius: 12px;
    background: #f7fafc; color: #2d3748; border: 2px solid #e2e8f0;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ===== 定数 =====
GROQ_TEXT_MODEL   = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
GROQ_AUDIO_MODEL  = "whisper-large-v3"
SAVE_FILE         = Path(__file__).parent / "meetup_session.json"
MEDIA_TYPES       = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
}

# ===== API キー =====
def get_groq_key() -> str:
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.getenv("GROQ_API_KEY", "")

# ===== 永続化 =====
def save_results(results: list) -> None:
    SAVE_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2))

def load_results() -> list:
    if SAVE_FILE.exists():
        try:
            return json.loads(SAVE_FILE.read_text())
        except Exception:
            return []
    return []

# ===== SESSION STATE =====
defaults: dict = {
    "phase":         "idle",  # idle | active | done
    "person_idx":    0,
    "session_start": None,
    "results":       None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.results is None:
    st.session_state.results = load_results()

# ===== Groq ヘルパー =====
def get_groq_client():
    from groq import Groq
    return Groq(api_key=get_groq_key())

def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    client = get_groq_client()
    resp = client.audio.transcriptions.create(
        file=(filename, io.BytesIO(audio_bytes)),
        model=GROQ_AUDIO_MODEL, language="ja", response_format="json",
    )
    return resp.text.strip()

def call_llm(messages: list, max_tokens: int = 500, max_retries: int = 3) -> str:
    client = get_groq_client()
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_TEXT_MODEL, max_tokens=max_tokens, messages=messages,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

def analyze_single(transcript: str) -> dict:
    raw = call_llm([{"role": "user", "content": (
        f"名刺交換会での会話。\n<会話>\n{transcript}\n</会話>\n\n"
        'JSONのみで返してください: {"name": "名前または不明", "summary": "要約2〜3文"}'
    )}])
    match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return {"name": data.get("name", "不明"), "summary": data.get("summary", raw)}
        except Exception:
            pass
    return {"name": "不明", "summary": raw}

def ocr_business_card(image_bytes: bytes, media_type: str) -> dict:
    client = get_groq_client()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    resp = client.chat.completions.create(
        model=GROQ_VISION_MODEL, max_tokens=300,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
            {"type": "text", "text": (
                "この名刺から以下をJSONのみで抽出してください:\n"
                '{"name":"氏名","company":"会社名","title":"役職","email":"メール","phone":"電話番号"}\n'
                "読み取れない項目はnullにしてください。"
            )},
        ]}],
    )
    raw = resp.choices[0].message.content.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            return {}
    return {}

def process_person(audio_file, person_idx: int) -> None:
    """音声を文字起こし→解析→results に追加"""
    person_num = person_idx + 1
    with st.spinner(f"🔄 {person_num} 人目を処理中... （10〜30秒）"):
        try:
            audio_bytes = audio_file.getvalue()
            filename = getattr(audio_file, "name", f"person_{person_num}.webm")
            transcript = transcribe_audio(audio_bytes, filename)
            if transcript:
                result = analyze_single(transcript)
                name    = result["name"]
                summary = result["summary"]
            else:
                name = "（不明）"
                summary = "（音声なし）"
                transcript = ""
        except Exception as e:
            name = "（エラー）"
            summary = f"処理失敗: {e}"
            transcript = ""

    st.session_state.results.append({
        "番号": person_num,
        "名前": name,
        "会社名": "", "役職": "", "メール": "", "電話": "",
        "会話要約": summary,
        "文字起こし": transcript,
    })
    save_results(st.session_state.results)

# ===== API キーチェック =====
if not get_groq_key():
    st.error("⚠️ GROQ_API_KEY が設定されていません。Streamlit Cloud の Secrets に追加してください。")
    st.stop()

# ===== HEADER =====
st.markdown("""
<div class="app-header">
  <h2>🤝 名刺会メモ</h2>
  <p>会話を録音 → その場で自動テキスト化</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📍 録音", "📋 結果"])

# ============================================================
# TAB 1: 録音
# ============================================================
with tab1:
    phase = st.session_state.phase

    # ---- IDLE ----
    if phase == "idle":
        if st.session_state.results:
            st.success(f"✅ 前回のセッション: {len(st.session_state.results)} 人分保存済み → 「結果」タブを確認")

        st.markdown("""
        <div class="info-banner">
            📱 アプリで直接録音できます。<br>
            「録音開始」→ マイクボタンで録音開始 → 停止後「次の人へ」でその場で解析。
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ 録音開始", use_container_width=True, type="primary"):
                st.session_state.update({
                    "phase": "active",
                    "person_idx": 0,
                    "session_start": time.time(),
                    "results": [],
                })
                if SAVE_FILE.exists():
                    SAVE_FILE.unlink()
                st.rerun()
        with col2:
            if st.button("🗑️ リセット", use_container_width=True):
                st.session_state.update({
                    "phase": "idle", "person_idx": 0,
                    "session_start": None, "results": [],
                })
                if SAVE_FILE.exists():
                    SAVE_FILE.unlink()
                st.rerun()

    # ---- ACTIVE ----
    elif phase == "active":
        elapsed = time.time() - st.session_state.session_start
        mins, secs = divmod(int(elapsed), 60)
        person_num = st.session_state.person_idx + 1

        st.markdown(f"""
        <div class="timer-wrap">
          <div class="timer-label">経 過 時 間</div>
          <div class="timer-value">{mins:02d}:{secs:02d}</div>
        </div>
        <div class="person-badge">👤 {person_num} 人目を録音中</div>
        """, unsafe_allow_html=True)

        audio = st.audio_input(
            "マイクボタンで録音 → 停止後にボタンが有効になります",
            key=f"audio_{st.session_state.person_idx}",
        )

        if audio:
            col1, col2 = st.columns(2)
            with col1:
                if st.button(
                    f"✂️ 次の人へ　→　{person_num + 1} 人目",
                    use_container_width=True, type="primary",
                ):
                    process_person(audio, st.session_state.person_idx)
                    st.session_state.person_idx += 1
                    st.rerun()
            with col2:
                if st.button("⏹️ 録音終了", use_container_width=True):
                    process_person(audio, st.session_state.person_idx)
                    st.session_state.phase = "done"
                    st.rerun()
        else:
            st.caption("👆 マイクボタンを押して録音を開始してください")
            if st.button("⏹️ セッション終了（音声なし）", use_container_width=True):
                st.session_state.phase = "done"
                st.rerun()

        # 処理済みミニカード（新しい順）
        if st.session_state.results:
            st.divider()
            st.caption(f"✅ 処理済み: {len(st.session_state.results)} 人")
            for r in reversed(st.session_state.results):
                short = r["会話要約"][:55] + "…" if len(r["会話要約"]) > 55 else r["会話要約"]
                st.markdown(
                    f'<div class="done-log">👤 {r["番号"]}人目 : <b>{r["名前"]}</b> — {short}</div>',
                    unsafe_allow_html=True,
                )

    # ---- DONE ----
    elif phase == "done":
        st.success(f"🎉 完了！{len(st.session_state.results)} 人分の記録が完成しました")
        st.info("「結果」タブで詳細確認・CSV ダウンロードができます")

        if st.button("🔄 新しいセッションを開始", use_container_width=True, type="primary"):
            st.session_state.update({
                "phase": "idle", "person_idx": 0,
                "session_start": None, "results": [],
            })
            if SAVE_FILE.exists():
                SAVE_FILE.unlink()
            st.rerun()

# ============================================================
# TAB 2: 結果
# ============================================================
with tab2:
    if not st.session_state.results:
        st.info("📍 録音タブで会話を記録すると、ここに結果が表示されます")
    else:
        st.subheader(f"📋 会話一覧　{len(st.session_state.results)} 人")

        for idx, row in enumerate(st.session_state.results):
            has_card = bool(row.get("会社名") or row.get("メール"))
            company_badge = f'<span class="card-company">🏢 {row["会社名"]}</span>' if row.get("会社名") else ""
            email_badge   = f'<span class="card-email">✉️ {row["メール"]}</span>'   if row.get("メール")  else ""

            st.markdown(f"""
            <div class="person-card">
              <div class="card-top">
                <span class="card-num">{row['番号']}</span>
                <span class="card-name">{row['名前']}</span>
                {company_badge}{email_badge}
              </div>
              <p class="card-summary">{row['会話要約']}</p>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("📎 詳細・名刺 OCR"):
                if has_card:
                    for field, label in [("会社名","会社"), ("役職","役職"), ("メール","メール"), ("電話","電話")]:
                        if row.get(field):
                            st.write(f"**{label}:** {row[field]}")
                    if st.button("🔄 撮り直す", key=f"redo_{idx}"):
                        st.session_state.results[idx].update(
                            {"会社名": "", "役職": "", "メール": "", "電話": ""}
                        )
                        save_results(st.session_state.results)
                        st.rerun()
                else:
                    st.caption("📷 名刺をアップロードすると会社名・メールが自動入力されます（スキップ可）")
                    card_img = st.file_uploader(
                        "名刺写真", type=["jpg", "jpeg", "png", "webp"],
                        key=f"card_{idx}", label_visibility="collapsed",
                    )
                    if card_img:
                        st.image(card_img, width=220)
                        if st.button("🔍 OCR 実行", key=f"ocr_{idx}", type="primary"):
                            with st.spinner("名刺を読み取り中..."):
                                mt = MEDIA_TYPES.get(Path(card_img.name).suffix.lower(), "image/jpeg")
                                data = ocr_business_card(card_img.read(), mt)
                            st.session_state.results[idx].update({
                                "名前":   data.get("name")    or row["名前"],
                                "会社名": data.get("company") or "",
                                "役職":   data.get("title")   or "",
                                "メール": data.get("email")   or "",
                                "電話":   data.get("phone")   or "",
                            })
                            save_results(st.session_state.results)
                            st.rerun()

                if row.get("文字起こし"):
                    st.divider()
                    st.caption("全文字起こし")
                    st.text(row["文字起こし"])

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        csv_fields = ["番号", "名前", "会社名", "役職", "メール", "電話", "会話要約"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(st.session_state.results)
        st.download_button(
            "📥 CSV ダウンロード",
            data=buf.getvalue().encode("utf-8-bom"),
            file_name="meetup.csv", mime="text/csv",
            use_container_width=True,
        )
