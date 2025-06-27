# Project Argus: 天枢计划

## 系统架构设计 (V2.0 - 整合版)

### 1. 核心架构理念

本架构是前两个版本的演进与融合，旨在构建一个**工业级、高韧性、可演进**的数据平台。其核心设计理念升级为：

1.  **事件驱动与彻底解耦 (Event-Driven & Fully Decoupled):** 引入**Apache Kafka**作为系统的中央神经系统。采集与处理被彻底解耦，数据以事件流的形式在系统内传递。这提供了极致的弹性、削峰填谷能力以及未来向实时处理演进的通路。
2.  **声明式控制与动态配置 (Declarative Control & Dynamic Configuration):** 系统的行为（如数据源优先级、融合规则）不再硬编码于代码中，而是由**Airflow (控制平面)**进行声明式调度，并从**外部配置中心**动态加载。这使得系统调整更加敏捷和安全。
3.  **事务性数据湖仓 (Transactional Data Lakehouse):** Gold层存储采用**Delta Lake**格式。这在Parquet的性能之上，增加了**ACID事务、数据版本控制（时间旅行）和Schema强制**等关键能力，从根本上解决了数据一致性与质量问题，防止数据湖沦为“数据沼泽”。
4.  **智能质量门禁 (Intelligent Quality Gates):** 质量保障不再是简单的规则检查，而是升级为**质量决策引擎**。它结合`Great Expectations`的验证结果和动态阈值，能做出更智能的决策（通过、告警、自动修复或转入人工审核）。
5.  **统一接入与安全 (Unified Ingress & Security):** 所有外部数据源的访问都通过一个**API网关**进行，统一负责认证、授权、限流和路由，构成了系统的安全边界。

#### 2. 整合版系统架构图

```mermaid
graph TD
    subgraph "数据平面 (Data Plane)"
        %% Data Sources
        subgraph "A. 数据源 (Sources)"
            DS1[fa:fas fa-server miniQMT]
            DS2[fa:fas fa-cloud Tushare Pro]
        end

        %% Ingestion
        subgraph "B. 统一接入与采集 (Ingestion)"
            GW[fa:fas fa-door-open API Gateway]
            DC[fa:fas fa-satellite-dish 智能数据采集器]
        end

        %% Buffering
        subgraph "C. 消息总线 (Message Bus)"
            KAFKA["fa:fas fa-stream Kafka<br><i>raw_data_topic</i>"]
        end

        %% Processing
        subgraph "D. 数据处理引擎 (Processing Engine)"
            BP["Bronze Processor<br><i>格式化/标准化</i>"]
            SP["Silver Processor<br><i>融合/清洗/填补</i>"]
            GP["Gold Publisher<br><i>发布到Delta Lake</i>"]
        end

        %% Storage
        subgraph "E. 事务性数据湖仓 (Transactional Lakehouse)"
            DL["fa:fas fa-gem Delta Lake<br><i>Gold Layer</i>"]
            PART["fa:fas fa-folder-tree Partitioned Storage<br><i>/gold/date=.../symbol=...</i>"]
        end

        %% Consumption
        subgraph "F. 数据消费 (Consumption)"
            NT[fa:fas fa-robot NautilusTrader]
        end
    end

    subgraph "控制平面 (Control Plane)"
        AIRFLOW[fa:fas fa-cogs Apache Airflow]
        CONFIG[fa:fas fa-cog 配置中心]
        ALERT[fa:fas fa-bell Alertmanager]
        USER[fa:fas fa-user-tie Data Analyst/Operator]
    end

    subgraph "质量与监控平面 (Quality & Observability Plane)"
        QDE[fa:fas fa-balance-scale 质量决策引擎]
        GE[fa:fas fa-check-square Great Expectations]
        PROM[fa:fas fa-chart-line Prometheus]
        GRA[fa:fas fa-tachometer-alt Grafana]
        ELK[fa:fas fa-search ELK Stack]
    end

    %% Data Flow
    DS1 --> GW
    DS2 --> GW
    GW --> DC
    DC --> KAFKA
    KAFKA --> BP
    BP --> SP
    SP --> QDE
    QDE -- "✅ 通过" --> GP
    GP --> DL
    DL --> PART
    PART --> NT

    %% Control Flow
    CONFIG -- "提供规则" --> DC
    CONFIG -- "提供规则" --> SP
    CONFIG -- "提供规则" --> QDE
    AIRFLOW -- "1. 调度采集" --> DC
    AIRFLOW -- "3. 调度处理" --> BP
    QDE -- "❌ 失败" --> ALERT
    ALERT -- "告警" --> USER
    ALERT -- "触发修复" --> AIRFLOW

    %% Quality & Observability Flow
    SP -- "2. 待验数据" --> GE
    GE -- "验证结果" --> QDE
    DC -- "指标/日志" --> PROM
    DC -- "指标/日志" --> ELK
    BP -- "指标/日志" --> PROM
    BP -- "指标/日志" --> ELK
    SP -- "指标/日志" --> PROM
    SP -- "指标/日志" --> ELK
    GE -- "质量指标" --> PROM
    PROM -- "数据源" --> GRA
    ELK -- "数据源" --> GRA
    GRA -- "看板" --> USER

    %% Styling
    classDef dataPlane fill:#e6f3ff,stroke:#367dcc,stroke-width:1px,color:#000
    classDef controlPlane fill:#f5e6ff,stroke:#8e44ad,stroke-width:1px,color:#000
    classDef qualityPlane fill:#e6ffe6,stroke:#27ae60,stroke-width:1px,color:#000
    class A,B,C,D,E,F dataPlane
    class AIRFLOW,CONFIG,ALERT,USER controlPlane
    class QDE,GE,PROM,GRA,ELK qualityPlane
```

