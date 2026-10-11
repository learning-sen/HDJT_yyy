# PyAether 新手速成教程

> 面向零基础队员。目标：看懂华大九天 PyAether 生态、会用常见命令、能答对基础知识问卷。
> 阅读方式：先读第 0 章建立地图，再按需查表。全篇尽量用表格，不背大段文字。

---

## 0. 先建立地图（5 分钟）

**EDA 是什么**：设计芯片用的软件。模拟芯片流程大致是：
`画电路图(schematic) → 仿真验证 → 画版图(layout) → 物理验证 → 导出制造文件`。

**三个层次，别混**：

| 层次 | 是什么 | 关键词 |
|---|---|---|
| 平台层 | 华大九天的整套工具（很多个软件） | Aether、ALPS、Argus、Liberal… |
| 工具层 | 每个软件干一件事 | 仿真、寄生提取、物理验证… |
| 接口层 | 用 Python 指挥这些软件 | **PyAether** |

**PyAether 一句话**：把 Aether 全定制平台的操作，变成 Python 命令，从而能写脚本自动画图、自动仿真、自动优化。

**命令命名规律（记住这一条，问卷一半题会做）**：

| 前缀 | 含义 | 例子 |
|---|---|---|
| `ae…` | **Ae Commands**，操作设计对象（画图形、开菜单、改属性） | `aeCreateRect` |
| `db…` | **数据库/版图命令**，直接操作底层数据（库、单元、视图、CDF） | `dbCrtVia` |
| `cdf…` | 操作器件**参数（CDF）** | `cdfGetCDF` |
| `emy…` | Python **数据模型类**（对象化的库/网表/图形） | `emyDesign` |
| `dm…` | **数据管理**类（文档、文件） | `dmCellObj` |

> 记忆口诀：**ae 画图、db 建库、cdf 调参、emy 建模、dm 管文件。**

---

## 1. 华大九天工具全家桶（问卷前半部分全考这个）

按"干什么用"分类记，比死记名字快。

### 1.1 仿真类

| 工具 | 定位 | 必背关键词 |
|---|---|---|
| **ALPS** | 大规模高精度电路仿真器 | 大规模、高精度、**Snapshot**（快照：秒级保存/恢复仿真状态，加速长仿真） |
| **ALPS CS** | 数模混合仿真 | **数模域同步协同 + 并行计算** |
| **ArtemisFPD** | 平板显示（FPD）仿真 | **显控一体**、**Noise 噪声/信号干扰分析** |

### 1.2 寄生与 K 库（"K 库"= 特征化库，告诉工具器件在不同条件下的行为）

| 工具 | 定位 | 必背关键词 |
|---|---|---|
| **ADA** | **版图寄生参数**提取/分析 | 新一代寄生参数分析 |
| **Liberal** | 全栈式 **K 库**解决方案 | 主要服务**模拟 IC** 设计 |
| **Liberal GT** | K 库**优化**工具 | 全球首发、**10X 提速**、GPU 加速 |
| **Liberal Mem** | 存储器特征化 | 效率提升 **100X** |
| **Liberal IP** | 混合信号 IP 设计 | **LVF 精准 K 库** |

### 1.3 版图/验证/制造类

| 工具 | 定位 | 必背关键词 |
|---|---|---|
| **Vision / Vision CA** | 版图处理、良率提升 | **Care Area 精准提取**、晶圆制造良率 |
| **Argus** | **物理验证**（DRC/LVS 类） | 支持范围广：**大规模数字 SoC、泛模拟、3D IC/Chiplet、射频版图** |
| **Storm** | **先进封装**设计平台 | 全球首发、**Chiplet 布线效率提升 1–2 倍**、支持 3D |
| **Polas** | **功率（电源）电路**设计 | 与功率电路强相关 → 说"与功率无关"就是错的 |

### 1.4 设计平台类

| 工具 | 定位 |
|---|---|
| **Aether** | 全定制（模拟）设计平台，画 schematic / symbol / layout |
| **MDE** | 仿真管理环境：配好 corner、一键跑仿真、看结果 |
| **AetherWings** | 版图辅助工具集（见 4.4） |
| **PyAether** | 上述平台的 **Python 自动化接口** |

---

## 2. Aether 里的基本概念（必须分清）

