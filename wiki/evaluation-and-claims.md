# 评估、指标与对外表述 / Evaluation and Claims

Last updated: 2026-08-01

本页定义 dashboard 指标来自哪里、每个指标表示什么，以及什么结论可以从工程演示中推出。
项目可以有很强的展示语言——多模态、端到端、可审计、隐私预算可见、模型贡献可量化——但
不同证据层级不能混写成临床性能。

## 证据层级

| 层级 | 当前代表 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 协议/安全回归 | `verify_security.py` 及子套件 | payload schema、签名、审计链、DP 机制、掩码相消、超时/重连/预算行为 | 恶意节点一定诚实、生产部署无漏洞、临床有效 |
| 通用工程 benchmark | HAR | 多节点、IID/non-IID、privacy-utility 和 centralized-DP 对照 | ASD、真实 subject-level 或跨医院效果 |
| 模态合成 demo | eyegaze/action/action_cdp/neuro synth | 原始格式→本地特征→联邦→模型→推理的端到端连通 | 真实患者、真实设备、真实 fMRI 或临床 AUC |
| 历史外部模型证据 | frozen CDP report/model | 原模型在其锁定测试设计下的历史表现 | 新 `action_cdp` DP forest 的表现 |
| 真实回顾性验证 | 尚需按研究设计完成 | 在给定 cohort/split/device 上的回顾性 utility | 前瞻临床效益、监管批准 |
| 多中心前瞻验证 | 不在当前工程 POC | 临床 generalisability、workflow utility | 自动获得产品注册或所有人群表现 |

## Dashboard 的测试集从哪里来

协调器启动时读取：

```text
data/test.npz  → X_TEST, Y_TEST
data/meta.json → classes, modality, baselines, DP config
```

每次聚合完成后，新的全局 ensemble 在同一个 locked test set 上评估。参与节点不上传自己的
test predictions 或 test labels，当前 dashboard 也不是在刚提交的 10+10 视频上计算 AUC。

这带来三个重要解释：

1. **同一纵尺**：轮次之间使用相同 test set，指标差异可作为模型快照变化；
2. **不是因果贡献**：一轮同时包含新随机树、DP 噪声和整个 cohort 的贡献，不能把 `Delta AUC`
   解释为某机构或某十个视频的 Shapley/causal contribution；
3. **证据受 test set 限制**：若 `data/test.npz` 来自 synthetic demo，dashboard 只能展示 synthetic
   engineering utility；替换节点的真实视频不会自动把测试集变成临床验证集。

## 当前二分类指标

系统显式把 `ASD` 定义为 positive class。设混淆矩阵为：

| | 预测 TD | 预测 ASD |
|---|---:|---:|
| 真实 TD | TN | FP |
| 真实 ASD | FN | TP |

### AUC

ROC AUC 衡量模型给随机 ASD 样本的分数高于随机 TD 样本的概率排序能力，与单一决策阈值无关。
优点是适合观察排序质量；局限是类别极不平衡时应同时看 PR-AUC，当前尚未报告 PR-AUC。

### Accuracy

`(TP+TN)/(TP+TN+FP+FN)`。直观，但在类别失衡时可能被多数类掩盖。

### Balanced accuracy

`(sensitivity + specificity)/2`。让 ASD 与 TD 两类获得相同权重，通常比普通 accuracy 更适合
不平衡二分类。

### Sensitivity / recall / TPR

`TP/(TP+FN)`，即真实 ASD 中被模型判为 ASD 的比例。dashboard 当前使用 argmax 决策；它不等于
历史 CDP 报告中某个预设阈值（例如 0.4507）下的 sensitivity。

### Specificity / TNR

`TN/(TN+FP)`，即真实 TD 中被模型判为 TD 的比例。它必须与 sensitivity 一起报告；不能只挑
更好看的一个。

### Precision / PPV

`TP/(TP+FP)`，即预测 ASD 中真实为 ASD 的比例。它强烈依赖样本 prevalence，不能把一个平衡
测试集的 precision 直接用于真实筛查人群。

### F1

precision 与 recall 的调和平均。它不使用 TN，因此不能替代 specificity 或 balanced accuracy。

