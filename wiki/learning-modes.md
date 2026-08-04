# 有标签、无标签与学习模式 / Learning Modes

Last updated: 2026-08-04

本页区分五个容易混淆的概念：监督学习、无标签推理、无监督学习、自监督预训练和半监督学习。
当前 GBA-DF 的**已实现训练路径是有标签监督分类**。无标签、自监督和半监督部分是可以沿现有
隐私架构扩展的研究设计，不是当前产品已经具备的按钮或协议。

## 能力状态矩阵

| 学习方式 | 当前状态 | 能否直接复用现有 leaf-count wire format | 准确解释 |
|---|---|---:|---|
| 有标签监督训练 | **已实现** | 是 | 本地 `y` 决定叶节点的 class bin |
| 一个机构只有一个类别 | 技术上可参与 | 是 | 整个 federation 与 locked test set 仍应覆盖全部类别 |
| 下载模型后对无标签 `X` 本地推理 | 部分实现 | 不产生训练更新 | 预计算 X-only NPZ 可推理；原始 folder 路径有误标风险 |
| 无标签样本参与当前分类训练 | **未实现** | 否 | 没有 `y` 就没有 leaf×class histogram |
| 主动学习后人工标注 | 可按现有工具手工完成，未产品化 | 标注后可以 | 最稳妥的近程半监督工作流 |
| hard pseudo-label self-training | 设计方案 | 大体可以 | 需要阈值、来源、去重、贡献上限和独立真值评估 |
| soft pseudo-label | 未实现 | 否 | 当前 payload 只允许非负整数计数 |
| 公共冻结 SSL encoder + 当前监督森林 | 可落地扩展 | 监督头可以 | encoder、预处理、embedding 轴和 bounds 必须冻结并版本化 |
| 各机构独立训练不同 SSL encoder 后直接聚合 | 不兼容 | 否 | 特征轴不对齐，也会破坏现有敏感度证明 |
| Federated SSL / FedAvg / FixMatch | 新协议研究 | 否 | 需要参数/梯度协议、裁剪、DP accountant 和新审计 |
| 无标签 DP density/occupancy forest | 接近现有原语，但未实现 | 可复用 masking 原语 | 输出密度/异常分数，不是 ASD/TD 分类器 |
| 多模态联合学习 | 未实现 | 否 | 当前每个模态是独立 federation |

## 先定义术语

### 有标签监督学习（supervised learning）

每个训练样本都有任务标签，例如 `ASD` 或 `TD`。模型直接优化或估计 `P(y|x)`。当前项目
使用的不是梯度 loss，而是标签条件的叶节点计数。

### 无标签推理（unlabeled inference）

已有模型对没有真值标签的新样本产生概率和预测。它不更新模型，因此不属于无监督训练或
半监督训练。推荐下载 JSON 模型后本地推理，使查询特征也不离开机构。

### 无监督学习（unsupervised learning）

从没有任务标签的数据中发现聚类、密度、异常或低维结构。它不一定产生 ASD/TD 分类器。

### 自监督学习（self-supervised learning, SSL）

从输入自身构造预训练目标，例如遮住一段姿态后重建、判断时间顺序或让同一记录的两种增强
表示接近。预训练不需要 ASD/TD 标签，但下游 ASD/TD 性能通常仍需少量标签评估或训练分类头。

### 半监督学习（semi-supervised learning）

同时使用少量真标签和大量无标签数据，例如伪标签、consistency regularization、label
propagation 或主动学习。伪标签不是 self-supervised；它是模型对无标签样本产生的猜测。

### 弱标签与伪标签

- **强真值标签**：经过明确诊断/专家 adjudication，且来源与时间点可追溯；
- **弱标签**：筛查问卷、行政编码、照护者报告或站点规则，可能系统性偏差；
- **伪标签**：模型预测，不是临床真值；
- **未标注**：没有任务标签，不代表数据匿名，也不代表隐私风险低。

训练前应保留 `label_source`、版本、标注者角色和置信等级；当前文件夹格式只编码 ASD/TD，
尚未把这些 provenance 字段放进产品 schema。

## 当前有标签监督学习：实际发生的每一步

```text
机构本地原始文件
  → 固定、版本化模态前端
  → public tanh(raw / scale)
  → X + 显式 y + 本地 file group
  → 公共 seed/bounds 生成相同随机树
  → 每行随机分配到一棵树
  → 本地 leaf × class 整数直方图
  → cohort≥3: X25519 pairwise masking
  → 协调器恢复 pooled leaf × class counts
  → Laplace(1/ε) 中央 DP
  → 叶概率森林
  → 跨轮 JSON forest ensemble
  → locked coordinator test set 上评估
```

