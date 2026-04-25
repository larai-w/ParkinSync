# ParkinSync: Bridging Analog Caregiving and Cloud Analytics for Parkinson’s Disease

## Project Overview
**ParkinSync** is a serverless Clinical Decision Support System (CDSS) designed to address the structural fragmentation of healthcare data in rural home-care settings. Specifically focused on Parkinson's Disease (PD) management in Yabu City, Hyogo, Japan, the system creates a secure bridge between traditional paper-based caregiver logs and modern cloud analytics.

By preserving the existing paper-based workflow, ParkinSync ensures "zero-disruption" to the caregivers' routine while leveraging **AWS Textract** for automated digitization and **Amazon SageMaker** for sophisticated correlation analysis between medication, environment, and motor symptoms.

## Key Features
- **Zero-Disruption Data Ingestion:** Maintains the analog paper-based input preferred by elderly caregivers while automating digital conversion.
- **AI-Powered OCR Engine:** Utilizes AWS Textract to extract structured data from handwritten logs with a high accuracy target (>90%).
- **Spatial-Temporal Risk Management:** Implements a "Spatial Curfew" protocol to track and enforce safety boundaries in confined spaces (e.g., bathrooms) during high-risk windows (e.g., post-rehabilitation fatigue after 22:00).
- **Hyper-Local Weather Integration:** Synchronizes local meteorological data (temperature and barometric pressure) to identify environmental triggers for "OFF" periods.
- **Human-in-the-Loop (HITL) Verification:** Integrates a Google Sheets interface for family members to verify and correct extracted data, ensuring clinical reliability.

## System Architecture
The system follows an event-driven, serverless architecture using AWS primitives:
- **Storage:** Amazon S3 (Ingestion and archive)
- **Compute:** AWS Lambda (Python 3.12)
- **OCR Engine:** Amazon Textract
- **Database/Visualization:** Google Sheets API v4
- **Security:** AWS Secrets Manager & AWS KMS
- **Analytics:** Amazon SageMaker

![Architecture Diagram](/architecture/architecture_diagram.svg)

## Directory Structure
- `/src`: Python source code for AWS Lambda functions.
- `/docs`: Technical reports (Unit 3), progress logs, and academic documentation.
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
