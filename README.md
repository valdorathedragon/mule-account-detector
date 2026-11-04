# Mule-Account-Detector

### 🛠️ Active Development Status

<p align="left">
  <img src="https://geps.dev/progress/10?dangerColor=ff4b4b&warningColor=ffa500&happyColor=00e676" alt="Progress Bar" width="600" />
</p>

[██░░░░░░░░░░░░░░░░░░░░░░░░░░] 10%


| Component | Status | Progress |
| :--- | :--- | :--- |
| 📋 System Architecture & Data Schema | 🟨 In Progress | 50% |
| 📊 Anomaly Feature Engineering (Velocity/Amount) | ⬜ Pending | 0% |
| 🤖 Agentic Scoring Model | ⬜ Pending | 0% |
| 🚀 Prototype Demo | ⬜ Pending | 0% |

### ⚡Tech Architecture Overview

   ┌──────────────────────────────┐
   │   Transaction Stream Data    │
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌──────────────────────────────┐
   │ Statistical Anomaly Filter   │
   │   (Pandas / Scikit-Learn)    │
   └──────────────┬───────────────┘
                  │
          [Flagged Anomalies]
                  │
                  ▼
   ┌──────────────────────────────┐
   │     AI Reasoning Engine      │
   │   (Context & Threat Scoring) │
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌──────────────────────────────┐
   │   High-Risk Mule Account     │
   │    Alert & Report Pipeline   │
   └──────────────────────────────┘

   ### 🧰 Core Tech & Tooling Stack

<p align="left">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" />
  <img src="https://img.shields.io/badge/Scikit--Learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
</p>

