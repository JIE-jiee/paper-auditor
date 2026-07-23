<p align="center">
  <strong>中文</strong> · <a href="./README.en.md">English</a> · <a href="./README.ja.md">日本語</a>
</p>

# Paper Auditor

一套可个人定制的 Codex 论文审核 Skill，用于在投稿前对学术论文进行基于证据的系统检查。它重点适配结构工程、地震工程、抗震韧性、自复位与摇摆体系，也可以通过个人配置和术语表扩展到其他研究方向。

## 主要检查内容

- 语法与英语变体；
- 已开展的研究工作使用过去时，通用结论与所提模型性能使用现在时；
- 摘要与正文分别首次定义缩写，定义后统一使用缩写；
- 专业术语、符号、单位、连字符和构件名称；
- 图、表、公式的编号、正文引用与语义对应；
- LaTeX 标签、交叉引用、引文和参考文献键；
- 正文引文与参考文献表的一一对应；
- 文献是否真实存在、书目信息是否准确，以及撤稿或更正状态；
- 引用处主张是否被被引文献原文支持，并区分支持、部分支持、不支持和无法核验；
- 公式符号、首次定义、作用域、量纲、单位换算、百分比及跨章节关键数值一致性；
- ASCE、ACI、AISC、Eurocode、GB 与 JGJ 等工程标准的完整代号、版本、条款定位、公式与适用范围；
- 研究目的、方法、结果、局限与结论之间的逻辑和观点一致性；
- 图表证据是否真正支持正文中的趋势、幅值和比较结论。
- 审核输入、证据锚点、各审核 pass 和最终报告是否使用同一版本；未执行或证据不足的项目不会冒充“无问题”。

支持 Word、LaTeX/BibTeX、PDF、Markdown 和纯文本。PDF 文本提取在需要时依赖 `pdftotext`。

## 审核方式

| 模式 | 适用场景 |
| --- | --- |
| `fast` | 确定性检查，加一次聚焦的编辑扫描 |
| `deep` | 完整投稿前审核，包括语义、逻辑、图表和书目核验 |
| `targeted` | 只检查用户指定的类别 |

确定性脚本负责可复现的格式、术语、引用和交叉引用检查；完整的语义、逻辑、观点和图表判断由 Codex 按 `SKILL.md` 中的审核流程完成。书目元数据核验不等于判断文献是否支持某项具体观点。

## 四条核心证据链

| 能力 | 证据链 | 不越过的边界 |
| --- | --- | --- |
| 引文支持性 | 论文主张 → 引用位置 → 被引来源原文 → 四级结论 | 缺少全文只能标记“无法核验”，不能据此认定不支持 |
| 公式、单位与数值 | 符号/定义 → 单位与量纲 → 计算 → 跨章节、表格和图件复核 | 图中估读值、弱匹配和未解析公式只作为复核候选 |
| 工程标准 | 完整代号/版本 → 条款或公式 → 限制与例外 → 研究适用范围 | 新版不自动等于控制版本；无准确正文不得判断条款内容 |
| 审核完整性 | 输入 manifest → 统一证据台账 → pass 覆盖状态 → 确定性裁决 | 输入改变标记 `stale`；pass 结果改变或缺失标记 `incomplete` |

## 安装为 Codex Skill

将整个仓库克隆到个人 Skill 目录，并保留 `SKILL.md`、`references/` 和 `scripts/` 的相对位置。

Windows PowerShell：

```powershell
git clone https://github.com/JIE-jiee/paper-auditor.git "$env:USERPROFILE\.codex\skills\paper-auditor"
```

macOS / Linux：

```bash
git clone https://github.com/JIE-jiee/paper-auditor.git "$HOME/.codex/skills/paper-auditor"
```

然后新建一个 Codex 任务，例如：

```text
使用 $paper-auditor 的 deep 模式审核 path/to/main.tex。
保持原稿不变，并把结果写入新的 review 目录。
```

## 命令行快速使用

完整审核先建立统一证据主干：

```powershell
python "<skill-root>\scripts\evidence_spine.py" prepare "<manuscript>" `
  --mode deep --output-dir "<new-review-root>\spine" `
  --artifact "bibliography=<references.bib>"
```