| 概念 | 英文 | 通俗解释 |
|---|---|---|
| 库 | **lib** | 一个项目文件夹 |
| 单元 | **cell** | 一个电路模块（如 `OPA`） |
| 视图 | **view** | 同一单元的多种表现：`schematic`（电路图）、`symbol`（符号）、`layout`（版图） |
| 实例 | **inst / instance** | 电路图里放的一个器件或子模块 |
| 网络 | **net** | 连线，如 `VOUTP`、`net12` |
| 端子 | **term / pin** | 单元的对外接口 |
| 图形 | **figure / fig** | 版图里的矩形、多边形、路径等 |
| CDF | Component Description Format | 器件的**参数表**（`w`、`l`、`m`…） |
| PR Boundary | — | 单元的**物理边界框**（占位/面积用） |

**三个视图的区别（高频考点）**：

- `schematic`：电路连接关系，用来仿真
- `symbol`：画在上一层里的小方块，只是个符号
- `layout`：真实几何图形，用来做版图验证

**核心思路**：同一份设计 = `lib` + `cell` + `view` 三者唯一确定。

---

## 3. 命令怎么找、怎么用（方法论）

1. **先按前缀猜分类**（见第 0 章口诀），能排除一半错误选项。
2. **看动词**：`Crt`=Create 创建、`Del`=删除、`Get`=获取、`Set`=设置、`Is`=判断（返回 True/False）、`Modify`=修改、`Conv/Convert`=转换。
3. **看返回类型**：名字带 `Is` / `Contains` 的，基本都返回**布尔值**。
4. **看对象**：`CV` = CellView（单元视图），`Cat` = Category（分类）。
5. **不会就查官方文档**，不要猜。

---

## 4. 命令速查表（问卷后半部分考点）

### 4.1 库 / 单元 / 视图

| 命令 | 作用 |
|---|---|
| `aeNewLib` / `aeDelLib` / `aeCopyLib` | 新建/删除/复制 **库** |
| `aeNewCell` / `aeDelCell` | 新建/删除 **单元** |
| `aeScheViewToView` | **视图互转**（schematic ↔ symbol） |
| `dbOpenCV` | 打开单元视图（`mode`：`r` 只读 / `w` 写 / `a` 追加 / `readOnly`） |
| `dbChangeCVMode` | 切换视图模式（`r` / `w` / `a`，**没有 `x`**） |
| `dbSeCheckDesignInfo` | 检查设计信息，返回 **Error strings / Warning strings** |
| `dbIsCellViewModified` | 判断单元视图是否被修改 → **布尔值** |
| `dbCatContains` | 判断分类是否包含某物 → **布尔值** |
| `dbCatModify` | 修改分类（参数如 `cat`、`cells`、`subs`、`lib`） |
| `dbLayerGen` | 层布尔运算，`op` 取值 **OR / AND / XOR / NOT** |

### 4.2 创建图形：`dbCrt*` 与 `aeCreate*` 对照

| 想创建 | db 系命令 | ae 系命令 |
|---|---|---|
| 矩形 | `dbCrtRect(cv, bbox, layer, purpose)` | `aeCreateRect`（起点终点、图层、purpose） |
| 圆 | `dbCrtCircle` | `aeCreateCircle` |
| 椭圆 | — | `aeCreateEllipse` |
| 圆环（甜甜圈） | — | `aeCreateDoughnut`（必给 **inner / outer 半径**） |
| 多边形 | `dbCrtPolygon` | `aeCreatePoly` |
| 线 | `dbCrtLine` | — |
| 路径 | `dbCrtPath`（由**点序列**构成） | `aeConvertShapeToPathSeg` / `aeConvertPolygonToPath` |
| 连线 | `dbCrtWire` | — |
| 通孔 via | `dbCrtVia` | — |
| 引脚 pin | `dbCrtPin` | — |
| 实例 | `dbCrtInst`（参数含 `master`、`lib`、`angle`、`params`） | — |
| PR 边界 | `dbCrtPRBoundary` | — |
| 圆弧 | `dbCrtSymbolArc` | — |
| 标记 marker | `dbCrtMarker`（有 `isVisible` 参数） | — |

> 记法：**`db` 偏版图底层，`ae` 偏 Aether 交互**。两者都能画矩形，别死记，记"哪一系里有哪些"。

