<p align="center">
  <a href="./README.md">中文</a> · <a href="./README.en.md">English</a> · <strong>日本語</strong>
</p>

# Paper Auditor

投稿前の学術論文を、根拠に基づいて体系的に点検するためのカスタマイズ可能な Codex Skill です。構造工学、地震工学、耐震レジリエンス、セルフセンタリング構造、ロッキング構造を主な対象とし、個人プロファイルや用語ルールを変更することで他分野にも適用できます。

## 主な点検項目

- 文法と英語表記の種類。
- 実施済みの研究作業は過去形、一般的結論と提案モデルの性能は現在形。
- 要旨と本文で略語を別々に初出定義し、その後は略語に統一。
- 専門用語、記号、単位、ハイフン、部材名称。
- 図、表、数式の番号、本文中の参照、意味上の整合性。
- LaTeX のラベル、相互参照、引用、参考文献キー。
- 本文中の引用と参考文献リストの対応。
- 文献の実在性、書誌メタデータ、撤回・訂正状況。
- 被引用文献の原文が論文中の主張を支持するかを、支持・部分的支持・不支持・検証不能に分けて判定。
- 数式記号、初出時の定義、スコープ、次元、単位換算、百分率、セクション間の主要数値の整合性。
- ASCE、ACI、AISC、Eurocode、GB、JGJ などの完全な規格番号、版、条項位置、式、適用範囲。
- 目的、方法、結果、限界、結論、主張のつながり。
- 図表が本文中の傾向、値、比較を実際に裏付けているか。
- 入力、根拠アンカー、各レビューパス、最終報告が同じ版に基づくか。未実行または証拠不足の項目を「問題なし」と扱いません。

Word、LaTeX/BibTeX、PDF、Markdown、プレーンテキストに対応します。PDF のテキスト抽出には、必要に応じて `pdftotext` を使用します。

## レビューモード

| モード | 用途 |
| --- | --- |
| `fast` | 決定論的チェックと重点的な編集レビュー |
| `deep` | 意味内容、論理、図版、書誌情報を含む投稿前の総合レビュー |
| `targeted` | ユーザーが指定した項目だけを点検 |

決定論的スクリプトは、書式、用語、引用、相互参照について再現可能なチェックを行います。意味内容、論理、主張、図版に関する総合的な判断は、`SKILL.md` の手順に従って Codex が行います。書誌メタデータの検証だけでは、文献が特定の主張を裏付けているかは判断できません。

## 4つの中核エビデンスチェーン

| 機能 | エビデンスチェーン | 超えてはならない境界 |
| --- | --- | --- |
| 引用の支持性 | 論文中の主張 → 引用位置 → 被引用文献の該当箇所 → 4段階判定 | 全文がなければ `unable_to_verify` とし、不支持の証拠にはしない |
| 数式・単位・数値 | 記号/定義 → 単位と次元 → 計算 → セクション、表、図の照合 | 図からの推定値、弱い対応、未解決の式はレビュー候補にとどめる |
| 工学規準 | 完全な番号/版 → 条項または式 → 制限と例外 → 研究への適用性 | 新版が自動的に支配版になるわけではなく、条項内容には正確な原文が必要 |
| レビュー完全性 | 入力 manifest → 共通 evidence ledger → pass coverage → 決定論的裁定 | 入力の変更は `stale`、pass 結果の変更・欠落は `incomplete` とする |

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

総合レビューの前に共通 evidence spine を作成します：

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep --output-dir "<new-review-root>\spine" `
  --artifact "bibliography=<references.bib>"
```

各 pass の後に `record-pass`、全範囲の記録後に `finalize` を実行します。完全な契約、証拠能力、意味的 Major/Blocker の再確認形式は `references/evidence-spine.md` を参照してください。
規格全文を裸の `standard_source` として登録することはできません。`--standards-source-map` を使用し、ローカル処理モード、権利表明、ASCE/ACI 等で必要な出版社許諾記録を先に確認します。未検証の主張、権利ゲートで停止した規格タスク、数値レビュー候補は `manual_checks` に残り、「問題なし」として黙って処理されません。
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

数式・単位・数値の整合性：

