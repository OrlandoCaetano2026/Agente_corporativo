# -*- coding: utf-8 -*-
"""
rag_engine.py — PASSOS 4, 5 e 6: Indexação vetorial, recuperação (RAG) e geração
--------------------------------------------------------------------------------
Núcleo do agente (versão revisada — v3):

  PASSO 4 - Indexação vetorial: embeddings (HuggingFace all-MiniLM-L6-v2) + FAISS.
  PASSO 5 - Recuperação: similaridade (para o limiar) + MMR (contexto diverso).
  PASSO 6 - Geração: LLM Groq com prompt refinado + FEW-SHOTS (10 exemplos).

Se o contexto NÃO for suficiente (baixa similaridade), o agente NÃO inventa:
responde de forma SUCINTA e oferece registrar um chamado.

Portabilidade: Colab e OCI. Sem GROQ_API_KEY, roda em "modo recuperação".
"""
from __future__ import annotations
import os
from typing import List, Tuple, Optional

from document_loader import carregar_documentos, Chunk

# ============ REGRAS DO RAG (ajuste aqui) ============
LIMIAR_SIMILARIDADE = float(os.getenv("RAG_LIMIAR", "0.50"))
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
FETCH_K = int(os.getenv("RAG_FETCH_K", "12"))
MMR_LAMBDA = float(os.getenv("RAG_MMR_LAMBDA", "0.5"))
LLM_TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS = int(os.getenv("RAG_MAX_TOKENS", "800"))
# =====================================================

# Mensagem de contorno cordial e SUCINTA (quando a base não tem a informação).
MSG_SEM_RESPOSTA = (
    "Isso não consta na base de conhecimento atual. Recomendo verificar o portal "
    "da companhia. Posso registrar um chamado para um especialista validar — "
    "deseja? Se sim, para qual ferramenta: SAP ou MES?"
)

# ============ FEW-SHOTS (exemplos de orientação pergunta -> resposta) ============
# Ensinam o modelo, PELO EXEMPLO, o tom, o formato e o comportamento esperados.
# 8 casos de "SABE responder" (por área) + 2 casos de "NÃO SABE" (contorno sucinto).
FEW_SHOTS = """# EXEMPLOS DE COMPORTAMENTO (siga este tom e formato)

Exemplo 1 (MM — liberação de pedido):
Pergunta: Recebo "estratégia de liberação não encontrada" ao liberar um pedido.
Resposta:
1. Confira grupo de compras, tipo de documento e valor total do pedido (ME23N).
2. Valide se a característica de classificação corresponde a uma estratégia ativa.
3. Verifique se o pedido não está abaixo do valor mínimo que exige liberação.
Execute a liberação em ME29N após o ajuste. (Fonte: Base de Conhecimento — SAP MM)

Exemplo 2 (MM — fatura bloqueada):
Pergunta: A fatura foi bloqueada no MIRO por diferença de preço, o que faço?
Resposta:
1. Compare o preço do pedido com o da fatura; cheque o registro info.
2. Se for erro de preço no pedido, corrija e reprocesse.
3. Se o preço da fatura estiver correto, libere manualmente em MRBR com justificativa.
(Fonte: Base de Conhecimento — SAP MM)

Exemplo 3 (MM — subcontratação):
Pergunta: Como funciona a subcontratação?
Resposta:
1. No pedido de subcontratação (item categoria L), o componente é enviado ao fornecedor (mov. 541).
2. No recebimento do beneficiado, o mov. 543 baixa os componentes automaticamente.
3. Acompanhe o estoque em poder de terceiros (estoque especial O) via MMBE.
(Fonte: Base de Conhecimento — SAP MM)

Exemplo 4 (PP — ordem não confirma):
Pergunta: A ordem de produção não confirma no CO11N.
Resposta:
1. Verifique a disponibilidade dos componentes e o status da ordem.
2. Confirme se a operação anterior já foi confirmada (sequenciamento).
3. Cheque se o centro de trabalho está ativo.
(Fonte: Base de Conhecimento — SAP PP)

Exemplo 5 (QM — lote de inspeção):
Pergunta: O lote de inspeção não é gerado na entrada de mercadoria.
Resposta:
1. Confirme o perfil de QM ativo no mestre do material (aba Qualidade).
2. Verifique se o tipo de inspeção correto (ex.: 01 para recebimento) está atribuído.
3. Sem tipo de inspeção ativo, o lote não é disparado — ative e teste novamente (QA32).
(Fonte: Base de Conhecimento — SAP QM)

Exemplo 6 (WM — ordem de transferência):
Pergunta: A LT01 não determina o depósito de destino.
Resposta:
1. Revise a estratégia de colocação/retirada e os tipos de depósito configurados.
2. Verifique se há posições bloqueadas ou sem capacidade.
3. Ajuste a estratégia e recrie a ordem de transferência (LT01).
(Fonte: Base de Conhecimento — SAP WM)

Exemplo 7 (MES — IDoc status 51):
Pergunta: A ordem não replica para o Opcenter, IDoc em status 51.
Resposta:
1. Abra o IDoc em WE02/WE19 e leia a mensagem de erro de aplicação.
2. Corrija o dado obrigatório ausente e valide a conexão da interface.
3. Reprocesse o IDoc em BD87.
(Fonte: Base de Conhecimento — Integração/MES)

Exemplo 8 (ECC x S/4 — diferença de dados):
Pergunta: Após migrar para o S/4HANA, notei divergência no mestre de material.
Resposta:
1. Diferenças de layout são esperadas (ex.: material com até 40 caracteres, MATDOC).
2. Divergência de VALORES não é esperada — registre material, campo e valores ECC x S/4.
3. Abra um chamado com essas evidências para análise.
(Fonte: Base de Conhecimento — SAP MM)

Exemplo 9 (NÃO SABE — RH):
Pergunta: Qual é a política de férias do RH?
Resposta: Isso não consta na base de conhecimento. Posso registrar um chamado para um especialista? (SAP ou MES)

Exemplo 10 (NÃO SABE — Infraestrutura):
Pergunta: Como faço o reset da senha da VPN?
Resposta: Isso não consta na base de conhecimento. Posso registrar um chamado para um especialista? (SAP ou MES)
"""


