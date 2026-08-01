# 法律、政策与跨境数据治理

Last updated: 2026-08-01

> **研究口径与免责声明。** 本页按 2026-08-01 可检索到的官方法律、监管指引和本仓库
> 当前代码整理，用于架构设计、合作方尽调和伦理/法务沟通，不构成香港、内地或任何境外
> 法域的法律意见。真实儿童、医疗或跨境数据上线前，必须由每个参与机构的法务、DPO/
> 个人信息保护负责人、信息安全负责人和伦理委员会书面确认；必要时向属地监管部门预沟通。

## 一页结论

这个项目的隐私技术有真实价值：推荐训练路径把原始视频、眼动、姿态和神经信号留在
机构节点，三节点及以上时上传的是成对掩码后的整数叶节点类别计数，协调端只恢复池化
计数，再添加中央差分隐私噪声。它明显降低了集中收集原始资料的风险。

但下面四句话必须同时成立：

1. **联邦学习不是法律豁免。** 本地提取、训练、上传统计量、远程查看、下载模型和备份都
   可能是“处理”或“跨境提供”。
2. **安全聚合不等于匿名化。** 它主要隐藏单个节点贡献；协调端仍会在加噪前恢复精确池化
   类别计数。小队列、已知参与机构和稀有 ASD 类别会增加属性推断风险。
3. **差分隐私不自动等于匿名。** 在节点诚实执行当前客户端、每个输入行只分配到一棵树且
   只贡献一个叶计数的信任模型下，当前邻接单位是一个输入行：眼动/神经通常是一份录制，
   action/action_cdp 是一个姿态窗口，而不是儿童、视频或家庭。协调端不能从上传向量证明
   节点遵守了该贡献界限；同一人贡献多个窗口、多份录制或多轮训练会按组合放大人级风险。
   模型是否达到法律意义上的匿名，仍需逐案、书面、可复核的重识别与模型攻击评估。
4. **单节点是真实数据红线。** `FED_COHORT=1` 会把一个机构的未掩码叶节点类别计数交给
   协调端，然后才加 DP 噪声；它是 central-DP solo demo，不是 secure aggregation。

在完成具体法域和接收方的匿名性评估前，本项目统一采用保守口径：

> 把联邦更新、DP 前池化计数、模型、指标、审计包、备份和远程访问日志都按“可能仍含
> 个人/敏感健康信息的衍生产物”管理；不得仅凭“raw stays local”“masked”或“DP”将其
> 自行认定为匿名资料。

## 文件中的义务标签

本页用四种标签避免把建议写成法律：

- **[现行法]**：本页核对日已生效的法律或具有约束力的规则；具体适用仍取决于事实。
- **[机构门槛]**：伦理、医院、大学或合作机构的内部批准条件。
- **[官方建议]**：监管机构发布的建议、模型条款或治理框架，不应误写成法定条文。
- **[项目准入策略]**：GBA-DF 为降低剩余风险设置的、可能比法律最低线更严格的门槛。

常用缩写：PDPO = 香港《个人资料（私隐）条例》；DPP = 香港保障资料原则；PICS =
Personal Information Collection Statement；PIPL = 内地《个人信息保护法》；PIPIA/DPIA =
个人信息/数据保护影响评估；RMC = 香港 PCPD 建议跨境合约条款；GBA SC = 粤港大湾区
标准合同；CIIO = 关键信息基础设施运营者；HGR = 人类遗传资源；DPA/DSA = 数据处理/
数据共享协议。缩写相同不代表不同法域的文件可以互相替代。

## 场景风险总览

下表的“风险”是项目规划等级，不是监管机关的法律分级。方向按资料、更新、模型、审计包
或远程访问实际流向判断；服务器物理位置不是唯一因素。

| 典型部署 | 主要规则叠加 | 规划风险 | 最低可行路径 |
|---|---|---:|---|
| 香港机构 → 香港协调端，所有运维均在港 | 香港 PDPO、研究伦理、机构安全政策 | 中高 | PICS 与 DPP3 新用途同意分别核对、伦理批准、角色与处理协议、DPIA 式风险评估、三节点安全聚合 |
| 深圳机构 → 香港协调端 | 内地 PIPL/数据安全/行业规则 + 香港接收方 PDPO/PIPL 潜在域外义务；可评估 GBA 标准合同 | 高但路线较清晰 | 确认不含重要数据、PIPIA、来源法域告知/所需同意、GBA 合同及两地备案、禁止 GBA 外访问/存储/转传、接收方域外角色与医院内部批准 |
| 香港机构 → 深圳协调端 | 香港 PDPO + 内地接收和处理规则；可评估 GBA 标准合同 | 高 | 香港目的/接收者告知与合约控制、内地 PIPL 角色确认、PIPIA、GBA 合同及备案 |
| 北京或其他非 GBA 内地机构 → 香港协调端 | PIPL 全国数据出境路径 + 数据安全/行业规则 + 香港 PDPO/PIPL 潜在域外义务 | 高至很高 | 按累计人数、敏感性、CIIO/重要数据选择标准合同、认证或安全评估；单独同意、PIPIA、接收方域外角色与机构批准 |
| 深圳机构 → 香港后再给北京、新加坡、欧美 | GBA 路径的禁止区外转传 + 后续法域规则 | **红线** | 不能沿用 GBA 合同直接转传；先证明产物真正匿名，或另行设计合法路径和部署边界 |
| EU/EEA 机构 → 香港协调端 | GDPR 合法基础 + Article 9/89 + DPIA + Chapter V transfer | 高 | 选择 Chapter V 工具；常规合作通常用 EU SCC + Transfer Impact Assessment/补充措施，并完成伦理和控制者协议；香港 RMC 不能代替 EU 工具 |
| 英国机构 → 香港协调端 | UK GDPR/DPA 2018 + 国际传输规则 | 高 | 选择 UK transfer mechanism；常规合作通常用 UK IDTA 或 EU SCC UK Addendum + risk/data protection test，并完成伦理与角色协议 |
| 美国机构 → 香港协调端 | HIPAA/Common Rule/FTC/州法按角色适用；另筛 DOJ Data Security Program | 高且事实敏感 | HIPAA/IRB/DUA/BAA 分析与逐州审查；DSP bulk/transaction 筛查和 PADFAA data-broker 筛查分别完成 |
| 新加坡或澳大利亚机构 → 香港协调端 | 当地出境/问责规则 + 香港接收方 PDPO | 中高至高 | 新加坡 comparable protection 或澳大利亚 APP 8 路径、合同与风险评估；逐国确认 |
| 任何内地机构 → GBA 以外外国协调端 | PIPL 全国出境 + 数据安全/行业规则 + 目的国法律 | 很高 | 先评估境内协调架构；如确需出境，完成内地法定路径和目的国接收要求 |

**首选试点次序：**先做全部香港机构的三节点研究演练；若商业/科研目标必须覆盖跨境，
第二选择是香港—深圳且数据、管理员、云、备份和接收者全部锁在 GBA 范围内；北京及欧美
真实数据接入应在前两类治理包跑通后单独立项。Synthetic/public benchmark 不受真实儿童
数据的同等风险约束，但仍要核对来源许可和是否确实不含个人资料。

## 当前系统究竟会处理和传输什么

### 数据流清单

