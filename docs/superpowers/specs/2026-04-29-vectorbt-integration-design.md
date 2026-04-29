# Vectorbt Integration Design

## Status: Approved

## Goal

用 vectorbt 替换 Backtrader 作为回测引擎，在保持结果一致的前提下大幅提升回测性能（10-100x），尤其是 walk-forward 参数搜索场景。

## Constraints

- 渐进共存：`--engine vectorbt|backtrader` flag 切换，旧代码保留到验证通过
- 先写适配层和测试，再集成
- 所有现有测试（197）必须保持通过
- 不改变 scorer、reversal filter、paper bot 的接口
- `vectorbt` 作为新增依赖加入 `pyproject.toml`

## Dependencies

- `vectorbt` — 向量化回测库（PyPI 包）
- 现有的 `pandas`、`numpy` 已满足计算需求

---

## Architecture

```
                          score_universe()
                               ↓
                    ranked DataFrame (per date)
                               ↓
              ┌────────────────┴────────────────┐
              ↓                                  ↓
     Backtrader path (existing)         Vectorbt path (new)
              ↓                                  ↓
    UniversalMultiFactor              build_orders()
    (bt.Strategy)                           ↓
              ↓                  vbt.Portfolio.from_orders()
    cerebro.run()                           ↓
              ↓                     portfolio.stats()
    metrics dict                            ↓
                                   metrics dict (same keys)
```

**Key insight**: scoring and reversal filter happen OUTSIDE both engines — shared by both paths. The engine only handles order execution and P&L tracking.

## New Files

```
engine/order_builder.py          # build_orders() — scored_df → vbt orders (pure function)
engine/vectorbt_runner.py        # run_backtest_vectorbt() — single backtest
tests/engine/test_order_builder.py
tests/engine/test_vectorbt_runner.py
scripts/                         # new directory
scripts/verify_engine_parity.py  # compare backtrader vs vectorbt output
```

## Modified Files

```
engine/runner.py                 # add engine dispatch
src/main.py                      # add --engine flag
src/optimize.py                  # add --engine flag, pass to evaluate_weight_tuple
```

---

## Component 1: `engine/order_builder.py`

纯函数，不依赖 vectorbt 或 Backtrader。它将一组 rebalance 日期的 scorer 输出转换为 vectorbt 可执行的订单。

### build_orders(period_scores, data_dfs, top_n, initial_cash, commission_rate, slippage_pct) → pd.DataFrame

**输入：**
- `period_scores`: `dict[pd.Timestamp, pd.DataFrame]` — 每个 rebalance 日的 scorer 输出
- `data_dfs`: `dict[str, pd.DataFrame]` — symbol → Close DataFrame
- `top_n`: int — 持仓数量
- `initial_cash`: float — 初始资金
- `commission_rate`: float — 佣金费率（如 0.001 = 10bp）
- `slippage_pct`: float — 滑点比例

**输出：**
```python
pd.DataFrame(columns=["symbol", "date", "size", "price", "fees"])
```

- `size`: float, 目标持仓市值占总资金的比例。例如 0.3167 表示该 symbol 应占 31.67%
- `price`: float, 执行价格（= 收盘价 × (1 - slippage) for BUY, × (1 + slippage) for SELL）
- `fees`: float, 佣金金额（= |size_transition| × price × commission_rate, pre-computed）
- `date`: pd.Timestamp, 订单执行日期

**Portfolio tracking approach（明确为 Approach A — target percentage）**：

`build_orders()` 不模拟持仓变化——它只表达"在每个 rebalance 日期，等权持有 top-N 股票"这个意向。实际的 P&L 计算由 vectorbt 的 `from_orders()` 完成。

具体逻辑：
1. 对每个 rebalance 日期，从 `scored` DataFrame 提取 `is_top_n=True` 的 symbols
2. 计算目标权重：`target_weight = 0.95 / len(top_n_symbols)`（等权，留 5% 现金缓冲）
3. 为每个 top symbol 生成一条订单：`size = target_weight`
4. 将收盘价调整为考虑滑点后的执行价
5. 预计算佣金（基于权重变化幅度 × price × commission_rate）

**为什么用 target percentage 而非绝对股数**：vectorbt 的 `size_type="targetpercent"` 模式会在每个日期将该 symbol 的持仓调整到目标权重，自动处理卖出旧仓、买入新仓、调仓。这天然匹配我们的月频等权 rebalance 逻辑。

**边界情况：**
- 第一个 rebalance 日期：全部为 BUY（从 0 到 target_weight）
- 空 scored：返回空 orders DataFrame
- top_n > 可用 symbol 数：使用实际可用数量重新计算目标权重

---

## Component 2: `engine/vectorbt_runner.py`

### run_backtest_vectorbt(...) → dict

**完整签名：**
```python
def run_backtest_vectorbt(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    top_n: int = 3,
    initial_cash: float = 1_000_000.0,
    commission_rate: float = 0.001,
    slippage_pct: float = 0.0005,
    momentum_definition: str = "90d",
    reversal_filter_params=None,
    evaluation_start: str | None = None,
    evaluation_end: str | None = None,
) -> dict:
```

**输出——与 `evaluate_weight_tuple()` 完全一致：**
```python
{
    "return_pct": float,            # total return % over evaluation window
    "sharpe": float,                # annualized Sharpe ratio
    "drawdown": float,              # max drawdown
    "symbol_returns": dict,         # {symbol: return_pct} per symbol, MATCHES EXISTING CONTRACT
    "scores": pd.DataFrame,         # scores as of the FINAL rebalance date (not end-of-window)
}
```