### MCC

Matthews correlation coefficient 同时使用 TP/TN/FP/FN，范围通常是 -1 到 1；0 近似随机相关，
1 是完美预测。对类别不平衡比 accuracy 更稳健。

### Brier score

阳性概率与二元真值平方误差的均值，越低越好。它同时反映 discrimination 与 calibration，不能
只用 AUC 判断概率是否可信。

### ECE

当前实现把 ASD 概率分成 10 个区间，计算 confidence 与 observed frequency 的加权差，越低越好。
ECE 对 bin 数和样本量敏感，小测试集上只能作诊断，不能作精确校准证明。

### ROC 与混淆矩阵

状态接口返回最多 32 个紧凑 ROC 点供 UI 绘制，并返回 TN/FP/FN/TP。完整科研分析应在冻结预测
上重新计算置信区间、阈值表和 bootstrap，而不是只截图 dashboard。

## 当前决策阈值

`GlobalModel` 默认选择概率最大的类别，二分类中通常相当于约 0.5 阈值。项目目前没有在新
`action_cdp` 模型上继承历史 CDP threshold，也没有 clinical operating point selection。

未来若选择 operating point，应在 calibration/validation set 上预先冻结，例如：

- 优先满足最低 sensitivity，再最大化 specificity；
- 预先定义 Youden J；
- 按真实筛查 prevalence 和 cost function 选择；
- 在独立 locked test set 上只评估一次。

不能在 test set 上一边挑阈值一边报告最终性能。

## 三个“模型参考”分别是什么

### Federated DP model

节点 leaf counts 经过安全聚合（或 cohort1 central-DP）与 Laplace 噪声后生成的 JSON ensemble。
这是 dashboard 和 `/model` 真正展示/下载的模型。

### Centralized-DP reference

`prepare_data.py` 在 pooled train set 上使用相同数据无关计数森林和 DP 噪声生成的机制参考。
它帮助检查 federation 是否大致复现同一种 pooled-DP mechanism；它不是生产模型。

### Non-private ExtraTrees ceiling

标签优化切分的 `ExtraTreesClassifier`，默认 `class_weight=balanced`。它不使用当前隐私结构，
只是显示“如果允许 pooled labels 与数据驱动切分，当前表示大概还有多少 utility 空间”。它不是
严格理论上限，也不能与不同 split、seed 或数据集的结果混比。

## Round curve 不是梯度收敛曲线

每轮重新从公开 seed 构造一批随机树、汇总计数、加噪并加入 ensemble。没有：

- loss/backprop；
- 在同一组树上更新参数；
- optimizer state；
- FedAvg；
- monotonic improvement guarantee。

曲线主要显示 ensemble-size variance reduction 与 DP 噪声/有限样本波动。准确用语是：

> “Per-round global ensemble utility” 或 “ensemble growth curve”。

不准确用语是：

> “Deep model convergence” 或 “每轮都在继续优化同一个模型”。

## 文件、窗口、视频与受试者指标

### 当前 analysis unit

| 模态 | 一条特征行 |
|---|---|
| eyegaze | 一个 CSV recording |
| action | 一个 `(T,33,4)` window；4D NPZ 中每个 window 一行 |
| action_cdp | 一个满足 24–64 sampled-frame 规则的 clip/window |
| neuro | 一个二维 scan/time-series 文件 |

`prepare_data.py` 使用相对文件路径作为 group，因此可以阻止同一 4D NPZ 的窗口跨 train/test。
但同一受试者若有多个文件仍可能跨 split；只有显式 subject id 才能称为 subject-level。

### 当前 coordinator 指标是 row/window-level

`data/test.npz` 当前只保存 X/y，没有保存 group。一个包含更多窗口的 action 文件可能在指标中
得到更大权重，无法直接输出 one-video-one-vote 或 one-subject-one-vote 指标。

真实研究至少应同时报告：

- window/row-level；
- recording/video-level aggregation；
- subject-level aggregation；
- institution-held-out；
- 每种设备/年龄/性别/语言/站点 subgroup（在伦理与样本量允许时）。

## DP 结果的评估单位

