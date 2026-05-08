# System Design: Enterprise-Grade Multimodal RAG Knowledge Engine

---

## 1. Executive Summary
This project aims to design and implement a production-ready **Retrieval-Augmented Generation (RAG)** system on Google Cloud. It addresses the common "hallucination" problem of LLMs by grounding responses in private, verified enterprise documents (PDFs containing text, tables, and complex architecture diagrams).

## 2. Problem Statement
Standard LLMs often lack context regarding specific enterprise architectures and private documentation. Furthermore, traditional RAG systems struggle with **Multimodal data** (e.g., understanding a VPC peering diagram within a PDF). This project provides a secure, scalable, and multi-modal solution.

---

## 3. Requirements Specification

### 3.1 Functional Requirements (FR)
- **Multimodal Understanding**: Must extract and reason over text and visual elements (diagrams/charts) in PDFs.
- **Contextual Retrieval**: High-precision semantic search using Vector Embeddings.
- **Citations & Grounding**: Every response must link back to the source document and specific page number.
- **Interactive Interface**: A responsive web UI for users to query the knowledge base and view source snippets.

### 3.2 Non-Functional Requirements (NFR)
- **Security (The PCA Standard)**:
    - **Identity-Centric**: Use Service Accounts with Least Privilege.
    - **Network Security**: Simulate **VPC Service Controls (VPC SC)** to prevent data exfiltration.
    - **Edge Defense**: Use **Cloud Armor** to protect the frontend.
- **Scalability**: Fully serverless architecture (Cloud Run) that scales to zero when idle.
- **Cost Efficiency**: Utilize **Gemini 1.5 Flash** for routine queries and **Pro** for complex multimodal analysis.
- **Observability**: Integration with **Cloud Logging** to monitor token usage and latency.

---

## 4. Proposed Architecture (Mapped to Reference Image)

The architecture follows the **Shared VPC / Multi-Project** pattern seen in enterprise Google Cloud deployments.

### 4.1 Data Layer (Storage)
- **Google Cloud Storage (GCS)**: Acts as the landing zone for raw PDFs. Organized by folders (e.g., `/architecture-guidelines/`, `/security-policies/`).

### 4.2 AI & Search Layer (The Engine)
- **Vertex AI Agent Builder (Search)**:
    - Automatically handles **Chunking** and **Embedding** using Google's state-of-the-art models.
    - Manages the **Vector Index** (RAG Datastore) as a managed service.
- **Gemini 1.5 Series**:
    - Acts as the "Brain" for reasoning and response synthesis.

### 4.3 Compute & Interface Layer (The Gateway)
- **Cloud Run**: Hosts the Python-based backend logic.
- **Streamlit**: Provides the user interface for document interaction.
- **Global Load Balancer + Cloud Armor**: Provides a secure entry point.

### 4.4 Data Synchronization (The Data Pipeline)
- Introduce Event-Driven Architecture to replace static indexing:
   * Workflow: GCS (PDF upload) -> Eventarc -> Cloud Run (Worker) -> Vertex AI Agent Builder (Indexing).
   * Benefit: The system can respond in real time to new document uploads and supports DLP (data loss prevention) scanning and preprocessing before indexing. 

### 4.5 Inference Logic Flow
- Introducing the Routing Layer and Evaluation Layer:
   * Router: Uses lightweight classification logic to route requests to either Gemini 1.5 Flash (Routine) or Pro (Complex).
   * Critic/Eval: After a response is generated, a second LLM instance scores its “fidelity” to reduce the risk of hallucinations.
---

## 5. Technical Implementation Details

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Inference Model** | Gemini 1.5 Pro | 2M context window and native multimodal support for diagrams. |
| **Search Engine** | Vertex AI Search | Managed "No-Ops" RAG that integrates seamlessly with GCS. |
| **Orchestration** | Python (Discovery Engine SDK) | Industry standard for AI application logic. |
| **Authentication** | IAM & Service Accounts | Ensures the Frontend only has `Discovery Engine Viewer` roles. |

---

## 6. Security Design (Architecture Alignment)
Based on the **VPC Service Controls** perimeter logic:
1. **Perimeter Defense**: Resources are isolated within a service perimeter to ensure data doesn't leave the GCP environment.
2. **Private Service Connect (PSC)**: The Cloud Run service communicates with Vertex AI via internal Google APIs, avoiding the public internet.
3. **Data Integrity**: GCS Buckets use Uniform Bucket-Level Access (UBLA).

---

## 8. Implementation Roadmap

### Phase 1: Infrastructure & Data Ingestion 
- Set up GCP Project and enable Vertex AI / Discovery Engine APIs.
- Create GCS Buckets and upload target PDFs.
- Configure Vertex AI Data Store and monitor the indexing process.

### Phase 2: Orchestration & Logic
- Develop the Python backend to call the `search` and `generate` APIs.
- Implement Prompt Engineering to enforce "No-Hallucination" rules.

### Phase 3: Frontend & Security Hardening
- Build the Streamlit UI.
- Containerize with Docker and deploy to Cloud Run.
- Configure Cloud Armor and Service Account permissions.



## Follow-up
Data Synchronization: How are updates to the GCS bucket synced to the Vertex AI Search Datastore? We could design an Eventarc trigger that detects new PDFs and triggers an index update.
Model Routing Logic: How exactly does the system decide between Gemini 1.5 Flash (routine) and Pro (complex)? We could define a lightweight routing mechanism or LLM-as-a-judge step.
RAG Evaluation: How will we measure hallucination rates? We could integrate Vertex AI Evaluation or RAGAS to score retrieval precision and response faithfulness.

