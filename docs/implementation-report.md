# InferTrace 实现报告

执行依据：docs/implementation-plan.md。当前目标版本：0.1.0rc2。
当前评审修复的验收状态见 [review-followups.md](review-followups.md)。
九项评审问题已全部修复，80 项测试、Python 3.10/3.12、Chromium、
独立 wheel 安装、Compose/Jaeger 和依赖审计均已通过。
rc2 源代码提交：218c4d1ca48a54c58741f94c01866049bffac077。
[rc2 完整 CI #39113508807](https://github.com/OrionHubble89/InferTrace/actions/runs/39113508807)。
Zero Overhead 的工程约束已测试；真实推理开销和引擎兼容性仍属未执行的 M9。
以下 M0–M8 提交表是 rc1 的历史基线，不作为 rc2 最终验收结论。
本报告将本地验证、GitHub CI 和 M9 实机验证分开记录。
M0–M8 已完成 release candidate 范围内的实现和验证。
rc1 源代码提交：6a256b27ffbea0dd8d5af3414b4a3f773041363e。
[完整 CI 运行 #39108236394](https://github.com/OrionHubble89/InferTrace/actions/runs/39108236394)
全部成功：Python 3.10、Python 3.12、Chromium UI、Compose、dependencies。
M9 未执行，因此不宣称真实引擎兼容性、Zero Overhead 或生产就绪。

## 阶段提交与验证
以下为 GitHub 上的提交 SHA，不是执行环境中的临时本地 SHA。

| 阶段 | GitHub Commit SHA | 测试证据 |
|---|---|---|
| M0 | 319036bdff95a9501fba923324fb0ed95a00de97 | 1 测试；lint/type/build；Python 3.10/3.12 CI 通过 |
| M1 | 09c921b5b6d756d8fc7f8dc3863bb2c1c5110f56 | 3 测试；真实公开 API 的父子关系/传播/错误/取消；CI 通过 |
| M2 | a20aead57a24cd65f4150a90035a638858981abd | 15 测试；严格 schema、序列化与兼容 fixture；CI 通过 |
| M3 | 097a79505ce58673ef8907d1164c86e6f3716ba1 | 26 测试；SSE、队列/出口故障、SQLite、本机 HTTP；CI 通过 |
| M4 | 7b4d417592613de2c6ffb013993eb65a257582a1 | 32 测试；并发重叠、缺失事件、时钟/因果关系；CI 通过 |
| M5 | 360b6aa392f89db02db1a5807dbb8859c533131b | 32 Python 测试 + Chromium UI；CI 通过 |
| M6 | f56fef0ad807f87d86d18c87a0cf1242e2a1f123 | 40 测试 + UI；有界内存/禁用路径/采样；CI 通过 |
| M7 | a6805dd65e481f217d71b4be2064896fc8a65e3e；修复 9df9d453d98552cb4c1228ff98fe1a51dc994197 | 44 测试；Compose/Jaeger/UI 实际运行通过；格式修复后完整 CI 通过 |
| M8 | 6a256b27ffbea0dd8d5af3414b4a3f773041363e | 55 测试；Python 3.10/3.12、wheel、Chromium、Compose/Jaeger、依赖审计全部 CI 通过 |
| M9 | 未执行 | RTX 4090 + 真实 vLLM，按要求最后进行 |

M7 初次完整 CI 因 smoke 脚本格式失败，未作为完成依据；修复后重新通过。
中间 688d087 提交没有功能差异，不作为阶段完成证据。

## 已实现的工程
- OTel session/turn/model request/tool spans；W3C traceparent 和请求 ID 传播。
- 严格版本化 Event，分离 chunk/token/phase/metrics，记录来源、缺失和时钟域。
- SSE completion/chat 客户端；断流、畸形消息、取消和退出清理。
- 后台有界队列、批量出口、SQLite 幂等事务存储、HTTP 查询和 OTLP JSON 边界适配。
- 公共 Prometheus metrics 适配；不把聚合指标分摊给单个请求。
- 父 span 关联、跨时钟显式校准、重叠区间保留、显式因果路径。
- User / Request / Token 三层 UI；下钻、筛选、缩放、键盘操作和证据详情。
- 禁用快路径、自适应准入、丢弃计数、超时关闭和内存约束。
- 严格配置、能力探测、非 root Compose、mock 端到端安装和 Jaeger 链路。
- CI 的格式/类型/测试/wheel/UI/Compose/依赖检查。

M8 复核补强了长因果链的迭代算法、交错流式消费上下文隔离、非法遥测
fail-open、冲突重复事件整批回滚、HTTP 出口按字节拆批和 OTLP JSON 适配。
这些补强已通过上述最终 M8 CI。当前没有阻断此 MVP release candidate 的已知严重问题。

## 本地验证范围
Python 3.12，55 个 CPU-only 测试；真实 Chromium 浏览器测试；独立虚拟环境
中的 wheel 安装、静态资源和 HTTP API 检查；pip check。
运行时 Python 依赖图审计：22 个依赖，未发现已知漏洞。
npm audit：0 个已报告漏洞。漏洞库结果只代表检查时点。
CPU 微基准原始结果见 cpu-microbenchmark.json；仅测预分配事件的 emit 调用，
包含饱和丢弃，不能作为推理性能开销结论。

## 架构与边界
详见 architecture.md、collector.md、event-schema.md、correlation.md。
应用边界采集 → 后台 Collector → HTTP/SQLite → 关联引擎 → 三层 UI；
OTel spans 独立经 OTel Collector 进入 Jaeger。

## 剩余问题与 M9 交接
1. 尚无 RTX 4090 / 真实 vLLM 验证，未测吞吐、TTFT、ITL 或 p99 开销。
2. 基线只能观察 HTTP chunks；engine token/phase 必须来自显式可信引擎数据源。
   当前内置 OTLP JSON 接入提供 span 边界，不提供自动 vLLM token hook。
3. vLLM metrics 是聚合数据；标签暂省略并标注缺失，不能推断 GPU 归属。
4. 跨机器时钟需外部校准，未实现时钟漂移估计。
5. UI 默认最新 1000 事件一页，可在完整数据库上筛选和翻页；页边界会显式标注部分数据。JS 纳秒数值存在精度限制。
6. 采样/溢出/出口故障可能产生部分 trace；LRU 驱逐后采样决策可能重算。
7. 自定义阻塞出口不能被 Python 强制终止；close 超时会返回 false。
8. HTTP 服务仅限可信本机环境，无内置认证/多租户/自动保留策略；详见 security.md。
9. 尚未发布 tag/PyPI 包；release candidate 不等于 production ready。

下一步是 M9：在可访问的 RTX 4090 24GB 环境部署真实 vLLM，
记录版本矩阵并执行对照实验。当前任务没有访问/租用 GPU 主机，也没有运行
GPU 基准。不得用 mock 结果替代真实环境验证。无需重做 M0–M8；
后续从 docs/release-checklist.md 的 M9 部分继续。
