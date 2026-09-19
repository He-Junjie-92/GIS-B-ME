# 适用范围与限制

## 数据性质

本数据集是半合成 Benchmark。真实部分为 OpenStreetMap 提供的道路网络、建筑轮廓与建筑位置；
受控部分为建筑业务类型、电梯任务数量、建筑容量、时间窗与候选技术人员。数据集用于算法比较与
Benchmark 研究，不是官方电梯台账或真实维保计划的复现。

## 已声明的简化

- 建筑业务类型 RES/OFF/COM/SCH 为受控实验标签，未与真实建筑用途登记核对。
- 建筑容量由建筑面积与楼层信息按公开规则估计。楼层信息优先取 `building:levels`，缺失时按
  建筑高度除以 3 m 估计，两者都缺失时仅依据面积确定，并在数据中标记为 `levels_observed`、
  `height_derived` 或 `area_only`。容量计算中的有效面积按各城市候选建筑面积分布的 99% 分位截尾。
- 行驶速度统一取 15 km/h，不区分道路等级，也不含时变交通。
- 场景假设单一维保站、静态已下达任务、每项任务 30 min 服务时间且不设加班。
- 同一建筑内的多次访问不额外计入惩罚，重复访问成本已体现在道路行驶与工时中。

## 空间数据许可

道路网络与建筑轮廓来自 OpenStreetMap，使用与再分发需遵守开放数据许可（ODbL）并保留署名。
OSM源快照时间与资产生成时间分别记录在 `data/shared/cities/shared_assets_manifest.json`。

## 发布元数据

许可范围已列于LICENSE.md。作者、机构信息与仓储地址以 GitHub v1.0 Release 的
最终记录为准。发布包已包含完整生成器快照、135份配置、冻结GIS输入、
135份最终BKS调度及其独立校验结果。


## English summary

This is a semi-synthetic research benchmark. Building business types, elevator
counts, capacities and service windows are controlled labels, not verified
official records. Missing floor/height attributes use the documented area-only
fallback. Speeds are fixed at 15 km/h; there is no dynamic traffic, overtime,
multiple depots or heterogeneous technician skill constraint in the core problem.

Road networks used by all released maps and OD matrices are dated 2026-08-31. Exact machine-readable provenance is retained in metadata/source_provenance.json. Original building IDs have been recovered from the frozen
cache; no live-data refresh was used to replace geometries. Local task and
candidate IDs require instance/city-qualified joins.

Personnel optimality and route-pool optimality are distinct from global travel
optimality. The 135 released BKS schedules and independent validation outputs
support feasibility checks; they do not by themselves prove global travel-time
optimality.
