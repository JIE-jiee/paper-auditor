<p align="center">
  <strong>中文</strong> · <a href="./README.en.md">English</a> · <a href="./README.ja.md">日本語</a>
</p>

# Paper Auditor

Paper Auditor 是一位有点较真的投稿前读者。把稿子交给它，它会记住你前面怎样定义缩写，回头核对摘要和结论里的数字，也会顺着关键引用往原文追。

> 摘要里是 2.0%，为什么到了结论变成 3.0%？
>
> 这篇文献确实存在，但它真的支持这里的观点吗？
>
> 这个缩写已经定义过了，后面怎么又写回了全称？
>
> 这项试验已经完成，这句话为什么还在用现在时？

它会从行文一路检查到证据和全文一致性。能确认的问题会带上原文位置、依据、严重程度和修改建议；材料不够时，它会明确写出“无法核验”，不会替你猜。原稿默认保持不变。

它现在主要面向结构工程、地震工程、抗震韧性、自复位与摇摆体系，并参考 EESD、Engineering Structures 和 ASCE Journal of Structural Engineering 的代表性论文风格。Word、LaTeX/BibTeX、PDF、Markdown 和纯文本都可以作为输入。

## 快速开始

### 1. 装进 Codex

Windows PowerShell：

```powershell
git clone https://github.com/JIE-jiee/paper-auditor.git "$env:USERPROFILE\.codex\skills\paper-auditor"
```

macOS / Linux：

```bash
git clone https://github.com/JIE-jiee/paper-auditor.git "$HOME/.codex/skills/paper-auditor"
```

安装后新建一个 Codex 任务。

### 2. 把这段话交给 Codex

```text
使用 $paper-auditor 的 deep 模式审核
"<论文或论文文件夹的绝对路径>"。

目标期刊是 Engineering Structures。
保持原稿不变，把结果写入新的 review 目录。
重点检查时态、缩写、关键数值、引用支持关系、图表和全文逻辑。
```

把路径换成你的 `.docx`、`.tex`、`.pdf` 或论文文件夹即可。有 `.bib`、编译后的 PDF、图表数据、附录，或合法取得的被引文献全文时，也可以一并告诉它。材料越完整，能够核验的内容越多。

接下来它会先清点材料并通读论文，再把重要问题排在前面，最后生成报告。是否修改稿件由你决定；只有你明确要求时，它才会在副本上改。

## 它读稿时会追问什么

### 先把语言理顺

这句话是在描述已经完成的试验，还是仍然成立的结论？Paper Auditor 按个人规则处理时态：已经开展的研究工作用过去时，通用结论与所提模型或体系的性能用现在时，已经完成的开发、标定和试验动作仍用过去时。

它还会检查语法、英式或美式拼写、术语、符号、单位、构件名称和连字符。摘要与正文各有一套缩写作用域：各自首次定义，之后统一使用缩写。重复定义、大小写漂移，或者定义后又写回全称，都会被指出来。

### 盯住会互相打架的数字

它会追踪公式中的符号是否先定义、上下标含义是否变化、量纲和单位换算是否成立，也会重算明确给出的百分比。摘要、正文、表格和结论里的关键数值会放在一起核对。

图件足够清晰时，它还会比较图中峰值和正文陈述。看不清的数值只会进入待确认项，不会被包装成确定错误。

### 对引用多问一句

第一步是检查正文引用与参考文献表能否对应。在你允许在线查询且查询服务可用时，它还会核对题名、作者、期刊、年份、DOI、撤稿或更正状态。

第二步更重要：文献存在，不代表它支持当前这句话。拿到合法的被引原文后，Paper Auditor 会沿着“论文主张 → 引用位置 → 被引原文”逐条核对，并给出支持、部分支持、不支持或无法核验。引用簇会逐篇判断，不会把几篇文献混成一个结论。

### 回头核对图表、公式和工程标准

图、表、公式的编号、首次引用、LaTeX 标签、交叉引用和文献键会一起检查。它也会看图表呈现的方向、幅值和比较关系是否真的支持正文。

结构工程稿件中出现 ASCE、ACI、AISC、Eurocode、GB 或 JGJ 时，它会先核对完整代号和版本。有准确版本原文且处理权限允许时，才继续复核条款、公式和适用范围。新版标准不会被自动当成研究采用的控制版本。

### 最后退后一步看整篇

研究目标、方法、结果、局限和结论是否接得上？创新点有没有换范围？结论是否跑得比证据更远？同一个试件、边界条件、破坏模式或核心观点在不同章节有没有悄悄变化？

这一步需要通读全文。没有可复现位置的担忧不会被硬写成正式错误，而会放进“给作者的问题”中。

## 三种审核节奏

