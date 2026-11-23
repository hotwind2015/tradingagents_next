# TradingAgents 开发规范 (AGENTS.md)

> 供所有 AI Agent 和人类开发者遵循的开发规范，确保代码风格、架构模式、i18n 使用的一致性。

---

## 1. CLI 命令结构规范

### 目录结构
```
tradingagents/cli/
├── main.py                 # 入口：仅负责参数解析、i18n 初始化、分发
├── commands/
│   ├── __init__.py
│   ├── run.py              # run 子命令实现
│   └── evidence.py         # evidence 子命令组实现
└── commands/evidence/      # 如有子命令再细分
```

### 核心原则
| 规则 | 说明 |
|------|------|
| **命令即文件** | 每个顶级子命令 = `commands/` 下一个 `.py` 文件 |
| **入口极简** | `main.py` 只做：i18n 初始化 → 解析参数 → 分发到对应 `run_xxx_command()` |
| **命令注册函数** | 每命令文件导出 `add_xxx_subparser(subparsers, i18n)` 和 `run_xxx_command(args, i18n)` |
| **i18n 显式传递** | 所有命令函数签名必须包含 `i18n: I18n` 参数，**禁止**在命令内部调用 `get_i18n()` |

### 示例：`run.py`
```python
def add_run_subparser(subparsers, i18n):
    parser = subparsers.add_parser("run", help=i18n.t("cli.run_help"))
    parser.add_argument("--ticker", required=True, help=i18n.t("cli.ticker_help"))
    ...

def run_run_command(args, i18n):
    ...
```

### `main.py` 分发模板
```python
def main():
    argv = sys.argv[1:]
    set_i18n(_requested_language(argv))
    i18n = get_i18n()
    parser = _build_parser(i18n)
    args = parser.parse_args(argv)

    if args.command == "run":
        sys.exit(run_run_command(args, i18n))
    elif args.command == "evidence":
        sys.exit(run_evidence_command(args, i18n))
```

---

## 2. i18n 多语言规范

### 翻译文件结构
```
i18n/
├── zh-CN.yaml
└── en-US.yaml
```

### Key 命名规范
| 场景 | Key 格式 | 示例 |
|------|----------|------|
| CLI 顶层 | `cli.xxx_help` | `cli.run_help` |
| 子命令帮助 | `cli.evidence_xxx_help` | `cli.evidence_list_help` |
| 参数帮助 | `cli.xxx_help` | `cli.evidence_task_id_help` |
| 表格列标题 | `cli.evidence_col_xxx` | `cli.evidence_col_id` |
| 运行时消息 | `run.xxx` / `evidence_cli.xxx` | `run.started` |

### 使用规则
| 场景 | 正确做法 | ❌ 禁止 |
|------|----------|---------|
| 命令注册时 | `help=i18n.t("cli.evidence_help")` | 硬编码中文/英文 |
| 运行时打印 | `print(i18n.t("cli.evidence_verify_ok", task_id=...))` | 直接 `print("OK...")` |
| 表格表头 | `i18n.t("cli.evidence_col_id")` | 硬编码 "ID" |

### 语言切换
- 全局 `--lang` 参数放在**主 parser**，不在子命令下
- `_requested_language(argv)` 在创建 parser 前解析，传给 `set_i18n()`

### 2.4 命名空间前缀变量模式（推荐）

当同一命名空间下有**大量 key**（如 `cli.subcommands.evidence.*` 下 20+ 个 key）时，**强制使用前缀变量 + lambda** 避免重复拼接：

#### ✅ 推荐写法
```python
def add_evidence_subparser(subparsers: argparse._SubParsersAction, i18n: I18n) -> None:
    # 1. 定义命名空间前缀
    node = "cli.subcommands.evidence"
    n = lambda k: f"{node}.{k}"   # 单行 lambda，简洁

    parser = subparsers.add_parser(
        "evidence",
        help=i18n.t(n("help")),           # -> cli.subcommands.evidence.help
        description=i18n.t(n("help")),
    )
    sub = parser.add_subparsers(dest="evidence_action", required=True)

    # 子命令参数
    p_list.add_argument("--task-id", required=True, help=i18n.t(n("task_id_help")))
    # ...
```

