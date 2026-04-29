# Vectorbt Integration Design

## Status: Draft

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

## New Files

```
engine/vectorbt_runner.py     # run_backtest_vectorbt() — single backtest
engine/order_builder.py       # build_orders() — scored_df → vbt orders
tests/engine/test_vectorbt_runner.py
tests/engine/test_order_builder.py
```

## Modified Files

```
engine/runner.py              # add engine dispatch
src/main.py                   # add --engine flag
src/optimize.py               # add --engine flag, pass to evaluate_weight_tuple
```

---

## Component 1: `engine/order_builder.py`

纯函数，不依赖 vectorbt 或 Backtrader。

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
pd.DataFrame(columns=["symbol", "date", "size", "price", "fees", "order_type"])
```

- `size`: 正数 = BUY, 负数 = SELL
- `price`: 执行价格（= 收盘价 × (1 - slippage) for BUY, × (1 + slippage) for SELL）
- `fees`: 佣金（= |size| × price × commission_rate）
- `order_type`: "target_weight" for rebalance orders

**逻辑：**
1. 对每个 rebalance 日期的 scored DataFrame，提取 `is_top_n=True` 的 symbols
2. 计算等权目标：`target_value = total_equity * 0.95 / top_n`
3. 与上一个 rebalance 日期的持仓比较，生成 BUY/SELL orders
4. 应用滑点和佣金

**边界情况：**
- 第一个 rebalance 日期：全部为 BUY
- 空 scored：返回空 orders DataFrame
- top_n > 可用 symbol 数：使用实际可用数量

---

## Component 2: `engine/vectorbt_runner.py`

### run_backtest_vectorbt(data_dfs, start, end, weights, top_n, initial_cash, commission_rate, slippage_pct, momentum_definition, reversal_filter_params) → dict

**输出：** 与 `evaluate_weight_tuple()` 相同的 metrics dict：
```python
{
    "return_pct": float,
    "sharpe": float,
    "drawdown": float,
    "scores": pd.DataFrame,  # from last scoring period
}
```

**流程：**
1. 按 rebalance 日期遍历，调用 scorer（`score_universe` 或 `score_research_universe`）
2. 每个日期调用 reversal filter（如果启用）
3. 累积 `period_scores`
4. 调用 `build_orders()` 生成 orders
5. 调用 `vbt.Portfolio.from_orders()`
6. 从 portfolio.stats() 提取 return / sharpe / drawdown

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

### CLI 修改

`main.py` 和 `optimize.py` 都添加：
```
--engine {backtrader,vectorbt}   (default: backtrader)
```

`optimize.py` 还添加快捷 flag：
```
--fast   (等同于 --engine vectorbt)
```

---

## Consistency Verification

两个引擎在相同输入下应该产生"足够接近"的结果：

| 指标 | 容差 |
|------|------|
| 年化收益 | < 1% 偏差 |
| Sharpe | < 0.05 偏差 |
| 排名（cross-sectionally） | 完全一致 |

验证方法：运行 `scripts/verify_engine_parity.py`，对比两个引擎在 `topix_top_10` 上 1 年回测的所有指标。

---

## Task Order

1. `engine/order_builder.py` + tests（纯函数，独立可测）
2. `engine/vectorbt_runner.py` + tests（依赖 order_builder + vbt）
3. Engine dispatch in `engine/runner.py` + `--engine` flag in CLI
4. Walk-forward integration in `optimize.py`
5. Parity verification script
6. Full test suite — confirm 197 existing tests pass, new tests pass

---

## Non-Goals

- 不删除 Backtrader 代码
- 不改动 scorer、reversal filter、paper bot 的签名
- 不优化 portfolio 配置（等权 top-N 保持不变）
- 不支持 `buy_rank_threshold` / `sell_rank_threshold` 的 vectorbt 实现。如果用户指定了非默认 threshold 值，vectorbt 引擎报错并提示使用 `--engine backtrader`
- vectorbt 路径仅支持 pure top-N equal weight 策略（这是当前 approved 配置，也是 OOS 验证使用的配置）
