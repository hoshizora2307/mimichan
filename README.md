# ミミちゃんチャット 🧡

超フランク&超ハイテンションな「ミミちゃん」と、LINEみたいにチャットできるAIアプリです。
社員のみなさんはスマホのブラウザ(Safari / Chrome)からURLを開くだけで使えます。

© 株式会社MONDOCOLO / Produced by MONDOCOLO STUDIO

## 特徴

**本物のチャット体験** — LINE風の画面(吹き出し・タイピング中の「…」表示・複数吹き出しでテンポよく返信)。スマホ最適化済み。

**一人ひとりを覚える** — 利用者ごとに会話が完全に分かれます。ミミちゃんは相手の名前や近況を長期記憶に保存し、次に話すとき自然に話題にしてくれます。会話が長くなっても自動要約で記憶を整理するので安心。

**ツール実行** — 計算・現在日時(日本時間)・Web検索・記憶保存を、ミミちゃんが自分の判断で使います。

**合言葉ガード** — 環境変数 `APP_PASSCODE` を設定すると、合言葉を知っている人(社員)だけが使えます。

**Gemini / Claude 両対応** — 標準では **Google Gemini**(無料枠あり)で動きます。`config.json` の `provider` を `anthropic` に変えれば Claude でも動きます。

## 社員向け: 使い方

1. スマホのブラウザで社内共有されたURLを開く
2. 合言葉を入力
3. あとはLINE感覚でチャットするだけ!(履歴はスマホごとに保存されます)

ホーム画面に追加(Safariの「ホーム画面に追加」/ Chromeの「アプリをインストール」)しておくと、アプリのように使えて便利です。

## 管理者向け: デプロイ手順 (Render・無料)

1. [Render](https://render.com/) にGitHubアカウントでサインアップ
2. ダッシュボードで **New → Blueprint** を選び、このリポジトリを接続
   (`render.yaml` を自動で読み込みます)
3. 環境変数を設定:
   - `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey) で取得したAPIキー(無料)
   - `APP_PASSCODE` — 社員に共有する合言葉(好きな文字列)
4. デプロイ完了後に表示される `https://〜.onrender.com` のURLを社員に共有

**注意**: 無料プランは15分アクセスがないとスリープし、次のアクセス時に起動へ数十秒かかります。常時快適にするなら有料プラン(月$7〜)にアップグレードしてください。

## ローカルで動かす場合

```
pip install -r requirements.txt
export GEMINI_API_KEY="AIza..."
export APP_PASSCODE="好きな合言葉"   # 省略するとパスコードなし
python app.py
```

→ http://localhost:5000

## APIキーの取得

**Gemini(標準・無料枠あり)**: [Google AI Studio](https://aistudio.google.com/apikey) にGoogleアカウントでログインし「APIキーを作成」を押すだけ。無料枠内なら課金なしで使えます。

**Claude に切り替える場合**: `config.json` を `"provider": "anthropic"`, `"model": "claude-sonnet-4-5"` に変更し、環境変数 `ANTHROPIC_API_KEY` に [Claude Platform](https://platform.claude.com/) のキーを設定(従量課金)。

## カスタマイズ

- **性格・口調**: `persona.md` を編集
- **名前・モデル**: `config.json` を編集(コストを抑えるなら model を `claude-haiku-4-5` に)
- **アイコン**: `static/avatar.png` を差し替え(正方形に近い画像推奨)
- **ツール追加**: `tools.py` に定義と処理を追加

## ファイル構成

```
mimichan/
├── app.py               # Flaskサーバー(マルチユーザー・合言葉・チャットAPI)
├── memory.py            # 記憶管理(履歴の永続化・長期記憶・自動要約)
├── tools.py             # ツール(計算・時刻・記憶・検索)
├── persona.md           # ミミちゃんのキャラ設定
├── config.json          # 設定
├── templates/index.html # LINE風チャットUI
├── static/avatar.png    # アイコン
├── render.yaml          # Renderデプロイ設定
└── data/                # 実行時に自動生成(gitには含めない)
```

## コストとセキュリティの注意

- Geminiの無料枠にはリクエスト数の上限があります。社員数が多い・利用が活発な場合は、Google AI Studioで従量課金を有効にするか上限を確認してください
- APIキーと合言葉は**絶対にリポジトリにcommitしない**でください(環境変数でのみ設定)
- 会話履歴 `data/` は個人的な内容を含むため `.gitignore` 済みです
- Renderの無料プランではサーバー再起動時に会話履歴が消えます(ディスクが永続化されないため)。履歴を永続化したい場合は有料プランで Persistent Disk を追加してください