| 产物 | 当前路径 | 接收方能够看到什么 | 合规判断与主要风险 |
|---|---|---|---|
| 原始视频、眼动 CSV、EEG/fMRI、原始/提取 NPZ | 推荐训练中留在节点；视频在桌面端本地提取 | 协调端不应收到 | 明确高风险；视频还可能含脸、声音、家居、旁观儿童。raw local 是风险控制，不是本地处理豁免 |
| 本地逐条特征 | 在节点生成并计数 | 推荐训练路径不上传 | 通常仍为可关联或去标识化个人资料；姿态、凝视和神经信号可能支持重识别/健康推断 |
| 注册元数据 | `/register` 上传 | `node_id`、显示名、Ed25519 公钥、临时 X25519 公钥、节点自报本地输入行数（诚实客户端中等于 `X.shape[0]`）、邀请绑定 | 机构机密；若显示名、IP、联系人可关联自然人，也可能是个人资料；自报行数不是经协调端核验的自然人数/视频数 |
| 单节点叶×类别计数 | cohort 1 直接上传未掩码整数向量 | 协调端看到该机构精确类别计数结构、样本量和轮次 | 不应处理真实儿童/临床数据；容易暴露机构 ASD/TD 构成，不能称安全聚合 |
| 三节点以上单个提交 | 节点上传 pairwise-masked 向量、自报输入行数、签名、轮次与 cohort fingerprint | 非合谋假设下不能从单个向量恢复单节点计数；仍看见机构身份和自报行数 | 显著降风险，但不是匿名化证明；协调端/节点合谋、低节点数、差分轮次仍有风险 |
| DP 前池化计数 | 完整 cohort 到齐后在协调端内存恢复 | 所有机构实际提交计数相加后的精确叶×类别计数 | 在诚实计数路径中每个输入行只进入一棵树，故把所有树叶按类别求和可得到池化 ASD/TD 输入行总数；这不验证单机构自报值或自然人数，随后才加噪 |
| DP JSON 全局模型 | 协调端加 Laplace 噪声并保存、供下载 | 叶概率、轮次、各节点自报注册行数之和作为 ensemble weight、树结构、模态、预算 | weight 未由协调端核验为真实人数/视频数；模型仍需成员/属性/提取测试和书面匿名性评估，多轮发布受预算组合影响 |
| Dashboard/status | 认证运营人员访问 | 节点名、节点自报输入行数、提交轮次、等待机构、全局指标、epsilon、模型树数 | 小样本机构存在敏感属性推断；自报行数也不应被宣传为经验证人数，不应在公开展台显示真实节点精确规模或单机构分类结果 |
| Audit bundle | 认证运营人员可下载 | 机构名称、公钥、邀请绑定、自报输入行数、提交回执/哈希/签名、事件、DP 配置和模型 | 是独立受控资料包；交给海外审计者、云备份或邮件发送都可能成为新传输 |
| 协调端测试集 | `coordinator.py` 读取 `data/test.npz` | 协调端直接持有带标签特征 | 当前 synthetic/demo 可用；真实合作方 test set 不应未经单独批准集中到协调端 |
| 托管 `/predict` | 调用者向协调端上传完整特征行 | 服务器直接看到推理特征 | 跨境真实数据模式应关闭，优先下载模型后本地推理 |
| 备份与运维日志 | 主机/备份端保存 | 私钥、邀请表、审计、模型、参与元数据；反向代理还可能记 IP/User-Agent | 云备份、境外灾备、海外 SRE/开发者远程访问都要进入数据流图和接收者清单 |

三节点模式的信任边界应写成：协调端看不到**单个机构未掩码计数**，但会看到**DP 前精确
池化计数**。这与“协调端看不到任何未加噪数据”是两回事。安全聚合也不验证节点提交是否
真实，不提供 Byzantine robustness。

### 有标签、无标签、自监督与半监督的法律差别

“label”是机器学习概念，不是个人资料法的开关：

| 学习方式 | 额外风险 | 不变的义务 |
|---|---|---|
| 有监督 | ASD/TD 真值、筛查结果和错误标签直接涉及健康、污名、歧视和准确性；标签用途通常要在同意/伦理中明确 | 本地处理、目的限制、数据最小化、安全、伦理、跨境、权利处理 |
| 无标签/自监督 | 没有人工 ASD/TD 标签，但视频、人脸、声音、姿态、眼动、EEG/fMRI 仍可识别或推断健康；预训练或新下游任务可能是新目的 | 同上；不能把 `unlabeled/` 宣称为 anonymous |
| 半监督/伪标签 | 同时处理真实标签、无标签资料和模型生成健康推断；错误伪标签可能被误当诊断并强化偏差 | 同上；伪标签须保留来源、模型版本、置信度、人工复核和撤销记录，不能自动写回病历 |
| 联邦训练 | 减少原始资料集中化，但产生更新、模型、指标、日志和跨境访问 | 仍需合法目的/基础、伦理、角色协议、影响评估和适用传输机制 |

如果原同意只写“视频筛查”或“本地分析”，新增自监督预训练、模型公开、跨机构下游分类、
托管推理或把模型交给第三方，均应先判断是否属于新目的并办理伦理修订/重新同意，不能用
“没有 label”绕过。

## 香港：本地和对外分享

### 现行 PDPO 边界

**[现行法]** 香港《个人资料（私隐）条例》（PDPO, Cap. 486）是技术中立的。资料只要与
在世可识别个人相关，并以可实际查阅/处理的形式存在，就可能是个人资料。项目应落实六项
Data Protection Principles：

- DPP1：合法、公平、目的明确，收集必要且不过量；向当事人说明目的、接收者类别和权利；
- DPP2：准确，保存不超过必要期限；使用处理者时以合同或其他方式控制保留；
- DPP3：不得在没有 prescribed consent 或适用豁免时用于新的、不直接相关目的；“use”
  包括披露和传输；
- DPP4：按资料性质和潜在伤害采取一切切实可行的安全措施，并管好处理者；
- DPP5：公开资料政策与做法；
- DPP6：支持资料查阅和改正。

**不要混同 PICS 与同意。** PDPO 不把 consent 作为所有收集和使用个人资料的统一合法基础。
直接向资料当事人收集时，DPP1 通常要求在收集前或收集时说明用途、通常/拟转移的接收者
类别、提供资料属强制还是自愿、如属强制而不提供的后果，以及查阅/改正权和联系人。资料
拟用于原收集目的及其直接相关目的之外的 **new purpose** 且没有 Part 8 豁免时，DPP3 才
要求 **prescribed consent**；它指明确、自愿给予且未以书面通知撤回的同意。研究参与同意
和 HAREC approval 又是独立伦理门槛，不能由一份 PICS 代替。

香港把决定收集、持有、处理或使用目的/方式的主体称为 **data user**。云商或受指示处理
资料的主体可能是 processor；但仅在合同里写“processor”不能改变谁实际决定目的和关键
方式。若 HKUST/协调端决定树结构、轮次、DP、评估和模型发布，而合作方决定哪些儿童进入
训练，双方可能在不同阶段分别或共同承担 data-user/controller 责任，必须先做角色矩阵。

### 第 33 条现在不能怎样写

**[现行法]** 截至 2026-08-01，现行 e-Legislation Cap. 486 未显示第 33 条已开始实施；
PCPD 2022 年 5 月的 RMC Guidance 明确写明该条 “not yet in operation”。2025-07-02 的
立法会会议记录中亦有议员作相同陈述，但只作为旁证，不是政府/PCPD 的独立法律裁定。因此：

- 不应把第 33 条六种出境条件写成当前已生效的香港法定手续；
- 也不能反过来说香港出境“无要求”。DPP3、DPP2(3)、DPP4(2) 和 data user 对代理人的
  责任仍然适用；
