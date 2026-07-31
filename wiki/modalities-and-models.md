# 模态与模型说明 / Modalities and Models

Last updated: 2026-08-01

本页回答三个经常被混在一起的问题：每种原始数据如何变成特征、哪些步骤使用了已训练模型，
以及最终真正参与联邦聚合的分类器是什么。这里的“模型”不是一个单独文件，而是三层组合：

1. **信号前端（signal front end）**：把 CSV、视频、姿态或神经时间序列转换成固定宽度向量；
2. **表示契约（representation contract）**：统一特征顺序、维度、公开归一化与版本；
3. **联邦分类头（federated classifier）**：所有模态共用的数据无关随机森林、叶节点计数、
   安全聚合与中央差分隐私机制。

这一区分非常重要。例如 `action_cdp` 使用了历史 CDP-TreeFusion 的特征表示参数，但当前
下载得到的全局分类器仍然是新的差分隐私概率森林，并不是历史 pickle 中的 ExtraTrees。

## 一页总览

| 模态 | 原始输入 | 本地前端 | 联邦输入 | 当前最终模型 | 是否需要本地标签 |
|---|---|---|---:|---|---|
| `eyegaze` | 每次记录一个 gaze CSV | I-VT 风格的注视、扫视、空间注意与瞳孔统计；确定性 NumPy 特征 | 32 维 | 数据无关随机森林 + DP 叶概率集成 | 是 |
| `action` | 本地视频，或 `body:(T,33,4)` NPZ | 视频先由 MediaPipe Holistic/Pose 提取 33 点；再计算平移/尺度不变的运动学统计 | 174 维 | 同上 | 是 |
| `action_cdp` | 与 `action` 相同 | 33→COCO17；230 维工程分支 + 1150 维分段袋分支；冻结 scaler/selector 选出 40+64 | 104 维 | 同上；**不是历史 CDP 分类器** | 是 |
| `neuro` | `ts` NPZ 或二维 CSV | 频带功率、相关性分布、图统计与信号尺度摘要 | 声明 48 维；当前 28 个计算槽 + 20 个预留零槽 | 同上 | 是 |

“需要标签”指节点在本地训练时必须知道每个样本属于哪个类；原始标签行不会上传。节点上传的
是按类别分桶的叶节点整数计数。在三节点安全聚合中，协调器只能恢复全体节点的汇总计数；在
单节点模式中没有成对掩码，协调器是中央 DP curator，因此必须明确采用不同的信任模型。

## 所有模态共用的联邦分类器

### 1. 公开、数据无关的森林结构

每一轮由公开的 `structure_seed + round`、公开特征维度和公开特征上下界生成一组完全二叉树。
每个内部节点随机选择一个特征，并在公开范围内随机选择阈值。树的结构不读取任何参与机构的
数据，因此不会通过“树长什么样”泄漏私有分布。

这与常规 Random Forest/ExtraTrees 的关键区别是：常规树会根据训练数据寻找最佳切分；这里
为了可对齐聚合与隐私证明，切分结构完全独立于参与者数据。代价是它通常需要更多树，并且上限
低于一个直接对标签优化的非隐私 ExtraTrees。

### 2. 节点只计算带类别的叶计数

对第 `r` 轮的每个本地样本 `(x_i, y_i)`：

1. 用公开随机数把样本分配给本轮的一棵树；
2. 沿公开阈值把 `x_i` 路由到一个叶节点；
3. 在该叶节点的 `y_i` 类别计数上加一。

每条记录在一轮内只贡献给一棵树的一个叶节点，所以整轮计数向量的 L1 sensitivity 为 1。
这也是当前差分隐私证明成立的核心约束。`y_i` 不会作为逐样本数组离开节点，但没有标签就
无法把该次贡献放进 ASD 或 TD 的类别槽，因此当前分类协议是监督学习协议。

### 3. 三节点以上：成对掩码安全聚合

当 `FED_COHORT >= 3` 时，每个节点用 X25519 派生的成对掩码处理整数向量。全体节点的向量
相加时掩码正负抵消，协调器恢复的是全队列汇总叶计数，而不是任一机构的计数。

当前实现要求本轮精确登记的全部节点都提交；没有 dropout recovery。每次提交携带精确
`(node_id, x_pub)` 集合的 cohort fingerprint，防止重连或旧掩码留下残差并悄悄破坏总和。

### 4. 单节点：中央 DP，但没有安全聚合

