# 🤖 Agente Corporativo de IA — Suporte SAP (Orla_Tech Consultoria)

> **Tech Challenge Alura + Oracle** — Agente de IA (RAG) que responde perguntas de
> colaboradores com base em documentos internos, em múltiplos formatos, com deploy
> na **Oracle Cloud Infrastructure (OCI)**.

🔗 **Aplicação no ar (HTTPS):** [https://agente-orla-tech.duckdns.org](https://agente-orla-tech.duckdns.org)

---

## 📌 Descrição

Agente de inteligência artificial corporativo — um **especialista SAP virtual** —
acessível a todos os colaboradores, que responde perguntas com base em documentos
internos da empresa fictícia **Orla_Tech Consultoria**. O contexto é o **suporte a
sistemas SAP na indústria**:

- **Foco principal:** SAP **MM** (Materials Management)
- **Módulos secundários:** PP, QM e WM
- **Sistemas:** SAP **ECC** e **S/4HANA**
- **Integrações MES:** Opcenter (Siemens) e PAS-X (Werum)

Quando o agente **não encontra** a resposta na base, ele **não inventa**: contorna de
forma cordial, recomenda consultar o portal da companhia e **oferece registrar um
chamado** no **ServiceToday** (fictício, inspirado no ServiceNow). Ao abrir o chamado:

- Pergunta a **ferramenta** de destino (**SAP** ou **MES**);
- **Detecta automaticamente o módulo** (MM/PP/QM/WM/MES) pelo texto do problema;
- Pergunta a **prioridade** (P1-Crítico, P2-Urgente, P3-Médio, P4-Leve) via **botões**;
- Gera um **número sequencial único** e registra na base.

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
        ├── achou resposta? ──► responde com solução + fontes
        │
        └── não achou? ──► contorno cordial ──► oferta de chamado
                                  │
                                  ▼
                        ticket_service.py (ferramenta SAP/MES,
                        módulo automático, prioridade P1-P4, ID único)
        │
        ▼
[Passo 7] app/main.py         ── interface conversacional (Streamlit)
        │
        ▼
[Passo 8] OCI                 ── deploy em nuvem (VM Compute Always Free + Caddy/HTTPS)
```

## 📂 Estrutura do projeto

```
Agente_corporativo/
├── app/
│   └── main.py                       # Interface conversacional (Streamlit)
├── assets/
│   ├── orlatech_fluxo_suporte.png    # Imagem do fluxo (para o README)
│   └── evidencias/                   # Prints dos testes (README)
│       ├── 01_consulta_base.png
│       ├── 02_problema_com_solucao.png
│       ├── 03_oferta_incidente.png
│       ├── 04_selecao_prioridade.png
│       ├── 05_chamado_criado.png
│       └── 06_fora_escopo.png
├── data/documentos/                  # Base de conhecimento (5 formatos)
│   ├── Base_Conhecimento_FAQ_SAP.pdf
│   ├── Catalogo_Transacoes_SAP.pdf
│   ├── Chamados_Incidentes_Abertos.xlsx
│   ├── Manual_Procedimentos_Suporte_SAP.docx
│   └── orlatech_fluxo_suporte.png
├── notebooks/
│   └── 01_setup_repositorio.ipynb    # Setup do repo + execução do RAG (Groq)
├── src/
│   ├── api.py                        # API REST (FastAPI) para o OCI
│   ├── document_loader.py            # Passo 3 — extração multi-formato
│   ├── rag_engine.py                 # Passos 4-6 — indexação, recuperação, geração
│   └── ticket_service.py             # Chamados: ferramenta, módulo auto, P1-P4, ID único
├── .gitignore
├── DEPLOY_OCI.md                     # Guia de deploy no OCI (sem Docker)
├── deploy.sh                         # Script de deploy (add+commit+push) no GitHub
├── README.md
└── requirements.txt
```

## 🛠️ Tecnologias

- **Python 3.10+**, **LangChain**, **FAISS**, **Sentence-Transformers** (all-MiniLM-L6-v2)
- **Groq (Llama 3.3 70B)** — LLM de geração (rápida e gratuita, plugável)
- **Streamlit** (interface), **FastAPI** (API REST)
- **Oracle Cloud Infrastructure (OCI)** — deploy em nuvem
- **Caddy** — reverse proxy com **HTTPS automático** (Let's Encrypt) + **DuckDNS**

---

## 🧪 Evidências de Testes (rodando na nuvem OCI 🔒)

> Todos os testes abaixo foram executados na aplicação publicada em
> **https://agente-orla-tech.duckdns.org** (HTTPS válido). Clique em cada item para ampliar a imagem.

### 🟢 1. Interface + consulta conceitual à base de conhecimento
Pergunta conceitual (*"O que é SAP?"*): o agente responde de forma natural e **cita a fonte**
consultada (Catálogo de Transações SAP). Repare no **cadeado HTTPS** na barra do navegador.

<details>
<summary>🖼️ Ver imagem</summary><br>

<img src="assets/evidencias/01_consulta_base.png" width="850">

</details>

### 🟢 2. Problema COM solução na base
Pergunta de problema real (*"Estou com problema na liberação do pedido XYZ1020"*): o agente
retorna um **passo a passo objetivo** com os tcodes e cita a fonte (Base de Conhecimento — FAQ SAP).

<details>
<summary>🖼️ Ver imagem</summary><br>

<img src="assets/evidencias/02_problema_com_solucao.png" width="850">

</details>

### 🟡 3. Problema SEM solução → oferta de incidente
Quando o usuário indica que **o problema persiste** (*"Não consegui resolver, ainda preciso de ajuda"*),
o agente encerra cordialmente e oferece o **botão “Abrir incidente”** (sem sair do contexto SAP).

<details>
<summary>🖼️ Ver imagem</summary><br>

<img src="assets/evidencias/03_oferta_incidente.png" width="850">

</details>

### 🟡 4. Seleção de prioridade por botões (P1-P4)
Ao clicar em **“Abrir incidente”**, o agente **detecta a ferramenta e o módulo** automaticamente
(SAP · MM) e apresenta a escolha de **prioridade em 4 botões** com o SLA de cada nível.

<details>
<summary>🖼️ Ver imagem</summary><br>

<img src="assets/evidencias/04_selecao_prioridade.png" width="850">

</details>

### ✅ 5. Chamado registrado com sucesso
Após a escolha da prioridade, o chamado é **gravado na base** e o agente devolve o
**número único** (ex.: `INC0010257`), ferramenta, módulo/categoria, prioridade, SLA e responsável.

<details>
<summary>🖼️ Ver imagem</summary><br>

<img src="assets/evidencias/05_chamado_criado.png" width="850">

</details>

### 🔴 6. Pergunta fora de escopo
Perguntas fora do domínio SAP/MES (*"Qual a previsão do clima para amanhã?"*) são
**declinadas educadamente**, sem inventar resposta e **sem** oferecer chamado.

<details>
<summary>🖼️ Ver imagem</summary><br>

<img src="assets/evidencias/06_fora_escopo.png" width="850">

</details>

---

## ▶️ Como executar

### Opção A — Google Colab (recomendado)
Abra `notebooks/01_setup_repositorio.ipynb` e execute as células em ordem
(atualiza o repositório e roda o agente com Groq).

### Opção B — Local
```bash
git clone https://github.com/OrlandoCaetano2026/Agente_corporativo.git
cd Agente_corporativo
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="sua-chave"
streamlit run app/main.py
```

### Opção C — Nuvem OCI
Siga o guia **[DEPLOY_OCI.md](DEPLOY_OCI.md)** (sem Docker).

---

## ✅ O que o agente responde
- Dúvidas de **SAP MM** (compras, estoque, faturas, mestre de materiais).
- Orientações gerais de **PP, QM e WM**.
- Integração com **MES** (Opcenter, PAS-X).
- Diferenças entre **ECC e S/4HANA** e boas práticas da base.

## ❌ O que o agente NÃO responde
- Assuntos fora de SAP/MES (RH, folha, infraestrutura de rede).
- Alteração de dados em produção; concessão de acessos (Basis).
- Informações confidenciais / dados pessoais (LGPD).

> Nesses casos, contorna cordialmente, recomenda o portal e oferece registrar um chamado.

---

## ⚙️ Onde ajustar o comportamento (RAG)
No arquivo **`src/rag_engine.py`**:
- **PROMPT** (persona, tom, formato): método `_montar_prompt()`
- **LIMIAR_SIMILARIDADE** (quando "não sabe"): topo do arquivo (padrão **0.45**)
- **TOP_K** (nº de trechos): topo do arquivo (padrão **5**)
- **Modelo Groq**: variável de ambiente `GROQ_MODEL`

---

## ☁️ Deploy em nuvem (OCI)

Publicado em uma **VM OCI Compute (Always Free)**, atendendo ao requisito de uso de
ao menos um serviço OCI. O acesso é feito por **HTTPS** (certificado Let's Encrypt),
com o **Caddy** atuando como reverse proxy à frente do Streamlit e o domínio gratuito
via **DuckDNS**:

```
Navegador ──HTTPS🔒──► Caddy (:443) ──HTTP──► Streamlit (:8501, interno)
```

🔗 **URL pública:** [https://agente-orla-tech.duckdns.org](https://agente-orla-tech.duckdns.org)

---

## 👤 Autor
**Orlando dos Santos Caetano** — Tech Challenge Alura + Oracle.
[LinkedIn](https://www.linkedin.com/in/orlando-caetano/) ·
[Repositório](https://github.com/OrlandoCaetano2026/Agente_corporativo)