- **[官方建议]** PCPD 提供 data user→data user 与 data user→processor 两套 Recommended
  Model Contractual Clauses (RMC)。核心条款处理资料类别与目的、准许法域、转传、保存/
  删除、安全及查阅/改正安排；指引另建议视风险增加定期报告、审计/检查、及时事故通知与
  合规协作条款。采用 RMC 本身属建议做法。若 transferee 是 processor，现行 DPP2(3) 和
  DPP4(2) 要求 data user 以合同或其他方式控制不过度保留及未经授权/意外访问、处理、删除、
  丢失或使用；**[项目准入策略]** 本项目要求境外处理采用 RMC 或实质同等/更严格条款；
- 香港 RMC 不能替代 EU SCC、UK IDTA 或内地数据出境机制。

### 儿童、健康、研究和“匿名化”

香港 PDPO 没有 GDPR Article 9 那样的法定“特殊类别”清单，但 PCPD 要求安全措施与资料
性质、潜在伤害相称。**[项目准入策略]** ASD/TD 标签、儿童家庭视频、眼动、姿态、EEG、
fMRI 统一按高敏感儿童健康研究资料保护。

- **[现行法/官方建议/机构门槛需分开]** PCPD 建议对儿童使用年龄适配的说明并鼓励家长
  参与；这不等于 PDPO 对所有未满 18 岁人士一律要求“双份文件”。在 DPP3 新用途场景中，
  具有 parental responsibility 的 relevant person 只可在儿童不能理解新用途并决定是否
  同意，且 relevant person 与 data user 均有合理理由相信新用途明显符合儿童利益时，代为
  给予 prescribed consent。HKUST Policy 对不能给予法律上有效同意的儿童要求 legally
  authorised representative 同意，并使用儿童可理解的 assent form；具体能力由伦理委员会
  和法务按个案确认。
- 视频录制要处理非目标主体：兄弟姐妹、家长声音、家庭地址/屏幕/校服等；可行时本地裁剪、
  消音或遮挡，并提供旁观者处理规则。
- PDPO 第 62 条只在资料用于制备统计数字或进行研究、不会用于任何其他目的，且所得统计
  数字或研究结果不会以可识别任何资料当事人的形式提供时，豁免 DPP3；它不豁免 DPP1、
  DPP2、DPP4、DPP5、DPP6，也不替代伦理审查。
- 只有当 data user 或其他人士不能从资料直接或间接识别有关个人，且结合现有或日后可获得
  的信息后也不能切实重新识别时，资料才可能不再构成 PDPO 下的个人资料。删名、节点 ID、
  假名化、加密、secure aggregation 或 DP 单独均不能证明达到该标准。

**[机构门槛]** 在 HKUST 管辖下开展、涉及从人类参与者新收集资料或二次使用既有个人资料
的研究，必须在研究开始前提交 HREP application 并取得 HAREC 批准，不允许事后追认。获批
方案的任何拟议变更均应先提交 amendment application，除为立即消除参与者风险采取的补救
措施外，不得在批准前实施。因此，新增跨境协调端/接收者、自监督/半监督目的、公开
dashboard、托管推理、模型公开或长期复用，只要改变已批准流程，就应先提交 amendment，
不能由项目组自行认定无需修订。

跨机构研究还要按 HKUST Policy 的角色分工判断：HKUST 研究者担任 PI/Project Coordinator
时需 HAREC 批准；作为香港其他机构项目的 Co-PI/Co-I/team member 时，应确认 host PI 已
取得 host-institution ethics approval；与非香港机构合作且 HKUST 工作落入该政策范围时，
仍应寻求 HAREC 批准。**[项目准入策略]** 其他合作方也需其本机构伦理/数据治理书面批准。

HKUST Policy 通常还要求说明研究资料/记录的管理、使用、访问与保存；公开披露原则上不含
个人标识，敏感资料特别保护，研究记录通常至少保存至发表后三年。该最低期限须与 DPP2 的
“不超过实现目的所需期限”通过逐类 retention schedule 协调，而不是笼统永久保存。影响
参与者权利、安全或福祉的未预期问题、方案偏离或不合规应不延误地向 HAREC 报告。

### 香港数据泄露

**[现行法]** PDPO 本身目前不设一般性的强制资料外泄通报义务或统一时限；eHealth 等特定
制度、其他法域和合同可能另有强制要求。

**[官方建议]** PCPD 建议 data user 按收集资料、遏制、伤害风险评估、考虑通报、记录的
步骤处理，并通常在知悉后尽快通知 PCPD 与受影响资料当事人，尤其在可能造成真实伤害时。
**[项目准入策略]** 合同可另设发现后 24 小时内通知牵头机构的内部时限，但须明确 24 小时
是项目/合同要求，不是 PDPO 法定时限；随后按每个适用法域的门槛和时限对外报告。

## 内地：PIPL、数据安全和真实研究

### 个人信息与敏感个人信息

**[现行法]** 《个人信息保护法》（PIPL）把收集、存储、使用、加工、传输、提供、公开、
删除都列为处理；只有“无法识别特定自然人且不能复原”的匿名化信息被排除。去标识化信息
仍是个人信息。

项目相关的敏感个人信息包括：

- 医疗健康：ASD/TD 标签、筛查结果、EEG、fMRI 及能反映健康状态的衍生特征；
- 生物识别：可关联个人或用于识别的人脸、声音、步态/姿态等，按实际用途和可识别性评估；
- 不满 14 周岁未成年人的**全部**个人信息。

敏感个人信息只能在特定目的、充分必要、严格保护下处理，通常需单独同意并说明必要性和
影响；不满 14 周岁还需父母/其他监护人同意和专门处理规则。14–17 岁的视频、健康、诊断
或生物识别资料仍可能因内容本身属于敏感个人信息。

### 处理、合作与影响评估

每个内地合作方至少要完成：

1. 为本地提取、监督/自监督训练、向协调端提交、评估、模型发布分别确定合法性基础；科研
   不是 PIPL 第 13 条中的笼统独立合法基础，不能默认免同意。
2. 告知处理者/接收者、目的、方式、类别、保存期限、权利渠道；目的/方式/类别改变时重新
   判断同意。
3. 向另一个独立个人信息处理者提供资料时，按第 23 条告知接收者并取得单独同意；委托
   处理则按第 21 条约定目的、期限、方式、类别、保护和监督。
4. 多机构共同决定目的和方式时，签共同处理安排；合同不影响当事人依法向任一方主张权利。
5. 在处理敏感信息、委托/对外提供、自动化决策和出境前做 PIPIA，记录目的必要性、权益
   影响、安全风险和措施，并至少保存三年。
6. 建立访问、更正、删除/撤回请求渠道和安全事件预案；模型已经聚合发布后能否移除个人
   影响，要在同意书中诚实说明，不能承诺技术上做不到的“模型遗忘”。

### 香港接收方的 PIPL 域外义务

**[现行法；具体适用待法务确认]** 香港协调端或 HKUST 若在境外处理境内自然人的个人信息，
并用于分析、评估其行为，可能落入 PIPL 第 3 条的域外适用范围。这与内地提供方完成何种
出境机制是两项不同义务。符合该情形的境外个人信息处理者，应按 PIPL 第 53 条在境内设立
专门机构或指定代表；《网络数据安全管理条例》第 26 条进一步要求向所在地设区的市级网信
部门报送机构/代表名称、联系方式等。ASD 筛查与“分析、评估行为”高度相关，接收方不能只
依赖内地合作方的标准合同/备案而忽略自身可能承担的域外义务。

