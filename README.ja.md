<p align="center">
  <a href="./README.md">中文</a> · <a href="./README.en.md">English</a> · <strong>日本語</strong>
</p>

# Paper Auditor

Paper Auditor は、投稿前の原稿をもう一度細かく見てくれる第二の読者です。略語の初出定義を追跡し、要旨と結論の数値を照合し、重要な引用は引用文献の本文まで確認します。

> 要旨では 2.0% なのに、なぜ結論では 3.0% になっているのか。
>
> この文献は実在するが、ここに書かれた主張を本当に裏づけているのか。
>
> この略語はすでに定義されているのに、なぜ後で正式名称に戻っているのか。
>
> この実験は完了しているのに、なぜこの文は現在形のままなのか。

文単位の書き方から根拠、論文全体の整合性まで順に確認します。確定できる指摘には、原文の位置、根拠、重要度、具体的な修正案を付けます。資料が足りない場合は推測せず、確認できなかったことを明記します。原稿は既定では変更しません。

投稿直前まで待つ必要はありません。研究課題が見え始めた段階では「論文の主線カード」を作り、執筆途中では研究上のギャップ、目的、方法、結果、図表、解釈、結論が同じ話を続けているかを追跡します。論理を自動で作成・修復するとは主張せず、すでにつながった根拠と、まだ補う必要がある箇所を見える形にします。

現在の個人ルールは、構造工学、地震工学、耐震レジリエンス、セルフセンタリング構造、ロッキング構造を中心に調整しています。Earthquake Engineering & Structural Dynamics (EESD)、Engineering Structures、ASCE Journal of Structural Engineering の代表的な論文も文体の参考にしています。Word、LaTeX/BibTeX、PDF、Markdown、プレーンテキストを入力できます。

## クイックスタート

### 1. Codex にインストールする

Windows PowerShell:

```powershell
git clone https://github.com/JIE-jiee/paper-auditor.git "$env:USERPROFILE\.codex\skills\paper-auditor"
```

macOS / Linux:

```bash
git clone https://github.com/JIE-jiee/paper-auditor.git "$HOME/.codex/skills/paper-auditor"
```

インストール後、新しい Codex タスクを開きます。

### 2. Codex に次のように依頼する

```text
$paper-auditor を deep モードで使用し、
"<原稿または原稿フォルダの絶対パス>" をレビューしてください。

投稿先は Engineering Structures です。
原稿は変更せず、結果を新しい review ディレクトリに保存してください。
時制、略語、主要な数値、引用による裏づけ、
図表、論文全体の論理を重点的に確認してください。
```

パスは自分の `.docx`、`.tex`、`.pdf`、または論文フォルダに置き換えてください。`.bib`、コンパイル済み PDF、図表データ、付録、適法に入手した被引用文献の本文があれば、その場所も伝えてください。資料がそろうほど、確認できる範囲が広がります。

Paper Auditor は資料を確認してから原稿を通読し、重要な指摘を先に並べて報告書を作ります。修正するかどうかは利用者が決めます。明示的に依頼した場合に限り、原稿の複製を編集します。

## 白紙の段階から完成稿まで使える

`draft` は執筆中のモードです。原稿がどこまで進んでいるかを伝えると、未完成の章を投稿上の欠陥として扱うのではなく、主線と不足している証拠を更新します。

本文に「Table 1 を準備中」「Figure 3 で後ほど比較する」と明記されている場合、その参照は直ちに欠陥とはせず、見える形の草稿計画項目にします。同じ行にある別の未解決参照は引き続き確認します。

### 執筆前：論文の骨格を見える形にする

```text
$paper-auditor を draft モードで、論文計画の第二の読者として使用してください。

研究テーマは「<テーマ>」、投稿先は「<学術誌>」です。
現在あるのは研究課題、方法の案、資料だけで、完成原稿はありません。
これらがチャット内にしかない場合は、まず新しい研究概要ファイルに整理し、
そのファイルを今回の入力にしてください。入力ファイルがない間は計画の対話にとどめ、
証拠に基づく「審査完了」状態を生成しないでください。
論文全体を代筆しないでください。まず論文の主線カードを作成してください：
研究上のギャップ → 研究課題、目的、または仮説 → 方法 → 必要な証拠
→ 結果が答えるべき問い → 解釈 → 結論の境界。

各リンクで不足している証拠を示し、この工学論文に適した章構成を提案してください。
Analytical formulation、Numerical model、Experimental program、
Results and Discussion などの独自の章を認め、
医学論文の章名を機械的に当てはめないでください。
```

