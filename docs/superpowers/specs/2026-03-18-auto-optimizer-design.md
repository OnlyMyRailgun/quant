# Multi-Factor Auto-Optimizer Design (Grid Search)

## Objective
To build a tool that automatically tests hundreds of different parameter combinations (weights) for the Universal Multi-Factor strategy to mathematically identify the optimal portfolio composition. This moves us from "guessing" factor weights to "data-driven optimization" (Grid Search / Parameter Sweeping).

## Architecture

We will leverage Backtrader's native but complex `cerebro.optstrategy()` capability, wrapping it in a user-friendly CLI script (`src/optimize.py`).

### 1. Grid Search Scope
Instead of passing a single value like `weight_mom=1.0`, we pass a range of possible values: `weight_mom=(0.0, 0.5, 1.0)`.
For 3 weights, this creates `3 x 3 x 3 = 27` parallel backtests. 
By running this over a historical window, we can map out the "terrain" of profitability.

### 2. Multi-Core Execution
Optimization is extremely CPU-intensive. `cerebro.run(maxcpus=None)` allows the script to split the 27 runs across all available CPU cores of your Mac, drastically speeding up the grid search.

### 3. Data Extraction Pipeline
When optimizing, Backtrader returns a complex nested list of strategy objects `[[Strat1], [Strat2], ...]`.
The engine must iterate through these results to extract:
* The specific weights injected (`strat.p.weight_mom`, etc.)
* Final Account Value
* Max Drawdown
* Sharpe Ratio

### 4. Presentation & Analysis
We will compile these results into a `pandas.DataFrame`, sort the DataFrame by **Final Account Value (Return)** or **Sharpe Ratio**, and print the top 10 best-performing weight combinations to the terminal in a clean, professional tabular format. 

In a future iteration, this cleanly structured DataFrame can be piped into a heatmap chart or 3D scatter plot using `matplotlib` or `seaborn`.

## Constraints & Trade-offs
* **Overfitting Danger:** The combinations that performed best in 2023 are not guaranteed to perform best in 2024. This is called "curve fitting." For now, our goal is engineering the tool, not finding the true Holy Grail formula. 
* **Logging Noise:** Printing every single buy/sell ticket 27 times will crash the terminal and make it unreadable. We must ensure the `_LoggingWrapper` or `print` logic is entirely silenced during Optimization runs.

## Implementation Steps
1. Create `src/optimize.py` as a standalone executable.
2. Initialize `bt.Cerebro(optreturn=False)` and bypass the noisy Trade Logger.
3. Configure `optstrategy(UniversalMultiFactor, weight_mom=(0.0, 0.5, 1.0), weight_vol=(0.0, 0.5, 1.0), weight_rev=(0.0, 0.5, 1.0))`.
4. Run, extract analyzers, load into `pandas`, and print the leaderboard.
