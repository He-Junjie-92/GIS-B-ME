# 数据结构说明

## 实例目录

`data/instances/` 下每个实例目录包含 9 个文件：

| 文件 | 内容 |
| --- | --- |
| `instance.xlsx` | 实例主工作簿，含节点、簇、技术人员、任务、建筑、时间窗、配置与校验表 |
| `road_matrix.parquet` | 完整有向任务级 OD 矩阵，含道路距离与标准化行驶时间 |
| `config.json` | 该实例的生成配置，路径字段为相对路径 |
| `README.md` | 该实例的简要说明 |
| `map_preview.png` | 实例空间分布预览图 |
| `task_points.geojson` | 电梯位置与维保站空间数据，筛选 `node_type=ELEVATOR` 得到任务位置 |
| `clusters.geojson` | 任务簇空间数据 |
| `used_buildings.geojson` | 实例使用的建筑面数据 |
| `used_building_anchors.geojson` | 建筑接入锚点数据 |

## 工作簿表结构

`instance.xlsx` 含 14 个工作表：

- `NODES`：维保站与电梯节点，含平面坐标、经纬度、簇编号、建筑类型与建筑属性。
- `CLUSTERS`：任务簇，含簇中心坐标、簇半径、簇内电梯数、锚点建筑与空间模式。
- `TECHNICIANS`：候选技术人员池，含班次起止、常规与最大工时、技能组与候选池归属。
- `TASKS`：PM 任务，含任务编号、电梯编号、建筑编号、建筑类型、服务时长、可用类别与时间窗摘要。
- `BUILDINGS`：实例使用的建筑，含面积、楼层、高度、容量数据质量、估计容量、已分配任务数与容量利用率。
- `TASK_WINDOWS`：任务级可服务日与日内窗口，含最早开始时间与最晚完成时间。
- `CONFIG`：实例级参数键值表。
- `VALIDATION`：结构校验结果。
- `GIS_VALIDATION`：空间数据校验结果。
- `ROAD_NETWORK`：该实例所依赖路网的规模指标。
- `BUILDING_STATS`：候选建筑面积统计。
- `CAPACITY_RULES`：建筑容量规则表。
- `ELEVATOR_DISTRIBUTION`：按建筑类型统计的任务承载分布。
- `README`：工作表说明。

## 关键字段约定

- `task_id` 在单个实例内唯一；跨实例使用 `(instance_id, task_id)` 作为联合主键，每部电梯对应且仅对应一项 PM 任务。
- 同一建筑内的多项任务共享同一道路接入节点，建筑之间行驶距离可为零，但每项任务各占 30 min 服务时间。
- `due_time_min` 为最晚完成时间，任务最晚开始时间等于 `due_time_min` 减服务时长。
- `road_matrix.parquet` 使用节点编号作为起讫点，包含维保站与全部任务节点；100、500、1000 任务实例
  分别含 101²、501²、1001² 条有向记录。
- `config.json` 中的 `output_root`、`shared_road_network_path` 与
  `shared_building_candidates_path` 已改写为相对本数据集根目录的相对路径。

## 元数据文件

- `metadata/frozen_parameters.json`：城市、规模、空间模式、种子、速度、班次、建筑类型比例与
  时间规则的冻结取值。
- `metadata/generation_configs/`：每个实例一份生成配置，属于生成输入快照；共有字段与实例配置一致，实例配置另含16个规则和统计字段。
- `metadata/instance_manifest.csv`：实例索引，列出实例编号、城市、规模、空间模式、种子与相对路径，
  行顺序为北京、上海、重庆。
- `metadata/checksums_sha256.csv`：全部发布文件的相对路径、字节数与 SHA-256 校验值。

## 补充约定（内部组装修订v3.0.1及v3.1.0）

- `building_osm_id`为已恢复的真实OSM对象类型与编号，如`way/123456789`；跨城市内部建筑主键为`(city_code, building_anchor_id)`。
- `CONFIG.road_network_file`相对数据集根目录解析；`CONFIG.road_matrix_file`相对实例目录解析。
- `lon/lat`与GeoJSON几何为EPSG:4326；`projected_x/y`单位为米，北京EPSG:32650、上海EPSG:32651、重庆EPSG:32648。
- `x_km/y_km`为局部公里坐标，原点见`metadata/coordinate_systems.json`。`crs=EPSG:4326`只说明经纬度，不代表所有坐标列。
- OD字段与连接方法、可选脚本、完整读取示例见英文[DATA_SCHEMA.md](DATA_SCHEMA.md)和[USAGE.md](USAGE.md)。
- GraphML内边属性`travel_time`和`speed_kph`属于来源处理属性，算法应读取正式OD的`road_time_min`，按15 km/h统一换算。
