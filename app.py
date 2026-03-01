import streamlit as st
import time
import json
import re
import os
import csv
import io
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
/* ---- ボタン共通 ---- */
div[data-testid="stButton"] button {
    height: 72px;
    font-size: 20px;
    border-radius: 12px;
}
div[data-testid="stButton"] button[kind="primary"] {
    font-size: 22px;
    font-weight: bold;
}

/* ---- ヘッダー ---- */
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

/* ---- タイマー ---- */
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

/* ---- 人物バッジ ---- */
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

/* ---- カットログ ---- */
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

# ===== 永続化 =====
SAVE_FILE = Path(__file__).parent / "meetup_session.json"

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
    "recording": False,
    "start_time": None,
    "timestamps": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ===== CLAUDE ヘルパー =====
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

def call_with_retry(client, messages: list, max_tokens: int = 500, max_retries: int = 3):
    """レートリミット対策：指数バックオフでリトライ"""
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                messages=messages,
            )
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s → 2s → 4s
            else:
                raise

def analyze_batch(client, transcripts: list) -> list:
    """全員を 1 回の API 呼び出しで解析（コスト最適化）"""
    sections = "\n\n".join(
        f"=== 人物{i + 1} ===\n{t}" for i, t in enumerate(transcripts)
    )
    prompt = (
        "以下は名刺交換会での複数人の会話記録です。\n\n"
        f"{sections}\n\n"
        "各人物についてJSONのみで返してください:\n"
        '[{"id": 1, "name": "名前または不明", "summary": "要約2〜3文"}, ...]'
    )
    resp = call_with_retry(client, [{"role": "user", "content": prompt}], max_tokens=2000)
    raw = resp.content[0].text.strip()
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("JSON配列が見つかりません")
    return json.loads(match.group())

def analyze_single(client, transcript: str, index: int) -> dict:
    """個別解析（バッチ失敗時のフォールバック）"""
    resp = call_with_retry(client, [{
        "role": "user",
        "content": (
            "名刺交換会での会話の文字起こしです。\n"
            f"<会話>\n{transcript}\n</会話>\n\n"
            "以下をJSONのみで返してください:\n"
            '- name: 相手の名前（「〇〇と申します」等から抽出。不明なら「不明」）\n'
            '- summary: 会話内容の要約（2〜3文）\n'
            '{"name": "...", "summary": "..."}'
        ),
    }])
    raw = resp.content[0].text.strip()
    match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
    if match:
        data = json.loads(match.group())
        return {"name": data.get("name", "不明"), "summary": data.get("summary", raw)}
    return {"name": "不明", "summary": raw}

def get_transcript(segs: list, t_start: float, t_end: float) -> str:
    return "".join(
        s.text for s in segs if t_start - 1 <= s.start < t_end + 1
    ).strip()

# ===== HEADER =====
st.markdown("""
<div class="app-header">
  <h2>🤝 名刺会メモ</h2>
  <p>会話を記録して、帰宅後に一覧で確認</p>
</div>
""", unsafe_allow_html=True)

