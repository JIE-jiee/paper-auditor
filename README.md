<p align="center">
  <strong>中文</strong> · <a href="./README.en.md">English</a> · <a href="./README.ja.md">日本語</a>
</p>

# Paper Auditor

一套可个人定制的 Codex 论文审核 Skill，用于在投稿前对学术论文进行基于证据的系统检查。它重点适配结构工程、地震工程、抗震韧性、自复位与摇摆体系，也可以通过个人配置和术语表扩展到其他研究方向。

## 主要检查内容

- 语法、上下文时态与英语变体；
- 缩写的首次定义、重复定义和前后一致性；
- 专业术语、符号、单位、连字符和构件名称；
- 图、表、公式的编号、正文引用与语义对应；
- LaTeX 标签、交叉引用、引文和参考文献键；
- 正文引文与参考文献表的一一对应；
- 文献是否真实存在、书目信息是否准确，以及撤稿或更正状态；
- 摘要、正文、图表和结论之间的数值一致性；
- 研究目的、方法、结果、局限与结论之间的逻辑和观点一致性；
- 图表证据是否真正支持正文中的趋势、幅值和比较结论。

支持 Word、LaTeX/BibTeX、PDF、Markdown 和纯文本。PDF 文本提取在需要时依赖 `pdftotext`。

## 审核方式

| 模式 | 适用场景 |
| --- | --- |
| `fast` | 确定性检查，加一次聚焦的编辑扫描 |
| `deep` | 完整投稿前审核，包括语义、逻辑、图表和书目核验 |
| `targeted` | 只检查用户指定的类别 |

确定性脚本负责可复现的格式、术语、引用和交叉引用检查；完整的语义、逻辑、观点和图表判断由 Codex 按 `SKILL.md` 中的审核流程完成。书目元数据核验不等于判断文献是否支持某项具体观点。

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

隐私控制选项：

```text
--offline          只提取，不发起网络请求
--no-title-search  只按 DOI 查询，不发送题名、作者和年份
```

## 输出

- `review-report.md`：便于阅读的审核报告；
- `findings.json`：含稳定 ID、严重度、置信度、状态、位置、证据和修改建议的结构化结果；
- `citation-report.md` 与 `references.json`：单独目录中的书目核验结果。

默认不修改原稿，报告写入独立目录。`--force` 只允许覆盖既有报告，不允许覆盖输入原稿或已读取的 BibTeX 源文件。

## 个性化

| 文件 | 用途 |
| --- | --- |
| `references/personal-profile.json` | 默认模式、英语变体、严重度和隐私偏好 |
| `references/terminology.tsv` | 首选术语、禁用词、缩写和别名 |
| `references/domain-style.md` | 结构与地震工程的术语和推理规则 |
| `references/journal-benchmarks.md` | EESD、Engineering Structures 与 ASCE 期刊风格基准 |
| `references/personalization-guide.md` | 安全修改个人规则的方法 |

## 隐私与边界

- 未经允许，不把未发表全文或图件发送给外部服务；
- 默认在线核验只发送 DOI，或最少量的题名、作者、年份元数据；
- `not_found` 只表示没有找到足够可靠的匹配，不能据此认定文献伪造；
- 判断“引文是否支持附近观点”仍需要阅读原文或同等直接证据；
- 本工具用于提高审核覆盖率和可复核性，不能替代作者、领域专家或期刊编辑的最终判断。

## 测试

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

当前版本包含 32 项回归测试，核心脚本只依赖 Python 标准库；PDF 提取工具 `pdftotext` 为可选依赖。
