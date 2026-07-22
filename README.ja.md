<p align="center">
  <a href="./README.md">中文</a> · <a href="./README.en.md">English</a> · <strong>日本語</strong>
</p>

# Paper Auditor

投稿前の学術論文を、根拠に基づいて体系的に点検するためのカスタマイズ可能な Codex Skill です。構造工学、地震工学、耐震レジリエンス、セルフセンタリング構造、ロッキング構造を主な対象とし、個人プロファイルや用語ルールを変更することで他分野にも適用できます。

## 主な点検項目

- 文法、文脈に応じた時制、英語表記の種類。
- 略語の初出時定義、重複定義、一貫性。
- 専門用語、記号、単位、ハイフン、部材名称。
- 図、表、数式の番号、本文中の参照、意味上の整合性。
- LaTeX のラベル、相互参照、引用、参考文献キー。
- 本文中の引用と参考文献リストの対応。
- 文献の実在性、書誌メタデータ、撤回・訂正状況。
- 要旨、本文、表、図、結論の間における数値の整合性。
- 目的、方法、結果、限界、結論、主張のつながり。
- 図表が本文中の傾向、値、比較を実際に裏付けているか。

Word、LaTeX/BibTeX、PDF、Markdown、プレーンテキストに対応します。PDF のテキスト抽出には、必要に応じて `pdftotext` を使用します。

## レビューモード

| モード | 用途 |
| --- | --- |
| `fast` | 決定論的チェックと重点的な編集レビュー |
| `deep` | 意味内容、論理、図版、書誌情報を含む投稿前の総合レビュー |
| `targeted` | ユーザーが指定した項目だけを点検 |

決定論的スクリプトは、書式、用語、引用、相互参照について再現可能なチェックを行います。意味内容、論理、主張、図版に関する総合的な判断は、`SKILL.md` の手順に従って Codex が行います。書誌メタデータの検証だけでは、文献が特定の主張を裏付けているかは判断できません。

## Codex Skill としてインストール

リポジトリ全体を個人用 Skill ディレクトリにクローンします。`SKILL.md`、`references/`、`scripts/` の相対配置は変更しないでください。

Windows PowerShell：

```powershell
git clone https://github.com/JIE-jiee/paper-auditor.git "$env:USERPROFILE\.codex\skills\paper-auditor"
```

macOS / Linux：

```bash
git clone https://github.com/JIE-jiee/paper-auditor.git "$HOME/.codex/skills/paper-auditor"
```

その後、新しい Codex タスクで次のように依頼します。

```text
$paper-auditor を deep モードで使用し、path/to/main.tex を投稿前レビューしてください。
原稿は変更せず、新しい review ディレクトリに結果を出力してください。
```

## コマンドラインでの使用

決定論的な原稿チェック：

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>"
```

書誌メタデータの検証：

```powershell
python "<skill-root>\scripts\verify_references.py" "<bibliography-or-manuscript>" `
  --output-dir "<new-verification-dir>"
```

プライバシー制御：

```text
--offline          抽出のみを行い、ネットワークへ接続しない
--no-title-search  DOI だけで検索し、題名・著者・年を送信しない
```

## 出力

- `review-report.md` — 人が読めるレビュー報告。
- `findings.json` — ID、重要度、確信度、状態、位置、根拠、修正案を含む構造化データ。
- `citation-report.md` と `references.json` — 別ディレクトリに保存される書誌検証結果。

既定では原稿を変更せず、結果は別のディレクトリに出力します。`--force` で上書きできるのは既存の報告ファイルだけであり、入力原稿や読み込んだ BibTeX ファイルは上書きしません。

## カスタマイズ

| ファイル | 用途 |
| --- | --- |
| `references/personal-profile.json` | 既定モード、英語表記、重要度、プライバシー設定 |
| `references/terminology.tsv` | 推奨用語、禁止用語、略語、別名 |
| `references/domain-style.md` | 構造・地震工学の用語と推論ルール |
| `references/journal-benchmarks.md` | EESD、Engineering Structures、ASCE 各誌のスタイル基準 |
| `references/personalization-guide.md` | 個人ルールを安全に更新する方法 |

## プライバシーと制限

- 未公開の本文や図版を、許可なく外部サービスへ送信しません。
- 既定のオンライン検証で送信するのは、DOI または最小限の題名・著者・年だけです。
- `not_found` は十分な一致を確認できなかったという意味であり、捏造の証拠ではありません。
- 引用文献が近くの主張を裏付けるかの判断には、原文または同等に直接的な証拠が必要です。
- 本ツールは点検範囲と追跡可能性を高めますが、著者、専門家、編集者の最終判断に代わるものではありません。

## テスト

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

現行版には 32 件の回帰テストがあります。主要スクリプトは Python 標準ライブラリだけで動作し、PDF 抽出用の `pdftotext` は任意の依存関係です。