### 執筆途中：主線が離れていないか確かめる

```text
$paper-auditor を draft モードで使用し、次の原稿を確認してください：
"<原稿または原稿フォルダの絶対パス>"。

原稿は変更しないでください。論文の主線カードを更新し、
ギャップが目的につながっているか、各目的に方法があるか、
各方法から結果が得られているか、各結果をどの図表が支えるか、
解釈と暫定的な結論が現在の証拠を超えていないかを追跡してください。

未完成の部分は planned または not_yet_written とし、正式な誤りにしないでください。
最後に、次の執筆で最初に補うべき 3 点を示してください。
```

### 完成稿：投稿前に論証の輪を閉じる

```text
$paper-auditor を deep モードで使用し、
"<原稿または原稿フォルダの絶対パス>" をレビューしてください。

投稿先は「<学術誌>」です。原稿は変更しないでください。
文章、略語、数値、引用、図表、規格・規準に加えて、
最終的な論文の主線カードを作成し、次を追跡してください：
題名と要旨 → 研究上のギャップ → 研究課題、目的、または仮説 → 方法
→ 結果と図表の証拠 → 解釈 → 結論。

本文に根拠がない要旨の主張、方法が示されていない結果、
対応する結果がない方法、証拠を超えた結論を重点的に確認してください。
不確かな点は推測せず、「著者への質問」に入れてください。
```

## 原稿を読みながら何を確かめるか

### まず文章の流れと時制を見る

この文は完了した実験を述べているのか、それとも現在も成り立つ結論を述べているのか。個人ルールでは、実施済みの研究作業には過去形、一般的な結論と提案モデルまたは提案システムの性能には現在形を使います。完了した開発、キャリブレーション、実験の動作は過去形のままです。

文法、米国式または英国式の綴り、専門用語、記号、単位、部材名、ハイフン表記も確認します。要旨と本文は別々に扱い、それぞれで初出時に定義し、その後は略語に統一します。再定義、大文字と小文字の揺れ、正式名称への逆戻りも指摘します。

### 食い違う数値を見逃さない

数式の記号が先に定義されているか、添字の意味が変わっていないか、次元と単位換算が正しいか、記載された割合を再計算できるかを確認します。要旨、本文、表、結論に現れる主要な数値も照合します。

図が十分に明瞭であれば、図中のピークと本文の記述も比較します。読み取りが曖昧な値は手動確認の対象とし、確定した誤りとして扱いません。

### 重要な引用にはもう一つ質問する

最初に、本文中の引用と参考文献リストの対応を確認します。メタデータ照会が許可され、利用できる場合は、題名、著者、掲載誌、年、DOI、訂正、撤回の状態も照合します。

次の確認がさらに重要です。文献が実在しても、引用箇所の主張を支えているとは限りません。適法な本文を利用できる場合は、「論文中の主張 → 引用位置 → 被引用文献の該当箇所」を一件ずつたどり、`supports`、`partially_supports`、`does_not_support`、`unable_to_verify` のいずれかで判定します。複数文献をまとめて引用している場合も、一編ずつ確認します。

### 図表、数式、規格・規準を振り返る

図、表、数式の番号に加え、本文での初回参照、LaTeX ラベル、相互参照、文献キーを確認します。図表が示す方向、値の大きさ、比較関係が本文の説明と一致するかも調べます。

ここでは図表を装飾ではなく論文の証拠として扱います。その図表がどの研究上の問いに答えるのか、キャプションだけで対象、条件、指標、単位、統計量、基準、各パネルの意味が分かるか、本文の重要な判断を図表までたどれるかを確認します。判読できない場合や対応が曖昧な場合は、確認待ちとして残します。

ASCE、ACI、AISC、Eurocode、GB、JGJ を引用している場合は、まず規格・規準の正式な文書番号と版を確認します。条項、数式、適用範囲の確認は、正確な版の本文を利用でき、処理の許可が確認できた場合に限ります。研究で採用された版を、最新版に自動で置き換えることはありません。

### 最後に論文全体を読み直す

