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

ASCE、ACI、AISC、Eurocode、GB、JGJ を引用している場合は、まず規格・規準の正式な文書番号と版を確認します。条項、数式、適用範囲の確認は、正確な版の本文を利用でき、処理の許可が確認できた場合に限ります。研究で採用された版を、最新版に自動で置き換えることはありません。

### 最後に論文全体を読み直す

研究目的、方法、結果、限界、結論はつながっているか。新規性の主張が途中で広がっていないか。結論が根拠から導ける範囲を超えていないか。同じ試験体、境界条件、破壊モード、中心的な見解が章によって変わっていないかを確認します。

この確認には論文全体が必要です。該当箇所を明確に示せない懸念は正式な指摘にせず、「著者への質問」に残します。

## 3 つのレビューモード

| モード | 適した場面 |
| --- | --- |
| `fast` | 指導教員や共同研究者に送る前。明確な文章、略語、用語、本文中の引用と参考文献リストの対応を短時間で確認する |
| `deep` | 投稿前。論理、図表、引用の裏づけ、数値、規格・規準まで含めて確認する |
| `targeted` | 「略語だけ」「参考文献だけ」のように、指定した項目だけを確認する |

迷った場合は `deep` を選んでください。範囲を絞りたい場合は `targeted` を指定してください。指定されていない項目まで確認範囲を広げません。

## レビュー後に受け取るもの

通常は次の 2 ファイルを使います。

- `review-report.md`: 人が読むための報告書です。Blocker と Major を先に示し、可能な限り原文の位置、短い引用、根拠、具体的な修正案を付けます。
- `findings.json`: 追跡、絞り込み、後続の自動処理に使える構造化結果です。

`deep` レビューでは、参考文献、引用の裏づけ、数値、規準、レビュー範囲についても個別の記録を残します。通常の利用ではすべてを開く必要はありません。対応が必要な内容は主報告書にまとめられます。

入力が変わった場合、レビューは `stale` になります。必要な確認が実行されていない場合や証拠が限られる場合、レビューは `incomplete` になります。未解決の重要な主張、規格・規準、数値の確認項目がある場合は、投稿準備状況を別に `manual_confirmation_required` と表示します。「問題が見つからなかった」と「確認できなかった」を同じ扱いにはしません。

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

ルールベースの原稿チェック：

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>"
```

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

完全な `deep` レビューでは、入力ハッシュ、証拠アンカー、各レビュー工程の実行範囲、最終判定を一つの evidence spine に記録します。契約は [`references/evidence-spine.md`](references/evidence-spine.md)、引用の裏づけは [`references/claim-support.md`](references/claim-support.md)、規格・規準の利用権限と確認手順は [`references/standards-verification.md`](references/standards-verification.md) を参照してください。

主報告書のほか、`citation-report.md`、`references.json`、`claim-evidence.json`、`claim-support.json`、`quantitative.json`、`standards.json`、`artifact-manifest.json`、`evidence-ledger.json`、coverage 記録を生成できます。`--force` で上書きできるのは既存の報告書だけです。入力原稿や読み込んだ BibTeX ファイルは上書きしません。

回帰テスト：

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

現在のバージョンには 131 件の回帰テストがあります。このうち 31 件のネガティブテストは、偽の coverage、誤った出典の紐づけ、存在しない位置情報（locator）、出力パスの別名、規格・規準の利用権限チェックなどを検証します。主要スクリプトは Python 標準ライブラリだけで動作し、PDF 抽出には任意で `pdftotext` を使用します。

</details>
