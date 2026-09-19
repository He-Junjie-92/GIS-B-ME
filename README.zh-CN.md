# GIS-B-ME：基于真实城市路网的半合成电梯预防性维保调度基准数据集

*GIS-B-ME: A Semi-Synthetic Benchmark for Elevator Preventive Maintenance Scheduling on Real-World Urban Road Networks*

GIS 增强型电梯预防性维保调度 Benchmark，对外数据集版本为 v1.0，共 135 个实例。
冻结实例的内部设计标识为 design v3 / assembly revision v3.1.0。

## 下载

- 正式 GitHub 仓库：`https://github.com/He-Junjie-92/GIS-B-ME`
- 正式 v1.0 Release：`https://github.com/He-Junjie-92/GIS-B-ME/releases/tag/v1.0`
- 完整 benchmark 压缩包：`GIS-B-ME-v1.0.zip`
- 校验和：`GIS-B-ME-v1.0.zip.sha256`

GitHub 自动生成的 **Source code (zip)** 和 **Source code (tar.gz)** 仅包含轻量代码与
文档，不包含完整 benchmark。135 个实例、OD 矩阵和经验证的 BKS 调度必须从 v1.0
Release 下载附件 `GIS-B-ME-v1.0.zip`。

GIS-B-ME 是半合成基准数据集。真实城市地理信息构成空间基础，维保任务及其业务属性按照受控
基准规则生成。GIS-B-ME 不是电梯台账或实际运营维保数据库。某一地理位置存在基准任务，并不
证明该位置真实存在电梯，也不证明其所有权、运行状态、技术状况或历史维保记录。城市标签仅表示
地理研究区域。

本文档及其余全部描述文件统一按下述城市顺序排列：**北京、上海、重庆**。

## 1. 实例设计

| 设计维度 | 水平 |
| --- | --- |
| 城市 | 北京（BJS）、上海（SHA）、重庆（CKG） |
| 任务规模 | 100、500、1000 项 PM 任务 |
| 空间模式 | CU（相对均匀覆盖）、CH（簇规模异质）、CZ（区域集中） |
| 实例种子 | S012、S034、S056、S078、S090 |

135 个实例由 3 城市 × 3 规模 × 3 空间模式 × 5 种子全因子构成，每个因子组合恰好 5 个实例，
合计 72,000 项 PM 任务，其中 100、500、1000 规模各 45 个实例，分别贡献 4,500、22,500 与
45,000 项任务。任务规模指电梯 PM 任务数而非建筑数，同一建筑可承载多项独立任务。

## 2. 城市与研究范围

| 城市 | 代码 | 研究范围 (km²) | 路网节点 | 有向边 | 合格建筑 | 冻结候选建筑 |
| --- | --- | --- | --- | --- | --- | --- |
| 北京 | BJS | 205.10 | 10,193 | 22,733 | 23,942 | 1,000 |
| 上海 | SHA | 202.82 | 7,687 | 18,283 | 34,578 | 1,000 |
| 重庆 | CKG | 193.35 | 8,134 | 15,805 | 5,530 | 1,000 |

同一城市的全部实例共享冻结的道路网络与建筑候选池。每个城市以可驾驶有向道路网络为基础，
建筑候选池按占地面积不低于 40 m²、且到最近可驾驶道路节点吸附距离不超过 150 m 筛选后固定抽取
1000 栋。建筑业务类型在 10×10 空间分层内按 RES/OFF/COM/SCH = 74/12/8/6 的精确全局比例分配。

## 3. 业务参数

- 规划周期 15 天，第 1 天为周一；第 1–5、8–12、15 天为工作日，第 6–7、13–14 天为周末。
- 每项任务现场服务时间 30 min，不设加班，每名技术人员每天最多工作 480 min。
- 技术人员同质，均从维保站出发并在当日返回维保站。
- 行驶时间按最短有向道路距离统一以 15 km/h 换算，不使用道路等级速度标签。
- 时间规则按建筑类型固定，不设时间窗场景维度：

| 建筑类型 | 可服务日期 | 日内服务窗口 |
| --- | --- | --- |
| RES（居住） | 全部 15 天 | 0–480 min |
| OFF（办公） | 工作日（11 天） | 120–360 min |
| COM（商业） | 工作日（11 天） | 0–480 min |
| SCH（学校） | 周末（4 天） | 0–480 min |

其中日内窗口的上界为最晚完成时间。以下均为135个实例分别计算后等权平均：建筑类型任务比例为 RES 72.68%、OFF 13.18%、
COM 8.68%、SCH 5.46%，每栋使用建筑任务数的实例均值为2.36，多任务建筑比例的实例均值为73.56%。