### 4.3 编辑 / 属性 / 转换

| 命令 | 作用 |
|---|---|
| `aeMoveObj` | 移动**选中的对象** |
| `dbPasteObj` | 把剪贴板内容粘贴到设计中（失败常见原因：**剪贴板为空、源/目标技术不同、超出边界**） |
| `aeAttribute` | 编辑/查看对象**属性** |
| `aeModifyCorner` | 修改**角（corner）** |
| `aeSchReplaceProperty` | 替换**原理图属性** |
| `aeBoolean` / `aeReplace` | ⚠️ 不是"编辑属性"类命令 |
| `dbSchIsWire` | 判断对象是否为**线** |

**CDF 改参三兄弟**：

| 命令 | 作用 |
|---|---|
| `cdfGetCDF` | 取 CDF 标识符（参数：`libName`、`cellName`…） |
| `cdfSetRefParamValues` | 批量设置参数值 ✅ 可用来"设置和修改" |
| `cdfSetParamValueByName` | 按名字设置单个参数值 ✅ |
| `cdfModify` / `cdfChange` | ❌ 不存在，干扰项 |

### 4.4 AetherWings（版图辅助神器，模块名要眼熟）

**七个功能模块**：`Kits-Tools`、`Pins-Tools`、`vEditors-Tools`、`Router-Tools`、`UniVia-Tools`、`GetNet-Tools`、`Customized-Tools`。

**能实现的功能**：自动打孔、自动跳层与避障、按电流约束设定布线规则、按 X/Y 方向约束布线规则。

### 4.5 界面 / 菜单 / 环境

| 命令 | 作用 |
|---|---|
| `aeCreateMenu` → `aeCreateMenuItem` → `aeInsertBannerMenu` | **自定义菜单三步走**（建菜单 → 建菜单项 → 插入到 Aether 顶部） |
| `aeDisplayForm` | 显示表单（属于 API，不是建菜单的必需步骤） |
| `aeClickMsgBoxOk` / `Cancel` / `Apply` | 自动点击弹窗按钮 |
| `aeRunTcl` | 在 Python 里**执行 Tcl 脚本** |
| `aeGetBindKey` | 获取快捷键绑定 |
| `aeGetSnapToSPTransform` | 获取对齐到捕捉模式的变换 |
| `aeDesignIsLayout` / `aeDesignIsSchematic` / `aeDesignIsSymbol` | 判断设计类型 |
| `aeDesignIsEditable` | 判断设计是否**可编辑** |
| `emyInitAether` | 初始化 Aether 系统（用 Ae Commands 之前） |

### 4.6 `emy*` 数据模型（Python 侧）

| 类 | 说明 |
|---|---|
| `emyDatabase` | 数据库总入口 |
| `emyDesign` | 设计对象，属性如 `name`、`cells`、`layers`、`views` |
| `emyNet` 及子类 | 网络：`emyScalarNet`（标量）、`emyBusNet`（总线）、`emyBundleNet`（捆绑） |
| `emyInst` / `emyTerm` | 实例 / 端子 |
| `emyFig` | 图形基类；**`emyRoute` 继承自 `emyFig`** |
| `emyBox` | 矩形框（`isInverted` 判断坐标是否倒序） |
| `emyBoundary` / `emyAreaBoundary` / `emyClusterBoundary` / `emyPRBoundary` | 各类边界 |
| `emyAttrDisplay` | 显示属性值，`object` 可为 `emyNet` / `emyInst` / `emyTerm`（**以上都是**） |
| `emyAntennaModel` / `emyAntennaData` / `emyAntennaRatioValue` | 天线效应相关 |
| `emyAntennaData` 方法 | `diff`、`gate`、`maxCAR`、`partialMetal` |
| `dmCellObj.getCell()` | 取 cell 属性：`name`、`type`、`readPath`、`writePath` |
| `dmCellFileObj` | 文件对象：文件类型、所属单元/库、读写路径 |

**Extension 模块**：PyAether 里提供 **Query、GOA** 等扩展功能的模块。
**MDE 模块**：仿真管理相关。

### 4.7 PyAether 生态能干什么（综述题）

✅ 自动生成版图、自动进行电路仿真设置、自动提取电路参数、自动进行设计规则检查 —— **都能**。