当前 sensitivity 1 与 epsilon 证明使用 add/remove-one-row adjacency。它不是自动的 person-level
DP。一个受试者贡献多个视频/窗口时，person-level sensitivity 会随最大贡献量上升。

任何 person-level claim 需要：

- 稳定 subject id 或本地 group key；
- 每人贡献 clipping/capping；
- group adjacency；
- 重新标定噪声；
- 重新跑 privacy accountant 与 utility benchmark。

## “更多数据带来改善”应怎样展示

可以强有力地展示：

- 本轮 cohort 代表的 local samples；
- 增加的树；
- epsilon 增量和剩余预算；
- AUC、sensitivity、specificity、Brier 等前后差；
- signed audit event 与 model hash；
- 原始记录传输量为 0；
- ≥3 节点时单节点计数被成对掩码隐藏。

不应自动声称：

- AUC 必然上升；
- 某节点造成了全部变化；
- 10+10 视频等于 20 个独立受试者；
- 多一轮就是更多“训练 epoch”；
- synthetic AUC 是 clinical AUC。

更合适的展示话术是：

> “新一轮贡献在不移动原始记录的前提下形成了一个新的可审计全局模型快照；中控台同时展示
> utility、calibration、隐私预算与协议事件，因此提升、波动和代价都可见。”

## 半监督/自监督评估设计

### 半监督

在相同人工标签预算、相同 epsilon 总预算、相同 split 下比较：

1. labeled-only；
2. labeled + unlabeled；
3. full-label upper bound；
4. pseudo-label coverage/precision/abstention；
5. calibration 与 per-class utility；
6. institution-held-out 与 subject-held-out；
7. subgroup 和 device/domain shift。

不能把伪标签自身当作 test truth。

### 自监督

至少比较 hand-crafted baseline、public frozen encoder、frozen encoder + linear/forest probe，
以及在相同标签预算下的 downstream ASD/TD utility。Pretext loss 下降不能替代真实下游评估。

若 encoder 使用参与者无标签数据训练，必须把 encoder 的隐私支出、训练 split 和 membership
leakage 纳入结果；不能只报告分类头 epsilon。

## 建议的科研报告清单

每个结果表至少记录：

- dataset/cohort 版本与 synthetic/real 标识；
- modality/schema/adapter hash；
- analysis unit 与 subject/group 定义；
- train/validation/test 数量及 class distribution；
- split 方法与 seed；
- institution/device inclusion；
- nodes/cohort/rounds/trees/depth；
- epsilon-per-round、总 epsilon、adjacency unit；
- secure aggregation 或 cohort1 central-DP；
- AUC/BACC/sensitivity/specificity/MCC/Brier/ECE；
- threshold selection 方法；
- confidence intervals；
- baselines 与统计检验；
- model hash 和 audit bundle hash。

## 对外可用的强表述

以下语言突出项目价值，同时与当前证据一致：

- “A single auditable privacy kernel serves four heterogeneous signal front ends.”
- “Raw recordings remain institution-local; federated learning operates on bounded leaf statistics.”
- “Utility, calibration, privacy spend, cohort state and signed evidence are visible in one console.”
- “The architecture separates representation innovation from the privacy-preserving classifier, so
  new modalities can be versioned without weakening the protocol boundary.”
- “The system supports an evidence ladder from synthetic end-to-end rehearsal to future
  institution-held-out validation.”

以下语言目前证据不足：

- “Clinically validated ASD diagnostic model”；
- “No information leaves the node”；
- “The coordinator never sees an un-noised aggregate”；
- “Cohort1 uses secure aggregation”；
- “action_cdp continues the historical CDP classifier”；
- “Unlabeled/self-supervised/federated SSL is already implemented”；
- “More data guarantees better AUC”。

## 相关页面

- [`modalities-and-models.md`](modalities-and-models.md)：四个前端与共同分类器；
- [`learning-modes.md`](learning-modes.md)：有标签、无标签、半监督、自监督和路线图；
- [`../TODO.md`](../TODO.md)：已决定的实施优先级与证据门槛；
- [`state-of-project.md`](state-of-project.md)：当前发布准备状态。