まず論文を主線カードとして整理します。研究上のギャップは目的または仮説につながっているか、その目的は方法として実行されているか、方法から結果が得られているか、結果は図表で支えられ、範囲を守って解釈されているか、結論は証拠の範囲内にあるかを追跡します。題名と要旨の重要な記述も、本文まで戻れる必要があります。

工学論文に IMRAD という見出しがそのまま使われていないことを理由に誤りとはしません。`Analytical formulation`、`Numerical model`、`Experimental program`、`Parametric study`、統合された `Results and Discussion` は、実際に担う役割に応じて主線へ配置します。役割が曖昧な場合は質問にします。

完成稿の確認には論文全体が必要であり、最終的な学術判断は著者が行います。Paper Auditor は切れたつながり、矛盾、根拠のない主張を見つける手助けをしますが、すべての学術的論理を自動で理解・修復するとは主張しません。位置を示せない懸念は正式な指摘にせず、「著者への質問」に残します。

## 4 つの作業モード

| モード | 適した場面 |
| --- | --- |
| `draft` | 計画中または執筆中。主線カードを更新し、未完成のリンクを質問と次の作業に変える。投稿可能とは判定しない |
| `fast` | 指導教員や共同研究者に送る前。明確な文章、略語、用語、本文中の引用と参考文献リストの対応を短時間で確認する |
| `deep` | 投稿前。論理、図表、引用の裏づけ、数値、規格・規準まで含めて確認する |
| `targeted` | 「略語だけ」「参考文献だけ」のように、指定した項目だけを確認する |

執筆中は `draft`、完成稿の投稿前確認には `deep` を使用してください。範囲を絞る場合は `targeted` を指定し、指定外へ広げません。

## レビュー後に受け取るもの

通常は次の 2 ファイルを使います。

- `review-report.md`: 人が読むための報告書です。Blocker と Major を先に示し、可能な限り原文の位置、短い引用、根拠、具体的な修正案を付けます。
- `findings.json`: 追跡、絞り込み、後続の自動処理に使える構造化結果です。

`deep` レビューでは、参考文献、引用の裏づけ、数値、規準、レビュー範囲についても個別の記録を残します。通常の利用ではすべてを開く必要はありません。対応が必要な内容は主報告書にまとめられます。

`draft` と完成稿の論理レビューでは、主報告書の前半に主線カードも示します。満たされた機能リンクと未解決リンク、本文に根拠がない要旨や結論、対応していない方法と結果、重要な図表が支える内容を一覧できます。明示された予定図表・ラベル、著者への質問、次の執筆作業は、論文の欠陥とは別に保ちます。

入力が変わった場合は `stale`、必要な確認が未実行または証拠不足なら `incomplete` です。未解決の重要な主張、規格・規準、数値には `manual_confirmation_required` を使います。完成稿の主線が `unresolved` のままなら `ready_given_evidence` にはなりません。正式な指摘があれば `revision_required`、なければ著者確認が必要です。問題のない部分稿は `draft_in_progress` であり、「投稿可能」にはなりません。「問題なし」と「未確認」を同じ扱いにはしません。

## 自分の書き方に合わせる

この Skill は個人ルールを持たせることを前提にしています。次の内容を調整できます。

- 英国式または米国式の英語、既定モード、重要度、プライバシー設定は [`references/personal-profile.json`](references/personal-profile.json)
- 推奨用語、避ける表現、略語、別名は [`references/terminology.tsv`](references/terminology.tsv)
- よく使う記号、次元、初出定義の要件は [`references/quantity-profile.tsv`](references/quantity-profile.tsv)
- 投稿先の文体と分野固有の推論ルールは [`references/journal-benchmarks.md`](references/journal-benchmarks.md) と [`references/domain-style.md`](references/domain-style.md)

まず実際の原稿で使い、どの指摘を採用したか、却下したか、原稿固有の例外だったかを記録してください。繰り返し現れ、実際に役立ったルールだけを書き戻します。手順は [`references/personalization-guide.md`](references/personalization-guide.md) を参照してください。

## 判断できないときは、そう明記する

- オンライン照合では、既定で DOI、または最小限の題名、著者、年だけを送信します。未公開の本文や図を、許可なく外部サービスへ送信しません。
- `not_found` は信頼できる一致が見つからなかったという意味です。文献捏造の証拠ではありません。
- 被引用文献の本文または同等の直接証拠がなければ、主張の裏づけは `unable_to_verify` に限られます。
- 規格・規準の本文がローカルにあっても、条項単位の処理には権利表明付きの source map が必要です。ASCE や ACI など `permission-required` の項目には、出版社の許可記録も必要です。
- 文章と相互参照の確認には編集可能な原稿が適しています。PDF はテキスト抽出、レイアウト、図の可読性に影響されます。
- このツールは確認範囲と追跡可能性を高めます。最終判断は著者、分野の専門家、学術誌の編集者が行います。