---

## 5. 三个必背小流程

**① 自定义菜单**：`aeCreateMenu` → `aeCreateMenuItem` → `aeInsertBannerMenu`

**② 改器件参数**：`cdfGetCDF` 拿到 CDF → `cdfSetParamValueByName` 或 `cdfSetRefParamValues` 写值

**③ 用 Ae Commands 前的初始化**：`emyInitAether`

---

## 6. 需要的 Python 最小知识

- 定义类用 **`class`**；定义函数用 `def`。没有 `method`、`func` 这种关键字。
- 常用结构：列表 `[]`、字典 `{}`、`for` 循环、`if` 判断、`import` 模块。
- 本赛题只需要：读文件、写文件、循环调命令、把结果存下来。够用了。

---

## 7. 易混点对照（考前 10 分钟看这个）

| 容易混 | 正确理解 |
|---|---|
| `ae` vs `db` | `ae` 操作 Aether 交互对象，`db` 操作底层库/版图数据 |
| `schematic` / `symbol` / `layout` | 电路图 / 符号 / 版图，互转用 `aeScheViewToView` |
| `dbChangeCVMode` vs `dbOpenCV` | 都涉及 mode；`dbChangeCVMode` 无 `x` |
| `aeBoolean` | 布尔运算，**不是**改属性 |
| `cdfModify` / `cdfChange` | 不存在，真的接口是 `cdfSetParamValueByName`、`cdfSetRefParamValues` |
| `Polas` | 功率电路相关，说它"与功率无关"是错的 |
| `Vision` | 良率/Care Area，不是仿真器 |
| `Liberal Mem` | 100X（存储器）；`Liberal GT` 是 10X（GPU 加速） |
| `ALPS` vs `ALPS CS` | ALPS = 大规模仿真 + Snapshot；CS = 数模混合 |

---

## 8. 三天学习计划

| 天 | 做什么 | 验收 |
|---|---|---|
| D1 | 读第 0、1、2 章；把工具"定位+关键词"表抄一遍 | 能说清每个工具干嘛的 |
| D2 | 读第 3、4 章；把命令按前缀分类默写一遍 | 给一个命令能说出前缀含义和大致作用 |
| D3 | 读第 5、6、7 章；做一遍问卷（计时 30 分钟） | 错题回头对章节 |

**答题策略提醒**：多选题 **少选得 1 分、选错 0 分** → 拿不准的**宁可不选**，不要凑数。

---

## 附录：考题 → 章节速查

| 题号 | 考点 | 章节 |
|---|---|---|
| 1–5 | Liberal Mem / ALPS / ALPS CS / Liberal IP / ADA | 1.1、1.2 |
| 6–8 | Vision CA / ArtemisFPD / Liberal | 1.3、1.2 |
| 9–11 | 视图互转 / aeMoveObj / aeCreateDoughnut | 4.1、4.3、4.2 |
| 12–14 | Extension 模块 / aeRunTcl / dbChangeCVMode | 4.6、4.5、4.1 |
| 15–18 | emyAttrDisplay / dbCrtPRBoundary / Python class / dbCrtRect | 4.6、4.2、第 6 章、4.2 |
| 19–22 | Argus / Liberal GT / ALPS / Storm | 1.3、1.2、1.1、1.3 |
| 23–25 | PyAether 生态能力 / dbSeCheckDesignInfo / AetherWings 模块 | 4.7、4.1、4.4 |
| 26–29 | aeCreateRect 参数 / dbLayerGen / 建菜单 / dmCellObj | 4.2、4.1、5①、4.6 |
| 30–33 | 属性编辑命令 / dbPasteObj / 库单元命令 / emyDesign | 4.3、4.3、4.1、4.6 |
| 34–36 | CDF 改参 / aeCreate 图形 / dbCatModify | 4.3、4.2、4.1 |
| 37–39 | Polas / Liberal GT / Vision | 1.3、1.2 |
| 40–46 | dbCrtMarker / dbCatContains / dbCrtPath / emyBox / dbIsCellViewModified / dbCrtLine / dbCrtSymbolArc | 4.1、4.2、4.6 |

---

> **一句话总结**：先分清 `ae / db / cdf / emy / dm` 五类命令，再记住每个工具的"定位 + 关键词"，问卷就稳了。
