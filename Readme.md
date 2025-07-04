# Project Argus: 天枢计划

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-95%25-green)
![Data Quality Score](https://img.shields.io/badge/Quality%20Score-99.85-blueviolet)
![License](https://img.shields.io/badge/License-MIT-blue)
![System Availability](https://img.shields.io/badge/Availability-99.9%25-informational)

**天枢 (Tiānshū)** 是北斗七星之首，自古便是定位和导航的核心。这寓意着本项目是整个量化交易体系的**核心枢纽 (Central Hub)**，为所有策略提供稳定、可靠、可信的方向指引和数据基石。

**Argus** 在希腊神话中是拥有百眼的巨人，一个完美的守望者。这完美契合了项目全链路、多维度、自动化的质量监控体系 **(Observability)**，象征着系统拥有无数双眼睛，时刻守护着数据质量。

本项目旨在构建一个工业级、全自动、高韧性的A股数据管道系统，通过智能融合多源数据（miniQMT, Tushare Pro），为 **NautilusTrader** 量化交易系统提供可信赖的“黄金标准”数据。

## ✨ 核心特性 (Core Features)

*   **事件驱动与彻底解耦 (Event-Driven & Decoupled):** 以 **Apache Kafka** 为中央神经系统，实现极致的系统弹性和可扩展性。
*   **事务性数据湖仓 (Transactional Data Lakehouse):** 采用 **Delta Lake** 存储Gold层数据，提供ACID事务、时间旅行和Schema强制，从根本上保障数据一致性。
*   **智能多源融合 (Intelligent Multi-Source Fusion):** 遵循明确的治理规则，以miniQMT为主、Tushare为辅，智能融合行情、财务、公司行动等多维度数据，并提供完整的数据血缘。
*   **内建质量保障 (Quality Built-in):** 贯穿全链路的**五级质量监控架构**和**智能质量决策引擎 (QDE)**，由 **Great Expectations** 提供超过128条自动化规则支撑。
*   **全链路可观测性 (Comprehensive Observability):** 基于 **Prometheus, Grafana, ELK** 技术栈，提供覆盖数据源、管道、存储到应用的全方位监控与告警。
*   **自动化与高韧性 (Automation & High-Resilience):** 由 **Airflow** 实现自动化调度，具备Tushare配额熔断、自动故障转移等工业级韧性。

## 🏛️ 系统架构 (System Architecture)

本系统采用分层解耦的现代化数据平台架构，分为**数据平面**、**控制平面**和**质量与监控平面**，确保了系统的高内聚、低耦合和清晰的职责划分。

```mermaid
graph TD
    subgraph "Windows 环境 (Windows Environment)"
        direction LR
        WIN_QMT["miniQMT Client"]
        WIN_AGENT["Windows QMT Data Agent - Python HTTP Service"]
        WIN_QMT --> WIN_AGENT
    end

    subgraph "Docker 环境 (Docker Environment - Project Argus Core)"
        subgraph "数据平面 (Data Plane)"
            subgraph "A. 数据源 (Sources)"
                DS_AGENT["QMT Data via Agent"]
                style DS_AGENT fill:#D2B4DE,stroke:#8E44AD
                DS2["Tushare Pro"]
            end

            subgraph "B. 统一接入与采集 (Ingestion)"
                DC["智能数据采集器 (qmt_collector.py calls Agent)"]
            end

            subgraph "C. 消息总线 (Message Bus)"
                KAFKA["Kafka - raw_data_topic"]
            end

            subgraph "D. 数据处理引擎 (Processing Engine)"
                BP["Bronze Processor - 格式化/标准化"]
                SP["Silver Processor - 融合/清洗/填补"]
                GP["Gold Publisher - 发布到 Delta Lake"]
            end

            subgraph "E. 事务性数据湖仓 (Transactional Lakehouse)"
                DL["Delta Lake - Gold Layer"]
                PART["Partitioned Storage - /gold/date=.../symbol=..."]
            end

            subgraph "F. 数据消费 (Consumption)"
                NT["NautilusTrader"]
            end
        end

        subgraph "控制平面 (Control Plane)"
            AIRFLOW["Apache Airflow"]
            CONFIG["配置中心"]
            ALERT["Alertmanager"]
            USER["Data Analyst / Operator"]
        end

        subgraph "质量与监控平面 (Quality & Observability Plane)"
            QDE["质量决策引擎"]
            GE["Great Expectations"]
            PROM["Prometheus"]
            GRA["Grafana"]
            ELK["ELK Stack"]
        end
    end

    %% Data Flow
    WIN_AGENT -->|HTTP Request/Response| DC
    DS2 --> DC
    DC --> KAFKA
    KAFKA --> BP
    BP --> SP
    SP --> QDE
    QDE -->|Pass| GP
    GP --> DL
    DL --> PART
    PART --> NT

    %% Control Flow
    AIRFLOW -->|调度| DC
    AIRFLOW -->|调度| BP
    CONFIG -->|提供规则| DC
    CONFIG -->|提供规则| SP
    CONFIG -->|提供规则| QDE
    CONFIG -->|Agent URL| DC
    QDE -->|Fail| ALERT
    ALERT -->|告警| USER

    %% Quality & Observability Flow
    SP -->|待验数据| GE
    GE -->|验证结果| QDE
    DC --> PROM
    DC --> ELK
    BP --> PROM
    BP --> ELK
    SP --> PROM
    SP --> ELK
    GE --> PROM
    GE --> ELK
    WIN_AGENT -->|Logs & Metrics| ELK
    WIN_AGENT -->|Logs & Metrics| PROM
    PROM --> GRA
    ELK --> GRA
    GRA -->|看板| USER

    %% Styling
    class WIN_QMT,WIN_AGENT fill:#EAEFF3,stroke:#5D6D7E

```

## 🛠️ 技术栈 (Technology Stack)

| 类别 | 技术 | 描述 |
| :--- | :--- | :--- |
| **部署与运行** | `Docker`, `Docker Compose` | 通过容器化实现环境一致性，支持一键部署和管理。 |
| **Windows数据代理** | `Python (http.server)`, `xtquantai` ( leveraging `server_direct.py`) | 在Windows上运行，提供对本地miniQMT的HTTP访问接口。其原始项目 `xtquantai` 还支持MCP协议，可用于AI集成。 |
| **数据湖仓** | `Delta Lake`, `Apache Parquet` | 提供事务性、高性能的列式存储。 |
| **消息总线** | `Apache Kafka` | 作为事件驱动核心，解耦系统各组件。 |
| **工作流调度** | `Apache Airflow` | 自动化、可编程的工作流调度与监控。 |
| **数据质量** | `Great Expectations` | 声明式的数据质量断言、文档生成和报告。 |
| **数据处理** | `Python 3.12`, `uv`, `Pandas`, `PyArrow`, `Prophet` | 高效的数据清洗、转换、融合与预测。 `uv` 用于包管理。 |
| **监控与告警** | `Prometheus`, `Grafana`, `Alertmanager`, `ELK` | 全链路的指标采集、可视化、告警和日志管理。 |
| **安全与配置**| `Docker Secrets`, `.env files`, `Consul` | 安全的凭证管理与动态的外部配置中心。 |

## ⚖️ 数据治理与质量 (Data Governance & Quality)

我们坚信**数据质量是量化交易的生命线**。Project Argus 将“质量内建”原则贯穿于数据生命周期的每个环节。

### 核心治理原则
1.  **数据源优先级原则 (Source Priority):`miniQMT` 为行情主源，`Tushare` 为补充和备份源。
2.  **黄金标准层原则 (Golden Record):** 只有 `Gold` 层数据对外发布，严禁消费中间层。
3.  **完整数据血缘原则 (Data Lineage):** 所有融合字段必须记录其来源 (`_source`)。
4.  **质量内建原则 (Quality Built-in):** 每个字段都关联明确的质量校验规则。
5.  **Schema不可变与演进原则 (Schema Immutability):** Schema变更受严格的版本控制。

### 部署模型 (Docker Compose)
系统所有服务均被容器化，并通过`docker-compose.yml`进行编排，实现了开发的便捷性和部署的一致性。

```mermaid
graph LR
    subgraph Docker Host
        subgraph "Docker Compose Services"
            A["Airflow<br>(Scheduler, Webserver)"]
            C["Data Collector<br>(as Airflow Task)"]
            P["Data Processor<br>(as Airflow Task)"]
            K[Kafka & Zookeeper]
            R["Redis<br>(Quota Manager)"]
            M["Monitoring Stack<br>(Prometheus, Grafana)"]
            S["Storage<br>(MinIO for Delta Lake)"]
        end
    end
    
    A -- "Schedules" --> C
    A -- "Schedules" --> P
    C -- "Raw Data" --> K
    K -- "Raw Data" --> P
    P -- "Fused Data" --> S
    C & P -- "Use" --> R
    subgraph Internet
        DS1[miniQMT]
        DS2[Tushare Pro]
    end
    C --> DS1 & DS2
```

## 🚀 快速开始 (Quick Start)

### 先决条件
*   Python 3.12 (for Project Argus core)
*   [uv](https://github.com/astral-sh/uv) (Python package manager)
*   [Docker](https://www.docker.com/get-started)
*   [Docker Compose](https://docs.docker.com/compose/install/)
*   **Windows QMT Data Agent 已成功部署和运行:**
    *   Project Argus 通过HTTP(S)依赖一个独立部署的 `Windows QMT Data Agent` 服务来接入 miniQMT 数据。
    *   请参照 `project-argus-qmt-agent` 项目的文档进行安装、配置和启动：[https://github.com/jiaenyue/project-argus-qmt-agent](https://github.com/jiaenyue/project-argus-qmt-agent)
    *   确保该Agent服务正在运行，并且Project Argus环境可以网络访问到它。
*   (可选，未来AI集成) 如果您计划探索 `xtquantai` 的MCP特性，可能需要Node.js 和 npx (请参考`project-argus-qmt-agent`或`xtquantai`的文档)。

### Windows QMT Data Agent Setup

`Windows QMT Data Agent` 是一个独立的项目，负责提供对 Windows 端 miniQMT 服务的HTTP访问接口。Project Argus 的数据采集器 (`qmt_collector.py`) 将通过网络调用此代理服务。

**请访问并遵循其专用仓库中的说明进行设置和启动：**
➡️ **[https://github.com/jiaenyue/project-argus-qmt-agent](https://github.com/jiaenyue/project-argus-qmt-agent)**

该仓库的 `README.md` 包含了详细的安装、配置（包括通过环境变量 `QMT_DATA_AGENT_PORT` 设置端口）、运行说明以及如何将其注册为Windows服务以实现持久化运行。

**Project Argus 与 Agent 的交互:**

*   Project Argus 的 `qmt_collector.py` 通过配置的环境变量 `QMT_DATA_AGENT_HOST` 和 `QMT_DATA_AGENT_PORT` 来定位并连接到已运行的 `Windows QMT Data Agent` 实例。
*   `Windows QMT Data Agent` 项目本身基于 `xtquantai`，也保留了其作为MCP服务器的潜力，可供未来AI集成探索。

### 本地开发环境设置 (Project Argus Core - 无 Docker)

如果您希望在本地（非 Dockerized）环境中运行或开发 Project Argus 核心组件（例如，测试`qmt_collector.py`与已运行的`Windows QMT Data Agent`的通信），可以按以下步骤操作：

1.  **克隆仓库**
    ```bash
    git clone https://github.com/your-org/project-argus.git
    cd project-argus
    ```

2.  **安装 uv**
    如果尚未安装 `uv`, 请参照其[官方文档](https://github.com/astral-sh/uv)进行安装。例如：
    ```bash
    # Piped install (macOS, Linux)
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Or using pip (if you have a global Python with pip)
    # pip install uv
    ```

3.  **创建并激活虚拟环境 (使用 uv)**
    ```bash
    uv venv .venv  # 创建虚拟环境到 .venv 目录
    source .venv/bin/activate  # 激活 (Linux/macOS)
    # .venv\Scripts\activate  # 激活 (Windows)
    ```
    项目使用 Python 3.12。请确保您的 `uv` 配置或系统 Python 指向 3.12 版本，或者在创建虚拟环境时指定：
    ```bash
    uv venv .venv -p 3.12
    ```

4.  **安装依赖 (使用 uv)**
    ```bash
    uv pip install -r requirements.txt
    ```
    或者，如果您的 `uv` 版本支持直接从 `pyproject.toml` 安装：
    ```bash
    # uv pip install .  # This would install the project and its dependencies
    ```
    **注意**: `xtquant` 库是 miniQMT 的一部分，通常需要从 QMT 客户端的安装目录中获取或通过特定方式安装到您的 Python 环境中。它不会通过 `requirements.txt` 从 PyPI 安装。确保 `xtquant` 在您的 Python 环境中可用才能运行数据采集脚本。

5.  **配置环境变量**
    复制示例环境文件，并填入您的 API Token 等敏感信息。
    ```bash
    cp .env.example .env
    # 编辑 .env 文件，例如:
    # TUSHARE_TOKEN=your_tushare_pro_api_token
    # QMT_CLIENT_PATH=/path/to/your/qmt/installation (if needed by scripts)
    ```

6.  **运行特定脚本 (示例)**
    此时，您可以直接运行项目中的 Python 脚本，例如测试数据采集器：
    ```bash
    python src/collectors/qmt_collector.py
    ```

### Dockerized 系统启动 (完整系统)

对于完整的系统部署（包括 Airflow, Kafka, MinIO 等），请遵循以下 Docker Compose 流程：

1.  **克隆仓库** (如果尚未操作)
    ```bash
    git clone https://github.com/your-org/project-argus.git
    cd project-argus
    ```

2.  **配置环境变量** (同上, 主要是 `.env` 文件中的 `TUSHARE_TOKEN`)
    ```bash
    cp .env.example .env
    # 编辑 .env 文件
    ```
    Docker Compose 构建过程将使用 `requirements.txt` (通过 `uv` 安装) 和 Python 3.12 基础镜像。

3.  **启动系统**
    使用 Docker Compose 一键启动所有服务。
    ```bash
    docker-compose up -d
    ```

4.  **访问服务**
    *   **Airflow UI:** `http://localhost:8080` (用于查看和管理DAGs)
    *   **Grafana:** `http://localhost:3000` (用于查看数据质量和系统监控看板)
    *   **MinIO Console:** `http://localhost:9001` (用于浏览Delta Lake数据)

## 📚 项目文档 (Project Documentation)

本项目采用全面的文档驱动开发模式。所有核心设计、规范和计划都有详细的文档支持，它们是理解本项目细节的**单一可信源 (Single Source of Truth)**。

| 文档名称 | 描述 |
| :--- | :--- |
| [`system_design.md`](./doc/system_design.md) | **系统架构设计**：描述了系统的核心架构理念、组件和数据流。 |
| [`data_governance_and_dictionary.md`](./doc/data_governance_and_dictionary.md) | **数据治理规范与字典**：定义了数据治理原则和Gold层数据字典。 |
| [`quality_kpi.md`](./doc/quality_kpi.md) | **数据质量体系设计**：定义了质量KPI、评分模型和分层质量门禁。 |
| [`tushare_pro_integration_design.md`](./doc/tushare_pro_integration_design.md) | **Tushare集成设计**：详细阐述了Tushare的接入、配额管理和容灾设计。 |
| [`plan.md`](./doc/plan.md) | **项目计划书**：包含了项目的实施计划、里程碑和资源安排。 |
| [`requirements_traceability_matrix.md`](./doc/requirements_traceability_matrix.md) | **需求追溯矩阵**：将所有需求与设计、开发、测试任务关联。 |
| [`user_story.md`](./doc/user_story.md) | **用户故事全集**：从不同角色视角描述了项目的功能和价值。 |
| [`backlog.md`](./doc/backlog.md) | **项目待办事项看板**：以看板形式可视化了详细的开发任务和依赖。 |
| [`risk_register.md`](./doc/risk_register.md) | **风险登记册**：全面识别、评估并规划了项目中的所有潜在风险。 |
| [`xtdata.md`](./doc/api/xtdata.md) | **行情数据API文档**：miniQMT行情数据模块接口说明（历史/实时K线、分笔、财务数据等） |
| [`xttrader.md`](./doc/api/xttrader.md) | **交易模块API文档**：miniQMT交易模块接口说明（下单、撤单、持仓管理等） |

## 🤝 贡献指南 (Contributing)

我们欢迎任何形式的贡献！如果您想为 Project Argus 做出贡献，请遵循以下步骤：

1.  Fork 本仓库。
2.  创建一个新的功能分支 (`git checkout -b feature/your-feature-name`)。
3.  提交您的更改 (`git commit -am 'Add some feature'`)。
4.  将分支推送到您的Fork (`git push origin feature/your-feature-name`)。
5.  创建一个新的 Pull Request。

请确保您的代码遵循现有的编码风格，并通过所有测试。

## 📜 许可证 (License)

本项目采用 [MIT License](./LICENSE) 授权。
