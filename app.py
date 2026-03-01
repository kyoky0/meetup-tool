import streamlit as st
import time
import json
import re
import os
import csv
import io
import base64
from pathlib import Path

# ===== PAGE CONFIG =====
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

/* ---- ボタン ---- */
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

/* ---- ヘッダー ---- */
.app-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 1.4rem 1.5rem; border-radius: 18px;
    text-align: center; margin-bottom: 1.4rem;
    box-shadow: 0 8px 32px rgba(102,126,234,0.3);
}
.app-header h2 { margin: 0 0 0.3rem 0; font-size: 1.7rem; letter-spacing: -0.5px; }
.app-header p  { margin: 0; font-size: 0.85rem; opacity: 0.8; }

/* ---- タイマー ---- */
.timer-wrap {
    background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
    border-radius: 20px; padding: 1.6rem 1rem;
    text-align: center; margin-bottom: 1rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
.timer-label { font-size: 0.75rem; color: #a0aec0; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 0.4rem; }
.timer-value { font-size: 64px; font-weight: 700; font-family: monospace; color: white; line-height: 1; }

/* ---- 人物バッジ ---- */
.person-badge {
    background: linear-gradient(135deg, #667eea22, #764ba222);
    border: 2px solid #667eea55; border-radius: 50px;
    padding: 12px 24px; text-align: center;
    font-size: 18px; font-weight: 700; color: #4c51bf;
    margin-bottom: 1rem;
}

/* ---- カットログ ---- */
.cut-log {
    background: #f0fff4; border-left: 3px solid #48bb78;
    padding: 6px 14px; border-radius: 0 10px 10px 0;
    margin: 3px 0; font-size: 0.82rem; color: #276749;
}

/* ---- 情報バナー ---- */
.info-banner {
    background: #ebf8ff; border: 1px solid #bee3f8; border-radius: 12px;
    padding: 12px 16px; color: #2b6cb0; font-size: 0.88rem;
    margin-bottom: 1rem; line-height: 1.6;
}

/* ---- アップロードエリア ---- */
.upload-label {
    font-size: 0.95rem; font-weight: 600; color: #4a5568; margin-bottom: 4px;
}

/* ---- 結果カード ---- */
.person-card {
    background: white; border-radius: 16px; padding: 18px 20px;
    margin: 10px 0; border: 1px solid #e8ecf0;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s;
}
.person-card:hover { box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
.card-top { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
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

/* ---- CSV ボタン ---- */
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
MAX_AUDIO_MB = 25

# ===== API キー（Secrets から取得）=====
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
if "results" not in st.session_state:
    st.session_state.results = load_results()
for key, val in {
    "recording":  False,
    "start_time": None,
    "timestamps": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ===== Groq ヘルパー =====
def get_groq_client():
    from groq import Groq
    return Groq(api_key=get_groq_key())

def transcribe_audio(audio_bytes: bytes, filename: str):
    client = get_groq_client()
    resp = client.audio.transcriptions.create(
        file=(filename, io.BytesIO(audio_bytes)),
        model=GROQ_AUDIO_MODEL, language="ja", response_format="verbose_json",
    )
    return resp.segments, resp.duration

def call_llm(messages: list, max_tokens: int = 2000, max_retries: int = 3) -> str:
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

def analyze_batch(transcripts: list) -> list:
    sections = "\n\n".join(f"=== 人物{i+1} ===\n{t}" for i, t in enumerate(transcripts))
    raw = call_llm([{"role": "user", "content": (
        f"以下は名刺交換会での複数人の会話記録です。\n\n{sections}\n\n"
        "各人物についてJSONのみで返してください:\n"
        '[{"id": 1, "name": "名前または不明", "summary": "要約2〜3文"}, ...]'
    )}])
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("JSON配列が見つかりません")
    return json.loads(match.group())

def analyze_single(transcript: str) -> dict:
    raw = call_llm([{"role": "user", "content": (
        f"名刺交換会での会話。\n<会話>\n{transcript}\n</会話>\n\n"
        'JSONのみで返してください: {"name": "名前または不明", "summary": "要約2〜3文"}'
    )}], max_tokens=300)
    match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
    if match:
        data = json.loads(match.group())
        return {"name": data.get("name", "不明"), "summary": data.get("summary", raw)}
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

def get_transcript(segs, t_start: float, t_end: float) -> str:
    return "".join(s.text for s in segs if t_start - 1 <= s.start < t_end + 1).strip()

# ===== API キーチェック =====
if not get_groq_key():
    st.error("⚠️ GROQ_API_KEY が設定されていません。Streamlit Cloud の Secrets に追加してください。")
    st.stop()

# ===== HEADER =====
st.markdown("""
<div class="app-header">
  <h2>🤝 名刺会メモ</h2>
  <p>会話を記録して、帰宅後に自動で一覧化</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📍 イベント中", "🏠 帰宅後"])

# ============================================================
# TAB 1: イベント中
# ============================================================
with tab1:

    if not st.session_state.recording:
        n = max(0, len(st.session_state.timestamps) - 1)
        if n > 0:
            st.success(f"✅ {n} 人分のタイムスタンプ記録済み → 「帰宅後」タブへ")

        st.markdown("""
        <div class="info-banner">
            📱 スマホの録音アプリで録音を開始してから<br>
            下の「タイマー開始」を押してください
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ タイマー開始", use_container_width=True, type="primary"):
                st.session_state.update({"recording": True, "start_time": time.time(), "timestamps": [0.0]})
                st.rerun()
        with col2:
            if st.button("🗑️ リセット", use_container_width=True):
                st.session_state.update({"recording": False, "start_time": None, "timestamps": [], "results": []})
                if SAVE_FILE.exists():
                    SAVE_FILE.unlink()
                st.rerun()
    else:
        elapsed = time.time() - st.session_state.start_time
        mins, secs = divmod(int(elapsed), 60)
        person_num = len(st.session_state.timestamps)

        st.markdown(f"""
        <div class="timer-wrap">
          <div class="timer-label">経 過 時 間</div>
          <div class="timer-value">{mins:02d}:{secs:02d}</div>
        </div>
        <div class="person-badge">👤 {person_num} 人目と会話中</div>
        """, unsafe_allow_html=True)

        if st.button(f"✂️ 次の人へ　→　{person_num + 1} 人目", use_container_width=True, type="primary"):
            st.session_state.timestamps.append(time.time() - st.session_state.start_time)
            st.rerun()

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        if st.button("⏹️ 録音終了", use_container_width=True):
            st.session_state.timestamps.append(time.time() - st.session_state.start_time)
            st.session_state.recording = False
            st.rerun()

        if len(st.session_state.timestamps) > 1:
            st.divider()
            st.caption("✂️ カット記録")
            for i, ts in enumerate(st.session_state.timestamps[1:], 1):
                m, s = divmod(int(ts), 60)
                st.markdown(f'<div class="cut-log">人物 {i} 終了 → {m:02d}:{s:02d}</div>', unsafe_allow_html=True)

# ============================================================
# TAB 2: 帰宅後
# ============================================================
with tab2:

    n_recorded = max(0, len(st.session_state.timestamps) - 1)
    if n_recorded > 0:
        st.success(f"✅ {n_recorded} 人分のタイムスタンプ記録済み")
    else:
        st.warning("⚠️ タイムスタンプ未記録。全音声を 1 人として処理します")

    audio_file = st.file_uploader(
        "🎙️ 録音ファイルをアップロード（mp3 / m4a / wav・25MB以下）",
        type=["mp3", "mp4", "m4a", "wav", "ogg", "webm"],
    )

    if audio_file:
        size_mb = len(audio_file.getbuffer()) / (1024 * 1024)
        if size_mb > MAX_AUDIO_MB:
            st.error(f"ファイルが大きすぎます（{size_mb:.1f}MB）。{MAX_AUDIO_MB}MB 以下に圧縮してください。")
            audio_file = None
        else:
            st.caption(f"📁 {audio_file.name}　{size_mb:.1f}MB ✅")

    if st.button("🚀 文字起こし・解析開始", type="primary", use_container_width=True, disabled=not audio_file):
        tss = list(st.session_state.timestamps) or [0.0]
        audio_bytes = bytes(audio_file.getbuffer())

        try:
            with st.spinner("🎙️ 文字起こし中...（音声の長さにより1〜2分かかります）"):
                all_segs, duration = transcribe_audio(audio_bytes, audio_file.name)
            st.success("✅ 文字起こし完了")

            tss_full = tss + [duration]
            n_persons = len(tss_full) - 1
            transcripts = [get_transcript(all_segs, tss_full[i], tss_full[i+1]) for i in range(n_persons)]

            bar = st.progress(0.0, text="🤖 AI で解析中...")
            results = []
            non_empty_idx = [i for i, t in enumerate(transcripts) if t]

            try:
                batch_data = analyze_batch([transcripts[i] for i in non_empty_idx])
                batch_map = {non_empty_idx[j]: batch_data[j] for j in range(min(len(non_empty_idx), len(batch_data)))}
                for i, t in enumerate(transcripts):
                    d = batch_map.get(i, {})
                    results.append({
                        "番号": i+1,
                        "名前":   d.get("name", "不明") if t else "（不明）",
                        "会社名": "", "役職": "", "メール": "", "電話": "",
                        "会話要約": d.get("summary", "（解析失敗）") if t else "（音声なし）",
                        "文字起こし": t,
                    })
                bar.progress(1.0, text="✅ 解析完了")
            except Exception:
                bar.progress(0.0, text="⚠️ 個別処理に切り替えます...")
                results = []
                for i, t in enumerate(transcripts):
                    bar.progress((i+0.5)/n_persons, text=f"解析中... {i+1}/{n_persons} 人目")
                    base = {"番号": i+1, "会社名": "", "役職": "", "メール": "", "電話": "", "文字起こし": t}
                    if not t:
                        results.append({**base, "名前": "（不明）", "会話要約": "（音声なし）"})
                    else:
                        try:
                            d = analyze_single(t)
                            results.append({**base, "名前": d["name"], "会話要約": d["summary"]})
                        except Exception:
                            results.append({**base, "名前": "不明", "会話要約": "（解析失敗）"})
                    bar.progress((i+1)/n_persons)
                bar.progress(1.0, text="✅ 解析完了")

            st.session_state.results = results
            save_results(results)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

    # ===== 結果表示 =====
    if st.session_state.results:
        st.divider()
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

            # 詳細・OCR（expander）
            with st.expander("📎 詳細・名刺 OCR"):
                if has_card:
                    for field, label in [("会社名","会社"), ("役職","役職"), ("メール","メール"), ("電話","電話")]:
                        if row.get(field):
                            st.write(f"**{label}:** {row[field]}")
                    if st.button("🔄 撮り直す", key=f"redo_{idx}"):
                        st.session_state.results[idx].update({"会社名":"","役職":"","メール":"","電話":""})
                        save_results(st.session_state.results)
                        st.rerun()
                else:
                    st.caption("📷 名刺をアップロードすると会社名・メールが自動入力されます（スキップ可）")
                    card_img = st.file_uploader("名刺写真", type=["jpg","jpeg","png","webp"],
                                                key=f"card_{idx}", label_visibility="collapsed")
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

# ===== タイマー毎秒自動更新（録音中のみ）=====
if st.session_state.recording:
    time.sleep(1)
    st.rerun()