### 全国数据出境机制

以下是非 CIIO 的基本判断，人数按同一处理者自当年 1 月 1 日起累计、按自然人去重，而不是
按视频、窗口或本项目房间计算；集团/医院如何合并统计应由法务确认。

| 向境外提供的资料 | 一般形式机制 |
|---|---|
| 学术合作等活动的数据，确实不含个人信息或重要数据 | 可免安全评估、标准合同、认证三种形式机制；其他义务和伦理仍可能适用 |
| 少于 10 万人的普通个人信息，且不含任何敏感个人信息 | 仅免安全评估、标准合同和认证三种形式机制；只要仍属个人信息出境，仍应依法履行告知、取得个人单独同意、开展 PIPIA 等义务 |
| 10 万至不足 100 万人的普通个人信息 | 个人信息出境标准合同或保护认证 |
| 正数量且不足 1 万人的敏感个人信息 | 一般按标准合同或保护认证准备；不能套用普通信息的 10 万人豁免 |
| 100 万人以上普通个人信息，或 1 万人以上敏感个人信息 | 数据出境安全评估 |
| 任何重要数据，或 CIIO 向境外提供个人信息/重要数据 | 数据出境安全评估 |

**[现行法；具体场景是否满足待法务确认]** 《促进和规范数据跨境流动规定》还列有境外
采集后未引入境内个人信息/重要数据而回传、履行个人作为一方当事人的合同、依法实施跨境
人力资源管理、紧急保护生命健康/财产安全等豁免情形。豁免的是三种形式机制，不是 PIPL 的
一般处理和出境义务。广东自贸区和北京负面清单只适用于符合主体、区域、行业、场景和字段
条件的处理者，不能因机构“在深圳/北京”就自行援引。

不论选择标准合同、认证或安全评估，非豁免的 PIPL 核心义务仍包括：告知境外接收方名称/
联系方式、目的、方式、种类和权利渠道，取得出境单独同意，事前 PIPIA，并采取措施使境外
接收方达到 PIPL 保护标准。目的、种类、接收方、保存期或处理方式重大改变要重新评估。

- 选择全国个人信息出境标准合同时，合同须在实际出境前生效，并在生效后十个工作日内向
  所在地省级网信部门备案标准合同和 PIPIA；不得拆分数量规避安全评估。备案不代表监管
  为项目背书，处理者仍对合法性负责。
- 个人信息出境认证的现行办法自 2026-01-01 施行，适用于符合其范围的非 CIIO 普通/敏感
  个人信息，认证证书有效期三年；申请前仍需告知、出境单独同意和 PIPIA。
- 进入数据出境安全评估的，应按现行申报指南准备；评估结果、延期和任何实质变化应由内地
  提供方建立到期/变更台账，不能只在项目 README 里记录一次。

内地服务器“没有下载到香港”也不一定避免出境：如果香港研究人员或境外运维可以远程
查询、调取、查看或控制访问，监管官方问答将此类境外访问纳入数据出境判断。反向地，海外
人员在内地现场访问且数据不向境外提供，不能仅凭机构国籍判断；仍需具体分析。

### 深圳—香港 GBA 标准合同

**[官方便利措施]** GBA Standard Contract 的采用是自愿的；一旦采用，应按合同、
Implementation Guidelines 和备案安排履行后续义务。组织类 Personal Information Processor
与 Recipient 应分别注册于香港或广州、深圳、珠海、佛山、惠州、东莞、中山、江门、肇庆；
个人类主体应位于这些地区。澳门目前不在该 Mainland–Hong Kong 安排内。仅因服务器或数据
主体位于深圳，不能让北京注册主体自动取得资格；若由独立注册的合资格 GBA 法人签约，应
按该法人和实际处理活动判断。

采用前应确认资料不含 important data，在 filing date 前三个月内完成 PIPIA；合同生效后
十个工作日内由香港一方向 Digital Policy Office、内地一方向广东省网信部门分别备案；
双向传输分别签对应方向合同。香港发送方仍按 PDPO 分别判断 PICS 与 DPP3 prescribed
consent；内地发送方按 PIPL 判断一般合法性基础、告知及出境单独同意，不能把两者合写成
一项统一 consent。经该路线接收的个人信息不得向 GBA 外组织/个人提供；DPO 当前 FAQ 明确
把 GBA 外 transfer、storage 和 access 都纳入限制。

**[项目准入策略/待法务确认]** 对由受控个人信息产生、但尚未通过可复核匿名性评估的模型、
指标和审计包，本项目先按仍受上述地域/转传控制的产物管理。因此深圳节点把更新交给香港
协调端后，不能仅因为名称变成“模型”就交给美国或北京合作方。该做法是保守风险控制；
具体合同范围和匿名后的后续处理由两地法务或备案机关确认。

### 北京和其他非 GBA 内地机构

由北京注册主体作为提供方的节点向香港协调端提交时不能采用 GBA 合同，应按全国路径判断。
由于本项目真实儿童/健康数据通常是敏感个人信息，即使只有 ASD 10 个视频和 TD 10 个视频，也不能据此认为低于
普通个人信息 10 万人的门槛便无手续：

- 台账按**自然人**而不是文件数统计；20 个视频可能来自 2 人或 20 人；
- 少于 1 万人的敏感信息通常仍需要标准合同或认证，除非确有其他适用豁免/清单；
- 达到 1 万敏感自然人、涉及重要数据、CIIO 或更严格行业规则时进入安全评估；
- 北京 2026 年 5 月发布的“两区”数据出境负面清单（2025 版）及管理办法只适用于在北京市
  “两区”内登记注册并开展数据跨境活动、且行业/业务场景/字段/数量逐项匹配的企业、事业
  单位、机构、团体或其他组织；仅服务器或节点位于北京不足以适用。当前 AI 训练场景列明
  文本、音频、图像并排除视频及未列明模态，行为视频不能直接援引，Pose、Eye-gaze、EEG/
  fMRI 也不应类推扩张。使用该清单须先按当地流程申请备案。

### 医疗卫生机构的额外规则

三套医疗行业文件的范围并不相同，不能笼统套用于每个大学研究特征文件。《国家健康医疗
大数据标准、安全和服务管理办法（试行）》适用于卫生健康行政部门、各类医疗卫生机构及
涉及健康医疗大数据管理的相关单位/个人，并要求覆盖数据存储于境内安全可信服务器，确需
向境外提供时依法进行安全评估审核；《人口健康信息管理办法（试行）》更偏向医疗卫生计生
服务机构在服务和管理中形成的信息，并明确不得存储、托管或租赁在境外服务器；医疗卫生
机构网络安全办法另强调全生命周期分类、审批、日志和技术管理。数据来源医院应书面判断
每套规则的适用范围，不能只看全国人数门槛就得出“签标准合同即可”的结论。结果是：

- “人数少于 1 万、签标准合同即可”未必足够；医院信息部门、伦理委员会或主管部门可以
  要求更严格的境内协调架构；
- 本项目的模型、叶计数和其他数据衍生产物也应纳入医疗机构数据分类，而不只列 raw video；
- 真实临床多中心研究的稳妥方案是内地协调端、原始/逐条特征留院、三节点以上安全聚合，
  香港只看经批准跨境或经书面评估真正匿名的结果。

### 数据安全、网络安全与重要数据

《数据安全法》《网络数据安全管理条例》和现行《网络安全法》还要求数据分类分级、等级
保护相关控制、身份认证、访问控制、加密备份、日志、风险监测、事件处置及重要数据管理。

