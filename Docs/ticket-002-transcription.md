# Ticket-002: 文字起こし

## 概要

帰宅後にアップロードした録音ファイルを faster-whisper でローカル文字起こしし、
タイムスタンプをもとに人物ごとのセグメントへ分割する機能。

## フェーズ

Phase 1（コア）

## ステータス

完了

---

## TODO

- [x] 対応フォーマット: mp3 / mp4 / m4a / wav / ogg / webm（X）
- [x] ファイルを一時ディレクトリに保存して処理後に削除（X）
- [x] Whisper モデル `small` で `language="ja"` 指定（X）
- [x] モデルを `session_state` にキャッシュして初回のみロード（X）
- [x] `compute_type="int8"` で CPU 動作を最適化（X）
- [x] 全音声を 1 パスで文字起こし → セグメントリストを取得（X）
- [x] `info.duration` から音声長を取得し最終タイムスタンプとして使用（X）
- [x] タイムスタンプで人物ごとにセグメントを分割する `get_transcript()` 実装（X）
- [x] 文字起こし進捗のリアルタイム % 表示（`seg.end / duration` でプログレスバー更新）（X）

---

## 仕様詳細

### モデル設定

| 項目           | 値      |
| -------------- | ------- |
| モデルサイズ   | `small` |
| 言語           | `ja`    |
| 推論精度       | `int8`  |

### セグメント分割ロジック

```python
def get_transcript(segs, t_start, t_end):
    return "".join(
        s.text for s in segs
        if t_start - 1 <= s.start < t_end + 1
    ).strip()
```

前後 1 秒のバッファを設けて、発話の切れ目でのセグメント欠損を防ぐ。

---

## 備考

- 初回起動時にモデルのダウンロードが発生する（small: 約 480MB）
- インターネット接続不要（ローカル処理）
- タイムスタンプ未記録の場合は全音声を 1 人として処理