### 训练数据要求

- 同一个 federation 的所有节点必须使用相同 modality key、schema、特征顺序、公开 scale、
  classes、forest depth、trees-per-round 与结构 seed；
- 每个训练特征行必须有 `ASD` 或 `TD` 标签；
- 一个机构可以只持有一个类别，但全体 cohort 最好覆盖全部类别；
- coordinator 的 locked test set 必须覆盖两个类别，才能计算二分类 AUC、灵敏度和特异度；
- 同一受试者/视频的衍生窗口应绑定同一 group，不能跨 train/test；
- 当前前端 group 是文件路径，因此默认只能保证 file/recording-grouped；同一人若有多个文件，
  仍需额外 subject id 才能实现真正 subject-level split。`prepare_data.py` 默认将该事实写入
  split metadata 并保留 test artifact 的 groups；只有提供完整的本地
  `recording,subject_id` CSV 映射时，才标记为 subject-grouped。

### 文件夹约定

```text
my_training_data/
├── asd/
│   ├── case_001.ext
│   └── case_002.ext
└── td/
    ├── case_101.ext
    └── case_102.ext
```

`.ext` 对眼动是 CSV，对动作是 NPZ 或经桌面端转换的视频，对神经数据是 NPZ/CSV。
标签优先从根目录下任何一层与 `asd`/`td` 完全匹配的路径段读取，也会从文件名 token 读取。

## 重要警告：当前原始文件夹不支持 `unlabeled/`

当前 `_label_of()` 为兼容旧演示，找不到 ASD/TD 时会回退为第一个类别；四个模态中第一个类别
都是 TD。也就是说：

```text
my_training_data/unlabeled/video_001.npz
```

现在会被标为“truth unavailable”，而不是作为 TD。`node.py` 和桌面端训练会拒绝包含这种
文件的目录；`predict.py` 可将独立的 `unlabeled/` 目录用于本地推理/审核，并在 CSV/终端
输出中明确标记 `truth unavailable`，且不将其纳入 accuracy。它不会生成训练更新。无标签池
仍应与有标签训练目录分开保存，直到显式 review/provenance schema 实现。

预计算的 X-only `data.npz` 和 raw-folder 都可用于有限的本地无标签推理；两者都不产生训练
更新。因此当前文档不能声称“无标签数据已经可以共享训练”。

## “共享有标签数据”到底共享了什么

原始文件和逐样本 `(x_i,y_i)` 不上传，但标签信息并非在数学上完全消失。节点计算的是
`leaf × class` 计数：

```text
C[tree, leaf, class]
```

因为每个样本每轮只进入一棵树，把所有 tree/leaf 的某类别计数相加即可得到 pooled class total。

- 三节点以上时，协调器只能得到整个 cohort 的 pooled counts，不能分离某个节点；
- 单节点时，协调器得到该节点精确的未加噪 counts，然后才加入中央 DP 噪声；
- 已发布模型受中央 DP 保护，但 trusted curator 在内存中确实见到 pre-noise pooled aggregate；
- dashboard 当前不展示类别总数，不代表协议层没有聚合标签信息。

这比上传原始标签行小得多，也有安全聚合和 DP 边界，但不应表述成“没有任何标签信息离开节点”。

## 20 个视频的监督学习例子

以 `action` 或 `action_cdp` 为例：

1. 在桌面端把 batch label 选为 ASD，一次选择 10 个 ASD 视频；
2. MediaPipe 在本机提取姿态并保存到当前临时/永久 NPZ 目录的 `ASD/`；
3. 把 batch label 改为 TD，再选择 10 个 TD 视频；
4. 扫描结果会同时显示 ASD/TD 文件数和衍生训练样本数；
5. 连接相同模态的 coordinator，测试 schema 后开始训练；
6. 默认每轮增加一批新的公开随机树并花费一个 epsilon-per-round；
7. dashboard 在服务器预先准备的 locked test set 上显示本轮模型指标。

当前浏览器转换通常每个视频保存一个 variable-length `(T,33,4)` 数组，因此通常是一个视频
产生一个特征行；已有 `(N,T,33,4)` NPZ 会产生 N 个窗口/行。合成 action demo 每文件有多个
60 帧窗口，所以合成演示的 samples/file 比例与真实浏览器视频可能不同。