- 医疗健康数据不应仅凭名称自动等同“重要数据”；2024 年跨境规定允许未被主管部门/地区
  告知或公开认定的资料不自行按重要数据申报安全评估，但机构仍须做内部分类和行业确认。
- 任何真实跨机构部署必须 HTTPS/TLS；邀请签名和公钥指纹固定只认证对端，不能加密传输。
  校园网明文 HTTP 加共享弱口令不属于可接受的真实数据方案。
- 未经内地主管机关批准，不应直接响应外国司法/执法机构要求而提供境内存储的数据；合同
  要约定政府访问请求、法律冲突、通知与升级流程。

### 人类遗传资源边界

现有 raw video、Pose、Eye-gaze、EEG 和 fMRI 通常不属于人类遗传资源信息；现行实施细则
把 HGR 信息限定为利用人类遗传资源材料产生的基因、基因组等信息，并明确临床、影像、
蛋白质和代谢数据不在该定义内。fMRI 是影像，不因来自人体或包含“神经”而自动成为 HGR。

若未来加入基因、基因组、转录组、表观基因组、核酸标志物或生物样本，须重新审查国际合作、
对外提供/开放使用、伦理、许可/备案和安全审查；不能用联邦学习或 GBA 合同替代 HGR 路径。
2026 年实施细则修订目前仍是征求意见稿，本页不按已生效规则引用。

人类遗传资源管理职责已自 2024-05-01 由科技部调整至国家卫生健康委，2023 年实施细则在
修订完成前继续作为现行规则使用。实施细则将设在港澳且由内资实际控制的机构视为中方单位；
HKUST 若无该等控制关系，不应自行按中方单位处理。未来加入遗传/组学资料时，应由内地中方
单位和国家卫健委 HGR 渠道确认 HKUST 的外方角色、国际合作及对外提供/开放使用程序。

### 内地未成年人研究伦理

涉及真实儿童行为、健康记录、影像或神经信号的高校/医院研究，应在收集、联邦训练和跨境
前完成伦理审查。方案与同意材料应明确监督、自监督/半监督、跨机构接收者、模型/指标发布、
保存、退出和销毁。真实敏感儿童资料不能默认适用“公开或匿名资料”的伦理豁免。

**[现行法]** 处理未满 18 周岁未成年人个人信息的个人信息处理者，无论是否主动识别其
未成年人身份，均应每年自行或委托专业机构开展未成年人个人信息保护合规审计，并于每年
1 月底前向所在地设区的市级网信部门报送上一年度审计情况。不满 14 周岁儿童还适用监护人
同意、专门处理规则等要求。

**[项目准入策略]** 对所有未满 18 岁参与者采用监护人许可、年龄适配 assent、严格权限和
自然人级台账，而不以 14 岁作为降低项目安全措施的分界。

## 香港与境外机构

“国外”不是一个法域。每增加一个国家、美国州、云区域或远程管理员所在地，都要新增一份
destination annex；不能签一份“国际合作协议”就覆盖全球。

### EU/EEA

**[现行法]** GDPR 下健康数据是 Article 9 special-category data；生物特征在用于唯一识别
时也属于特殊类别。研究通常同时需要 Article 6 合法基础、Article 9 条件、适用成员国法律
和 Article 89 safeguards；参与者研究同意、伦理同意与 GDPR lawful basis 是不同问题。

- 综合处理目的、范围、规模、资料性质、儿童和新技术后如 **likely high risk**，DPIA 是
  法定要求；无论是否达到该触发线，**[项目准入策略]** 本项目的真实儿童健康研究均做 DPIA。
  小样本也不免除 lawful basis、Article 9 和传输规则。
- EU/EEA 机构向香港或内地提供仍属个人数据的产物，目前通常没有 adequacy 覆盖，须选择
  GDPR Chapter V 机制；常规私营/多中心合作通常采用 EU SCC，并完成 transfer impact
  assessment 和必要补充措施。其他 Article 46 工具或 Article 49 狭义例外须逐案论证。
- 香港 RMC 只解决香港侧治理，不能替代 EU SCC。
- 远程访问、境外技术支持、下载 audit bundle 或模型若仍属个人数据，也属于 transfer map。
- EDPB 对 AI 模型的匿名性要求逐案判断：直接/间接识别训练者及通过查询提取个人数据的
  可能性都要极低并有文件证据；“用了 DP”不足以单独证明。

### 英国

英国逻辑与 GDPR 类似：需 UK GDPR Article 6 合法基础、Article 9 条件、DPA 2018 研究保障
及在 likely-high-risk 时所需的 DPIA；本项目仍把真实儿童健康研究 DPIA 设为准入门槛。
英国向香港/内地传输须选择适用的 UK transfer mechanism；常规合作通常使用 UK IDTA 或
EU SCC UK Addendum，并完成 ICO 当前要求的 transfer risk/data protection test，其他
safeguards/derogations 逐案判断。

ICO 的联邦学习指引特别适合本项目：更新可能比 raw 风险低，但仍可泄露个人信息；本地训练
仍受数据保护法；参与方不能看到彼此 raw 并不排除共同控制者；DP 要按实际实现评估而不是
只展示一个 epsilon。

### 美国

美国没有一个覆盖所有私营健康研究的统一联邦隐私法，必须按机构和资料角色叠加分析：

- HIPAA 只直接覆盖 covered entities、business associates 及 PHI。医院向研究者披露可依
  authorization、IRB/Privacy Board waiver，或 limited data set + DUA 等路径；若研究者/
  云商代表医院处理 PHI，可能需要 BAA。
- HIPAA 去标识化有 Safe Harbor 或合格专家 Expert Determination 两条正式路径；聚合、
  加密、掩码或 DP 不能自动代替。
- Common Rule 适用于其覆盖的联邦资助/实施研究及选择适用的机构；儿童研究还需 Subpart D
  和 IRB 对 parental permission/assent 的判断。编码资料是否仍是 human-subject research
  取决于研究者能否容易确认身份等事实。
- 非 HIPAA 实体还可能受 FTC Act、Health Breach Notification Rule、教育记录法和州健康/
  消费者隐私法影响；必须按数据主体所在州和机构角色筛查。

另一个容易漏掉的高风险项是美国 DOJ **Data Security Program (DSP)**：

- 自 2025-04-08 起生效的规则把 PRC 定义包括香港和澳门；
- 对达到门槛的美国 bulk sensitive personal data 或特定政府相关数据交易施加禁止/限制；
- 匿名、去标识、假名、聚合或加密不自动排除；健康数据门槛为 10,000 名美国人，生物识别
  为 1,000 人，基因组为 100 人，组合资料用最低适用门槛；
- 无付款或其他有价值对价、仅基于共同研究兴趣和合作发表的安排可能不构成 covered commercial
  transaction，但没有“所有学术研究一律豁免”；联邦 grant 授权活动也可能有特定豁免；
- 每个美国机构应**分别**完成两套筛查：DSP 记录敏感数据类别、过去 12 个月累计美国人数、
  是否属于 data brokerage/vendor/employment/investment 等 covered data transaction、是否
  存在付款/其他有价值对价，以及接收者是否为 country of concern/covered person；PADFAA
  则先判断转让方是否构成法定 data broker、资料是否为 personally identifiable sensitive
  data、接收者是否为 foreign-adversary country 或其控制实体。PADFAA 不是 DSP bulk threshold
  的另一名称，普通学术合作方也不当然是 data broker。

