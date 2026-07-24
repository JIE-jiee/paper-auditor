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

它也不必等到投稿前才出现。刚有研究问题时，它可以和你一起搭一张“论文主线卡”；写到一半时，它会盯住研究缺口、目标、方法、结果、图表和结论是不是还在讲同一件事。它不会替你自动补出一套逻辑，而是把已经写下的依据和尚未接上的环节摊开，让你知道下一步该补什么。

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

## 从空白页到完整稿，都可以叫它进来

`draft` 是写作中的工作模式。告诉它稿子进行到哪一步，它会先维护主线和待补证据，不会把尚未完成的章节一律当成投稿缺陷。

如果正文明确写着“Table 1 正在整理”或“Figure 3 将补充比较”，它会把这些引用列进“草稿计划项”，而不是先判成论文错误；同一行里没有计划依据的缺失引用仍会继续检查。

### 写作前：先把论文骨架想清楚

```text
使用 $paper-auditor 的 draft 模式，作为写作中的第二读者。

研究主题是“<主题>”，目标期刊是“<期刊>”。
我现在只有研究问题、方法设想和已有资料，还没有完整稿件。
如果这些内容只在聊天里，先把它们整理成一个新的研究简报文件，
再把该文件作为本轮输入；没有输入文件时只做规划讨论，
不要生成“已完成审核”的证据化状态。
不要代写整篇论文。先建立一张论文主线卡：
研究缺口 → 研究问题、目标或假设 → 方法 → 需要取得的证据
→ 结果应回答的问题 → 解释 → 结论边界。

指出每一环还缺什么证据，并建议合适的工科论文结构。
允许使用 Analytical formulation、Numerical model、
Experimental program、Results and Discussion 等自定义章节，
不要机械套用医学论文的章节名称。
```

### 写到一半：看看主线有没有走散

```text
使用 $paper-auditor 的 draft 模式检查这份正在写的稿件：
"<论文或论文文件夹的绝对路径>"。

保持原稿不变。更新论文主线卡，并逐项追踪：
研究缺口是否落到目标，目标是否有对应方法，
方法是否已经产生结果，结果由哪张图或表支撑，
讨论和暂定结论是否超出当前证据。

尚未完成的部分标为 planned 或 not_yet_written，
不要直接判成正式错误。最后告诉我下一轮最该先补的三件事。
```

### 完整稿：做一次投稿前闭环检查

```text
使用 $paper-auditor 的 deep 模式审核
"<论文或论文文件夹的绝对路径>"。

目标期刊是“<期刊>”。保持原稿不变。
除语言、缩写、数值、引用、图表和工程标准外，
建立最终论文主线卡，并逐项核对：
题名与摘要 → 引言中的研究缺口 → 研究问题、目标或假设
→ 方法 → 结果与图表证据 → 讨论 → 结论。

重点指出摘要在正文中找不到依据、结果缺少方法来源、
方法没有对应结果，以及结论超出证据的地方。
不确定的问题放入“给作者的问题”，不要猜测。
```

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

图表在这里不是装饰，而是论文证据的一部分。它会追问：这张图或表正在回答哪个研究问题？题注是否交代了对象、工况、指标、单位、统计量、基线和分图含义？正文中的关键判断能否回到图表中的对应依据？看不清或无法唯一对应时，它会留下待确认项。

结构工程稿件中出现 ASCE、ACI、AISC、Eurocode、GB 或 JGJ 时，它会先核对完整代号和版本。有准确版本原文且处理权限允许时，才继续复核条款、公式和适用范围。新版标准不会被自动当成研究采用的控制版本。

### 最后退后一步看整篇

Paper Auditor 会先把论文整理成一张主线卡：研究缺口是否导向目标或假设，目标是否由方法落实，方法是否产生相应结果，结果是否被图表承载并在讨论中得到有边界的解释，结论是否仍停留在证据允许的范围内。题名和摘要中的每个重要说法，也要能回到正文中的相应位置。

它不会因为工科论文没有标准 IMRAD 标题就判错。`Analytical formulation`、`Numerical model`、`Experimental program`、`Parametric study` 或合并的 `Results and Discussion`，会按实际承担的写作职责进入主线。职责不清时，它会提问。

完整稿的这一步需要通读全文，也需要作者作最终判断。Paper Auditor 能发现断开的连接、前后冲突和缺少依据的主张，但不会宣称自动理解或修复所有学术逻辑。没有可复现位置的担忧不会被硬写成正式错误，而会放进“给作者的问题”中。