若合并全部任务记录，RES/OFF/COM/SCH分别为72.9403/12.9194/8.6500/5.4903%；
72000项任务对应30599条实例内使用建筑记录，平均2.3530项/建筑，多任务记录22364条（73.0874%）。
同一真实建筑在不同实例中重复出现，因此30599不是城市去重建筑数。

## 4. 参考结果说明

冻结结果为 K-OPT = 77、K-OPEN = 58、Gap1 = 40、Gap2 = 18。`K-OPT` 表示经验证的
人员上界与有效人员下界相等，`K-OPEN` 表示人员数量仍存在缺口。BKS 是相应已发布人员数量下的
当前最好已知参考结果，除非另有严格证明，否则不表示全局最优。路线池重组结果只能表述为
“在有限候选路线池内最优”，不能称为原始调度问题的全局最优。

## 5. GitHub 仓库目录

```text
GIS-B-ME/
├── .gitignore
├── README.md
├── README.zh-CN.md
├── LICENSE.md
├── OSM_ATTRIBUTION.md
├── CITATION.cff
├── CITATION.md
├── DATA_SCHEMA.md
├── DATA_SCHEMA.zh-CN.md
├── DATA_DICTIONARY.md
├── USAGE.md
├── LIMITATIONS.md
├── CHANGELOG.md
├── code/
├── configs/
├── environment/
├── metadata/
├── reference_results/
└── validation/
```

以上为 `git clone` 后得到的轻量仓库，不包含完整实例、OD 矩阵或 BKS 调度文件。

## 6. 完整 Release 压缩包目录

以下结构指 GitHub v1.0 Release 附件 `GIS-B-ME-v1.0.zip`：

```text
GIS-B-ME-v1.0/
├── README、许可、引用、数据结构、数据字典与使用说明
├── MANIFEST.csv、CHECKSUMS.sha256
├── code/
├── configs/
├── data/
│   ├── instances/              135 个完整实例目录
│   └── shared/cities/          冻结 GIS 资产
├── environment/
├── metadata/
├── reference_results/
│   └── solutions/              135 份经验证的 BKS 调度
├── reports/
├── scripts/
├── travel_matrices/            各实例内 OD 矩阵的索引
└── validation/
```

## 7. 校验状态

- 12 项统一校验在 135 个实例上全部通过，共 1,620 条检查记录全部为通过。
- 校验项覆盖建筑类型合法性、候选池数量、任务时间窗完整性、固定时间窗规则、15 km/h 速度设定、
  行驶时间矩阵公式、居住类全周期可服务、受限标志与建筑类型一致、道路矩阵全可达以及整体状态。
- 每个实例目录均包含 9 个文件，无缺失、无多余文件。

## 8. 数据来源与许可

道路网络与建筑轮廓来自 OpenStreetMap。使用本数据集时需遵守 OpenStreetMap 的开放数据许可
（ODbL）与署名要求。建筑业务类型与电梯容量为受控实验标签，不代表真实建筑用途登记或官方电梯
台账。数据库采用ODbL-1.0，原创说明文档和地图版式采用CC-BY-4.0，工具脚本采用MIT，
详见[LICENSE.md](LICENSE.md)。最终作者与机构信息以 GitHub v1.0 Release 元数据为准。

## 9. 版本

- 数据集名称：GIS-B-ME
- 对外发布版本：v1.0
- 实例数：135
- 状态：rebuilt_and_validated
- 城市顺序约定：北京、上海、重庆

## 10. 发布修订与来源

对外数据集版本为v1.0；内部设计标识为design v3，组装修订标识为assembly revision v3.1.0。
上述内部标识不构成公开发布版本。真实OSM建筑编号已从冻结缓存恢复，
3000栋候选建筑均通过几何匹配；`metadata/building_id_mapping.csv`保留旧编号映射。
Excel内部共享路网路径已改为相对发布根目录的路径，移除了不适用于v3的旧pilot说明。

本发布包中北京、上海和重庆的正式地理底座统一采用 2026-08-31 快照日期。
上海的 45 个实例、OD 矩阵和参考解均基于统一后的上海地理来源重新生成并重新验证，
没有通过修改日期标签沿用旧任务点。精确来源证据及发布资产哈希见
`metadata/source_provenance.json` 和 `OSM_ATTRIBUTION.md`。

读取示例与检查命令见[USAGE.md](USAGE.md)，英文说明见[README.md](README.md)。
数据包已包含 135 份最终 BKS 调度与可审计的参考结果表，不包含 Pareto 前沿、
种群历史、全部候选路线、中间检查点或调试日志。任务编号在实例内唯一；跨实例使用
`(instance_id, task_id)`。同一建筑允许回访，每次任务仍独立占用30分钟。

地图数据 © OpenStreetMap contributors，https://www.openstreetmap.org/copyright 。
ODbL许可：https://opendatacommons.org/licenses/odbl/1-0/ 。