### 新加坡与澳大利亚示例

- 新加坡 PDPA 的 Transfer Limitation Obligation 通常要求接收方提供与 PDPA 可比的保护；
  以合同、尽调和安全措施证明。
- 澳大利亚 APP 8 通常要求披露方在跨境披露前采取合理步骤，且在许多场景继续为境外接收方
  行为承担问责；健康信息和研究另有例外/州法，须由澳洲机构确认。

这两项只作为常见路线示例，不代表已经覆盖“国外”。日本、加拿大、欧盟成员国的本地研究
法、美国各州等都应另做 annex。

## 风险登记册

| 风险事件 | 可能性/影响 | 本项目触发点 | 最低控制 |
|---|---|---|---|
| 未覆盖的新目的 | 中/高 | 视频筛查资料改作 SSL、第三方模型、公开指标、临床推理 | purpose matrix、伦理 amendment、重新告知/同意 |
| 单节点类别泄露 | 高/高 | cohort 1 未掩码 leaf×class counts | 真实数据禁用 cohort 1；只许 synthetic/local demo |
| 小 cohort 属性推断 | 中高/高 | 三机构总量、已知两方构成、节点自报输入行数、稀有 ASD 类 | 建议 5 节点/最低人群与类别阈值、隐藏/分箱自报行数、拒绝差分查询 |
| 协调端看到 DP 前精确总量 | 确定/中高 | secure-sum 后才加噪 | trusted-curator 合同与访问隔离；长期研究 threshold/distributed noise |
| “epsilon”误导 | 高/高 | 诚实节点假设下的窗口/录制输入行级 ε 被当成人级或无条件保证 | 人/视频贡献裁剪、跨轮/房间统一台账、向量有效性研究、对外注明 adjacency 与诚实节点前提 |
| 多轮差分与重复参与 | 中高/高 | 同一儿童在多个房间/实验/teacher 版本重复贡献 | 稳定本地 subject token、全项目人级预算与去重、查询限制 |
| 模型记忆/成员推断 | 中/高 | DP 模型、未来 neural encoder、公开下载 | membership/inversion/extraction 测试、接收者限制、最小队列、发布审批 |
| 元数据泄露 | 中/中高 | node name、节点自报输入行数、IP、等待状态、audit bundle | RBAC、最小化、分箱、下载审计、保留/删除 |
| 境外远程访问漏登记 | 中高/高 | 海外开发者、云监控、GitHub/日志、远程 support | 完整 data-flow/transfer register、地域锁、审批和访问日志 |
| GBA 外转传 | 中/高 | 香港收到深圳资料后给北京/欧美、海外云备份 | GBA 地域锁；禁 onward；匿名性评估或另行合法路径 |
| 旁观者/家居资料 | 高/高 | 家庭视频含兄弟姐妹、家长声音、屏幕/地址 | 拍摄指引、本地裁剪/消音/遮挡、旁观者规则、短保留 |
| 撤回与模型不可逆 | 中/中高 | 已聚合模型/签名审计无法逐人移除 | 同意书说明边界；停止未来贡献；删除可控 raw/feature；发布前冻结 |
| 错误/伪标签伤害 | 中/高 | ASD/TD 标签、半监督 pseudo-label | 来源与版本、人工复核、禁止写回病历、查阅/改正流程 |
| 节点投毒/完整性 | 中/高 | invitation 只认证机构，不证明 counts 真实 | 质量门槛、异常检测、独立评估；不作临床自动决策 |
| 安全事件/私钥与备份泄露 | 中/高 | audit backup 含 key/metadata；弱 TLS/口令 | 强 TLS/mTLS、独立凭据、KMS/离线备份、演练、合同 24h 内部通知 |
| 法律/政府请求冲突 | 低中/高 | 境外执法要求内地数据；多法域保存/披露冲突 | contract escalation、法务审查、最少数据、政府请求透明流程 |
| 临床效果夸大 | 中/高 | demo AUC 被写成跨院临床效果 | synthetic/engineering 标识、样本量/CI/来源、human oversight、禁诊断措辞 |

## 真实数据准入包

每家机构不是“发一份 invitation”就完成准入。邀请只认证机构和节点密钥，不证明伦理、
同意或合法跨境。上线前应形成一个可审计的 **Institution Data Admission Pack**：

1. 法人、节点、协调端、测试集、云、备份、日志、管理员和远程支持所在地；
2. 数据主体收集地/常居地、年龄、是否未成年人，以及自然人级累计数量；
3. raw、feature、count、masked payload、pool、model、metric、audit、backup 的 data-flow map；
4. 每阶段 data user/controller/joint controller/processor/受托人角色矩阵；
5. 原始收集目的、监督/SSL/半监督、模型发布、验证和二次用途的 purpose matrix；
6. 香港 PICS/prescribed consent、内地一般/敏感/出境单独同意、研究同意、监护人许可和 child
   assent 的分别核对；
7. 各机构伦理批准、依赖/协作安排和 amendment 状态；
8. DPIA/PIPIA、模型匿名性与成员/属性/提取攻击评估；
9. 适用的香港 RMC、GBA 合同、PIPL 全国标准合同/认证/安全评估及香港接收方 PIPL 域外代表/
   报送判断、EU/UK 传输机制；
10. 美国 HIPAA/Common Rule/州法，以及彼此独立的 DSP bulk/transaction 与 PADFAA data-broker
    筛查（如有美国参与方/数据）；
11. 医院数据分类、信息部门批准、CIIO/重要数据/HGR/行业规则结论；
12. DPA/Data Sharing Agreement：目的、字段、接收者、准许法域、onward/subprocessor、保留/
    删除、撤回、权利请求、审计、政府请求、事故时限、责任、IP/模型发布和研究终止；
13. TLS/mTLS、凭据、RBAC、密钥/备份、日志、最小队列、贡献裁剪、epsilon 台账和退出方案；
14. DPO/法务、PI/伦理、信息安全、数据主管和实际系统 owner 的具名书面 go-live 批准。

### 合同必须列出实际字段

至少把下列内容逐项写进 transfer schedule，而不是笼统写“federated updates”：

- 绝不离开节点：raw video/CSV/NPZ、逐帧特征、姓名/病历号/本地 case ID；
- 会发送：掩码或未掩码叶×类别计数、节点自报 `n_samples`（不是协调端验证的自然人数）、
  节点/机构名称、公钥、轮次、cohort fingerprint、签名、payload hash、时间戳、传输字节统计；
- 协调端内部可见：DP 前精确池化计数、带标签测试集（如有）、指标；
- 会长期保存/下载：DP 模型、审计包、邀请绑定、备份；
- 禁止：再识别、成员推断/模型提取、未批准下游训练、广告/保险/招生/个体画像、未经批准
  临床使用和 GBA 外转传；
- 退出：停止未来贡献，删除可控 raw/features/本地映射；说明已合法匿名并发布的模型或不可变
  审计链可能无法逐人逆向删除。

## 技术准入策略

**[项目准入策略]** 新增一个面向未来的 `cross_border_research` profile 时，应至少满足：

- 硬性禁止 `FED_COHORT=1` 和 `FED_SOLO_SHARED`；至少三个相互独立、非合谋机构；真实敏感
  小样本建议五个节点，但五个也不是匿名保证；
- 关闭 hosted `/predict`；只允许下载批准模型后本地推理；
- 协调端 `test.npz` 只能是 synthetic/public 或有明确集中处理批准的资料；真实合作方评估应
  本地计算受限统计，再安全聚合并加 DP；