#### ❌ 禁止写法
```python
# 重复拼接，易错、难改、难读
help=i18n.t("cli.subcommands.evidence.list_help")
help=i18n.t("cli.subcommands.evidence.task_id_help")
# ...
```

#### 适用场景
| 场景 | 是否强制 |
|------|----------|
| 同一命名空间下 **≥ 5 个 key** | ✅ 强制 |
| 临时/一次性 key | 可直接写全路径 |
| 跨命名空间引用 | 写全路径，不建议跨空间复用 lambda |

#### 原则小结
| 原则 | 说明 |
|------|------|
| **前缀变量名** | 推荐 `node` / `ns` / `prefix`，语义清晰 |
| **lambda 命名** | 推荐单字母 `n` / `k` / `key`，简洁 |
| **定义位置** | 函数开头，紧跟 docstring 之后 |
| **命名空间分隔** | 用 `.` 分隔，与 YAML key 一致 |

---

## 3. Provider 插件开发规范

### 目录约定
```
plugins/
└── sources/
    └── yfinance/
        ├── __init__.py          # 可选：统一导出
        ├── kline.py             # provider_id="yfinance_kline", provides={"market_raw_kline"}
        ├── news.py              # provider_id="yfinance_news", provides={"news_raw"}
        └── fundamentals.py      # provider_id="yfinance_fund", provides={"fundamentals_enriched"}
```

### 核心约定
| 规则 | 说明 |
|------|------|
| **文件 = Provider** | 一个 `.py` = 一个 Provider，必须声明 `provider_id` |
| **provides 精准声明** | `provides = {"market_raw_kline"}` 只声明本文件产出的类型 |
| **能力声明** | 在类上定义 `capabilities: dict[str, ProviderCapability]` |
| **插件目录优先级** | 本地 `--plugin-dir` > `pip install` 包 > 官方内置 |

---

## 4. Evidence / 基因链 规范

### 数据模型字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `metadata.processing_level` | `ProcessingLevel` | `raw`/`enriched`/`derived` |
| `metadata.quality_scores` | `dict[str, float]` | 质量评分 |
| `metadata.processing_chain` | `list[str]` | 处理步骤链路 |
| `lineage` | `list[str]` | 祖先证据 ID 列表（基因链） |

### API 使用
```python
# 正向溯源
ctx.evidence.get_lineage(ev_id)      # -> ["ev-0001", "ev-0002"]
# 反向追踪
ctx.evidence.get_descendants(ev_id)  # -> ["ev-0003", "ev-0004"]
# 按层级筛选
ctx.evidence.get_by_level("market_data", "raw")
```

---

## 5. Git 提交规范

### Commit Message 格式
```
<type>: <subject>

<body>

<footer>
```

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 重构（无功能变更） |
| `docs` | 文档更新 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖更新 |

### 示例
```
feat(cli): add evidence list/show/graph/verify commands

- New evidence CLI group with list/show/graph/verify subcommands
- Full i18n support for zh-CN/en-US
- DOT/JSON graph output for evidence DAG

Closes #123
```

---

## 6. 测试规范

| 层级 | 工具 | 运行命令 |
|------|------|----------|
| 单元/冒烟 | pytest / 内置 smoke | `.venv/Scripts/python.exe tests/smoke_batch*.py` |
| CLI 集成 | 直接调用 CLI | `python -m tradingagents.cli.main evidence list ...` |

---

## 7. 提交前检查清单

- [ ] 代码通过 `py_compile` 语法检查
- [ ] 所有 smoke tests 通过
- [ ] CLI `--lang en-US/zh-CN` 双语言验证通过
- [ ] 无硬编码中文/英文字符串（均通过 `i18n.t()`）
- [ ] 新增 i18n key 已同步添加到 `zh-CN.yaml` 和 `en-US.yaml`
- [ ] 新文件有模块级 docstring（中文）
- [ ] 新命令遵循 `commands/` 目录结构和注册模式

---

> **更新规则**：修改架构模式、i18n 用法、目录结构时，**必须同步更新本文档**。