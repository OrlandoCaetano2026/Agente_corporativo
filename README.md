# 🤖 Agente Corporativo de IA — Base de Conhecimento Conversacional

> Desafio Tech Challenge **Alura + Oracle** — Agente de IA (RAG) capaz de responder
> perguntas de colaboradores com base em documentos internos da empresa, em múltiplos
> formatos, com deploy na **Oracle Cloud Infrastructure (OCI)**.

---

## 📌 Descrição

Agente de inteligência artificial corporativo, acessível a todos os colaboradores,
capaz de responder perguntas com base em documentos internos da empresa. O agente
compreende e processa múltiplos formatos de arquivo (**PDF, Word, Excel, PowerPoint,
Markdown, CSV, JSON e HTML**) e cobre diferentes domínios organizacionais — de RH e
financeiro a jurídico, operacional e estratégico — funcionando como uma base de
conhecimento conversacional, centralizada e sempre disponível.

## 🏗️ Arquitetura

```
Documentos (PDF/Word/Excel/PPT/MD/CSV/JSON/HTML)
        │
        ▼
[1] Ingestão & Extração (loaders LangChain)
        │
        ▼
[2] Chunking (divisão em trechos)
        │
        ▼
[3] Embeddings → Indexação Vetorial (FAISS/Chroma)
        │
        ▼
[4] Recuperação (Retriever) ── consulta do usuário
        │
        ▼
[5] LLM + Prompt (RAG) → Resposta fundamentada
        │
        ▼
[6] Interface (Streamlit) → Deploy OCI
```

## 🛠️ Tecnologias

- **Python 3.10+**
- **LangChain** — orquestração do pipeline RAG
- **FAISS / ChromaDB** — armazenamento vetorial
- **LLM** — (Gemini / OpenAI / modelo à escolha)
- **Streamlit** — interface conversacional
- **Oracle Cloud Infrastructure (OCI)** — deploy em nuvem

## 📂 Estrutura do projeto

```
agente-corporativo/
├── app/                 # Interface (Streamlit)
├── src/                 # Módulos: ingestão, indexação, RAG
├── data/documentos/     # Documentos da empresa fictícia
├── notebooks/           # Notebooks de desenvolvimento (Google Colab)
├── assets/              # Imagens/vídeos para o README
├── requirements.txt
├── .gitignore
└── README.md
```

## ▶️ Como executar

```bash
# 1. Clonar o repositório
git clone https://github.com/OrlandoCaetano2026/agente-corporativo.git
cd agente-corporativo

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente (chave da LLM)
export GOOGLE_API_KEY="sua-chave"   # ou OPENAI_API_KEY

# 4. Rodar a aplicação
streamlit run app/main.py
```

## ✅ O que o agente responde / ❌ O que NÃO responde

- ✅ Perguntas cujo conteúdo esteja presente nos documentos indexados.
- ❌ Perguntas fora do escopo dos documentos (o agente informa quando não sabe).

## ☁️ Deploy em nuvem (OCI)

> _(A ser preenchido no Passo 8 — incluir imagem/vídeo do agente rodando na nuvem)_

![Demonstração do agente](assets/demo.gif)

## 🔧 Instruções para modificações

- Adicionar novos documentos: colocar arquivos em `data/documentos/` e reindexar.
- Trocar a LLM: ajustar o módulo em `src/`.
- Ajustar chunking/recuperação: parâmetros em `src/`.

## 👤 Autor

Orlando dos Santos Caetano — Tech Challenge Alura + Oracle.