- 强制 TLS，优先 mTLS、机构独立写凭据、分角色读凭据、IP allow-list；禁止默认空口令或
  演示弱口令；
- 隐藏或分箱节点精确样本量，不显示真实小机构单节点标签数/AUC/混淆矩阵；
- 设置最小总人数、最小类别和最小机构数；不足时只显示“已参与，不具备统计发布条件”；
- 把 DP 单位提升到视频/人：节点本地 per-person clipping，跨房间/实验统一预算和去重；
- 对模型、指标和 audit bundle 设具名接收人、到期、地域、用途和下载审计；
- 邀请元数据可关联 jurisdiction、伦理批准编号、允许模态/目的、传输机制版本、到期日；但
  不把 invitation 本身称为法律授权证明；
- 长期研究 threshold/distributed-noise aggregation，使协调端也不接触 DP 前精确总量；
- 独立协议/安全评审和模型 privacy red-team 完成前，不开放真实跨境生产模式。

这些是推荐产品路线，当前代码**尚未全部实现**；不可在 README 宣称现成支持。

## Go / No-Go 决策树

对每个机构、每个模态、每个方向分别走一次：

1. **能否书面证明所有发送产物在合理可用手段下不可识别且不可复原？**
   - 能：记录方法、攻击测试、接收者能力和复核日期；仍核对伦理、许可、重要数据和合同。
   - 不能/不确定：按个人/敏感资料继续。
2. **来源与任何可访问地点在哪里？**
   - 香港内部、深圳↔香港、北京/其他内地↔香港、EU/UK/US/其他分别选择路线。
   - 把云、备份、日志、管理员和远程支持加入地点，不只看服务器。
3. **是否儿童、健康、生物识别、医疗机构资料？**
   - 是：敏感资料、监护人/assent、伦理、PIPIA/DPIA 和更严格发布门槛。
4. **是否 CIIO、重要数据、医疗行业限制或 HGR？**
   - 未确认：停止真实跨境；由数据提供方分类和属地确认。
5. **是否合法覆盖此目的和接收者？**
   - 原同意未覆盖 SSL/模型公开/跨境，或伦理 amendment 未批准：停止。
6. **传输机制、合同与备案是否在传输前完成？**
   - 深圳 GBA、北京全国路径、EU/UK 适用传输机制、美国角色/DSP 分别核对。
7. **技术门槛是否满足？**
   - solo、明文 HTTP、弱共享口令、真实集中测试集、hosted predict、无最小队列：停止。
8. **四类 owner 是否具名签字？**
   - 法务/DPO、伦理/PI、信息安全、系统 owner 缺一项：不启用真实数据。

### 立即 No-Go 条件

- 用 `FED_COHORT=1` 或 `FED_SOLO_SHARED` 处理真实儿童、临床或跨机构资料；
- 仍用明文 HTTP、空口令或共享演示密码跑真实数据；
- 不知道协调端、备份、日志、管理员和远程支持的实际法域；
- 深圳 GBA 合同资料允许北京/新加坡/欧美人员访问；
- 北京/内地医院未完成敏感信息、重要数据、行业规则和出境路径确认；
- 原同意/伦理未覆盖联邦训练、当前学习方式、接收者和模型发布；
- 把带标签真实测试集集中到协调端但没有单独批准；
- 公开真实小机构精确样本量、类别数、单节点 AUC/混淆矩阵；
- 把 masked/DP/model 宣称成已匿名或宣称“GDPR/PIPL/HIPAA compliant by design”；
- 参与者退出、保留/删除、事故通知和模型发布责任无人承担。

### 有条件 Go

- synthetic/public、许可明确且经核验不含个人资料的工程 demo；或
- 全部香港的三机构研究试点，完成伦理、PICS 与适用的 DPP3 prescribed consent、角色协议、
  风险评估和安全部署；或
- 香港—深圳三机构研究试点：除各机构伦理、来源法域告知/所需同意、角色与处理协议、安全
  部署和具名批准外，还完成 GBA 合同、备案前三个月内 PIPIA、两地备案和严格地域锁，且
  不含重要数据；
- 以上仍只代表受控研究处理获批，不代表临床或医疗器械合规。

## 对外可用与禁用表述

### 可用

> 推荐训练路径中，原始记录和逐条特征留在参与机构节点。三节点及以上时，节点传输成对
> 掩码的整数叶节点类别计数及必要协议元数据；协调端恢复池化计数后应用中央差分隐私并
> 发布 JSON 模型。这些措施降低披露风险，但不会自动使所有更新、模型或元数据成为匿名
> 资料，也不替代合法处理依据、伦理批准或适用的跨境传输机制。

### 禁用

- “没有任何数据/信息离开节点”；
- “安全聚合后就是匿名数据”；
- “DP 天然满足 GDPR/PIPL/HIPAA”；
- “单节点也有安全聚合”；
- “epsilon 10 就是每位儿童的 epsilon 10”；
- “邀请文件等于机构、伦理或参与者授权”；
- “无标签数据不受隐私法限制”；
- “模型和审计包可以自由公开或跨境转发”；
- “dashboard AUC 证明跨院临床效果”。

## 给法务、DPO 和伦理委员会的问题

1. 每个阶段谁实际决定目的和关键方式：独立、共同 data user/controller，还是 processor？
2. 原 PICS/同意/伦理是否明确覆盖联邦 leaf counts、监督/SSL/半监督、模型发布和境外接收者？
3. 哪些产物仍是个人/敏感资料？匿名性判断采用何种攻击者能力、外部资料和复核周期？
4. 一个自然人的视频/窗口跨轮、跨房间如何去重和计算出境人数/隐私预算？
5. 协调端、测试集、audit、backup、日志、管理员和 support 分别位于哪里？
6. 深圳是否采用 GBA 合同；若采用，如何技术上保证无人从 GBA 外访问任何受控产物？
7. 北京/医院适用标准合同、认证、安全评估、负面清单还是更严格境内存储？
8. 是否涉及 CIIO、重要数据、人口健康信息或未来 HGR？谁出具书面分类结论？
9. EU/UK/US 合作方各自的 lawful basis、special-category 条件、transfer instrument 和伦理依据？
10. 美国机构是否触发 HIPAA/BAA/DUA/Common Rule/州法？DSP bulk/covered-transaction 和
    PADFAA data-broker 两套独立筛查的结论分别是什么？
11. 参与者撤回后删什么、停止什么、哪些已发布产物无法逐人回滚，说明是否足够清楚？
12. 事故由谁在何时通知谁；若各法域门槛冲突，以哪个更严格时限执行？
13. 模型可否下载、再训练、公开、申请专利或用于临床；谁拥有和审批这些用途？
14. 当前依赖诚实节点执行的输入行级 DP 是否足以支持研究承诺；何时完成 person-level
    clipping、提交有效性控制和跨实验账本？

## 官方来源

### 香港

