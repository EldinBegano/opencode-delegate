# opencode-delegate

[English](README.md) | [Français](README.fr.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

[Claude Code](https://claude.com/claude-code) のスキルで、判断力を要しない雑務を無料の [opencode](https://opencode.ai) モデルに任せ、Claude の利用枠を本当に必要な部分に回します。

Claude が主導権を握り続けます。何を委譲するかを決め、プロンプトを書き、サンドボックス化された worker 経由で無料モデルを実行し、その後 diff をレビューしてテストも自身で実行します。

![Claude Code loading the skill, delegating 33 docstrings to a free model with the tests as the check, then reviewing the diff](docs/demo.gif)

ベンチマーク fixture 上の実際の Claude Code セッションで、待機時間はカットしてあります。Claude の使用料は $0.31 でした。同じタスクをこのスキルなしで行うと平均 $0.63 かかりました。

## 得られるもの

- **`skill/SKILL.md`**: Claude に委譲すべきタイミング（定型コード、テスト、ドキュメント、fixture、複数ファイルにまたがる編集）とすべきでないタイミング（設計、厄介なバグ、セキュリティ）、および結果のレビュー方法を伝えます。
- **`bin/oc-delegate`**: 無料モデルのフォールバックチェーンで worker を実行します。モデルが失敗したりハングした場合、そのモデルが編集したファイルだけが巻き戻され、次のモデルが試されます。自分の未コミットの変更はそのまま残ります。
- **`opencode/cc-worker.md`**: ロックダウンされた opencode エージェントです。リポジトリ内のファイルの読み取りと編集のみ可能で、それ以外は何もできません：shell なし、web なし、`.git`、`.env*`、鍵や認証情報ファイルもなし。
- **`claude-md-snippet.md`**: 雑務の委譲を Claude のデフォルトにする `CLAUDE.md` のセクションです。これがないと、Claude は自分からこのスキルを選ぶことがほとんどありません。

## 前提条件

| 必要 | 備考 |
| --- | --- |
| Claude Code | スキルに対応した最近のバージョンならどれでも。 |
| [opencode](https://opencode.ai) | v2.0.32 および v2.1.3 でテスト済み。無料の OpenCode Zen モデルは API キーなしで動作します。 |
| `bash`、`git`、`jq` | |
| GNU coreutils | Linux にはこれらが入っています。macOS では Homebrew で `coreutils` をインストールし、その `gnubin` ディレクトリを `PATH` の先頭に置いてください。 |
| `~/.local/bin` が `PATH` 上にあること | インストーラーが `oc-delegate` を置く場所です。 |
| `bwrap`（任意、Linux） | [bubblewrap](https://github.com/containers/bubblewrap) が worker のファイル書き込みをリポジトリ内に制限します。推奨。 |

opencode がなければインストールし、無料モデルが一覧に表示されることを確認してください：

```sh
curl -fsSL https://opencode.ai/install | bash
opencode models | grep -E -- '-free|big-pickle'
```

## インストール

### Claude Code に任せる

これを Claude Code に貼り付けてください：

```text
https://github.com/EldinBegano/opencode-delegate から opencode-delegate スキルをインストールしてください。

1. README の前提条件を確認してください：bash、git、jq、GNU coreutils、opencode。不足があれば、自分のシステムへのインストール方法を教えて停止してください。システムパッケージを自分でインストールしないでください。
2. リポジトリを ~/.local/share/opencode-delegate にクローン、または既にあれば git pull してください。install.sh を読み、その後実行してください。~/.local/bin が PATH にないという警告が出たら、shell 設定に追加する行を教えてください。
3. ~/.claude/settings.json の permissions.allow に "Bash(oc-delegate:*)" を追加し、そのファイルの他の内容はすべて保持してください。編集できない場合は、追加する正確な JSON を表示してください。
4. ~/.claude/CLAUDE.md に claude-md-snippet.md を追記してください。ただし、そのファイルに "# opencode delegation" セクションが既にある場合は除きます。
5. README のスモークテストを一時的な git リポジトリで実行し、oc-delegate の出力と git diff を表示してください。
6. 変更内容を要約してください。委譲用のリポジトリを承認しないでください。初めて聞かれたときに答えます。
```

その後、スキルと `CLAUDE.md` のセクションが読み込まれるように、新しい Claude Code セッションを開始してください。

### 手動

1. クローンしてインストール：

   ```sh
   git clone https://github.com/EldinBegano/opencode-delegate.git
   cd opencode-delegate
   ./install.sh
   ```

   インストーラーはスキル、worker エージェント、`oc-delegate` を `~/.claude/skills/`、`~/.config/opencode/agents/`、`~/.local/bin/` にシンボリックリンクするので、`git pull` で更新されます。コピーしたい場合は `./install.sh --copy` を使ってください。内容が異なる既存ファイルは先にバックアップされます。

2. Claude が毎回確認なしで wrapper を実行できるようにします。これを `~/.claude/settings.json` に、既存の `permissions.allow` リストへマージして追加してください：

   ```json
   {
     "permissions": {
       "allow": ["Bash(oc-delegate:*)"]
     }
   }
   ```

3. [`claude-md-snippet.md`](claude-md-snippet.md) を `~/.claude/CLAUDE.md` に貼り付けてください。省略しないでください：スキルだけをインストールした場合、Claude は雑務を自分で書いてしまう傾向があります。このスニペットは無料モデル用に承認したリポジトリの一覧を保持します。Claude は新しいリポジトリでの最初の委譲前に一度だけ確認します。

4. スモークテスト：

   ```sh
   tmp=$(mktemp -d) && cd "$tmp" && git init -q
   printf 'a\nb\n' > list.txt && git add . && git commit -qm init
   oc-delegate "Append a line containing exactly 'c' to list.txt. Change no other file."
   git diff
   ```

   `model: opencode/...`、`M list.txt`、および `c` を追加する diff が表示されるはずです。

## 使い方

ほとんどの場合、何も呼び出す必要はありません。Claude は複数モジュールにまたがる docstring やテストといった大きな雑務を委譲し、無料モデルが何をしたか、何をチェックしたかを教えてくれます。小さな仕事は意図的に Claude に残されます。委譲する方がコストがかかるためです。

強制するには "delegate this"、"use opencode"、"use the free model" と言うか、`/opencode-delegate` と入力してください。

どの git リポジトリでも、自分で wrapper を実行できます：

```sh
oc-delegate "task"                                       # default model chain
oc-delegate -m opencode/deepseek-v4.1-flash-free "task"   # one model, no fallback
oc-delegate -c "pytest -q" "task"                        # run a check after the worker
```

`-c` を使うと、失敗したチェックは worker に修正のために戻され、最大 `-r` 回（デフォルト 2）繰り返されます。それでも失敗する場合、そのモデルの編集は巻き戻され、次のモデルが試されます。実行前にチェックがすでに失敗している場合はスキップされます。

### 設定

| 変数 | デフォルト | 効果 |
| --- | --- | --- |
| `OC_DELEGATE_MODELS` | 下記のチェーン | `-m` が指定されていないときに使われる、スペース区切りのモデルチェーン。 |
| `OC_DELEGATE_TIMEOUT` | `300` | モデル実行が強制終了され次のモデルが試されるまでの秒数。 |
| `OC_DELEGATE_IDLE` | `180` | 出力もネットワーク通信もない状態がこの秒数続くと、モデルはハングしたとみなされます。 |
| `OC_DELEGATE_TOTAL` | `540` | 実行全体の秒数。Claude Code の 600 秒の Bash タイムアウト以下に保ってください。 |
| `OC_DELEGATE_CHECK` | なし | `-c` が指定されていないときに使うチェックコマンド。 |
| `OC_DELEGATE_RETRIES` | `2` | モデルごとのチェック再試行回数。`-r` が指定されていないときに使われます。 |
| `OC_DELEGATE_CHECK_TIMEOUT` | `120` | チェック実行 1 回あたりの秒数。 |
| `OC_DELEGATE_SANDBOX` | `1` | `bwrap` なしで実行するには `0` に設定してください。 |
| `OC_DELEGATE_TAIL` | `40` | 表示する worker の要約行数。 |
| `OC_DELEGATE_LOG` | `~/.local/state/oc-delegate.log` | すべてのモデル試行のログ。`column -ts$'\t' ~/.local/state/oc-delegate.log` で表示できます。 |

### モデル

デフォルトのチェーンは `beam-free` → `deepseek-v4.1-flash-free` → `space-bunny-free` → `mimo-v2.6-flash-free` → `big-pickle` で、すべて `opencode/` 配下です。無料のラインナップは頻繁に変わります。これらが古くなったら、`opencode models | grep free` を確認し `OC_DELEGATE_MODELS` を設定してください。順序の決め方：[docs/development.md](docs/development.md#model-choice)。

## プライバシーと安全性

- **無料モデルはプロンプトを記録し、学習に使う場合があります。** worker がリポジトリで読むものはすべてそのプロバイダーに送られます。機密リポジトリでは委譲しないでください。
- worker の拒否リストはファイル名にのみマッチします。`config.yaml` 内の秘密は依然として読めます。
- worker は `.git` に触れられません。`bwrap` 使用時は、`.git` も読み取り専用でマウントされます。
- worker は `git diff` に表示されない gitignore 対象のファイルを編集できます。wrapper はそれらを `not in git diff` の下に一覧表示します。
- worker はテストやビルドを実行できません。Claude が結果を検証します。
- タスクプロンプトに秘密を含めないでください。

## 開発

`bats test` を実行してください（ネットワーク不要、約 1 分）。テスト、モデルベンチマーク、スキル評価は [docs/development.md](docs/development.md) に記載されています。

## アンインストール

```sh
rm ~/.claude/skills/opencode-delegate/SKILL.md ~/.config/opencode/agents/cc-worker.md ~/.local/bin/oc-delegate
rmdir ~/.claude/skills/opencode-delegate
```

その後、権限ルールと `CLAUDE.md` のセクションを削除してください。

## ライセンス

[MIT](LICENSE)