各 pass 完成后使用 `record-pass` 登记覆盖状态，最后运行 `finalize`。完整字段、证据能力和语义 Major/Blocker 复核格式见 `references/evidence-spine.md`。
标准全文不能作为裸 `standard_source` 登记；必须通过 `--standards-source-map`，先验证本地处理模式、权利声明，以及 ASCE/ACI 等条目所需的出版方许可记录。未核验的主张、被阻断的标准任务和量值候选会保留在 `manual_checks`，不会被静默当成“无问题”。
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

引文支持性证据准备与定稿：

```powershell
python "<skill-root>\scripts\claim_support.py" prepare "<manuscript>" `
  --references-json "<citation-review-dir>\references.json" `
  --sources-dir "<lawful-local-paper-sources>" `
  --output-dir "<new-claim-evidence-dir>" --scope priority

python "<skill-root>\scripts\claim_support.py" finalize `
  "<claim-evidence-dir>\claim-evidence.json" "<claim-decisions.json>" `
  --output-dir "<new-claim-result-dir>"
```

工程标准台账（默认仅核验元数据）：

```powershell
python "<skill-root>\scripts\verify_standards.py" "<manuscript>" `
  --output-dir "<new-standard-review-dir>"
```

标准全文只在显式 `--source-map` 通过权利声明后本地处理；ASCE 与 ACI 还要求记录出版方许可依据。

隐私控制选项：

```text
--offline          只提取，不发起网络请求
--no-title-search  只按 DOI 查询，不发送题名、作者和年份
```

## 输出

- `review-report.md`：便于阅读的审核报告；
- `findings.json`：含稳定 ID、严重度、置信度、状态、位置、证据和修改建议的结构化结果；
- `citation-report.md` 与 `references.json`：单独目录中的书目核验结果。
- `claim-evidence.json` 与 `claim-support.json`：逐条主张—来源证据链及最终支持性结论；
- `quantitative.json`：符号、单位、量纲、计算、重复数值和人工复核候选；
- `standards.json` 与 `standards-report.md`：标准版本台账、条款任务与适用性复核入口。
- `artifact-manifest.json`、`evidence-ledger.json`、`coverage.json` 与 `final-evidence-ledger.json`：输入哈希、稳定稿件/外部原文证据 ID、pass 执行状态和陈旧性依据。

默认不修改原稿，报告写入独立目录。`--force` 只允许覆盖既有报告，不允许覆盖输入原稿或已读取的 BibTeX 源文件。

## 个性化

| 文件 | 用途 |
| --- | --- |
| `references/personal-profile.json` | 默认模式、英语变体、严重度和隐私偏好 |
| `references/terminology.tsv` | 首选术语、禁用词、缩写和别名 |
| `references/domain-style.md` | 结构与地震工程的术语和推理规则 |
| `references/claim-support.md` | 引文支持性判定流程与决策格式 |
| `references/quantity-profile.tsv` | 个人符号含义、量纲与必须定义规则 |
| `references/standards-registry.json` | 标准版本元数据与全文处理策略 |
| `references/standards-verification.md` | 标准条款、公式、适用性和授权门控流程 |
| `references/journal-benchmarks.md` | EESD、Engineering Structures 与 ASCE 期刊风格基准 |
| `references/personalization-guide.md` | 安全修改个人规则的方法 |
| `references/evidence-spine.md` | 统一 manifest、证据台账、覆盖记录和最终裁决流程 |

## 隐私与边界

- 未经允许，不把未发表全文或图件发送给外部服务；
- 默认在线核验只发送 DOI，或最少量的题名、作者、年份元数据；
- `not_found` 只表示没有找到足够可靠的匹配，不能据此认定文献伪造；
- 判断“引文是否支持附近观点”仍需要阅读原文或同等直接证据；
- 仅在本地发现标准 PDF 不代表获得自动处理授权；标准条款核验遵循显式权利声明和出版方许可门槛；
- 本工具用于提高审核覆盖率和可复核性，不能替代作者、领域专家或期刊编辑的最终判断。

## 测试

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

当前版本包含 131 项回归测试，其中 31 项负向用例专门覆盖伪造覆盖状态、错绑来源、虚假定位、输出别名和权利门禁等对抗边界。核心脚本只依赖 Python 标准库；PDF 提取工具 `pdftotext` 为可选依赖。
