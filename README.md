# 🤖 Agente Corporativo de IA — Suporte SAP (Orla_Tech Consultoria)

> **Tech Challenge Alura + Oracle** — Agente de IA (RAG) que responde perguntas de
> colaboradores com base em documentos internos, em múltiplos formatos, com deploy
> na **Oracle Cloud Infrastructure (OCI)**.

---

## 📌 Descrição

Agente de inteligência artificial corporativo, acessível a todos os colaboradores,
capaz de responder perguntas com base em documentos internos da empresa fictícia
**Orla_Tech Consultoria**. O contexto é o **suporte a sistemas SAP na indústria**:

- **Foco principal:** SAP **MM** (Materials Management)
- **Módulos secundários:** PP, QM e WM
- **Sistemas:** SAP **ECC** e **S/4HANA**
- **Integrações MES:** Opcenter (Siemens) e PAS-X (Werum)

Quando o agente **não encontra** a resposta na base, ele informa educadamente que
não sabe, explica que é necessária validação humana e **pergunta se o usuário deseja
abrir um chamado**. Após a confirmação, cria um chamado com número sequencial único
na ferramenta fictícia **ServiceToday** (inspirada no ServiceNow).

---

## 🏗️ Arquitetura

```
Documentos (PDF, XLSX, DOCX, Imagem)
        │
        ▼
[Passo 3] document_loader.py  ── extração de conteúdo (chunks)
        │
        ▼
[Passo 4] rag_engine.py       ── embeddings + índice vetorial (FAISS)
        │
        ▼
[Passo 5] rag_engine.py       ── recuperação por similaridade (retriever)
        │
        ▼
[Passo 6] rag_engine.py       ── geração da resposta (LLM Groq / Llama 3.3)
        │
        ├── achou resposta? ──► responde com a solução + fontes
        │
        └── não achou? ──► pede confirmação ──► ticket_service.py (cria chamado)
        │
        ▼
[Passo 7] app/main.py         ── interface conversacional (Streamlit)
        │
        ▼
[Passo 8] OCI                 ── deploy em nuvem (VM Compute Always Free)
```

## 📂 Estrutura do projeto

```
Agente_corporativo/
├── app/
│   └── main.py                     # Interface conversacional (Streamlit)
├── src/
│   ├── document_loader.py          # Passo 3 — extração multi-formato
│   ├── rag_engine.py               # Passos 4-6 — indexação, recuperação, geração
│   ├── ticket_service.py           # Criação de chamados (número sequencial único)
│   └── api.py                      # API REST (FastAPI) para o OCI
├── data/documentos/                # Base de conhecimento (4 formatos)
│   ├── Base_Conhecimento_FAQ_SAP.pdf
│   ├── Chamados_Incidentes_Abertos.xlsx
│   ├── Manual_Procedimentos_Suporte_SAP.docx
│   └── orlatech_fluxo_suporte.png
├── notebooks/
│   ├── 00_setup_repositorio.ipynb  # Versionamento no Colab
│   └── 01_executar_agente_rag.ipynb# Executar o RAG passo a passo
├── assets/                         # Imagens/vídeos para o README
├── requirements.txt
├── DEPLOY_OCI.md                   # Guia de deploy no OCI (sem Docker)
├── .gitignore
└── README.md
```

## 🛠️ Tecnologias

- **Python 3.10+**
- **LangChain** — orquestração do pipeline RAG
- **FAISS** — índice vetorial
- **Sentence-Transformers** — embeddings (all-MiniLM-L6-v2)
- **Groq (Llama 3.3 70B)** — LLM de geração (rápida e gratuita, plugável)
- **Streamlit** — interface conversacional
- **FastAPI** — API REST
- **Oracle Cloud Infrastructure (OCI)** — deploy em nuvem

---

## ▶️ Como executar

### Opção A — Google Colab (recomendado, sem instalar nada)

Abra o notebook `notebooks/01_executar_agente_rag.ipynb` no Colab e execute as células
em ordem. Ele clona o repo, instala dependências e roda o agente passo a passo.

### Opção B — Local

```bash
# 1. Clonar
git clone https://github.com/OrlandoCaetano2026/Agente_corporativo.git
cd Agente_corporativo

# 2. Ambiente virtual + dependências
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configurar a chave da LLM
export GROQ_API_KEY="sua-chave"   # Windows: set GROQ_API_KEY=...

# 4. Rodar a interface
streamlit run app/main.py
```

### Opção C — Nuvem OCI

Siga o guia detalhado em **[DEPLOY_OCI.md](DEPLOY_OCI.md)**.

---

## ✅ O que o agente responde

- Dúvidas de **SAP MM** (compras, estoque, faturas, mestre de materiais).
- Orientações gerais de **PP, QM e WM**.
- Questões de **integração com MES** (Opcenter, PAS-X).
- Diferenças entre **ECC e S/4HANA**.
- Procedimentos e boas práticas presentes na base de conhecimento.

## ❌ O que o agente NÃO responde

- Assuntos fora de SAP/MES (ex.: RH, folha de pagamento, infraestrutura de rede).
- Solicitações de alteração de dados em produção.
- Concessão de acessos e autorizações.
- Informações confidenciais / dados pessoais (LGPD).

> Nesses casos, o agente **não inventa**: informa a limitação e, com a confirmação
> do usuário, abre um chamado no ServiceToday.

---

## ☁️ Deploy em nuvem (OCI)

O agente foi publicado em uma **VM OCI Compute (Always Free)**, atendendo ao requisito
de uso de ao menos um serviço OCI.

<!-- Substitua pela imagem/vídeo do agente rodando na nuvem (Passo 9) -->
![Agente rodando na nuvem OCI](assets/demo_oci.png)

*(Print do agente em execução, com o IP público do OCI visível na barra de endereço.)*

---

## 🔧 Instruções para modificações

- **Adicionar documentos:** coloque novos arquivos em `data/documentos/` e reindexe
  (o `document_loader` já suporta PDF, DOCX, XLSX e imagens; extensível a CSV/JSON/HTML).
- **Trocar a LLM:** ajuste o método `_get_llm()` em `src/rag_engine.py` (hoje usa Groq;
  o modelo pode ser trocado pela variável `GROQ_MODEL`).
- **Ajustar sensibilidade:** mude a variável `RAG_LIMIAR` (limiar de similaridade)
  ou `RAG_TOP_K` (nº de trechos recuperados).
- **Migrar a base de chamados para banco:** substitua a leitura/escrita do Excel em
  `src/ticket_service.py` por um banco (ex.: Oracle Autonomous Database no OCI).

---

## 👤 Autor

**Orlando dos Santos Caetano** — Tech Challenge Alura + Oracle.