class RAGEngine:
    def __init__(self, pasta_documentos: str,
                 modelo_embeddings: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.pasta = pasta_documentos
        self.modelo_embeddings = modelo_embeddings
        self.chunks: List[Chunk] = []
        self._vectorstore = None
        self._embeddings = None
        self._llm = None

    # ---------- PASSO 4: indexação ----------
    def indexar(self):
        self.chunks = carregar_documentos(self.pasta)
        if not self.chunks:
            raise RuntimeError("Nenhum documento encontrado para indexar.")

        from langchain_community.vectorstores import FAISS
        from langchain_community.embeddings import HuggingFaceEmbeddings

        self._embeddings = HuggingFaceEmbeddings(model_name=self.modelo_embeddings)
        textos = [c.texto for c in self.chunks]
        metadados = [{"fonte": c.fonte, "tipo": c.tipo, **c.meta} for c in self.chunks]
        self._vectorstore = FAISS.from_texts(textos, self._embeddings, metadatas=metadados)
        return len(self.chunks)

    # ---------- PASSO 5: recuperação ----------
    def recuperar(self, pergunta: str, k: int = TOP_K) -> List[Tuple[str, dict, float]]:
        """Retorna [(texto, metadados, similaridade)] — usado para checar o limiar."""
        if self._vectorstore is None:
            raise RuntimeError("Índice não construído. Chame indexar() primeiro.")
        docs = self._vectorstore.similarity_search_with_score(pergunta, k=k)
        resultados = []
        for doc, dist in docs:
            similaridade = 1.0 / (1.0 + float(dist))
            resultados.append((doc.page_content, doc.metadata, similaridade))
        return resultados

    def recuperar_mmr(self, pergunta: str):
        """Recupera trechos diversificados (MMR) para montar o contexto da LLM."""
        return self._vectorstore.max_marginal_relevance_search(
            pergunta, k=TOP_K, fetch_k=FETCH_K, lambda_mult=MMR_LAMBDA)

    # ---------- PASSO 6: geração ----------
    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        from langchain_groq import ChatGroq
        modelo = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._llm = ChatGroq(model=modelo, temperature=LLM_TEMPERATURE,
                             max_tokens=LLM_MAX_TOKENS)
        return self._llm

    def _montar_prompt(self, contexto: str, pergunta: str) -> str:
        return f"""# IDENTIDADE
Você é um especialista SAP sênior da Orla_Tech Consultoria. Seu tom é técnico,
direto e cordial — como um consultor experiente que respeita o tempo do colega.

# COMO INTERPRETAR O CONTEXTO
- Leia TODO o contexto antes de responder e conecte informações de trechos diferentes.
- Priorize dados objetivos (tcodes, movimentos, status, tabelas) sobre generalidades.
- Se o contexto tiver a resposta apenas parcial, entregue o que há e sinalize o que falta.

# COMO RESPONDER QUANDO SOUBER
- Comece pela solução; evite rodeios e introduções longas.
- Use passos numerados curtos (máximo ~6). Cite o TCODE sempre que aplicável
  (ex.: ME29N, MIGO, MIRO, MRBR, CO11N, MD01N, QA32, LT01, BD87).
- Não repita informação. Ao final, cite a fonte entre parênteses.

# COMO RESPONDER QUANDO NÃO SOUBER (seja SUCINTO)
- NÃO invente e NÃO dê aula genérica sobre o tema.
- Responda em no máximo 2 frases: informe que não está na base e ofereça o chamado.
- Modelo: "Isso não consta na base de conhecimento. Posso registrar um chamado
  para um especialista? (SAP ou MES)"

# O QUE VOCÊ PODE RESPONDER (com base no contexto)
- SAP MM: pedido/ME29N liberação, MIGO entrada/divergência, MIRO/MRBR fatura,
  registro info, contrato, subcontratação (541/543), consignação (K), MM17 massa.
- SAP PP: ordem CO11N, MRP MD01N/MD04, backflush, lista técnica (BOM/CS02), ATP.
- SAP QM: lote de inspeção, tipo de inspeção, decisão de uso (QA32), certificado.
- SAP WM: ordem de transferência LT01/LT12, picking, diferenças LI20, reabastecimento.
- MES: replicação SAP↔Opcenter/PAS-X, IDoc status 51 (WE02/BD87), filas (SMQ1/SMQ2).
- Diferenças ECC x S/4HANA e boas práticas presentes na base.

# O QUE VOCÊ NÃO PODE RESPONDER (use o contorno sucinto)
- RH, folha de pagamento, férias, benefícios.
- Infraestrutura/TI: reset de senha, VPN, e-mail, rede.
- Opiniões pessoais, previsões ou qualquer tema fora de SAP/MES.
- Instruções para alterar dados diretamente em produção (isso exige chamado/aprovação).
- Qualquer coisa que NÃO esteja embasada no contexto abaixo.

{FEW_SHOTS}

# AGORA RESPONDA (use o contexto abaixo; siga o tom e o formato dos exemplos)

CONTEXTO:
{contexto}

PERGUNTA: {pergunta}

RESPOSTA:"""

    def responder(self, pergunta: str) -> dict:
        """
        Retorna:
          {"tem_resposta": bool, "resposta": str,
           "fontes": [ {fonte, tipo, score} ], "precisa_chamado": bool}
        """
        recuperados = self.recuperar(pergunta)
        melhor_score = recuperados[0][2] if recuperados else 0.0

        # Base sem embasamento suficiente -> não inventa, contorna de forma sucinta.
        if melhor_score < LIMIAR_SIMILARIDADE:
            return {
                "tem_resposta": False,
                "resposta": MSG_SEM_RESPOSTA,
                "fontes": [],
                "precisa_chamado": True,
            }

        docs_mmr = self.recuperar_mmr(pergunta)
        contexto = "\n\n".join(
            f"[Fonte: {d.metadata.get('fonte')} | tipo: {d.metadata.get('tipo')}]\n{d.page_content}"
            for d in docs_mmr
        )
        fontes = [{"fonte": m.get("fonte"), "tipo": m.get("tipo"), "score": round(s, 3)}
                  for _, m, s in recuperados]

        llm = self._get_llm()
        if llm is None:
            resposta = ("[Modo recuperação — sem LLM configurada]\n\n"
                        "Trechos mais relevantes encontrados na base:\n\n" + contexto[:1500])
            return {"tem_resposta": True, "resposta": resposta,
                    "fontes": fontes, "precisa_chamado": False}

        prompt = self._montar_prompt(contexto, pergunta)
        resposta = llm.invoke(prompt).content
        return {"tem_resposta": True, "resposta": resposta,
                "fontes": fontes, "precisa_chamado": False}


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..", "data", "documentos")
    engine = RAGEngine(base)
    n = engine.indexar()
    print(f"Indexados {n} chunks.\n")
    for pergunta in [
        "Como resolver o erro de estrategia de liberacao no pedido de compra?",
        "Qual a politica de ferias do RH?",
    ]:
        print("PERGUNTA:", pergunta)
        r = engine.responder(pergunta)
        print("Tem resposta:", r["tem_resposta"], "| Precisa chamado:", r["precisa_chamado"])
        print("Resposta:", r["resposta"][:300])
        print("-" * 70)
