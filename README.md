<p align="center">
  <a href="https://anamnesis-agent.onrender.com/" target="_blank">
    <img src="docs/screenshots/logo.svg" alt="Anamnesis Logo" width="110" />
  </a>
</p>

<h1 align="center">🔺 A N A M N E S I S</h1>

<p align="center">
  <b>A Persistent Memory Layer for AI Data Agents on DataHub</b>
  <br />
  <i>Empowering AI Agents to Recall, Inherit, and Resolve Pipeline Failures Forever.</i>
</p>

<p align="center">
  <a href="https://anamnesis-agent.onrender.com/" target="_blank">
    <img src="https://img.shields.io/badge/🚀_LIVE_DEMO-Anamnesis_App-00E5FF?style=for-the-badge&logo=render&logoColor=white" alt="Live Demo" />
  </a>
  <a href="https://github.com/AmitK241/Anamnesis" target="_blank">
    <img src="https://img.shields.io/badge/GitHub_Repo-AmitK241-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub" />
  </a>
  <a href="https://www.linkedin.com/in/amit-kumar-3a602a289" target="_blank">
    <img src="https://img.shields.io/badge/LinkedIn-Amit_Kumar-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Apache_2.0-00D2FF?style=flat-square&logo=apache&logoColor=white" alt="License" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/DataHub-Agent_Hackathon_2026-7000FF?style=flat-square" alt="Hackathon" />
</p>

---

## ⚡ Quick Links & Live Application

> 🌐 **Live Web Application:** [https://anamnesis-agent.onrender.com/](https://anamnesis-agent.onrender.com/)  
> 📂 **Source Repository:** [https://github.com/AmitK241/Anamnesis](https://github.com/AmitK241/Anamnesis)  
> 💼 **Developer Profile:** [Amit Kumar on LinkedIn](https://www.linkedin.com/in/amit-kumar-3a602a289)

---

## 🎯 Executive Summary

Every data team has felt this: a schema breaks, an engineer spends hours tracing the root cause through lineage, writes a fix — and that knowledge dies with that conversation. Months later, a different engineer hits the same class of problem and starts from zero again.

**Anamnesis** provides a **persistent memory graph** for AI data agents built on top of **DataHub**. Instead of evaluating schema breakages in isolation, agents equipped with Anamnesis retain, search, and inherit institutional resolution knowledge across execution runs.

---

## 📸 Product Visual Showcase

<table>
  <tr>
    <td width="50%">
      <h3 align="center">1. Hero Dashboard & Overview</h3>
      <a href="docs/screenshots/dashboard-overview.png"><img src="docs/screenshots/dashboard-overview.png" alt="Dashboard" /></a>
      <p align="center"><i>Real-time metrics tracking persistent memory objects, contract anomalies, and active DataHub connections.</i></p>
    </td>
    <td width="50%">
      <h3 align="center">2. 3D Memory Constellation</h3>
      <a href="docs/screenshots/memory-constellation.png"><img src="docs/screenshots/memory-constellation.png" alt="Constellation Graph" /></a>
      <p align="center"><i>Interactive Three.js visualizer rendering resolved incident vectors connected by similarity edges.</i></p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3 align="center">3. High-Confidence Vector Recall</h3>
      <a href="docs/screenshots/recall-match.png"><img src="docs/screenshots/recall-match.png" alt="Recall Match" /></a>
      <p align="center"><i>Vector similarity search recalling past resolution patterns (e.g. 97.2% Match Score).</i></p>
    </td>
    <td width="50%">
      <h3 align="center">4. 5-Stage Full Loop Tracker</h3>
      <a href="docs/screenshots/pipeline-flow.png"><img src="docs/screenshots/pipeline-flow.png" alt="Pipeline Flow" /></a>
      <p align="center"><i>End-to-end automated governance: Detect ➔ Diagnose ➔ Recall ➔ Fix ➔ Write.</i></p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3 align="center">5. Persistent Knowledge Base</h3>
      <a href="docs/screenshots/memory-list.png"><img src="docs/screenshots/memory-list.png" alt="Memory Store" /></a>
      <p align="center"><i>Stored incident fixes, dbt patches, fault localizations, and verified execution logs.</i></p>
    </td>
    <td width="50%">
      <h3 align="center">6. Severity & Risk Analytics</h3>
      <a href="docs/screenshots/severity-breakdown.png"><img src="docs/screenshots/severity-breakdown.png" alt="Severity Analytics" /></a>
      <p align="center"><i>Automatic classification of contract anomalies (Critical, Medium, Info) by lineage blast radius.</i></p>
    </td>
  </tr>
</table>

<br />

<div align="center">
  <h3>7. Problem Statement & System Architecture</h3>
  <a href="docs/screenshots/about-page.png"><img src="docs/screenshots/about-page.png" alt="About Architecture" width="85%" /></a>
  <p><i>Architectural concept solving AI agent amnesia by embedding resolution vectors directly into DataHub.</i></p>
</div>

---

## ✨ Key Features

* 🧠 **Persistent Agent Memory:** Stores resolved schema mutations, column casts, and contract breaches as reusable vector objects.
* 🌌 **3D Constellation Graph:** Interactive network visualizer displaying similarity clusters between new anomalies and historical fixes.
* 🔍 **Schema Mutation Detector:** Instant inspection of DataHub dataset URNs to detect breaking mutations and type shifts.
* 🎯 **Automated Fault Localization:** Traces root causes across lineage graphs and generates verified SQL/dbt patch scripts.
* ⚡ **Ultra-Fast & Resilient Runtime:** Cloud-optimized architecture (<100MB RAM footprint) with seamless fallback data resilience.

---

## 🏗️ System Architecture

```text
┌──────────────────────────┐      ┌───────────────────────────┐      ┌───────────────────────────┐
│   DataHub Metadata MCP   │ ───► │   Anamnesis Engine        │ ───► │  3D Constellation Graph   │
│   (Dataset URN / Lineage)│      │   (Recall & Diagnosis)    │      │  (Interactive Vector UI)  │
└──────────────────────────┘      └───────────────────────────┘      └───────────────────────────┘
                                                │
                                                ▼
                                 ┌───────────────────────────┐
                                 │ Persistent Memory Graph   │
                                 │ (Vectorized Incident Store│
                                 └───────────────────────────┘
