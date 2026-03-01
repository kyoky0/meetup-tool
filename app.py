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

# ===== SESSION STATE =====
for key, val in {
    "recording": False,
    "start_time": None,
    "timestamps": [],   # [0.0, cut1, cut2, ..., end]
    "results": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

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
        # 記録済みがあれば案内
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
                st.rerun()

    else:
        elapsed = time.time() - st.session_state.start_time
        mins, secs = divmod(int(elapsed), 60)
        person_num = len(st.session_state.timestamps)  # 1始まり

        # タイマー表示
        st.markdown(f"""
        <div class="timer-wrap">
          <div class="timer-label">経過時間</div>
          <div class="timer-value">{mins:02d}:{secs:02d}</div>
        </div>
        """, unsafe_allow_html=True)

        # 現在の人物バッジ
        st.markdown(
            f'<div class="person-badge">👤 {person_num} 人目と会話中</div>',
            unsafe_allow_html=True,
        )

        # 主操作ボタン
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

        # カット記録ログ
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

    # タイムスタンプ状態
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

            # 2. 文字起こし（リアルタイム進捗付き）
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

            # 3. タイムスタンプ末尾に音声長を追加
            tss_full = tss + [duration]
            n_persons = len(tss_full) - 1

            def get_transcript(segs, t_start, t_end):
                return "".join(
                    s.text for s in segs
                    if t_start - 1 <= s.start < t_end + 1
                ).strip()

            # 4. Claude Haiku で人物ごとに解析
            client = Anthropic(api_key=api_key.strip())
            results = []
            bar = st.progress(0.0, text="解析中...")

            for i in range(n_persons):
                transcript = get_transcript(all_segs, tss_full[i], tss_full[i + 1])
                bar.progress((i + 0.5) / n_persons, text=f"解析中... {i+1}/{n_persons} 人目")

                if not transcript:
                    results.append({"番号": i + 1, "名前": "（不明）", "会話要約": "（音声なし）"})
                    bar.progress((i + 1) / n_persons)
                    continue

                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{
                        "role": "user",
                        "content": (
                            "名刺交換会での会話の文字起こしです。\n"
                            f"<会話>\n{transcript}\n</会話>\n\n"
                            "以下をJSONのみで返してください:\n"
                            '- name: 相手の名前（「〇〇と申します」等から抽出。不明なら「不明」）\n'
                            '- summary: 会話内容の要約（2〜3文）\n'
                            '{"name": "...", "summary": "..."}'
                        ),
                    }],
                )

                raw = resp.content[0].text.strip()
                match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group())
                        results.append({
                            "番号": i + 1,
                            "名前": data.get("name", "不明"),
                            "会話要約": data.get("summary", raw),
                        })
                    except json.JSONDecodeError:
                        results.append({"番号": i + 1, "名前": "不明", "会話要約": raw})
                else:
                    results.append({"番号": i + 1, "名前": "不明", "会話要約": raw})

                bar.progress((i + 1) / n_persons, text=f"完了: {i+1}/{n_persons} 人")

            st.session_state.results = results
            bar.progress(1.0, text="✅ 完了！")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
        finally:
            os.unlink(temp_path)

    # ===== 結果表示 =====
    if st.session_state.results:
        st.divider()
        st.subheader(f"📋 会話一覧（{len(st.session_state.results)} 人）")

        st.dataframe(
            st.session_state.results,
            use_container_width=True,
            hide_index=True,
            column_config={
                "番号": st.column_config.NumberColumn("No.", width="small"),
                "名前": st.column_config.TextColumn("名前", width="medium"),
                "会話要約": st.column_config.TextColumn("会話要約", width="large"),
            },
        )

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["番号", "名前", "会話要約"])
        writer.writeheader()
        writer.writerows(st.session_state.results)
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