- [香港《个人资料（私隐）条例》Cap. 486](https://www.elegislation.gov.hk/hk/cap486)
- [PCPD：六项 Data Protection Principles](https://www.pcpd.org.hk/english/data_privacy_law/6_data_protection_principles/principles.html)
- [PCPD：Preparing Personal Information Collection Statements and Privacy Policy Statements](https://www.pcpd.org.hk/english/resources_centre/publications/files/GN_picspps_e.pdf)
- [PCPD：Recommended Model Contractual Clauses for Cross-border Transfer](https://www.pcpd.org.hk/english/resources_centre/publications/files/guidance_model_contractual_clauses.pdf)
- [香港政府：第 33 条尚未生效及当前 DPP/processor 责任说明](https://www.info.gov.hk/gia/general/201504/29/P201504280758.htm)
- [香港立法会 2025-07-02 官方会议记录（议员发言称第 33 条仍未实施，作旁证）](https://www.legco.gov.hk/yr2025/english/counmtg/hansard/cm20250702-translate-e.pdf)
- [PCPD：研究/统计豁免与匿名化个案说明](https://www.pcpd.org.hk/tc_chi/enforcement/case_notes/casenotes_2.php?content_nature=&content_type=&id=2025E02&msg_id2=612)
- [PCPD：GBA Standard Contract 指引](https://www.pcpd.org.hk/english/resources_centre/publications/files/standard_contract_gba.pdf)
- [香港 Digital Policy Office：GBA 标准合同、流程及 FAQ](https://www.digitalpolicy.gov.hk/en/our_work/digital_infrastructure/mainland/gbacbdf/cross-boundary_data_flow/index.html)
- [PCPD：面向互联网儿童用户收集/使用资料的提示（2015）](https://www.pcpd.org.hk/english/resources_centre/publications/files/guidance_children_e.pdf)
- [PCPD：疫情期间学校在线教学的视频、录音与 tracking 提示（2020）](https://www.pcpd.org.hk/english/news_events/media_statements/press_20200402.html)
- [PCPD：Data Breach Notification](https://www.pcpd.org.hk/english/enforcement/data_breach_notification/dbn.html)
- [PCPD：AI Model Personal Data Protection Framework](https://www.pcpd.org.hk/english/news_events/media_statements/press_20240611.html)
- [HKUST：Human Participants Research Policy](https://vprd.hkust.edu.hk/policies-compliance/policies-guidelines/human-participants)
- [HKUST：Human and Artefacts Research Ethics Committee](https://vprd.hkust.edu.hk/policies-compliance/crp/harec)

### 中国内地与大湾区

- [国家网信办：《个人信息保护法》全文](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm)
- [全国人大：《数据安全法》](https://www.npc.gov.cn/npc/c2/c30834/202106/t20210610_311888.html)
- [国家法律法规数据库：《网络安全法》（2026-01-01 起现行修正版）](https://flk.npc.gov.cn/detail?fileId=&id=021e7d7684474107b8f3febbb1c4f8b5&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E7%BD%91%E7%BB%9C%E5%AE%89%E5%85%A8%E6%B3%95&type=)
- [国务院：《网络数据安全管理条例》](https://www.cac.gov.cn/2024-09/30/c_1729384452307680.htm)
- [国家网信办：《促进和规范数据跨境流动规定》](https://www.cac.gov.cn/2024-03/22/c_1712776612187994.htm)
- [国家网信办：《个人信息出境标准合同办法》](https://www.cac.gov.cn/2023-02/24/c_1678884830036813.htm)
- [国家市场监管总局/国家网信办：《个人信息出境认证办法》（2026-01-01 施行）](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2025/art_58457106dd624e06be6d179d09284dcb.html)
- [国家网信办：数据出境安全评估申报指南（第三版）](https://www.cac.gov.cn/2025-06/27/c_1752652339765002.htm)
- [国家网信办：境外远程访问的数据出境问答](https://www.cac.gov.cn/2025-10/31/c_1763633376984070.htm)
- [GBA 标准合同实施指引](https://www.cac.gov.cn/2023-12/13/c_1704042786237103.htm)
- [北京市政府：“两区”数据出境管理负面清单（2025 版）及管理办法](https://www.beijing.gov.cn/zhengce/zhengcefagui/202605/t20260511_4645754.html)
- [国家网信办：未成年人个人信息保护合规审计问答（2026）](https://www.cac.gov.cn/2026-04/29/c_1779200509387274.htm)
- [国家网信办：未成年人个人信息保护年度审计情况报送公告](https://www.cac.gov.cn/2025-12/29/c_1768735145606358.htm)
- [国家卫健委：《医疗卫生机构网络安全管理办法》](https://www.nhc.gov.cn/guihuaxxs/c100133/202208/8a23d01133214a779879094dd20cd383.shtml)
- [国家网信办：《国家健康医疗大数据标准、安全和服务管理办法（试行）》](https://www.cac.gov.cn/2018-09/15/c_1123432498.htm)
- [国家卫健委：《人口健康信息管理办法（试行）》](https://www.nhc.gov.cn/guihuaxxs/c100133/201405/bf0167b13f8b4c448bdeda1cdb729c12.shtml)
- [国家卫健委：《涉及人的生命科学和医学研究伦理审查办法》](https://www.nhc.gov.cn/qjjys/c100016/202302/6b6e447b3edc4338856c9a652a85f44b.shtml)
- [科技部：HGR 管理职责调整至国家卫健委](https://www.most.gov.cn/tztg/202404/t20240425_190494.html)
- [人类遗传资源管理条例实施细则](https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/bmgz/202306/t20230601_186416.html)

### EU、英国、美国及其他示例

- [EU GDPR 官方全文](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng)
- [European Commission：Adequacy Decisions](https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en)
- [European Commission：SCC 与 transfer assessment 说明](https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/new-standard-contractual-clauses-questions-and-answers-overview_nl)
- [EDPB Opinion 28/2024：AI 模型与个人资料](https://www.edpb.europa.eu/documents/opinion-of-the-board-art-64/opinion-282024-on-certain-data-protection-aspects-related-to_en)
- [ICO：AI、security、data minimisation 与 federated learning](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/artificial-intelligence/guidance-on-ai-and-data-protection/how-should-we-assess-security-and-data-minimisation-in-ai/)
- [ICO：International Transfers](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/international-transfers/)
- [HHS：HIPAA De-identification](https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html)
- [HHS OHRP：Common Rule](https://www.hhs.gov/ohrp/regulations-and-policy/regulations/common-rule/index.html)
- [FTC：Consumer Health Information、HIPAA 与 FTC Act/HBNR](https://www.ftc.gov/business-guidance/resources/collecting-using-or-sharing-consumer-health-information-look-hipaa-ftc-act-health-breach)
- [FTC：Protecting Americans’ Data from Foreign Adversaries Act (PADFAA)](https://www.ftc.gov/legal-library/browse/statutes/protecting-americans-data-foreign-adversaries-act-2024-padfaa)
- [U.S. DOJ：Data Security Program](https://www.justice.gov/nsd/data-security)
- [U.S. DOJ：Data Security Program FAQ](https://justice.gov/nsd/media/1415006/dl)
- [Singapore PDPC：Data Protection Obligations](https://www.pdpc.gov.sg/overview-of-pdpa/the-legislation/personal-data-protection-act/data-protection-obligations)
- [Australia OAIC：APP 8 Cross-border Disclosure](https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines/chapter-8-app-8-cross-border-disclosure-of-personal-information)

## 维护规则

- 每次增加机构、国家、云区域、管理员所在地、学习目的、模态或模型发布对象，都新增/更新
  destination annex 和数据流图；不得复用旧结论而不复核。
- 每次协议字段、DP 单位、test set、hosted inference、audit bundle 或备份内容改变，都更新
  本页“当前系统究竟会处理和传输什么”。
- 法律状态至少每季度复核；GBA、内地出境、美国 DSP 和未成年人规则应在真实数据上线前再
  核验一次。
- 法务形成最终结论后，把“待确认”事项和书面批准日期记录到 `decisions-log.md`，不要把本页
  的一般研究结论当成某一机构已经获批。
