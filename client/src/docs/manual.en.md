# Introduction

Welcome to **ASK**, an intelligent assistant developed by Carraro Group. 

**ASK** employs advanced document search, enabling fast, understandable responses tailored to queries rooted in the organization’s knowledge base. Document search respects privacy and only accesses documents permitted to the user by group. 

Users can interact with **ASK** in natural language, just like speaking to a collegue.

## Glossary

**LLM (Large Language Model)**:  
A type of artificial intelligence model designed to understand and generate human-like text based on the input it receives. LLMs are trained on vast amounts of textual data and use statistical methods to predict and produce coherent, contextually appropriate responses. Examples include GPT (Generative Pre-trained Transformer) models.

**Token**:  
A unit of text used by language models as the basic element of processing. Tokens can represent words, parts of words, punctuation marks, or even spaces, depending on the language and model. For example, the word “unbelievable” might be split into tokens like “un”, “believ”, and “able” by some models. The number of tokens often determines the computational cost and output length of an LLM’s response.

# Work Area

## ASK

The Work Area is designed as the main hub for initiating new chats and managing interactive sessions across various features.

### Chat Box

The Chat Box provides multiple functionalities for streamlining chat sessions. Below are the key features, listed from left to right:

- **Model Selector**: Allows users to choose the preferred LLM model for the chat. Each model offers distinct performance and token limits. Once the allocated tokens for a selected model are exhausted, the system automatically switches to the next available model.
- **Mode**: Provides options for chat modes:
    - **Chat**: Suited for general conversation and queries.
    - **Focus**: Ideal for interactions centered around a single document.
- **Documents Selector**: Enables filtering of accessible documents. By default, all documents the user has permission to access are available. The search feature facilitates rapid selection of any document or folder.
- **Sources**: Allows specification of desired Knowledge Base for answering:
    - **Model**: Utilizes Internal Knowledge of the selected LLM.
    - **Docs**: Incorporates content from selected documents.
    - **Web**: Engages the web for information retrieval.

### Messages

When a message is submitted, it appears in the chat interface with accompanying action buttons:

- **User Message**:
    - **Copy**: Copies the user message to the clipboard.
    - **Edit**: Enables editing of the user message and continuation of the conversation.

- **Assistant Message**: Displays a loading animation during answer generation, showing the steps being undertaken by the assistant. Once complete, only the final answer remains with action buttons:
    - **Information**: Presents details about the interaction, including:
        - **Question**: User input.
        - **Mode**: Active chat mode.
        - **Used Tokens**: Token consumption (divided by input and output).
        - **LLM model**: Model used for answer generation.
    - **Feedback**: Opens a form for submitting feedback to developers.
    - **Copy**: Copies the assistant’s answer to the clipboard.
    - **Expand**: Regenerates the answer from the current point.
    - **Regenerate**: Reproduces the answer anew.

Depending on answer content, citations may be displayed as IDs within brackets. Typically, these IDs appear at sentence ends, referencing the precise source used. Citations are grouped by type (document or web page) below the answer and can be explored interactively.

## Chats

The Chats section presents a chronological listing of past chat conversations sorted by last edit.

- It's possible to create a new chat deciding its name.
- The search bar aids in locating previous chats by entering any part of the chat name, returning all relevant matches regardless of position.
- Deletion of past chats is accomplished by clicking the corresponding trashcan icon.

## Documents

The Documents section displays all uploaded documents accessible to the user, based on visibility groups (see *Settings > User Data > Groups*).

- A search bar is available to find documents quickly by entering any part of a document name, showing all matching entries.
- Document inspection is performed by clicking on a document, which opens a rendered Markdown view.

Enhanced options are available based on permissions (see *Settings > User Data > Permissions*):
- **Upload common**: Allows uploading documents to a shared area. Visibility is determined by assigned groups. Only users permitted to upload common documents can delete them.
- **Upload private**: Permits uploading documents for private access. Only the uploader can view and delete these documents.
- **Delete document**: Executed by clicking the trashcan icon next to the desired document.

# Information

The Information section operates as a centralized resource for essential documentation.

Each section features a top-right index to facilitate resource navigation.

## Manual

Offers comprehensive guidance for understanding and utilizing the application’s features and functionalities.

## Privacy Policy

Provides in-depth explanations regarding the collection, usage, and protection of user data, fostering transparency and user trust.

## Changelog

Documents all past updates, including new features, fixes, and improvements, allowing users to track changes and evolutions of the application.

# Settings

Settings empower users to customize their experience and manage account specifics.

## Theme

Features options for personalizing the visual appearance, such as switching between light and dark modes.

## Language

Selection of the application interface language. This adjustment is purely visual and does not affect functional aspects.

## User Data

The User Data section displays detailed information about the signed-in account, including:

- **E-mail**: Shows the email associated with the signed-in account.
- **Name**: Displays the account holder’s name.
- **Permissions**: Lists available permissions, with ticks indicating granted access.
- **Groups**: Shows supported visibility groups, highlighting those accessible. Visibility groups govern access to specific documents, folders, and features.
- **Domain**: Indicates the account domain.
- **Total tokens limit**: Specifies the daily token limit (further details in *Tokens Consumption > Account tokens usage*).
- **Total tokens reset period**: Outlines the interval for token limit resets (see *Tokens Consumption > Account tokens usage*).
- **Trial expiry date**: Marks the account’s trial expiration, after which access is disabled.

## Tokens Consumption

Tokens Consumption provides data on account usage limits and metrics:

- **Account tokens usage**: Presents the total daily token limit.
- **Models tokens usage**: Details per-model usage limits, including:
	- **Model**: Name of the model presented to the user.
	- **Provider**: Name of the LLM provider.
    - **Tokens reset period**: Reset interval for model-specific tokens usage.
    - **Next reset**: Date and time of the next model reset.
    - **Tokens usage**: Current token consumption status per model.

## Logout

Log out from the signed-in account.