### 为什么更多视频通常有帮助，但 AUC 不保证上升

- 计数信号相对固定尺度 Laplace 噪声更强；
- 更多姿态、设备、场景和站点覆盖可能提高泛化；
- 但随机树结构有表达上限；
- 错标、类别失衡、设备域偏移和低质量 pose 会稀释信号；
- 小数据时，一轮 20 棵深度 6 的树有大量叶槽，许多叶的真实计数接近 0，DP 噪声可能主导；
- 跨轮指标是 ensemble 增长后的变化，可能上升、下降或波动。

因此 dashboard 的 `Delta AUC` 是同一 held-out set 上的真实前后差，不是某个机构的因果边际
贡献，也不是“增加 10 个视频必然提高多少”的承诺。

## 当前最稳妥的半监督路线：主动学习

主动学习把无标签数据用于“决定先标哪一些”，但只有人工确认后的样本才进入训练：

1. 下载当前 DP 全局模型；
2. 在机构本地对独立的 unlabeled pool 推理；
3. 按低置信度、接近决策边界、模型分歧或代表性选择候选；
4. 由合格人员本地完成标签；
5. 记录 model hash、选择策略、标注来源和 subject id；
6. 将已确认样本移入 `asd/` 或 `td/`；
7. 沿现有监督协议贡献下一批计数。

它的优势是 wire format、DP forest 和安全聚合协议都不用改变，并且不会把模型自己的错误直接
当真值强化。需要产品化的部分包括本地 review queue、显式 `unlabeled/`、去重、标签审计和
永不把待审核/已训练病例混入 locked test set。

## 半监督路线 A：hard pseudo-label self-training

这是与现有整数计数最接近、但尚未实现的算法路线：

1. 用第 `r` 轮发布的 DP 模型作为固定 teacher；
2. 本地推理无标签池；
3. 仅接受 `max(P(ASD),P(TD)) >= tau` 的样本；
4. 低置信度样本 abstain；
5. 对每类、每视频、每受试者设贡献上限；
6. 记录 teacher model hash、阈值、时间和 pseudo-label provenance；
7. 在下一轮把接受的 hard label 放入整数 class counts；
8. 最终只在独立人工标注 test set 上评估。

### 为什么看起来兼容

接受后的伪标签仍是 ASD/TD hard label，因此最终可进入现有整数叶计数。对固定 DP teacher 的
本地推理属于 post-processing；伪标签在下一轮参与训练时，下一轮照常花费新的隐私预算。

### 为什么仍不能直接宣称支持

当前产品没有：

- human/pseudo 标签来源字段；
- 阈值和 class-specific calibration；
- 同一记录跨轮去重；
- 每类/每人 cap；
- 伪标签撤回与 teacher 更新策略；
- human-only、mixed 和 full-label 对照；
- 防止把 pseudo label 显示为临床真值的 UI。

更重要的是，teacher 的系统性偏差会形成 confirmation bias。只有 AUC 上升不足以证明伪标签
有效，必须报告伪标签 coverage、precision、class balance 和人工真值上的净改善。

## 半监督路线 B：soft pseudo-label

当前协议只接受非负整数 class counts，不支持例如 `[0.7,0.3]` 的软贡献。实现需要：

- fixed-point quantization；
- 每行 soft vector 的 L1 clipping；
- 新的整数范围、向量长度与模数溢出分析；
- 重新推导敏感度和 Laplace/Gaussian 噪声；
- coordinator 侧结构验证；
- 防止节点提交任意大权重；
- 审计中标出 hard/soft contribution。

不要用复制样本的方式模拟 0.7/0.3 权重；复制会增加单条记录的贡献并破坏 sensitivity 1。

## 自监督路线 A：公共冻结 encoder + 现有监督头

这是风险最低的 SSL 接入方式：先在公开数据或另行治理的数据上训练 encoder，然后冻结并发布：

- 输入预处理和采样规则；
- 模型格式、权重 hash 与许可证；
- 训练数据来源说明；
- 固定 embedding 维度和每个轴的语义契约；
- 公开 bounds/scales；
- schema version。

每个机构在本地运行完全相同的 encoder，把 embedding 作为新模态特征；有标签 subset 再进入
现有 DP forest。优点是原始数据仍本地、监督头可复用、协议证明边界清晰。

