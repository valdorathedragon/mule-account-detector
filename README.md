# Mule-Account-Detector

### 🛠️ Active Development Status

<p align="left">
  <img src="https://geps.dev/progress/10?dangerColor=ff4b4b&warningColor=ffa500&happyColor=00e676" alt="Progress Bar" width="600" />
</p>


| Component | Status | Progress |
| :--- | :--- | :--- |
| 📋 System Architecture & Data Schema | 🟨 In Progress | 50% |
| 📊 Anomaly Feature Engineering (Velocity/Amount) | ⬜ Pending | 0% |
| 🤖 Agentic Scoring Model | ⬜ Pending | 0% |
| 🚀 Prototype Demo | ⬜ Pending | 0% |

### ⚡ Tech Architecture Overview

```mermaid
graph TD
    A[💳 Transaction Stream Data] -->|Real-time Ingestion| B[📊 Statistical Anomaly Filter<br/>Pandas / Scikit-Learn]
    B -->|Flagged Anomalies| C[🤖 AI Reasoning Engine<br/>Context & Threat Scoring]
    C -->|High-Risk Detection| D[🚨 High-Risk Mule Account<br/>Alert & Report Pipeline]

    style A fill:#1f2937,stroke:#61afef,stroke-width:2px,color:#fff
    style B fill:#1f2937,stroke:#e5c07b,stroke-width:2px,color:#fff
    style C fill:#1f2937,stroke:#98c379,stroke-width:2px,color:#fff
    style D fill:#1f2937,stroke:#e06c75,stroke-width:2px,color:#fff

   ### 🧰 Core Tech & Tooling Stack

<p align="left">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" />
  <img src="https://img.shields.io/badge/Scikit--Learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
</p>