## 四种工作节奏

| 模式 | 什么时候用 |
| --- | --- |
| `draft` | 写作前或写到一半：维护论文主线卡，把未完成环节变成问题和下一步任务，不假装稿件已经可投稿 |
| `fast` | 发给导师或合作者前，先扫一遍明确的语言、缩写、术语，以及正文引用与参考文献对应问题 |
| `deep` | 投稿前完整审核，加入逻辑、图表、文献支持性、数值和标准复核 |
| `targeted` | 只查一个方向，例如“只查缩写”或“只核对参考文献” |

写作中用 `draft`，完整稿投稿前用 `deep`。如果只想检查某一类问题，请明确写 `targeted`，它不会自行扩大范围。

## 审完以后你会拿到什么

最常用的是两份文件：

- `review-report.md`：给人看的审核报告。Blocker 和 Major 问题排在前面，每条尽量带原文位置、短引文、依据和可执行的修改建议。
- `findings.json`：给后续追踪、筛选或自动化处理用的结构化结果。

深度审核还会保留文献、主张支持性、公式与数值、工程标准和审核覆盖情况的单独记录。普通使用时不必逐个打开它们，主报告已经汇总了需要你处理的内容。


在 `draft` 或完整逻辑审核里，主报告还会把论文主线卡放在前面：哪些功能连接已经满足，哪些仍未解决，哪些摘要或结论找不到正文依据，哪些方法和结果尚未配对，以及每张关键图表正在支撑什么。明确计划的图表/标签、给作者的问题和下一步写作任务分别列出，不会被冒充成论文缺陷。
如果输入后来发生变化，旧结果会标为 `stale`。某个必要环节没有运行或证据受限时，审核状态会标为 `incomplete`；尚待解决的重点主张、标准或数值候选会标为 `manual_confirmation_required`。完整稿的主线仍为 `unresolved` 时绝不会得到 `ready_given_evidence`：已有正式问题就进入 `revision_required`，否则要求人工确认。干净的部分稿只会得到 `draft_in_progress`，不会被说成“可以投稿”。“没有查到问题”和“没有完成核验”不会混在一起。

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

Windows PowerShell 5.1 出现中文乱码时，可把下面命令中的 `python` 换成 `python -X utf8`。

确定性论文检查：

```powershell
python "<skill-root>\scripts\audit_manuscript.py" "<manuscript>" `
  --output-dir "<new-review-dir>" `
  --manuscript-stage complete
```

审核写到一半的稿件时，把 `complete` 改成 `draft`；明确计划中的图表或标签会进入 `planned_items`。

写作中的 `draft` 证据主干与主线图：

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

完整稿的 `deep` 证据主干与主线图：

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

两种模式都要按实际稿件与作者决定填写主线卡、节点、连接和当前
`evidence_ids`，不要靠关键词自动猜出论文逻辑。

确定性结果中的 `planned_items` 经最终证据锚定后显示为 `draft_planned_items`；
语义审读者给出的 `next_writing_tasks` 是另一份依赖排序任务表，二者不会自动重复。

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

`draft` 和完整 `deep` 审核使用统一证据主干，记录输入哈希、证据锚点、审核覆盖和最终裁决。论文主线规则见 [`references/manuscript-architecture.md`](references/manuscript-architecture.md)，操作契约见 [`references/evidence-spine.md`](references/evidence-spine.md)，引用支持性与工程标准流程分别见 [`references/claim-support.md`](references/claim-support.md) 和 [`references/standards-verification.md`](references/standards-verification.md)。

除主报告外，流程可生成 `manuscript-map-validation.json`、`manuscript-map-traceability.md`、`citation-report.md`、`references.json`、`claim-evidence.json`、`claim-support.json`、`quantitative.json`、`standards.json`、`artifact-manifest.json`、`evidence-ledger.json` 和覆盖记录。`--force` 只能覆盖已有报告，不能覆盖输入原稿或已读取的 BibTeX 文件。

运行回归测试：

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

当前版本包含 196 项回归测试，其中包含核心审核被伪装成不适用、草稿计划项冒充、结构校验冒充语义审核、未配对主线、伪造覆盖状态、过期或无稿件身份的 ledger、错绑来源、虚假定位、输出别名和标准权限门槛等负向边界。核心脚本只依赖 Python 标准库；PDF 文本提取可选用 `pdftotext`。

</details>