当 `FED_COHORT=1` 时没有第二个节点可以产生抵消掩码。节点仍然发送整数叶计数，协调器加入
Laplace 噪声并输出 DP 模型；但协调器进程在加噪前可以看到该唯一节点的计数，所以这是
**trusted-curator central DP**，不能称为 secure aggregation。

### 5. 协调器加噪并形成概率森林

协调器对汇总后的每个叶类别计数加入 `Laplace(1/epsilon)` 噪声，负值截到 0，再把同一叶的
类别计数归一化为概率。每轮发布一个新的概率森林；跨轮模型是这些森林的加权集成。

同一轮内，记录在树之间不重叠，使用 parallel composition；不同轮次重用同一数据，使用
sequential basic composition。全局 epsilon ledger 保证同一轮最多扣费一次，预算耗尽后拒绝
继续训练。

### 6. 输出模型

`GET /model` 返回 pickle-free JSON：

- 类别顺序；
- 每轮森林的左右子节点、特征索引、阈值和叶概率；
- 轮次、聚合来源与权重；
- 模态、隐私支出、测试指标与审计 tip。

它可以由 `predict.py` 下载后在机构本地推理。新查询记录可沿相同前端变成向量，不必上传原始
视频、眼动轨迹或神经信号。

## `eyegaze`：眼动／社交注意前端

### 输入契约

- 一个 CSV 代表一次记录；
- 必需列：`x`、`y`，也接受 `gaze_x/gaze_y`、`gazex/gazey`、`norm_x/norm_y`；
- 可选列：`pupil`、`pupil_diameter` 或 `pupildiameter`；
- 若找不到表头，代码把前两列当成 x/y、第三列当成 pupil；
- 实现假设坐标大致是屏幕归一化 0–1，速度代理按约 30 Hz 计算。

### 32 维表示包含什么

特征由确定性规则计算，没有在当前参与数据上拟合眼动神经网络：

- fixation run 数量、平均/标准差/最大持续样本数；
- fixation sample fraction；
- saccade 数量、幅度均值/标准差/最大值；
- 速度均值、标准差、95 分位；
- scanpath 总长度；
- x/y 离散度、均值与中位数；
- 轨迹包围盒面积；
- 中央 AOI dwell 与四象限占比；
- pupil 缺失比例、均值与标准差；
- 有效样本数；
- AOI 转移次数、微运动比例和长跳比例。

代码注释称其为 “I-VT-style”，意思是具有速度阈值式 fixation/saccade 概念，并不表示已完整
复现某一眼动仪厂商的事件检测算法。

### 当前模型与适用边界

32 维公开归一化特征进入统一 DP 森林，输出 ASD/TD 概率。合成演示数据只验证流程；真实项目
需要校准采样率、屏幕坐标、任务范式、AOI 定义、设备误差、缺失规则和 subject-level split。
如果不同机构使用不同刺激材料或采样频率，当前汇总特征可能更多反映设备/范式差异，而不是
稳定的社会注意差异。

### 最自然的自监督扩展

适合的无标签任务包括 masked trajectory reconstruction、时间片顺序判断、不同裁剪/轻微抖动
的对比学习、AOI transition prediction 和下一段轨迹预测。自监督编码器必须有全体机构一致的
版本与特征轴，冻结后其 embedding 才能接到现有 DP 森林；每家单独训练、语义不对齐的 embedding
不能直接进行叶计数聚合。

## `action`：视频／MediaPipe 姿态运动学前端

### 视频先发生什么

桌面端在本机浏览器视图内运行固定版本的 MediaPipe Holistic/Pose。视频像素不会发送到
协调器；本地桥只保存 `body:(T,33,4)`，四个通道是 x、y、z、visibility。输入也可以直接是
已存在的 NPZ。

MediaPipe 本身是一个已训练的姿态估计模型；但它只负责把像素转换成关键点。项目随后使用的
174 维运动表示是确定性工程特征，最终分类头仍是联邦 DP 森林。

### 一个文件与一个训练样本的区别

- `body:(T,33,4)`：文件含一个窗口，产生一个训练样本；
- `body:(N,T,33,4)`：文件含 N 个窗口，产生 N 个训练样本；
- group id 始终是文件相对路径，因此 `prepare_data.py` 的 grouped split 会把同一视频的全部
  窗口放在同一侧，避免最直接的窗口泄漏。

桌面端所说的“10 个 ASD 视频 + 10 个 TD 视频”是 20 个原始文件；中控台显示的 local samples
可能更大，因为一个视频能产生多个窗口。两者不应混称。

