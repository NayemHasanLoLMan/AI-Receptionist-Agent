# 🛎️ AI Receptionist Agent – Smart Booking Assistant with Dynamic RAG & Web Knowledge Integration

This project is a fully automated **AI Receptionist Agent** designed to handle customer interactions, manage booking processes, and intelligently answer inquiries using real-time business data. It combines **advanced Retrieval-Augmented Generation (RAG)**, **web scraping**, **custom prompt tuning**, and **local model support** to deliver a flexible, domain-adaptive conversational system.

---

## 🧠 Project Highlights

- 🗣️ **Conversational AI Receptionist**  
  Engages users in natural dialogue to assist with:
  - Booking appointments
  - Answering general business questions
  - Navigating service availability
  - Suggesting relevant follow-up queries

- 🌐 **Web Knowledge Ingestion**  
  Uses **web scraping** and **curl-based crawlers** to dynamically fetch business knowledge:
  - Service offerings
  - Business hours & FAQs
  - Staff bios, pricing, and more

- 📥 **Custom RAG Implementation**  
  Leverages **advanced vector retrieval pipelines**:
  - Extracts relevant context chunks
  - Injects them into prompt windows
  - Supports hybrid search (semantic + keyword)

- 🧾 **Prompt & Tone Personalization**  
  Implements instruction-tuned prompts that match the business' desired tone (e.g. friendly, professional, playful).

- 🧪 **Local LLM Testing**  
  Enables testing and comparison of **local LLMs** (e.g., LLaMA 3.2, Mistral, Phi-2) with:
  - Switchable backends
  - Model-specific configuration
  - Evaluation tools

---

## 🔧 Technologies Used

| Component            | Tool / Library                             |
|----------------------|--------------------------------------------|
| **LLM Integration**   | OpenAI GPT / HuggingFace Transformers      |
| **RAG Engine**        | Custom pipeline / LangChain / LlamaIndex   |
| **Vector Store**      | FAISS / Chroma / Qdrant                    |
| **Web Scraping**      | BeautifulSoup, `requests`, `curl`, `trafilatura` |
| **Frontend Interface**| Gradio / Streamlit (optional)             |
| **Prompt Design**     | Manual + Instruction-tuned templates       |

---





# ⚙️ Setup Instructions

1. Clone the Repository

        git clone https://github.com/yourusername/ai-receptionist-agent.git
        cd ai-receptionist-agent

2. Install Dependencies

        pip install -r requirements.txt

3. Set Up Environment Variables

        cp .env.example .env






# 💡 How It Works


1. Knowledge Gathering
    scraper.py automatically scrapes business-relevant pages (e.g., /about, /services, /contact) and stores them as plain text.

2. Embedding & Indexing
    These pages are embedded and indexed using FAISS or ChromaDB for rapid retrieval.

3. Dynamic RAG + Prompting
    On user query, relevant knowledge chunks are retrieved and inserted into custom prompt templates. The system responds via OpenAI or a local model.

4. Booking Flow
    The agent engages users with dynamic booking-related questions (date, time, service type) and summarizes their request.







# 🔮 Future Enhancements
 
 - Add calendar integration (Google Calendar / Outlook)
 - Support voice input/output via Deepgram or ElevenLabs
 - Add chatbot memory for follow-up conversations
 - CRM integration for contact + history logging


 

# 📜 License

MIT License – Open for adaptation with attribution.