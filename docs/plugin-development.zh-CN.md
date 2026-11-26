# 插件开发参考

[English](plugin-development.md) | 简体中文

本文整理了项目支持的扩展插件类型，将关键接口、模板和配方示例直接列出，便于在自己的目录中使用。

## 1. 插件加载方式

项目支持三类插件。配置中的 `dataprovider` 对应当前代码中的插件类型 `provider`。

| 插件用途 | `plugin_type` | 必需的 ID 属性 | 核心接口 |
| --- | --- | --- | --- |
| 分析角色、项目经理 | `role` | `role_id` | `prepare_context()`、`parse_output()` |
| 证据数据提供者（DataProvider） | `provider` | `provider_id` | `fetch(DataRequest)` |
| 大语言模型 | `llm` | `llm_id` | `invoke(prompt, model_config)` |

运行时通过 `--plugin-dir` 指定一个或多个插件目录，并递归加载其中的 Python 文件。插件类需要有可无参数调用的构造函数，并声明对应的 `plugin_type` 和 ID。自定义插件 ID 与已加载插件冲突时，自定义插件会覆盖先前注册的同类型插件。

```text
my_plugins/
├── providers/
│   └── mock_provider.py
├── llms/
│   └── mock_llm.py
├── roles/
│   └── mock_roles.py
└── templates/
    ├── analysts/
    │   └── mock_fundamentals.j2
    └── project_manager_custom.j2
```

插件目录在命令行显式指定；不要依赖 YAML 中未使用的 `plugindir` 字段。运行命令的当前目录会影响配置文件和模板等相对路径，建议从项目根目录执行。

## 2. 分析执行链

1. 配方中的 `team` 选择分析角色和最终的项目经理角色。
2. 分析角色通过 `consumes` 声明需要的证据类型。`data.provider_chain` 按配置顺序选择数据提供者；提供者返回的证据会保存到本次运行目录。
3. 系统根据角色的 `consumes` 和 `produces` 构建 DAG。角色使用 Jinja2 模板和上下文数据生成提示词，再由配置的 LLM 生成结果。
4. 分析结果以 `RoleOutput` 结构保存在 `runs/<run_id>/outputs/`。
5. 项目经理汇总团队分析，生成最终角色输出；报告渲染器再用 Markdown 报告模板生成最终报告。

数据类型名称需要保持一致：`data.required`、提供者返回的 `RawEvidence.evidence_type` 和分析角色的 `consumes` 应使用相同名称；`provider_chain` 中的插件 ID 应与提供者的 `provider_id` 一致。分析角色的 `produces` 应与下游角色（通常是项目经理）的 `consumes` 对应。

## 3. 数据提供者示例

数据提供者实现 `DataProvider` 接口。每个实现应声明自己能提供的证据类型，并在 `fetch()` 中返回 `RawEvidence` 列表。必需数据获取失败时，运行会中止。

```python
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence


class MockProvider(DataProvider):
    plugin_type = "provider"
    provider_id = "mock"
    provides = {"fundamentals"}

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        if req.evidence_type != "fundamentals":
            return []

        return [
            RawEvidence(
                evidence_type="fundamentals",
                provider=self.provider_id,
                method="mock_fetch",
                summary="Mock 数据：营收同比增长 15%，净利润增长 8%。",
                raw_payload={"revenue_growth": 0.15},
            )
        ]
```

`DataRequest` 包含 `evidence_type`、`ticker`、`as_of` 和 `params`。生产环境中的提供者可在无参数构造函数中读取凭据或其他设置，并在 `fetch()` 中完成外部数据请求。

## 4. LLM 提供者示例

LLM 插件接收提示词和模型参数，返回字符串。通常返回 JSON 字符串，再由角色的 `parse_output()` 转换为 `RoleOutput`。

```python
import json
from typing import Any

from tradingagents.llm.base import LLMClient


class MockLLM(LLMClient):
    plugin_type = "llm"
    llm_id = "mock"

    def invoke(self, prompt: str, model_config: dict[str, Any]) -> str:
        return json.dumps(
            {
                "fundamental_score": 0.8,
                "narrative": "这是模拟分析结果，不会调用真实模型。",
                "cited_evidence": [],
            },
            ensure_ascii=False,
        )
```

此 Mock 实现适合验证流程和插件接线，不会理解或分析输入提示词。

## 5. 分析角色与项目经理示例

分析角色实现 `AnalystRole` 接口：`prepare_context()` 选择需要的证据并返回模板上下文；`parse_output()` 将模型返回值解析为 `RoleOutput`。

```python
import json
from typing import Any

from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput
from tradingagents.run.context import RunContext


class MockFundamentalsAnalyst(AnalystRole):
    plugin_type = "role"
    role_id = "mock_fundamentals"
    consumes = {"fundamentals"}
    produces = {"fundamental_score"}
    template = "analysts/mock_fundamentals.j2"

    def prepare_context(
        self, evidence: EvidenceView, ctx: RunContext
    ) -> dict[str, Any]:
        return {"evidence": evidence.to_prompt_items(self.consumes)}

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = json.loads(raw_response)
        return RoleOutput(
            role_id=self.role_id,
            fields={"fundamental_score": data["fundamental_score"]},
            narrative=data["narrative"],
            cited_evidence=data.get("cited_evidence", []),
        )
```

