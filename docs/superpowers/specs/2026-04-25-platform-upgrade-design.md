# Platform Upgrade Design

## Status: Approved

## Goal

系统性提升量化研究平台的专业度，聚焦研究能力和回测质量，逐步引入业界标准开源工具替代自建轮子。

## Constraints

- 硬件：4-core 24GB ARM
- 预算：零（免费数据源）
- 范围：渐进式升级
- 时间：1-2 个月
- 策略：日股低频，追求高胜率低回撤

## Non-Goals（这个阶段不做的事）

- 实时/高频交易系统
- 付费数据源接入
- ML 模型训练
- Web UI / Dashboard
- 多市场多币种

---

## Phase 1: OOS 验证（0 代码改动）

### Why first

在不确定信号是否真的有效的情况下，任何架构改动都是在错误基础上叠加复杂度。

### What

- 用现有系统，将 `12_1 mom-only` 配置在 2019-01 到 2024-12 上做研究（walk-forward 窗口内选最优权重）
- 用 2025-01 至今的数据做纯 OOS holdout 验证
- 如果 holdout 期 Sharpe 为负，停下来分析原因是因子失效还是其他问题
- 不通不过：不进入下一阶段

### Success criteria

- holdout 期 Sharpe > 0（目标 > 0.5）
- holdout 期 max drawdown < 30%

---

## Phase 2: 接入 alphalens-reloaded（1-2 周）

### Why second

alphalens 是纯增量，不依赖任何回测引擎，直接在现有 scorer 输出上运行。零风险。

### What

- 安装 `alphalens-reloaded`
- 新增 `research/factor_analysis.py`：
  - 从 `score_universe()` 的输出生成 alphalens 兼容格式
  - 计算：IC 均值/标准差/IR、分位数收益单调性、因子自相关、换手率
  - 支持按行业分组的因子分析
- CLI 入口：`python -m quant_factor_analysis --universe japan_large_30 --start ... --end ...`
- 不改动现有 scorer 的输出协议，只新增一个适配层

### Dependencies

- `alphalens-reloaded`（PyPI 包）

### Success criteria

- 能对现有 momentum / low-vol / mean-reversion 三个因子输出完整 alphalens tear sheet
- IC 分析结果与 walk-forward 回测结果方向一致（验证正确性）

---

## Phase 3: 丰富因子库（1-2 周）

### Why third

在 alphalens 框架就绪后，新增因子的评估成本大幅降低——因子质量几秒就能判断。

### What

- 行业因子：接入东证 33 行业分类，实现行业中性化打分
- 宏观因子：日银短观数据、日本 GDP 等公开免费宏观指标
- 基本面因子（可选，视 EDINET 数据获取难度）：
  - 如果 EDINET 接入顺利：加入 BPR、ROE、负债比率等基础财务因子
  - 如果数据清洗量过大：推迟到后续版本

### Dependencies

- 东证行业分类数据（公开信息）
- 日银统计数据 API（公开免费）
- EDINET API（公开免费，但数据清洗可能复杂）

### Success criteria

- 因子数量从 3 个扩展到 6+ 个
- 每个新因子都通过 alphalens IC 分析验证
- 行业中性化后因子的 IC 质量保持或有改善

---

## Phase 4: vectorbt 替换 Backtrader（2-3 周）

### Why last

1. Backtrader 当前是可用的，不是紧急问题
2. Phase 1-3 让因子质量得到充分验证，此时换引擎的价值最大化
3. 避免在未验证的信号上重新踩坑

### What

- 新增 `engine/vectorbt_runner.py`，封装 vectorbt 回测逻辑
- 移植 commission/slippage 模型到 vectorbt（保留 friction.json 反馈闭环）
- 重构 `research/walk_forward.py` 使用 vectorbt 替代 Backtrader
- 保留旧 Backtrader 代码，用 CLI flag（`--engine vectorbt` vs `--engine backtrader`）切换
- 对比两种引擎在相同配置下的输出，确认一致性后删除旧代码

### Dependencies

- `vectorbt`（PyPI 包）

### Success criteria

- 相同参数配置下，vectorbt 输出与 Backtrader 输出偏差 < 1%
- 回测耗时减少 50% 以上
- 所有现有测试仍然通过（或合理修改后通过）

---

## Phase 5: pyfolio 绩效分析 + riskfolio-lib 组合优化（1-2 周）

### Why last

这些是锦上添花——在因子验证完毕、回测引擎稳定之后再加入，不会干扰因子研究的归因。

### What

- 接入 `pyfolio-reloaded`：为每次 walk-forward 实验生成标准 tear sheet
- 接入 `riskfolio-lib`：在 walk-forward 窗口内用 HRP 或风险平价替代等权分配
- 对比等权 vs 优化后的 OOS 表现，确认优化器的实际贡献

### Dependencies

- `pyfolio-reloaded`
- `riskfolio-lib`

### Success criteria

- 每个 walk-forward 实验都有 pyfolio tear sheet
- 风险优化后的组合在 holdout 期 Sharpe >= 等权基线

---

## Risk Mitigation

- **渐进发布**：每个 phase 是独立可交付的增量，不阻塞现有功能
- **旧代码共存**：Backtrader 路径保留到 Phase 4 验证通过
- **回归测试**：173 个现有测试必须在每个 phase 之后保持通过
- **数据不变性**：`.research_artifacts/` 和 approved params 格式向后兼容