| 模式 | 什么时候用 |
| --- | --- |
| `fast` | 发给导师或合作者前，先扫一遍明确的语言、缩写、术语，以及正文引用与参考文献对应问题 |
| `deep` | 投稿前完整审核，加入逻辑、图表、文献支持性、数值和标准复核 |
| `targeted` | 只查一个方向，例如“只查缩写”或“只核对参考文献” |

拿不准时用 `deep`。如果只想检查某一类问题，请明确写 `targeted`，它不会自行扩大范围。

## 审完以后你会拿到什么

最常用的是两份文件：

- `review-report.md`：给人看的审核报告。Blocker 和 Major 问题排在前面，每条尽量带原文位置、短引文、依据和可执行的修改建议。
- `findings.json`：给后续追踪、筛选或自动化处理用的结构化结果。

深度审核还会保留文献、主张支持性、公式与数值、工程标准和审核覆盖情况的单独记录。普通使用时不必逐个打开它们，主报告已经汇总了需要你处理的内容。

如果输入后来发生变化，旧结果会标为 `stale`。某个必要环节没有运行或证据受限时，审核状态会标为 `incomplete`；尚待解决的重点主张、标准或数值候选会另外把投稿准备状态标为 `manual_confirmation_required`。“没有查到问题”和“没有完成核验”不会混在一起。

## 把它调成你的写作习惯

这套 Skill 本来就是为个人使用准备的。你可以逐步教它：

- 你习惯的英式或美式英语、默认审核模式和隐私偏好，写在 [`references/personal-profile.json`](references/personal-profile.json)；
- 你所在方向的首选术语、禁用词、缩写和别名，写在 [`references/terminology.tsv`](references/terminology.tsv)；
- 常用符号、量纲和首次定义要求，写在 [`references/quantity-profile.tsv`](references/quantity-profile.tsv)；
- 期刊风格与领域推理规则，分别放在 [`references/journal-benchmarks.md`](references/journal-benchmarks.md) 和 [`references/domain-style.md`](references/domain-style.md)。

先用真实稿件跑一轮，再记录哪些建议被接受、哪些是稿件特例。只有反复出现且确认有效的习惯，才值得写回个人规则。具体方法见 [`references/personalization-guide.md`](references/personalization-guide.md)。

## 它也会克制地说“不知道”

- 默认在线核验只发送 DOI，或最少量的题名、作者和年份元数据。未经允许，不会把未发表全文或图件发送给外部服务。
- `not_found` 只表示没有找到足够可靠的匹配，不能据此认定文献伪造。
- 没有被引原文或同等直接证据时，引用支持性只能写“无法核验”。
- 标准全文即使在本地存在，也要先通过带权利声明的来源映射，才会进入条款级处理。ASCE、ACI 等标记为需要许可的条目，还要提供出版方许可记录。
- 编辑源文件更适合文字和交叉引用检查。PDF 会受到文本提取质量、版面和图件清晰度影响。
- 它帮助作者提高审核覆盖率和可复核性，最终判断仍由作者、领域专家和期刊编辑完成。

<details>
<summary>进阶：命令行、完整产物与测试</summary>

多数用户只需要在 Codex 中调用 `$paper-auditor`。如果你想自己控制流程，请先阅读 [`SKILL.md`](SKILL.md)。

确定性论文检查：

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>"
```

书目元数据核验：

```powershell
python "<skill-root>\scripts\verify_references.py" "<bibliography-or-manuscript>" `
  --output-dir "<new-verification-dir>"
```

公式、单位与数值一致性：

```powershell
python "<skill-root>\scripts\quantitative_checks.py" "<manuscript.tex>" `
  --quantity-profile "<skill-root>\references\quantity-profile.tsv" `
  --output "<new-review-dir>\quantitative.json"
```

工程标准台账：

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" `
  --output-dir "<new-standard-review-dir>"
```

完整 `deep` 审核使用统一的证据主干，记录输入哈希、证据锚点、各审核环节的覆盖状态和最终裁决。操作契约见 [`references/evidence-spine.md`](references/evidence-spine.md)，引用支持性流程见 [`references/claim-support.md`](references/claim-support.md)，工程标准权限与核验流程见 [`references/standards-verification.md`](references/standards-verification.md)。

除主报告外，流程可生成 `citation-report.md`、`references.json`、`claim-evidence.json`、`claim-support.json`、`quantitative.json`、`standards.json`、`artifact-manifest.json`、`evidence-ledger.json` 和覆盖记录。`--force` 只能覆盖已有报告，不能覆盖输入原稿或已读取的 BibTeX 文件。

运行回归测试：

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

当前版本包含 131 项回归测试，其中 31 项负向用例专门检查伪造覆盖状态、错绑来源、虚假定位、输出别名和标准权限门槛等边界。核心脚本只依赖 Python 标准库；PDF 文本提取可选用 `pdftotext`。

</details>