项目经理实现 `ProjectManager` 接口。它接收团队的 `RoleOutput` 列表和证据视图，将分析结果放入提示词上下文：

```python
import json

from tradingagents.roles.base import ProjectManager, RoleOutput


class MockProjectManager(ProjectManager):
    plugin_type = "role"
    role_id = "mock_pm"
    consumes = {"fundamental_score"}
    template = "project_manager_custom.j2"

    def prepare_context(self, outputs, evidence, ctx):
        return {
            "analyst_outputs": [
                {"role": output.role_id, "narrative": output.narrative}
                for output in outputs
            ]
        }

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = json.loads(raw_response)
        return RoleOutput(
            role_id=self.role_id,
            fields={"final_report": data["narrative"]},
            narrative=data["narrative"],
            cited_evidence=data.get("cited_evidence", []),
        )
```

当前执行器按 `team.project_manager` 的值查找项目经理插件。自定义项目经理时，建议让 `roles` 中的配置键、`team.project_manager` 和插件类的 `role_id` 使用同一个 ID。

当前本地 `mock_test_v2.yaml` 将项目经理的 `team` 配置键写为 `project_manager`，而对应角色声明的 `role_id` 是 `mock_pm`。按当前执行器的查找方式，这不会调用 ID 为 `mock_pm` 的自定义项目经理。下方可复制的配方已将三个 ID 对齐，供自定义项目经理使用。

## 6. Jinja2 模板

分析角色的 `prepare_context()` 返回值会传入模板；运行器还会注入 `ticker` 和 `output_language`。模板使用的变量必须存在于上下文中。

文件 `my_plugins/templates/analysts/mock_fundamentals.j2`：

```jinja2
请分析 {{ ticker }} 的基本面，使用 {{ output_language }} 输出。

证据：
{% for item in evidence %}
- [{{ item.evidence_id }}] {{ item.summary }}
{% endfor %}

请返回 JSON，包含 fundamental_score、narrative 和 cited_evidence。
```

角色配置中的模板路径相对于 `templates/` 目录，例如 `analysts/mock_fundamentals.j2`。内置 `templates/` 先于插件目录搜索；建议使用独特的模板文件名，避免与内置模板重名。插件目录下的 `templates/` 搜索路径用于角色和项目经理的提示词模板；最终报告当前使用项目内的 `templates/report.j2`。

项目经理模板 `my_plugins/templates/project_manager_custom.j2`：

```jinja2
请汇总 {{ ticker }} 的团队分析，使用 {{ output_language }} 输出。
{% for item in analyst_outputs %}
- {{ item.role }}：{{ item.narrative }}
{% endfor %}

请返回 JSON，包含 narrative 和 cited_evidence。
```

## 7. Mock 配方示例

下面的最小配方将 Mock 数据提供者、分析角色和 LLM 串起来。保存为 `my_config/mock_test.yaml`，并确保上文的插件类放在 `my_plugins/` 下。

```yaml
id: mock_test
version: "0.1"
target_profile: equity
evidence_schema: v1
prompt_persistence: full

data:
  required: [fundamentals]
  provider_chain:
    fundamentals: [mock]

models:
  provider: mock
  quick: {temperature: 0.1}
  deep: {temperature: 0.2}

roles:
  mock_fundamentals:
    role_id: mock_fundamentals
    display_name_key: role.fundamentals
    consumes: [fundamentals]
    produces: [fundamental_score]
    template: analysts/mock_fundamentals.j2
    model_tier: quick
  mock_pm:
    role_id: mock_pm
    display_name_key: role.pm
    consumes: [fundamental_score]
    produces: [final_report]
    template: project_manager_custom.j2

team:
  analysts: [mock_fundamentals]
  project_manager: mock_pm
```

保存后运行：

```bash
tradingagents run --ticker AAPL --config ./my_config/mock_test.yaml --plugin-dir ./my_plugins
```

该示例使用 Mock provider 和 Mock LLM，不需要真实模型 API Key；若提供者也返回 Mock 数据，则不需要访问行情数据服务。实际角色应根据真实模型输出解析字段，并只引用证据清单中存在的 `evidence_id`。

## 8. `smoke_v2.yaml` 和 `mock_test_v2.yaml` 示例的区别

| 本地示例 | 展示内容 | 运行依赖 |
| --- | --- | --- |
| `smoke_v2.yaml` | 使用内置角色、`yfinance` 和 `openai` 的完整分析团队，包括行情、基本面、新闻、多空研究和项目经理。适合作为内置组件的配置参考，不是自定义插件示例。 | 网络、数据源可用性，以及 OpenAI 兼容 API 凭据。 |
| `mock_test_v2.yaml` | 使用 `mock` 数据提供者和 LLM 的简化分析配方，适合作为自定义插件接线参考。 | 对应的本地 Mock 插件文件。 |