但若参与机构的无标签数据没有参与 encoder 训练，就只能说“使用了自监督预训练表示”，不能
说“这些机构的无标签数据已联邦贡献”。

### 各模态可用的 pretext tasks

| 模态 | 可研究的自监督目标 | 需要特别控制的增强 |
|---|---|---|
| eyegaze | masked timestep/segment reconstruction、next-fixation、temporal order、片段对比 | 不应让增强破坏 AOI/刺激语义；需使用真实时间戳 |
| action | masked joint/frame、future pose、temporal contrastive、速度/局部裁剪一致性 | 镜像可能改变左右不对称；视角增强必须符合摄像机几何 |
| action_cdp | 17 点序列 SSL 或 104 维 masked-feature autoencoder | 应发布 `action_cdp_v2`，不能静默改变 v1 特征含义 |
| EEG | masked channel/time-frequency reconstruction、跨片段/跨 session 对比 | 需先做采样率、滤波、伪迹与通道规范化 |
| fMRI | masked ROI、连接图 autoencoder、TR-aware temporal contrastive | 必须与当前 EEG-like `neuro` schema 分开 |

## 自监督路线 B：真正的 federated SSL

若希望各机构无标签数据共同更新 encoder，就需要新的训练协议，而不是给现有叶计数接口换名字：

- 全局 encoder、projection head 和 optimizer/checkpoint；
- FedAvg/FedProx 或 federated contrastive 方法；
- per-example 或 per-client update clipping；
- 梯度/参数的量化或 fixed-point 编码；
- 安全聚合权重/梯度；
- central/distributed DP noise；
- RDP、PRV 或适合多步训练的 privacy accountant；
- dropout recovery；
- poisoning/Byzantine 检测；
- checkpoint hash、模型版本、训练事件与审计扩展。

`secure_agg.py` 能掩码整数向量，不代表系统已经支持“安全聚合梯度”。当前 coordinator 的长度、
语义校验、噪声尺度和证明都绑定 leaf counts；神经更新必须重新设计与验证。

### 为什么不能各家自己训练一个 encoder 再直接用现有森林

即使各 encoder 输出相同维度，第 17 列在 A 机构和 B 机构也可能表达不同概念，公共随机阈值
无法对齐。另外，若 encoder/PCA/scaler/feature selector 由整个私有数据集拟合，移除一条记录
可能改变 encoder，并改变很多其他记录的叶路由；现有“移除一行只改变一个计数”的 DP 证明
不再成立。

因此不能在节点上私自拟合以下组件后继续沿用当前隐私声明：

- PCA 或 dictionary/codebook；
- StandardScaler/quantile normalization；
- feature selector；
- 自适应 embedding adapter；
- 用全部本地数据微调的 encoder。

除非这些步骤本身具有独立 DP、稳定性边界并纳入完整 accountant。

## 最接近当前机制的无监督扩展：DP occupancy/density forest

无标签样本也可以路由到公开随机树，但只统计每个 leaf 的 occupancy，不分 ASD/TD：

```text
O[tree, leaf]
```

每行仍可只贡献一个计数，因此可以复用成对掩码和 sensitivity-1 思路。潜在用途包括：

- 机构总体分布覆盖；
- 新样本低密度/异常分数；
- 跨轮或跨站点 drift 监测；
- 半监督模型的 confidence smoothing。

但当前 `JsonForest` 只保存叶类别概率，不保存可用于密度的 noisy leaf mass；模型 schema、预算、
评估和 UI 都要新增。occupancy forest 不是 ASD/TD 分类器，不能用无标签数据凭空产生 clinical
AUC；AUC 仍需要独立真值测试集。

## 隐私保证的单位：目前是行／窗口，不自动是人

当前 sensitivity 1 对应 add/remove-one-feature-row adjacency。若一段视频产生 `k` 个窗口，或者
同一个人贡献 `k` 个文件，那么移除整段视频/整个人最多改变 `k` 个计数；当前噪声没有按 `k`
放大。因此：

- 当前是 row/window-level DP；
- 不是自动的 video-level、recording-level 或 person-level DP；
- “标签替换”会从一个 class bin 减一、向另一个 bin 加一，L1 可为 2；当前证明对应 add/remove；
- 若要 person-level DP，需要每人贡献 clipping/capping、subject id、group adjacency 和重新标定噪声；
- 多个增强 view、重复 pseudo-label 或重复窗口也必须计入贡献上限。

## 各学习方式改变了什么隐私边界

