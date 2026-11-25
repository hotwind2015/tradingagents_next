# Legacy Plugin Architecture Example

旧版插件架构完整示例（迁移前的可运行基线）。这是在插件化架构重构前，经过多轮验证可稳定运行的完整代码集。

## 目录结构

```
legacy_plugin_architecture/
├── providers/      # 数据提供者 - 仅 yfinance 单一数据源
│   └── yfinance/   # 行情、基本面、新闻、快照
├── roles/          # 分析师角色 - 4个基础分析师 + researchers
│   ├── market_analyst.py
│   ├── news_analyst.py
│   ├── fundamentals_analyst.py
│   └── researchers.py
├── templates/      # 简易 Jinja2 模板
│   ├── project_manager.j2
│   └── report.j2
├── config/         # 单一默认配置
│   └── default.yaml
└── report/         # 简易报告渲染器
    └── renderer.py
```

## 快速运行（作为插件目录，零配置）

### 中文报告
```bash
python -m tradingagents.cli.main run \
  --ticker AAPL \
  --config config/default.yaml \
  --plugin-dir examples/legacy_plugin_architecture \
  --lang zh-CN
```

### 英文报告
```bash
python -m tradingagents.cli.main run \
  --ticker AAPL \
  --config config/default.yaml \
  --plugin-dir examples/legacy_plugin_architecture \
  --lang en-US
```

## 常用命令参考

| 场景 | 命令 |
|------|------|
| 基础分析 | `python -m tradingagents.cli.main run --ticker AAPL --config config/default.yaml --plugin-dir examples/legacy_plugin_architecture --lang zh-CN` |
| 指定模型 | `python -m tradingagents.cli.main run --ticker AAPL --config config/default.yaml --plugin-dir examples/legacy_plugin_architecture --lang zh-CN --set models.quick.model=gpt-4o` |
| 恢复运行 | `python -m tradingagents.cli.main run --ticker AAPL --config config/default.yaml --plugin-dir examples/legacy_plugin_architecture --lang zh-CN --resume <run_id>` |
| 证据查看 | `python -m tradingagents.cli.main evidence list --task-id <run_id> --runs-dir runs` |

## 与新架构对比

| 特性 | Legacy (本示例) | New (迁移后主代码) |
|------|----------------|-------------------|
| 数据源 | 仅 yfinance | yfinance + FRED + Reddit + StockTwits |
| 角色数 | 4基础分析师 + researchers | 7角色 + project_manager |
| 报告结构 | 扁平叙述 | 7大专业章节 + 证据附录 + 证据基因链 |
| 模板能力 | 简易变量替换 | Jinja2 宏 + 专业表格渲染 + i18n |
| 证据链 | 无 | 完整基因链溯源 + 质量评分 |
| 宏观数据 | 无 | FRED 系列指标 (CPI, 失业率, 国债收益率等) |
| 社交情绪 | 无 | StockTwits + Reddit 多平台 |
| 内部人交易 | 无 | yfinance 基本面包含 |

## 适用场景

- **教学参考**：理解插件架构的基础形态
- **对比测试**：新旧架构输出质量对比
- **轻量部署**：仅需 yfinance 单一依赖的极简场景
- **回归基线**：新架构重构时的行为基线

## 迁移说明

此代码在 2026-11-25 迁移前作为正式代码运行。迁移后的新架构位于：
- `tradingagents/providers/` - 多数据源插件
- `tradingagents/roles/` - 7角色完整体系
- `templates/` - 专业报告模板
- `config/` - 完整配方集
- `tradingagents/report/` - 专业报告生成器

---

*归档时间：2026-11-25 | 迁移版本：v2.0*