`scores` 说明：与当前 Backtrader 路径（在评估窗口结束时一次性调用 scorer）不同，vectorbt 路径在每月 rebalance 时调用 scorer。返回的 `scores` 来自最后一个 rebalance 日期的评分结果——这与其下游用途一致（artifact 持久化和 diagnostics）。

`symbol_returns` 说明：从 `portfolio.positions` 推导每个 symbol 的收益。这是 walk-forward diagnostics pipeline 的必需字段（walk_forward.py lines 343-344 读取它来计算 hit rate、top/bottom contributors）。

**流程：**
1. 根据 `momentum_definition` 确定所需 lookback 天数（90d → 90, 12_1 → 252）
2. 生成 rebalance 日期列表：从 `start` 到 `end` 的月末交易日
3. 对每个 rebalance 日期 `T`：
   a. 从 `data_dfs` 中为每个 symbol 截取 `[T - lookback_days, T]` 的数据窗口
   b. 对窗口内数据调用 scorer（`score_universe` 或 `score_research_universe`）
   c. 如果启用，调用 `apply_reversal_filter()` 过滤
   d. 将结果存入 `period_scores[T]`
4. 调用 `build_orders(period_scores, ...)` 生成目标权重 orders
5. 构建 Close 价格矩阵（日期 × symbol）
6. 调用 `vbt.Portfolio.from_orders()` — **明确禁止二次应用 slippage/commission**：
   ```python
   portfolio = vbt.Portfolio.from_orders(
       close=close_prices,          # date × symbol Close matrix
       size=orders_df["size"],      # target percentage
       size_type="targetpercent",
       price=orders_df["price"],    # slippage already baked in
       fees=orders_df["fees"],      # commission already pre-computed
       freq="D",
       cash_sharing=True,           # share cash across all symbols
       init_cash=initial_cash,
       group_by=True,               # group all symbols under one portfolio
       call_seq="auto",
   )
   ```
7. 如果指定了 `evaluation_start/evaluation_end`，仅取该子窗口的 returns 计算 metrics
8. 提取 `symbol_returns`：遍历 `portfolio.positions` 计算每个 symbol 的 PnL
9. 从 `portfolio.stats()` 提取 return_pct, sharpe, drawdown

**Warmup 逻辑**：调用方（`evaluate_weight_tuple`）已通过 `_slice_window_data()` 加载了包含 warmup bars 的扩展数据窗口。`run_backtest_vectorbt()` 在 step 3a 中自行对每个 rebalance 日期截取 scoring 所需的 lookback 窗口。这保证了 scorer 在任何日期都不会看到未来数据。

**Slippage 来源**：slippage_pct 由调用方传入。对于 walk-forward 路径，调用方负责调用 `load_live_slippage()` 获取实时校准值。Vectorbt runner 不直接读取 friction.json。

---

## Component 3: Engine Dispatch

### `engine/runner.py` 修改

```python
def run_backtest(data_dfs, ..., engine="backtrader"):
    if engine == "vectorbt":
        return run_backtest_vectorbt(...)
    # existing backtrader path
    ...
```

### `optimize.py` 修改

`evaluate_weight_tuple()` 接收 `engine` 参数。当 `engine="vectorbt"` 时跳过 Backtrader 的 cerebro 创建，直接调用 `run_backtest_vectorbt()`。**Scoring 不再在 `evaluate_weight_tuple` 中执行**——改为 vectorbt runner 在 rebalance 日期遍历中执行。

### CLI 修改

`main.py` 和 `optimize.py` 都添加：
```
--engine {backtrader,vectorbt}   (default: backtrader)
```

`optimize.py` 还添加：
```
--fast   (等同于 --engine vectorbt)
```

---

## Consistency Verification

两个引擎在相同输入下应该产生"足够接近"的结果：

| 指标 | 容差 | 备注 |
|------|------|------|
| 年化收益 | < 1% 偏差 | 允许因浮点精度和订单执行时机产生的微小差异 |
| Sharpe | < 0.05 偏差 | 同上 |
| 排名（cross-sectionally） | 完全一致 | scorer 输出在两个路径间共享，必须相同 |
| symbol_returns | < 0.5% 每 symbol | 逐 symbol 验证 |

验证方法：运行 `scripts/verify_engine_parity.py`，对比两个引擎在 `topix_top_10` 上 1 年回测的所有指标。

---

## Task Order

1. `engine/order_builder.py` + tests（纯函数，独立可测）
2. `engine/vectorbt_runner.py` + tests（依赖 order_builder + vbt）
3. Engine dispatch in `engine/runner.py` + `--engine` flag in CLI
4. Walk-forward integration in `optimize.py` — 修改 `evaluate_weight_tuple()` 支持 engine 参数
5. `scripts/verify_engine_parity.py` — 双引擎对比脚本
6. Full test suite — confirm 197 existing tests pass, new tests pass

---

## Non-Goals

- 不删除 Backtrader 代码
- 不改动 scorer、reversal filter、paper bot 的签名
- 不优化 portfolio 配置（等权 top-N 保持不变）
- 不支持 `buy_rank_threshold` / `sell_rank_threshold` 的 vectorbt 实现。如果用户指定了非默认 threshold 值，vectorbt 引擎报错并提示使用 `--engine backtrader`
- vectorbt 路径仅支持 pure top-N equal weight 策略（这是当前 approved 配置，也是 OOS 验证使用的配置）