例如，`smoke_v2.yaml` 可按本地路径运行：

```bash
tradingagents run --ticker AAPL --config tests/recipes/smoke_v2.yaml
```

## 9. Evidence Schema 与模板取值路径

运行一次分析后，每条证据都会保存为 `runs/<run_id>/raw/ev-XXXX.json`。文件不仅包含原始载荷，还自动生成元数据，帮助模板作者快速找到正确的取值路径。

### 9.1 证据 JSON 结构

每个 `ev-XXXX.json` 包含：

| 字段 | 说明 |
|------|------|
| `indicator`、`values` 等 | Provider 返回的原始载荷（因 provider 而异） |
| `_template_meta` | 自动生成的模板编写指引（见下） |
| `_evidence_meta` | 完整证据元数据（ID、类型、provider、summary、lineage、质量评分等） |

### 9.2 `_template_meta` — 模板作者的指引

```json
"_template_meta": {
  "raw_payload_schema": {
    "type": "object",
    "jinja_path": "raw_payload",
    "properties": {
      "indicator": { "type": "string", "jinja_path": "raw_payload.indicator", "example": "rsi" },
      "values": {
        "type": "object",
        "jinja_path": "raw_payload.values",
        "properties": {
          "2026-11-24": { "type": "string", "jinja_path": "raw_payload.values.2026-11-24", "example": "56.85" }
        },
        "keys": ["2026-11-25", "2026-11-24", ...],
        "example": { "2026-11-25": "N/A", "2026-11-24": "56.85" }
      },
      "as_of_date": { "type": "string", "jinja_path": "raw_payload.as_of_date", "example": "2026-11-25" },
      "look_back_days": { "type": "integer", "jinja_path": "raw_payload.look_back_days", "example": 30 }
    }
  },
  "jinja_paths": [
    "raw_payload.indicator",
    "raw_payload.values",
    "raw_payload.values.2026-11-24",
    "raw_payload.as_of_date",
    "raw_payload.look_back_days",
    "raw_payload.description"
  ],
  "top_level_keys": ["indicator", "values", "as_of_date", "look_back_days", "description"]
}
```

#### 关键字段说明

| 字段 | 用途 |
|------|------|
| `raw_payload_schema` | 完整载荷的递归 JSON Schema，每个字段都有 `jinja_path` |
| `jinja_paths` | 所有叶子字段的扁平访问路径列表 — **可直接复制到模板** |
| `top_level_keys` | 根层级键名快览 |

### 9.3 模板中如何使用

1. **先跑一次**生成证据文件：
   ```bash
   tradingagents run --ticker AAPL --config config/default.yaml --lang zh-CN
   ```

2. **打开任意 `runs/<run_id>/raw/ev-XXXX.json`**，查看 `_template_meta.jinja_paths`

3. **复制路径**并在 Jinja2 模板中使用（加 `ev.raw_payload.` 前缀）：
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

   > **重要**：键名可能与 Python dict 方法冲突（如 `values`、`keys`、`items`），请用括号语法 `ev.raw_payload["values"]`，不要用点号 `ev.raw_payload.values`。

### 9.4 `_evidence_meta` — 完整证据上下文

```json
"_evidence_meta": {
  "evidence_id": "ev-0001",
  "evidence_type": "market_indicators",
  "provider": "yfinance_kline",
  "method": "stockstats",
  "summary": "rsi values from 2026-10-26 to 2026-11-25",
  "fetched_at": "2026-11-25T14:00:38.853340+00:00",
  "fallback_hit": false,
  "metadata": {
    "source_provider": "yfinance_kline",
    "source_method": "stockstats",
    "processing_level": "raw",
    "processing_chain": ["fetch"],
    "quality_scores": { "completeness": 1.0, "freshness": 1.0 }
  },
  "lineage": []
}
```

可用于调试、审计、报告中展示数据溯源。

### 9.5 Provider 开发最佳实践

实现新 `DataProvider` 时，确保 `RawEvidence.raw_payload` 是 **可 JSON 序列化的 dict**。Schema 推导完全自动，支持任意结构（对象、数组、嵌套），store 端无需改代码。

若 provider 有特殊字段需提示模板作者，可在 raw_payload 中加入可选的 `_template_hint`（会被合并到 `_template_meta`）：
```python
RawEvidence(
    ...
    raw_payload={
        "my_custom_field": [...],
        "_template_hint": {
            "category": "technical",
            "description": "自定义波动率指标，用 ev.raw_payload.my_custom_field 遍历"
        }
    }
)
```

---

这样模板作者**完全不需要读 provider 代码** — 跑一次、打开 JSON、复制 `jinja_paths`、粘贴进模板即可。
