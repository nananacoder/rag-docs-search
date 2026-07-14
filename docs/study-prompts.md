# 手机学习 Prompt 库 — 在 Claude Chat 上学透这个项目的 AI/LLM 知识

用法：**每次新对话，先贴〔背景卡〕，再贴一个 Prompt。** 背景卡让 Chat 版
Claude 获得这个项目的全部关键事实（它看不到 repo）。哪里不懂就追问，
追问才是学习发生的地方。

---

## 〔背景卡〕每次新对话先贴这个

```
我在做一个 GCP 上的两阶段 RAG portfolio 项目，语料是 OpenStax Astronomy 2e
教科书（1,151 页 PDF）。核心设计是受控实验：同一语料、同一生成模型
（Gemini 2.5 Flash）、同一评测集，只换检索架构，对比 managed vs self-built。

Phase 1（managed）：Vertex AI Search，文档级检索，黑盒。实测 keyword
score 18.54%（prompt 三模式调优后），citation accuracy 0%（Standard tier
不返回页码，结构性不可能）。

Phase 2（self-built，已建成实测）：
- 解析：pymupdf 提取文本块+嵌入图片（678张），章节来自 PDF 书签目录（43章）
- 分块：章节感知递归切分，800 token / 120 overlap，不跨章，过滤 list-item
  （修 Phase 1 的"Key Terms 压过正文"结构噪音）
- Contextual Retrieval（Anthropic 2024）：每个 chunk 前置 50-100 token 的
  LLM 生成定位上下文；embedding 和 BM25 索引的是"前缀+原文"拼接，
  citation 展示只用原文（两列分开存）
- 图片：Gemini Vision 生成 caption，当文本 chunk 入库（caption-as-text）
- Embedding：gemini-embedding-001，MRL 截断到 768 维（pgvector HNSW 索引
  上限 2000 维，原生 3072 不行），实测截断后不归一化所以手动 L2 normalize
- 存储：Cloud SQL PostgreSQL 16 + pgvector 0.8.1，HNSW (m=16,
  ef_construction=64)，tsvector 是 GENERATED 生成列
- 检索：一条 SQL CTE 完成 hybrid——向量 top-40 + BM25(ts_rank_cd) top-40
  → RRF (k=60) 融合 → top-20；再用 Gemini Flash 当 LLM reranker 打分
  0-10 → top-5；解析失败回退 RRF 顺序
- DB 层：Pydantic + Repository + 原生 SQL（拒绝了 SQLAlchemy 和 Alembic，
  有书面 ADR）
- 评测：8 题人工金标集（keyword overlap + citation accuracy 两指标），
  Phase 2 实测 86.46% / 57.5%，cross_topic 和 figure bucket 从 0% 到 100%；
  端到端延迟 p50 约 19.6s，其中检索 SQL 只占 0.2s，大头在两次 LLM 调用
- 实测过的坑：章节正则在真书上命中 0（书签目录才是对的）；429 打爆
  RPM 配额（后来每个 LLM stage 都加了缓存+指数退避）；金标集的 book_id
  是契约，入库自创 id 导致 citation 全挂

我的背景：资深 Python 工程师，做过后端和数据，AI/LLM 属于进阶学习中。
用中文回答，专业术语保留英文。
```

---

## A. 学习型 Prompt（理解概念）

### A1. 万能三层讲解（把 X 换成任何概念）
```
请分三层讲解 X：
① 直觉层：给一个非 AI 工程师能懂的类比；
② 机制层：它内部具体怎么运作，关键参数/公式是什么；
③ 工程层：在我的项目里它具体出现在哪一步、我做了什么选择、
   如果不用它会发生什么。
最后出 1 道检验我是否真懂的问题，等我回答后再点评。
X = HNSW 索引
```
> 可替换的 X 清单：embedding / MRL 套娃截断 / cosine 相似度与 L2 归一化 /
> BM25 与 tsvector 的区别 / RRF / Contextual Retrieval / LLM reranker /
> cross-encoder / prompt caching / RAG 的 chunking / 生成列 GENERATED
> COLUMN / IAM 数据库认证 / SSE 流式响应

### A2. 数据的一生
```
以我项目里教科书第 26 章讲 Slipher 红移观测的某一段文字为例，
从 PDF 里的一段字，到最终出现在用户答案的引用里，
把它经历的每一次"变身"按顺序讲清楚（解析→分块→加前缀→向量化→入库→
被检索→被重排→进入 prompt→被引用）。每一步说明：它此刻长什么样、
哪个组件处理它、可能在这一步丢失什么信息。
```

