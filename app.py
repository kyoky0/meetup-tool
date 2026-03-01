import streamlit as st
import time
import json
import re
import os
import csv
import io
import base64
import tempfile
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
div[data-testid="stButton"] button {
    height: 72px;
    font-size: 20px;
    border-radius: 12px;
}
div[data-testid="stButton"] button[kind="primary"] {
    font-size: 22px;
    font-weight: bold;
}
.app-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 1rem 1.5rem;
    border-radius: 14px;
    text-align: center;
    margin-bottom: 1.2rem;
}
.app-header h2 { margin: 0 0 0.2rem 0; font-size: 1.6rem; }
.app-header p  { margin: 0; font-size: 0.9rem; opacity: 0.85; }
.timer-wrap {
    background: #f7f8fc;
    border: 2px solid #e2e8f0;
    border-radius: 14px;
    padding: 1rem;
    text-align: center;
    margin-bottom: 0.8rem;
}
.timer-label { font-size: 0.8rem; color: #718096; margin-bottom: 0.2rem; }
.timer-value {
    font-size: 52px;
    font-weight: bold;
    font-family: monospace;
    color: #1a202c;
    line-height: 1;
}
.person-badge {
    background: #e8f4fd;
    border: 2px solid #4a90d9;
    border-radius: 50px;
    padding: 10px 20px;
    text-align: center;
    font-size: 18px;
    font-weight: bold;
    color: #2c5282;
    margin-bottom: 1rem;
}
.cut-log {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 6px 12px;
    border-radius: 0 8px 8px 0;
    margin: 4px 0;
    font-size: 0.85rem;
    color: #276749;
}
</style>
""", unsafe_allow_html=True)

# ===== 定数 =====
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
SAVE_FILE    = Path(__file__).parent / "meetup_session.json"
MEDIA_TYPES  = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
}
MAX_AUDIO_MB = 25  # OpenAI Whisper API の上限

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
    "recording":   False,
    "start_time":  None,
    "timestamps":  [],
    "openai_key":  os.getenv("OPENAI_API_KEY", ""),
    "claude_key":  os.getenv("ANTHROPIC_API_KEY", ""),
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ===== 文字起こし（OpenAI Whisper API）=====
def transcribe_audio(openai_key: str, audio_bytes: bytes, filename: str):
    """OpenAI Whisper API で文字起こし → (segments, duration)"""
    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    resp = client.audio.transcriptions.create(
        model="whisper-1",
        file=(filename, io.BytesIO(audio_bytes)),
        language="ja",
        response_format="verbose_json",
        timestamp_granularities=["segment"],
    )
    return resp.segments, resp.duration

def get_transcript(segs, t_start: float, t_end: float) -> str:
    return "".join(
        s.text for s in segs if t_start - 1 <= s.start < t_end + 1
    ).strip()

# ===== Claude ヘルパー =====
def call_with_retry(client, messages: list, max_tokens: int = 500, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=CLAUDE_MODEL, max_tokens=max_tokens, messages=messages,
            )
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

def analyze_batch(client, transcripts: list) -> list:
    sections = "\n\n".join(f"=== 人物{i+1} ===\n{t}" for i, t in enumerate(transcripts))
    resp = call_with_retry(client, [{
        "role": "user",
        "content": (
            f"以下は名刺交換会での複数人の会話記録です。\n\n{sections}\n\n"
            "各人物についてJSONのみで返してください:\n"
            '[{"id": 1, "name": "名前または不明", "summary": "要約2〜3文"}, ...]'
        ),
    }], max_tokens=2000)
    raw = resp.content[0].text.strip()
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("JSON配列が見つかりません")
    return json.loads(match.group())

def analyze_single(client, transcript: str) -> dict:
    resp = call_with_retry(client, [{
        "role": "user",
        "content": (
            f"名刺交換会での会話。\n<会話>\n{transcript}\n</会話>\n\n"
            'JSONのみで返してください: {"name": "名前または不明", "summary": "要約2〜3文"}'
        ),
    }])
    raw = resp.content[0].text.strip()
    match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
    if match:
        data = json.loads(match.group())
        return {"name": data.get("name", "不明"), "summary": data.get("summary", raw)}
    return {"name": "不明", "summary": raw}

def ocr_business_card(client, image_bytes: bytes, media_type: str) -> dict:
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    resp = call_with_retry(client, [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": (
                "この名刺から以下をJSONのみで抽出してください:\n"
                '{"name": "氏名", "company": "会社名", "title": "役職", '
                '"email": "メール", "phone": "電話番号"}\n'
                "読み取れない項目はnullにしてください。"
            )},
        ],
    }], max_tokens=300)
    raw = resp.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            return {}
    return {}

# ===== HEADER =====
st.markdown("""
<div class="app-header">
  <h2>🤝 名刺会メモ</h2>
  <p>会話を記録して、帰宅後に一覧で確認</p>
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
        st.info("📱 スマホの録音アプリで録音を開始してから、下のボタンを押してください")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ タイマー開始", use_container_width=True, type="primary"):
                st.session_state.recording = True
                st.session_state.start_time = time.time()
                st.session_state.timestamps = [0.0]
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
          <div class="timer-label">経過時間</div>
          <div class="timer-value">{mins:02d}:{secs:02d}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<div class="person-badge">👤 {person_num} 人目と会話中</div>', unsafe_allow_html=True)

        if st.button(f"✂️ 次の人へ　→　{person_num + 1} 人目", use_container_width=True, type="primary"):
            st.session_state.timestamps.append(time.time() - st.session_state.start_time)
            st.rerun()
        if st.button("⏹️ 録音終了", use_container_width=True):
            st.session_state.timestamps.append(time.time() - st.session_state.start_time)
            st.session_state.recording = False
            st.rerun()

        if len(st.session_state.timestamps) > 1:
            st.divider()
            st.caption("カット記録")
            for i, ts in enumerate(st.session_state.timestamps[1:], 1):
                m, s = divmod(int(ts), 60)
                st.markdown(f'<div class="cut-log">✂️ 人物 {i} 終了 → {m:02d}:{s:02d}</div>', unsafe_allow_html=True)

# ============================================================
# TAB 2: 帰宅後
# ============================================================
with tab2:

    n_recorded = max(0, len(st.session_state.timestamps) - 1)
    if n_recorded > 0:
        st.success(f"✅ {n_recorded} 人分のタイムスタンプ記録済み")
    else:
        st.warning("⚠️ タイムスタンプ未記録。全音声を 1 人として処理します")

    # API キー設定
    with st.expander("⚙️ API キー設定", expanded=not st.session_state.claude_key):
        openai_input = st.text_input("OpenAI API Key（文字起こし用）", type="password",
                                     value=st.session_state.openai_key, placeholder="sk-...")
        claude_input = st.text_input("Claude API Key（名前抽出・OCR用）", type="password",
                                     value=st.session_state.claude_key, placeholder="sk-ant-...")
        if openai_input:
            st.session_state.openai_key = openai_input.strip()
        if claude_input:
            st.session_state.claude_key = claude_input.strip()

    audio_file = st.file_uploader(
        "録音ファイル（mp3 / m4a / wav / ogg / webm・25MB以下）",
        type=["mp3", "mp4", "m4a", "wav", "ogg", "webm"],
    )

    # ファイルサイズ警告
    if audio_file:
        size_mb = len(audio_file.getbuffer()) / (1024 * 1024)
        if size_mb > MAX_AUDIO_MB:
            st.error(f"ファイルが大きすぎます（{size_mb:.1f}MB）。{MAX_AUDIO_MB}MB 以下に圧縮してください。")
            audio_file = None
        else:
            st.caption(f"ファイルサイズ: {size_mb:.1f}MB ✅")

    can_process = (
        audio_file is not None
        and bool(st.session_state.openai_key)
        and bool(st.session_state.claude_key)
    )

    if st.button("🚀 文字起こし・解析開始", type="primary", use_container_width=True, disabled=not can_process):

        tss = list(st.session_state.timestamps) or [0.0]
        audio_bytes = audio_file.getbuffer()

        try:
            from anthropic import Anthropic

            # 1. 文字起こし（OpenAI Whisper API）
            with st.spinner("🎙️ 文字起こし中... （音声の長さにより1〜2分かかります）"):
                all_segs, duration = transcribe_audio(
                    st.session_state.openai_key, audio_bytes, audio_file.name
                )
            st.success("✅ 文字起こし完了")

            # 2. 人物ごとに分割
            tss_full = tss + [duration]
            n_persons = len(tss_full) - 1
            transcripts = [
                get_transcript(all_segs, tss_full[i], tss_full[i + 1])
                for i in range(n_persons)
            ]

            # 3. Claude Haiku でバッチ解析
            claude_client = Anthropic(api_key=st.session_state.claude_key)
            bar = st.progress(0.0, text="🤖 Claude Haiku で解析中（一括処理）...")
            results = []
            non_empty_idx = [i for i, t in enumerate(transcripts) if t]

            try:
                batch_data = analyze_batch(claude_client, [transcripts[i] for i in non_empty_idx])
                batch_map = {
                    non_empty_idx[j]: batch_data[j]
                    for j in range(min(len(non_empty_idx), len(batch_data)))
                }
                for i, t in enumerate(transcripts):
                    d = batch_map.get(i, {})
                    results.append({
                        "番号": i + 1,
                        "名前":   d.get("name", "不明") if t else "（不明）",
                        "会社名": "", "役職": "", "メール": "", "電話": "",
                        "会話要約": d.get("summary", "（解析失敗）") if t else "（音声なし）",
                        "文字起こし": t,
                    })
                bar.progress(1.0, text="✅ 解析完了（一括処理）")

            except Exception:
                bar.progress(0.0, text="⚠️ 個別処理に切り替えます...")
                results = []
                for i, t in enumerate(transcripts):
                    bar.progress((i + 0.5) / n_persons, text=f"解析中... {i+1}/{n_persons} 人目")
                    base = {"番号": i+1, "会社名": "", "役職": "", "メール": "", "電話": "", "文字起こし": t}
                    if not t:
                        results.append({**base, "名前": "（不明）", "会話要約": "（音声なし）"})
                    else:
                        try:
                            d = analyze_single(claude_client, t)
                            results.append({**base, "名前": d["name"], "会話要約": d["summary"]})
                        except Exception:
                            results.append({**base, "名前": "不明", "会話要約": "（解析失敗）"})
                    bar.progress((i + 1) / n_persons)
                bar.progress(1.0, text="✅ 解析完了")

            st.session_state.results = results
            save_results(results)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

    # ===== 結果表示 =====
    if st.session_state.results:
        st.divider()
        st.subheader(f"📋 会話一覧（{len(st.session_state.results)} 人）")

        display_fields = ["番号", "名前", "会社名", "メール", "会話要約"]
        display_data = [{k: r.get(k, "") for k in display_fields} for r in st.session_state.results]
        st.dataframe(display_data, use_container_width=True, hide_index=True, column_config={
            "番号":     st.column_config.NumberColumn("No.", width="small"),
            "名前":     st.column_config.TextColumn("名前", width="medium"),
            "会社名":   st.column_config.TextColumn("会社名", width="medium"),
            "メール":   st.column_config.TextColumn("メール", width="medium"),
            "会話要約": st.column_config.TextColumn("会話要約", width="large"),
        })

        st.subheader("📝 詳細・名刺 OCR（タップで展開）")
        for idx, row in enumerate(st.session_state.results):
            has_card = bool(row.get("会社名") or row.get("メール"))
            icon = "🪪" if has_card else "👤"
            label = f"{icon} {row['番号']}. {row['名前']}"
            if row.get("会社名"):
                label += f"　　{row['会社名']}"

            with st.expander(label):
                st.write(row["会話要約"])
                st.divider()
                st.caption("📷 名刺（任意・スキップ可）")

                if has_card:
                    for field, label_text in [("会社名", "会社"), ("役職", "役職"), ("メール", "メール"), ("電話", "電話")]:
                        if row.get(field):
                            st.write(f"**{label_text}:** {row[field]}")
                    if st.button("🔄 名刺を撮り直す", key=f"redo_{idx}"):
                        st.session_state.results[idx].update({"会社名": "", "役職": "", "メール": "", "電話": ""})
                        save_results(st.session_state.results)
                        st.rerun()
                else:
                    card_img = st.file_uploader("名刺写真", type=["jpg", "jpeg", "png", "webp"],
                                                key=f"card_{idx}", label_visibility="collapsed")
                    if card_img:
                        st.image(card_img, width=240)
                        if st.button("🔍 OCR 実行", key=f"ocr_{idx}", type="primary"):
                            if not st.session_state.claude_key:
                                st.error("Claude API キーが必要です")
                            else:
                                with st.spinner("🪪 名刺を読み取り中..."):
                                    from anthropic import Anthropic
                                    c = Anthropic(api_key=st.session_state.claude_key)
                                    mt = MEDIA_TYPES.get(Path(card_img.name).suffix.lower(), "image/jpeg")
                                    data = ocr_business_card(c, card_img.read(), mt)
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

        csv_fields = ["番号", "名前", "会社名", "役職", "メール", "電話", "会話要約"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(st.session_state.results)
        st.download_button("📥 CSV ダウンロード", data=buf.getvalue().encode("utf-8-bom"),
                           file_name="meetup.csv", mime="text/csv", use_container_width=True)

# ===== タイマー毎秒自動更新（録音中のみ）=====
if st.session_state.recording:
    time.sleep(1)
    st.rerun()