# ===== TABS =====
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
                st.session_state.recording = False
                st.session_state.start_time = None
                st.session_state.timestamps = []
                st.session_state.results = []
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

        st.markdown(
            f'<div class="person-badge">👤 {person_num} 人目と会話中</div>',
            unsafe_allow_html=True,
        )

        if st.button(
            f"✂️ 次の人へ　→　{person_num + 1} 人目",
            use_container_width=True,
            type="primary",
        ):
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
                st.markdown(
                    f'<div class="cut-log">✂️ 人物 {i} 終了 → {m:02d}:{s:02d}</div>',
                    unsafe_allow_html=True,
                )

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
        "録音ファイル（mp3 / m4a / wav / ogg / webm）",
        type=["mp3", "mp4", "m4a", "wav", "ogg", "webm"],
    )

    api_key = st.text_input(
        "Claude API Key",
        type="password",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        placeholder="sk-ant-...",
    )

    can_process = audio_file is not None and bool(api_key.strip())

    if st.button(
        "🚀 文字起こし・解析開始",
        type="primary",
        use_container_width=True,
        disabled=not can_process,
    ):
        tss = list(st.session_state.timestamps) or [0.0]
        suffix = Path(audio_file.name).suffix or ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_file.getbuffer())
            temp_path = f.name

        try:
            from faster_whisper import WhisperModel
            from anthropic import Anthropic

            # 1. Whisper モデル（初回のみロード）
            with st.spinner("🔄 Whisper モデル読み込み中（初回は少し時間がかかります）..."):
                if "whisper" not in st.session_state:
                    st.session_state.whisper = WhisperModel("small", compute_type="int8")
                model = st.session_state.whisper

            # 2. 文字起こし（リアルタイム進捗）
            segs_gen, info = model.transcribe(temp_path, language="ja")
            duration = info.duration
            t_bar = st.progress(0.0, text="🎙️ 文字起こし中...")
            all_segs = []
            for seg in segs_gen:
                all_segs.append(seg)
                pct = min(seg.end / duration, 1.0)
                t_bar.progress(
                    pct,
                    text=f"🎙️ 文字起こし中... {int(pct * 100)}%（{int(seg.end)}秒 / {int(duration)}秒）",
                )
            t_bar.progress(1.0, text="✅ 文字起こし完了")

            # 3. 人物ごとの文字起こしを取得
            tss_full = tss + [duration]
            n_persons = len(tss_full) - 1
            transcripts = [
                get_transcript(all_segs, tss_full[i], tss_full[i + 1])
                for i in range(n_persons)
            ]

            # 4. Claude Haiku でバッチ解析（失敗時は個別にフォールバック）
            client = Anthropic(api_key=api_key.strip())
            bar = st.progress(0.0, text="🤖 Claude Haiku で解析中（一括処理）...")
            results = []

            non_empty_idx = [i for i, t in enumerate(transcripts) if t]
            try:
                batch_data = analyze_batch(client, [transcripts[i] for i in non_empty_idx])
                # id をキーにしてマッピング（Claude が id を返す場合）
                # 返ってきた順番で対応
                batch_map = {
                    non_empty_idx[j]: batch_data[j]
                    for j in range(min(len(non_empty_idx), len(batch_data)))
                }
                for i, t in enumerate(transcripts):
                    d = batch_map.get(i, {})
                    results.append({
                        "番号": i + 1,
                        "名前": d.get("name", "不明") if t else "（不明）",
                        "会話要約": d.get("summary", "（解析失敗）") if t else "（音声なし）",
                        "文字起こし": t,
                    })
                bar.progress(1.0, text="✅ 解析完了（一括処理）")

            except Exception:
                # バッチ失敗 → 個別処理にフォールバック
                bar.progress(0.0, text="⚠️ 個別処理に切り替えます...")
                results = []
                for i, t in enumerate(transcripts):
                    bar.progress((i + 0.5) / n_persons, text=f"解析中... {i+1}/{n_persons} 人目")
                    if not t:
                        results.append({"番号": i+1, "名前": "（不明）", "会話要約": "（音声なし）", "文字起こし": ""})
                        bar.progress((i + 1) / n_persons)
                        continue
                    try:
                        d = analyze_single(client, t, i)
                        results.append({"番号": i+1, "名前": d["name"], "会話要約": d["summary"], "文字起こし": t})
                    except Exception:
                        results.append({"番号": i+1, "名前": "不明", "会話要約": "（解析失敗）", "文字起こし": t})
                    bar.progress((i + 1) / n_persons)
                bar.progress(1.0, text="✅ 解析完了")

            st.session_state.results = results
            save_results(results)  # ページリロード後も保持

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
        finally:
            os.unlink(temp_path)

    # ===== 結果表示 =====
    if st.session_state.results:
        st.divider()
        n_results = len(st.session_state.results)
        st.subheader(f"📋 会話一覧（{n_results} 人）")

        # 概要テーブル（文字起こし列は除外）
        display_data = [
            {"番号": r["番号"], "名前": r["名前"], "会話要約": r["会話要約"]}
            for r in st.session_state.results
        ]
        st.dataframe(
            display_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "番号": st.column_config.NumberColumn("No.", width="small"),
                "名前": st.column_config.TextColumn("名前", width="medium"),
                "会話要約": st.column_config.TextColumn("会話要約", width="large"),
            },
        )

        # 詳細：タップで全文字起こしを展開
        st.subheader("📝 詳細（タップで展開）")
        for row in st.session_state.results:
            label = f"{row['番号']}. {row['名前']}"
            with st.expander(label):
                st.write(row["会話要約"])
                transcript = row.get("文字起こし", "")
                if transcript:
                    st.divider()
                    st.caption("全文字起こし")
                    st.text(transcript)

        # CSV ダウンロード
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["番号", "名前", "会話要約"])
        writer.writeheader()
        writer.writerows(display_data)
        st.download_button(
            "📥 CSV ダウンロード",
            data=buf.getvalue().encode("utf-8-bom"),
            file_name="meetup.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ===== タイマー毎秒自動更新（録音中のみ）=====
if st.session_state.recording:
    time.sleep(1)
    st.rerun()
