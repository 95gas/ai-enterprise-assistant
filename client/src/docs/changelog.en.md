# Updates - Change Log

---

## [2.0.1] - 05-07-2026
### Added
- **Private Spaces:** Each user can now manage up to 10 private documents, providing greater flexibility and security for personal or sensitive information.
- **SharePoint Versioning Integration:** Implemented document versioning for the SharePoint site *PROCEDURES*, specifically within the *PROCEDURES* folder. This ensures a robust, auditable, and common knowledge base for all users.
- **Enhanced Document Metadata:** Additional metadata is now visible in the document list, including:
   - Upload datetime
   - Number of tokens in the document
   - Where available (Wiki & SharePoint), a button providing a direct link to the original document
- **Document Nesting & Folder Navigation:** Documents are now organized in nested folders, making it easier to structure information and navigate large collections.
- **Folder-Based Filtering in Chat:** Users can filter batches of documents in chat by simply selecting a folder—e.g., select "WikiCarraro" to include all Wiki documents in the knowledge base for their chat session.

### Modified
- **Model Management:** Legacy models (GPT-5, mini, nano) were removed due to slow response times. Updated to deploy the more efficient gpt-5.4 and gpt-5.4-mini models for improved performance and reliability.
- **Document Handling:** Upgraded handling, storage, and presentation of document metadata on the frontend, providing users with smoother and more informative document management.
- **Manual Update:** The user manual has been revised to reflect all new features and improvements.

### Fixed
- **Permissions:** Corrected permission assignments, ensuring that users previously without an active visibility group now have appropriate access and visibility within the platform.

---

## [2.0.0] - 04-01-2026
### Added
- Implemented key features:
  - **Active Chat**: Active planning and reasoning capabilities; ASK automatically breaks down complex requests and determines which tools to use to provide complete answers, iterating when necessary.
  - **Integrated Web Search and Advanced Search**: Real-time web browsing and cross-referencing of external data with the company knowledge base through advanced search filters.
  - **Dynamic Wiki Synchronization**: Automatically updates information between the company Wiki and ASK’s knowledge base within 24 hours, ensuring a single source of truth.

### Modified
- Redesigned search filters in the user interface (UI) to promote transparency, trust, and control.
- Introduced:
  - Distinction between the **sources** of each answer (web-based or document-based).
  - Removed the **roles** system in favor of **permissions**, to clearly display the connected user’s access rights.
- New **shortcuts**, **official logo**, updated manual, and **privacy policy**.
- Backend transitioned to a **microservices** and **cloud-native** architecture (integration with S3), improving scalability and security.
- Implemented the **streaming tool** integrated with agentic search, making ASK’s computed actions visible.

### Fixed
- Optimized context management through **Dynamic Chat History**, which maintains conversation memory without wasting resources.
- Introduced **JWT tokens** for secure authentication between server and microservices.
- Resolved consistency issues between testing and production environments through **frontend dockerization**.