<details>
<summary>上級者向け：スクリプト、全出力、テスト</summary>

通常は Codex で `$paper-auditor` を呼び出すだけで十分です。処理を自分で制御する場合は、最初に [`SKILL.md`](SKILL.md) を読んでください。

Windows PowerShell 5.1 で中国語の CLI 表示が文字化けする場合は、以下の `python` を `python -X utf8` に置き換えてください。

ルールベースの原稿チェック：

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>" `
  --manuscript-stage complete
```

執筆途中では `complete` を `draft` に変更します。明示された将来の図表・ラベルは `planned_items` に入ります。

`draft` レビューの evidence spine と主線マップを作成します：

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode draft --output-dir "<new-review-root>\spine"
python "<skill-root>\scripts\manuscript_map.py" init `
  "<new-review-root>\manuscript-map.json" --stage draft
python "<skill-root>\scripts\manuscript_map.py" validate `
  "<new-review-root>\manuscript-map.json" `
  --ledger "<new-review-root>\spine\evidence-ledger.json" `
  --completion draft --output-dir "<new-review-root>\manuscript-map-review"
```

完成原稿の `deep` evidence spine と主線マップを作成します：

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep --output-dir "<new-review-root>\spine"
python "<skill-root>\scripts\manuscript_map.py" init `
  "<new-review-root>\manuscript-map.json" --stage complete
python "<skill-root>\scripts\manuscript_map.py" validate `
  "<new-review-root>\manuscript-map.json" `
  --ledger "<new-review-root>\spine\evidence-ledger.json" `
  --completion complete --output-dir "<new-review-root>\manuscript-map-review"
```

どちらのモードでも、主線カード、ノード、リンク、現在の `evidence_ids` は、
キーワード推測ではなく原稿と著者の判断から記入してください。

生成側の `planned_items` は最終的な証拠アンカー確認後に `draft_planned_items` となります。
レビュー担当者の `next_writing_tasks` は別の依存順タスクリストで、重複登録されません。

書誌メタデータの照合：

```powershell
python "<skill-root>\scripts\verify_references.py" "<bibliography-or-manuscript>" `
  --output-dir "<new-verification-dir>"
```

数式、単位、数値の整合性：

```powershell
python "<skill-root>\scripts\quantitative_checks.py" "<manuscript.tex>" `
  --quantity-profile "<skill-root>\references\quantity-profile.tsv" `
  --output "<new-review-dir>\quantitative.json"
```

規格・規準の台帳：

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" `
  --output-dir "<new-standard-review-dir>"
```

`draft` と完全な `deep` レビューでは、入力ハッシュ、証拠アンカー、確認範囲、最終判定を一つの evidence spine に記録します。論文の主線は [`references/manuscript-architecture.md`](references/manuscript-architecture.md)、契約は [`references/evidence-spine.md`](references/evidence-spine.md)、引用主張の支持性は [`references/claim-support.md`](references/claim-support.md)、規格・規準は [`references/standards-verification.md`](references/standards-verification.md) を参照してください。

主報告書のほか、`manuscript-map-validation.json`、`manuscript-map-traceability.md`、`citation-report.md`、`references.json`、`claim-evidence.json`、`claim-support.json`、`quantitative.json`、`standards.json`、`artifact-manifest.json`、`evidence-ledger.json`、coverage 記録を生成できます。`--force` で上書きできるのは既存の報告書だけです。入力原稿や読み込んだ BibTeX ファイルは上書きしません。

回帰テスト：

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

現在のバージョンには 196 件の回帰テストがあります。必須 pass の not-applicable 回避、planned item のなりすまし、構造校正結果による意味レビューのなりすまし、未対応の主線ノード、偽の coverage、古い、または原稿に結び付かない ledger、誤った出典、存在しない位置情報、出力パスの別名、規格・規準の利用権限などのネガティブ境界も含みます。主要スクリプトは Python 標準ライブラリだけで動作し、PDF 抽出には任意で `pdftotext` を使用します。

</details>
