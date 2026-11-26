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

## 8. Jinja2 模板规范

### 反斜杠转义规则

在 Jinja2 模板（`.j2` 文件）的**纯文本区域**（非 `{{ ... }}`/`{% ... %}` 表达式内）出现字面量反斜杠时，**必须写双反斜杠 `\\`**：

| 场景 | ❌ 错误写法 | ✅ 正确写法 | 说明 |
|------|-------------|-------------|------|
| 模板文本中的换行符提示 | `with \n for newlines` | `with \\n for newlines` | 单 `\` 会被词法分析器当成转义字符报错 |
| JSON 示例字符串中的换行 | `"line1\nline2"` | `"line1\\nline2"` | 模板源码里写 `\\n`，渲染后输出给 LLM 的是字面量 `\n` |
| Windows 路径等其他反斜杠 | `C:\Users` | `C:\\Users` | 同理 |

**报错示例**：
```
TemplateSyntaxError: unexpected char '\\' at 2232
```
这是 Jinja2 词法分析器（`env.parse(source)`）在解析模板源码时，遇到未转义的单反斜杠导致的。

### 模板搜索优先级

- **插件模板目录优先**（`--plugin-dir` 下的 `templates/`）
- **主框架模板目录兜底** (`templates/`)

这与 `report/renderer.py` 的行为保持一致，确保用户自定义模板生效。

### Jinja2 语法禁忌（极易踩坑）

| ❌ 禁止写法 | 原因 | ✅ 正确替代 | 示例位置 |
|------------|------|------------|----------|
| `{{ [expr for x in list] }}` | **Python 列表推导式**不被 Jinja2 表达式支持 | `{% for x in list %}{{ expr }}{% if not loop.last %}, {% endif %}{% endfor %}` 或自定义 filter | `report.j2:6` |
| `{{ dict_comp }}` | Python dict/set 推导式同理不支持 | 改用 for 循环或 filter | - |
| `{% if x in dict %}` | Jinja2 `in` 只能测序列/映射键，不能测值 | 用 `dict.get(x)` 或自定义 test | - |

> **原则**：模板表达式 `{{ ... }}` 只能用 Jinja2 原生语法（变量、filter、test、简单运算），**任何 Python 专有语法（推导式、lambda、walrus `:=`、match-case 等）全部禁止**。

### 自定义 Filter 注册规范

`report/renderer.py` 中注册 filter 时：

| 规则 | 说明 | 示例 |
|------|------|------|
| **覆盖内置同名 filter** | 模板若用 `map('tojson')`，需 `env.filters['tojson'] = ...` | `tojson_safe` 替代内置 `tojson` |
| **透传 `**kwargs`** | 模板可能传 `indent=2` 等参数 | `def tojson_safe(obj, **kwargs): return json.dumps(obj, **kwargs)` |
| **异常兜底返回字符串** | 防止序列化失败导致模板渲染崩溃 | `except Exception: return str(obj)` |
| **补充缺失内置 filter** | Jinja2 无 `zip`、`groupby` 等，需自行注册 | `env.filters['zip'] = lambda *it: list(zip(*it))` |

### i18n Key 管理规范

| 规则 | ❌ 错误示例 | ✅ 正确示例 |
|------|-------------|-------------|
| **同一层级 key 不可重复** | `report.analyst_views` 出现两次（字符串 + dict），后者覆盖前者导致类型错 | 扁平化所有 key，嵌套结构改用 `report.analyst_views.mkt` 等子 key |
| **所有叶子值必须为字符串** | `analyst_views: {mkt: "市场"}` 导致 `i18n.t("report.analyst_views")` 取到 dict 报错 | 叶子节点全为字符串，嵌套只用于分组，不直接取值 |
| **模板用到的 key 必须双语言同步** | zh-CN 有 `action_plan`，en-US 没有 | 新增 key 时同步更新 `zh-CN.yaml` 和 `en-US.yaml` |

---

## 9. Evidence Schema 与模板取值路径规范

### 9.1 证据文件结构

运行结束后，每条证据保存为 `runs/<run_id>/raw/ev-XXXX.json`，包含：

| 字段 | 说明 |
|------|------|
| 业务字段 | Provider 返回的原始 `raw_payload` |
| `_template_meta` | 自动生成的模板编写指引（Schema + jinja_paths） |
| `_evidence_meta` | 完整证据元数据（ID、类型、provider、summary、lineage、质量评分等） |

### 9.2 `_template_meta` 关键字段

```json
"_template_meta": {
  "raw_payload_schema": { ... },   // 递归 Schema，每字段含 jinja_path
  "jinja_paths": [...],             // 扁平路径列表，**可直接复制到模板**
  "top_level_keys": [...]           // 根键快览
}
```

| 字段 | 用途 |
|------|------|
| `raw_payload_schema` | 递归 JSON Schema，每字段含 `jinja_path` 与 `example` |
| `jinja_paths` | 所有叶子字段的访问路径，**直接复制进模板** |
| `top_level_keys` | 根层级键名快览 |

### 9.3 模板取值规范

1. **跑一次**生成证据：`tradingagents run --ticker AAPL ...`
2. **打开** `runs/<run_id>/raw/ev-XXXX.json` → 看 `_template_meta.jinja_paths`
3. **复制路径**到模板，**用括号语法**避免 dict 方法冲突：

```jinja2
{% for ev in evidence %}
- [{{ ev.evidence_id }}] {{ ev.summary }}
{% if ev.raw_payload["values"] is mapping %}
  **关键数值 (最近 5 个交易日)：**
  {% for k, v in (ev.raw_payload["values"].items() | list)[-5:] %}
  - {{ k }}: {{ v }}
  {% endfor %}
{% endif %}
{% endfor %}
```

> **强制**：键名可能冲突 dict 方法（`values`、`keys`、`items` 等），**必须用 `ev.raw_payload["key"]` 而非 `ev.raw_payload.key`**。

### 9.4 Provider 合规要求

- `RawEvidence.raw_payload` 必须是可 JSON 序列化的 dict
- 任意嵌套结构均自动推导 Schema，store 端零配置
- 可选：在 raw_payload 加入 `_template_hint` 提供额外提示

---

> **更新规则**：修改架构模式、i18n 用法、目录结构、**模板规范、Evidence Schema** 时，**必须同步更新本文档**。