| 情形 | 协调器能看到什么 | 当前证明是否直接适用 |
|---|---|---|
| >=3 节点有标签监督 | 精确 pooled leaf×class counts；不能分离节点 | 是：行级 add/remove、诚实计数假设 |
| cohort=1 有标签监督 | 精确单节点 leaf×class counts | 发布模型为 central-DP；没有 secure aggregation |
| 下载模型后无标签本地推理 | 协调器看不到查询 | 不产生训练 epsilon |
| hosted 无标签推理 | 协调器收到特征行 X | 不训练，但有查询隐私风险 |
| 固定 teacher hard pseudo-label | 下一轮 pooled pseudo class counts | 满足贡献上限时可作为新轮组合；尚未实现 |
| 本地数据拟合 encoder | encoder 与后续许多路由依赖整个数据集 | 否，需要新分析 |
| 联邦 SSL 梯度 | pooled update，可能泄漏属性或成员 | 否，需要 clipping + DP + 新协议 |
| 多窗口/多增强 | 一人贡献多行 | 仍只是行级，不是人级 DP |

安全聚合不是 DP，DP 不是加密。无标签数据仍可能包含身份、站点、设备和健康信息；representation
也可能编码站点或身份。无标签路线同样需要 access control、membership/site leakage、domain
shift、subgroup 和模型反演测试。

## 半监督和 SSL 应怎样评估

### 半监督比较至少包含

1. 相同人工标签预算的 labeled-only baseline；
2. labeled + unlabeled 方法；
3. 若可能，full-label upper bound；
4. 相同 split、相同 test set、相同 epsilon 总预算和相同树/参数预算；
5. human-only test labels；
6. pseudo-label coverage、precision、abstention 和 class distribution；
7. subject-held-out、institution-held-out 与 device/domain-shift；
8. calibration、敏感度、特异度和 subgroup 结果。

### SSL 比较至少包含

- random/fixed hand-crafted features；
- public pretrained frozen encoder；
- frozen encoder + linear probe 或当前 DP forest head；
- 若微调，单独报告 fine-tuning 数据和隐私预算；
- 不用 pretext loss 代替 ASD/TD downstream utility；
- 不用同一人的不同窗口同时放入 train/test。

### Dashboard 指标的正确解释

dashboard 的 AUC、balanced accuracy、sensitivity、specificity、F1、MCC、Brier、ECE、混淆矩阵
和 ROC 都来自 coordinator 启动前准备的 fixed test set，而不是本轮刚贡献的 10+10 个视频。
它们显示全局 ensemble 在该 test set 上的变化：

- 不证明某个节点造成了因果提升；
- 不保证随轮次单调；
- sensitivity/specificity 当前来自 argmax 决策，不等同于另一个历史模型的特定 operating point；
- 若 test set 是合成数据，数值只代表合成工程 utility；
- 若 test set 不是 institution-held-out，不能代表跨机构泛化。

详见 [`evaluation-and-claims.md`](evaluation-and-claims.md)。

## 推荐分阶段路线

### Stage 0：当前可用

- 继续使用显式 ASD/TD 标签的监督 DP forest；
- 强化 file/subject provenance 和数据质量；
- 下载模型后本地推理；
- 中控台透明显示模式、预算、真实指标和限制。

### Stage 1：最低风险产品扩展

- 把未标注原始文件改为 fail-closed；
- 新增显式 `unlabeled/` 与本地 review queue；
- 支持 X-only/raw-folder 无标签推理且不伪造 truth；
- 加入主动学习排序、人工确认与 audit provenance；
- 建立每视频/每受试者贡献上限。

### Stage 2：研究型半监督

- hard pseudo-label + abstention；
- 严格 teacher hash、阈值、去重和 pseudo/human 标识；
- 与 labeled-only 同预算对照；
- 重新验证 adaptive composition 与贡献敏感度。

### Stage 3：公共冻结 SSL 表示

- 每个模态建立独立、版本化 encoder；
- 公布训练来源、hash、preprocessing、bounds 与 license；
- 以当前 DP forest 作为下游监督头；
- `action_cdp_v1`、EEG 和 fMRI 不静默改 schema。

### Stage 4：新一代联邦 SSL

- 新的参数/梯度 secure aggregation；
- clipping、DP-SGD/RDP accountant、dropout recovery；
- poisoning 与模型更新验证；
- 新的证据包和安全审计。

Stage 2–4 是独立研究计划，不属于当前 September monitored pilot 的已实现能力。