### A3. 对比表生成器
```
用一张表对比 [A] 和 [B]，维度包括：原理、延迟、成本、可解释性、
适用场景、在我项目里选了哪个和为什么。表后面用 3 句话总结
"什么信号出现时应该从 A 切到 B"。
例：[向量检索] vs [BM25]；[LLM rerank] vs [cross-encoder] vs
[Voyage/Cohere rerank API]；[caption-as-text] vs [多模态 embedding] vs
[ColPali]；[pgvector] vs [专用向量库]；[RAG] vs [长上下文塞全书]
```

### A4. 为什么不是另一条路（决策钢人化）
```
针对我项目的这个决策：[填一个决策，如"用 Pydantic+Repository 而不是
SQLAlchemy"]，请先用最强的论证替"被拒绝的那个方案"辩护（steelman），
然后再给出支持我实际选择的论证，最后告诉我：在什么条件变化下，
被拒绝的方案会反过来变成正确答案。
```

### A5. 论文/技术溯源
```
我项目用了 Contextual Retrieval（Anthropic 2024）。请讲：它解决的核心
问题是什么（为什么切块会破坏检索）、方法本身、35%/49%/67% 三个数字
分别对应什么实验条件、prompt caching 为什么让它变便宜、
以及它和 late chunking、HyDE 这类同目标技术的区别。
```

## B. 训练型 Prompt（检验与输出）

### B1. 苏格拉底拷问模式
```
你是苏格拉底式导师。就 [主题，如"hybrid retrieval"] 向我连续提问，
每次只问一个问题，从基础到刁钻。我答对就加深一层，答错或含糊就
往下挖一层找到我的知识缺口，再用一个类比补上。10 个问题后给我
一份"已掌握 / 有缺口"清单。不要提前给答案。
```

### B2. 模拟技术面试官（压力版）
```
你是资深 ML 平台面试官，对我的 RAG 项目做 30 分钟深挖面试。规则：
① 从"介绍一下这个项目"开始；② 对我的每个回答至少追问一次，
专挑含糊和数字下手（比如"86% 是怎么算的？金标集才 8 题你敢信吗？"
"19.6 秒延迟用户能接受吗？"）；③ 我说完 [结束] 后，给我打分并列出
3 个我答得最弱的点和参考答案。开始吧。
```

### B3. 费曼模式（我讲你挑刺）
```
我现在用自己的话向你解释 [概念]。你扮演一个只有基础工程背景的听众，
在我讲完后：① 指出我哪里讲错了；② 哪里我用了术语但可能自己也没懂；
③ 哪里的类比有漏洞。然后让我重讲一遍修正版。
我的解释如下：[你的解释]
```

### B4. 每日闪卡
```
基于我的项目知识范围，出 8 张闪卡（问题在前，我说"翻面"你再给答案）。
覆盖：2 张概念定义、2 张数字/参数（如 RRF 的 k、HNSW 维度上限）、
2 张"为什么这么设计"、2 张排错场景（如"figure bucket 突然 0 分，
按什么顺序排查"）。
```

### B5. 一分钟电梯稿打磨
```
听我讲这个项目的 60 秒电梯稿，然后：① 掐表估算实际时长；
② 指出哪句是废话哪句缺数字；③ 给出修改版；④ 再给一个 30 秒
极限压缩版和一个 3 分钟展开版的提纲。
我的版本：[你的电梯稿]
```

## C. 拓展型 Prompt（超出项目边界）

### C1. 知识地图定位
```
画出 2026 年 RAG 技术栈的全景知识地图（分层列出：解析/分块/嵌入/索引/
检索/重排/生成/评测/运维），在每个节点标注：我的项目覆盖了没有、
用的什么方案、该层的工业界主流替代方案。最后指出我的知识版图上
最值得补的 3 块空白。
```

### C2. 新技术雷达
```
针对 [某个新技术/新模型名]，用我项目的语境评估：它替代的是我管线里
哪个组件？切换成本是什么？预期收益有多少、怎么测量？
如果是我，值得为它开一个 Phase 3 受控实验吗？
```

---

**维护提示**：项目有新的实测数字或新决策时，回来更新〔背景卡〕——
它是所有 prompt 的地基。
