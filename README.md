# ParkinSync: Automated Parkinson's Medical Log Pipeline

## 📝 Project Overview
**ParkinSync** is a cloud-native automation pipeline designed to digitize handwritten medical logs for Parkinson's disease patients. The system captures medical data from PDFs via Amazon Textract and enriches it with historical meteorological data to help clinicians analyze how environmental factors influence symptoms.

## 🚀 Key Features
- **Zero-Disruption Data Ingestion:** Maintains the analog paper-based input preferred by elderly caregivers while automating digital conversion.
- **AI-Powered OCR Engine:** Utilizes AWS Textract to extract structured data from handwritten logs with a high accuracy target (>90%).
- **Spatial-Temporal Risk Management:** Implements a "Spatial Curfew" protocol to track and enforce safety boundaries in confined spaces (e.g., bathrooms) during high-risk windows (e.g., post-rehabilitation fatigue after 22:00).
- **Hyper-Local Weather Integration:** Synchronizes local meteorological data (temperature and barometric pressure) to identify environmental triggers for "OFF" periods.
- **Human-in-the-Loop (HITL) Verification:** Integrates a Google Sheets interface for family members to verify and correct extracted data, ensuring clinical reliability.

- **Multi-Cloud Integration**: Seamlessly connects AWS (Lambda, S3, Textract, Secrets Manager) with Google Cloud (Sheets API).
- **Historical Weather Enrichment**: Uses the **Visual Crossing API** to fetch weather conditions specifically for the date written on the medical log, not just the upload time.
- **Localization (JST)**: Implemented time-zone handling to ensure all timestamps are in **Japan Standard Time (UTC+9)** for clinical relevance.
- **Enterprise-Grade Security**: Zero hardcoded credentials. All API keys and service account JSONs are securely managed using **AWS Secrets Manager**.
- **Automated Table Extraction**: Utilizes Textract's `TABLES` feature to map complex medical logs directly into structured spreadsheet rows.

## System Architecture
The system follows an event-driven, serverless architecture using AWS primitives:
- **Storage:** Amazon S3 (Ingestion and archive)
- **Compute:** AWS Lambda (Python 3.12)
- **OCR Engine:** Amazon Textract
- **Database/Visualization:** Google Sheets API v4
- **Security:** AWS Secrets Manager
- **Analytics:** Amazon SageMaker

![Architecture Diagram](/architecture/architecture_diagram.svg)

## 📂 Directory Structure
- `/src`: Python source code for AWS Lambda functions.
- `/docs`: Technical reports (Unit 3), progress logs, and academic documentation.
- `/tests`: test code
- `/architecture`: High-resolution system diagrams and data flowcharts.
- `/design`: Templates for the paper-based caregiver logs.

## Getting Started
### Prerequisites
- Python 3.12+
- AWS CLI configured with appropriate IAM permissions.
- Google Cloud Service Account credentials (JSON).

### Installation & Deployment
1. Clone the repository:
   ```bash
   git clone [https://github.com/larai-w/ParkinSync.git](https://github.com/larai-w/ParkinSync.git)

2. Navigate to the development branch:


   ```bash
   git checkout development

3. Deploy the Lambda function using your preferred framework (AWS SAM, Terraform, or AWS Management Console).

## Security & Ethics
Security and ethics are core non-functional requirements of ParkinSync:

Principle of Least Privilege (PoLP): IAM roles are strictly scoped to necessary resources to minimize the attack surface.

Data Anonymization: Personally Identifiable Information (PII) is stripped before ingestion into the analytics engine to protect patient and caregiver privacy.

Zero Hardcoding Policy: All API keys and sensitive tokens (e.g., Google Sheets API, Weatherbit API) are managed via AWS Secrets Manager.

## Branching Strategy
The project follows a standard Git-based workflow as outlined in Document 1:

main: Contains production-ready code and finalized documentation.

development: Used for active iteration and feature testing. All merges to main require manual review and verification.

## License
This project is licensed under the MIT License - see the LICENSE file for details.

## Author
**larai-w**
MSIT Candidate, University of the People
Department of CS & MSIT