```powershell
python "<skill-root>\scripts\quantitative_checks.py" "<manuscript.tex>" `
  --quantity-profile "<skill-root>\references\quantity-profile.tsv" `
  --output "<new-review-dir>\quantitative.json"
```

引用支持性の証拠準備と確定：

```powershell
python "<skill-root>\scripts\claim_support.py" prepare "<manuscript>" `
  --references-json "<citation-review-dir>\references.json" `
  --sources-dir "<lawful-local-paper-sources>" `
  --output-dir "<new-claim-evidence-dir>" --scope priority

python "<skill-root>\scripts\claim_support.py" finalize `
  "<claim-evidence-dir>\claim-evidence.json" "<claim-decisions.json>" `
  --output-dir "<new-claim-result-dir>"
```

工学規準台帳（既定はメタデータのみ）：

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" `
  --output-dir "<new-standard-review-dir>"
```

規格全文は、明示的な `--source-map` が権利ゲートを通過した場合に限りローカルで処理します。ASCE と ACI については、出版社の許諾記録も必要です。

プライバシー制御：

```text
--offline          抽出のみを行い、ネットワークへ接続しない
--no-title-search  DOI だけで検索し、題名・著者・年を送信しない
```

## 出力

- `review-report.md` — 人が読めるレビュー報告。
- `findings.json` — ID、重要度、確信度、状態、位置、根拠、修正案を含む構造化データ。
- `citation-report.md` と `references.json` — 別ディレクトリに保存される書誌検証結果。
- `claim-evidence.json` と `claim-support.json` — 主張と原文の証拠チェーン、および最終判定。
- `quantitative.json` — 記号、単位、次元、計算、反復値、レビュー候補。
- `standards.json` と `standards-report.md` — 規格版の台帳、条項・適用性の確認タスク。
- `artifact-manifest.json`、`evidence-ledger.json`、`coverage.json`、`final-evidence-ledger.json` — 入力ハッシュ、安定した原稿/外部原文の根拠 ID、pass 状態、古い報告の判定根拠。

既定では原稿を変更せず、結果は別のディレクトリに出力します。`--force` で上書きできるのは既存の報告ファイルだけであり、入力原稿や読み込んだ BibTeX ファイルは上書きしません。

## カスタマイズ

| ファイル | 用途 |
| --- | --- |
| `references/personal-profile.json` | 既定モード、英語表記、重要度、プライバシー設定 |
| `references/terminology.tsv` | 推奨用語、禁止用語、略語、別名 |
| `references/domain-style.md` | 構造・地震工学の用語と推論ルール |
| `references/claim-support.md` | 引用支持性の判定手順と決定形式 |
| `references/quantity-profile.tsv` | 個人用の記号定義、次元、定義必須ルール |
| `references/standards-registry.json` | 規格版メタデータと全文処理ポリシー |
| `references/standards-verification.md` | 条項、式、適用性、権利ゲートの手順 |
| `references/journal-benchmarks.md` | EESD、Engineering Structures、ASCE 各誌のスタイル基準 |
| `references/personalization-guide.md` | 個人ルールを安全に更新する方法 |
| `references/evidence-spine.md` | 共通 manifest、根拠台帳、coverage、最終裁定の手順 |

## プライバシーと制限

- 未公開の本文や図版を、許可なく外部サービスへ送信しません。
- 既定のオンライン検証で送信するのは、DOI または最小限の題名・著者・年だけです。
- `not_found` は十分な一致を確認できなかったという意味であり、捏造の証拠ではありません。
- 引用文献が近くの主張を裏付けるかの判断には、原文または同等に直接的な証拠が必要です。
- 規格 PDF がローカルに存在するだけでは自動処理の許可になりません。条項確認には明示的な権利表明と出版社許諾のゲートを適用します。
- 本ツールは点検範囲と追跡可能性を高めますが、著者、専門家、編集者の最終判断に代わるものではありません。

## テスト

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

現行版には 131 件の回帰テストがあり、そのうち 31 件の負例は偽装された coverage、誤った出典結合、虚偽 locator、出力パスの別名、権利ゲートなどの対抗境界を検証します。主要スクリプトは Python 標準ライブラリだけで動作し、PDF 抽出用の `pdftotext` は任意の依存関係です。