#### 3. 核心组件详解

*   **A. 数据源 (Sources):**
    *   `miniQMT` 和 `Tushare Pro`：职责不变，分别为主要行情源和补充/备份源。

*   **B. 统一接入与采集 (Ingestion):**
    *   **API Gateway:** **[整合点]** 作为所有数据流入的唯一入口，负责统一的认证、限流、熔断降级（如Tushare API错误率超阈值时）和请求路由。
    *   **智能数据采集器 (Data Collector):** 由Airflow调度，从`配置中心`读取数据源优先级和采集策略。它向`API Gateway`发起请求，并将采集到的原始数据作为事件发送到`Kafka`。**[对应需求: FR-001, FR-002, BR-004]**

*   **C. 消息总线 (Message Bus):**
    *   **Apache Kafka:** **[核心整合点]** 系统的“解耦层”和“缓冲池”。原始数据被发布到`raw_data_topic`。这带来了巨大好处：
        1.  **弹性与韧性:** 即使下游处理引擎宕机，数据采集也不会中断，数据被安全地保留在Kafka中。
        2.  **背压处理:** 自动处理上下游速率不匹配的问题。
        3.  **可扩展性:** 未来可以轻松增加新的消费者（如实时异常检测）来消费同一份原始数据，而无需改动采集器。

*   **D. 数据处理引擎 (Processing Engine):**
    *   这是一组由Airflow协调的、消费Kafka消息的批处理任务（可实现为`Spark Structured Streaming`或`KubernetesPodOperator`）。
    *   **Bronze Processor:** 消费`raw_data_topic`，进行格式统一、Schema验证和基础清洗，然后将结果输出到内部的`cleaned_topic`（或直接在内存中传递给下一步）。
    *   **Silver Processor:** 核心处理单元。从`配置中心`获取融合规则，执行时间轴对齐、多源冲突解决、以及使用ML模型（如Prophet）进行智能缺失值填补。**[对应需求: FR-003 to FR-006]**

*   **E. 事务性数据湖仓 (Transactional Lakehouse):**
    *   **Delta Lake:** **[核心整合点]** 最终的Gold层存储格式。它在Parquet之上提供了：
        *   **ACID事务:** 保证数据写入的原子性，杜绝了不完整或脏数据。
        *   **时间旅行:** 可查询任意历史版本的数据，便于审计、回滚和复现问题。
        *   **Schema强制与演进:** 防止脏数据写入，并支持平滑地增加字段。
    *   **分区存储:** 采用更优化的分区策略 `/gold/date=YYYYMMDD/symbol=STOCKCODE`，极大提升按股票查询的性能。**[对应需求: BR-001, FR-011, TR-004]**

*   **F. 数据消费 (Consumption):**
    *   `NautilusTrader`直接高效地读取分区化的Delta Lake/Parquet文件。

#### 4. 平面化管理与监控

*   **控制平面 (Control Plane):**
    *   **Apache Airflow:** 职责不变，但其任务（Task）更倾向于编排容器化作业（如`KubernetesPodOperator`），而非直接执行Python代码，实现更好的资源隔离。
    *   **配置中心 (Configuration Center):** **[整合点]** 如Consul或Nacos。集中存储数据源优先级、融合逻辑、质量规则阈值等，实现配置与代码分离，支持动态热更新。
    *   **Alertmanager:** 负责告警的路由、去重和抑制，根据策略将告警分发给不同的人或系统。

*   **质量与监控平面 (Quality & Observability Plane):**
    *   **Great Expectations (GE):** 作为规则库，被`质量决策引擎`调用。
    *   **质量决策引擎 (Quality Decision Engine):** **[整合点]** 这是GE的智能“上层”。它执行GE的规则集，并结合从`配置中心`获取的动态阈值（例如，市场波动大时放宽某些检查），最终决定数据是`通过`进入Gold层，还是`失败`触发告警和修复流程。**[对应需求: FR-007, BR-003]**
    *   **Prometheus, Grafana, ELK:** 职责不变，构成全面的可观测性技术栈，监控从API网关到数据消费的全链路指标、日志和数据质量。**[对应需求: NFR-001 to NFR-008]**

#### 5. 关键技术决策与优势

1.  **Kafka vs. Direct Processing:** 选择Kafka引入了轻微的延迟和运维成本，但换来了无与伦比的系统弹性和可扩展性，这是工业级系统的标志。
2.  **Delta Lake vs. Raw Parquet:** 选择Delta Lake增加了对Spark/Delta库的依赖，但彻底解决了批处理ETL中常见的数据一致性和可靠性难题，极大提升了Gold层数据的“黄金”成色。
3.  **Config Center vs. Hardcoding:** 采用配置中心使得系统更加灵活，运维人员或数据分析师可以在不重新部署代码的情况下调整数据处理逻辑，大大缩短了响应时间。