### 174 维表示的精确组成

每一帧先用左右髋中点做平移归一化，再除以视频窗口内的中位躯干长度做尺度归一化。随后计算：

| 特征组 | 维度 |
|---|---:|
| 33 个关节速度均值 | 33 |
| 33 个关节速度标准差 | 33 |
| 33 个关节最大速度 | 33 |
| 每个关节 x 位置标准差 | 33 |
| 每个关节 y 位置标准差 | 33 |
| 肩、肘、腕、髋、膝、踝 6 对左右速度不对称 | 6 |
| 总运动能量、平均 visibility、活跃帧比例 | 3 |
| **合计** | **174** |

它对整体平移和近似人体尺度更稳健，但没有旋转不变性，也没有显式建模摄像机视角、遮挡、多人
身份跟踪或长程动作语义。

### 当前模型与自监督方向

174 维向量进入统一 DP 森林。可扩展的无标签预训练包括 masked joint/time reconstruction、
temporal order、速度一致性、骨架增强对比学习，以及 ST-GCN/pose transformer 表示学习。若引入
神经编码器，推荐先冻结一个共同版本，再用少量标签训练现有 DP 森林；若要联邦更新编码器参数，
则必须新增梯度/参数聚合协议，当前叶计数协议不能直接聚合神经网络权重。

## `action_cdp`：CDP-TreeFusion 表示适配实验

### 它复用了什么

`action_cdp` 与 `action` 共用相同的本地视频和 MediaPipe 33 点输入，但表示前端更接近历史
CDP-TreeFusion：

1. 从 MediaPipe 33 点选择鼻、眼、耳、肩、肘、腕、髋、膝、踝，映射到 COCO 风格 17 点；
2. 保留 x、y、visibility，做视频级有效点 min/max 归一化；
3. 计算 230 维 engineered branch；
4. 用 32 帧窗口、16 帧 stride 计算每段 230 维特征，再按 mean/std/max/min/slope 汇成
   `230 × 5 = 1150` 维 segment-bag branch；
5. 应用历史训练得到但已转为纯 JSON 的冻结 StandardScaler；
6. engineered 选择 40 维，segment-bag 选择 64 维，拼接为 104 维；
7. 再通过项目统一的公开 `tanh(raw/scale)` 进入 [-1,1] 联邦特征范围。

### 230 维 engineered branch

它覆盖身体中心、全局速度/加速度、关节速度离散度、边界框宽高面积、帧级可见率、平均置信度、
左右间距、鼻/肩/腕/踝等选定关节速度、六组左右关节距离，以及帧数、关节数和总体 visibility。
大部分序列量均使用 mean、std、min、max、p10、p25、p50、p75、p90 九种统计。

### 输入限制

- 至少 24 个采样帧；
- 超过 64 帧时均匀抽样到 64；
- 浏览器路径锁定在历史适配器使用的 4 fps；
- JSON adapter 的格式、字段、选中特征名和 payload SHA-256 均被验证；
- adapter 禁止携带样本 ID、group、report、pipeline、estimators 或 tree 节点。

### 它没有复用什么

节点和协调器**不会加载**历史 `final_model.pkl`，也不会把历史 ExtraTrees 分类器并入全局模型。
因此准确表述是：

> “在冻结 CDP 表示上训练新的隐私保护联邦森林。”

不准确的表述是：

> “多家机构继续训练或改进了原 CDP-TreeFusion 模型。”

任何“优于历史 CDP”的结论都需要同一 grouped/subject/institution-held-out 测试集、冻结阈值和
配对统计检验；仅看到新中控台 AUC 变化不足以证明提升。

### 自监督与半监督价值

104 维冻结表示可以直接作为 tabular autoencoder、masked-feature modeling 或对比学习的输入，
但这样学习到的 latent 轴必须全局一致。更自然的路线是在 17 点序列上做姿态自监督预训练，再
以 104 维 CDP 表示作为稳定基线做消融，而不是宣称二者是同一个模型。

## `neuro`：EEG／fMRI 时间序列前端

### 输入契约

- NPZ：键 `ts`，二维数组；若没有 `ts`，读取第一个数组；
- CSV：二维数值矩阵；
- 内部期望 `(channels,time)`，若行数大于列数则转置；
- 至少两个通道和两个时间点。

### 当前 48 维 schema 的实际内容

当前实现计算 28 个数并将剩余 20 个槽置零，保持已发布的 48 维协议兼容：

| 特征组 | 有效维度 |
|---|---:|
| delta/theta/alpha/beta/gamma 五个通道平均频带功率比例 | 5 |
| 低频 log-PSD 斜率 | 1 |
| 通道相关系数非对角项的 12-bin 直方图 | 12 |
| 绝对相关均值、相关标准差、强连接比例、均值、p90、p10 | 6 |
| 通道方差均值/标准差、通道数、时间点数 | 4 |
| schema 预留零槽 | 20 |
| **总宽度** | **48** |

### 必须明确的科学限制

代码用 128 Hz 计算 1–45 Hz 频带，这是 EEG 风格的工程假设。fMRI BOLD 的采样率和生理频段
完全不同，因此当前“EEG/fMRI”是统一二维时间序列接口的工程 POC，不是一个可直接用于真实
fMRI 的经过验证特征模型。真实 fMRI 应单独定义 TR、预处理、脑区 parcellation、低频范围、
运动回归和连接图 schema，并建立新模态版本，不能只把 fMRI 矩阵塞进现有 EEG 频带代码。

### 可扩展方向

EEG 可采用 masked channel/time reconstruction、频谱增强对比学习和跨 session 一致性；fMRI
可采用 masked ROI reconstruction、连接图 autoencoder 或 temporal contrastive learning。
由于二者物理意义不同，生产设计更适合拆成 `eeg_v1` 与 `fmri_v1`，而不是共享同一 48 维名字。

## 公开归一化与 schema 版本

四个前端产生的原始统计尺度不同。项目使用：

```text
x_public = tanh(x_raw / public_scale)
```

`public_scale` 来自固定 seed 的公开合成参考 cohort，保存在 `public_scales.json`，不是从当前
参与机构估计。归一化后所有特征落在公开 `[-1,1]`，随机树可以在这个范围中选择阈值。

这里的“公开”不等于“临床标准”。它只保证 DP 树结构不依赖参与数据。若替换前端、特征顺序、
采样规则、adapter 或 scale，必须视为新 schema；不同 schema 的节点不能加入同一 federation。

## 基线模型、联邦模型与历史模型不要混称

| 名称 | 训练位置 | 是否上线作为联邦模型 | 用途 |
|---|---|---|---|
| Non-private ExtraTrees ceiling | `prepare_data.py`，准备阶段 pooled train | 否 | 展示不使用数据无关结构与 DP 时的参考上限 |
| Centralized-DP reference | `prepare_data.py`，对 pooled train 建 DP forest | 否 | 检查安全聚合结果是否接近同机制的集中式结果 |
| Federated DP JSON forest | 节点计数 + 协调器汇总/加噪 | **是** | 下载、推理和中控台指标的真实全局模型 |
| Historical CDP ExtraTrees | 外部历史项目 pickle | 否 | 只提供 scaler/selector 的迁移来源与未来对照基线 |
| MediaPipe Holistic/Pose | 桌面端本地浏览器 | 是，作为视频关键点前端 | 像素→33 点，不执行 ASD/TD 分类 |

## 当前评估输出

二分类全局模型在协调器持有的 locked test set 上报告：AUC、accuracy、balanced accuracy、
sensitivity、specificity、precision、F1、MCC、Brier score、ECE、混淆矩阵和紧凑 ROC 点。
ASD 被显式定义为阳性类，避免因类别排序把 TD recall 误称为 sensitivity。

这些指标描述当前测试集上的工程表现；它们不自动代表新机构、设备、年龄段或真实临床人群。
模态合成数据只能验证端到端协议，HAR 只能验证通用工程能力。真实医学结论需要 subject-level、
institution-held-out、设备/亚组分析、外部校准和预注册验证。

## 相关实现

- [`../modalities.py`](../modalities.py)：四模态 registry、输入解析、确定性特征和公开归一化；
- [`../features.py`](../features.py)：`action` 174 维运动学特征；
- [`../cdp_features.py`](../cdp_features.py)：`action_cdp` 33→17、230/1150 分支与 104 维 adapter；
- [`../dp.py`](../dp.py)：数据无关森林、叶计数和中央 DP；
- [`../secure_agg.py`](../secure_agg.py)：X25519 成对掩码；
- [`../fed_common.py`](../fed_common.py)：JSON forest、全局集成与评估；
- [`../prepare_data.py`](../prepare_data.py)：grouped split、基线和运行时 schema。
