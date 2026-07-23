# -*- coding: utf-8 -*-
"""
rag_engine.py — PASSOS 4, 5 e 6: Indexação vetorial, recuperação (RAG) e geração
--------------------------------------------------------------------------------
Núcleo do agente (versão revisada — v4):

  PASSO 4 - Indexação vetorial: embeddings (HuggingFace all-MiniLM-L6-v2) + FAISS.
  PASSO 5 - Recuperação: similaridade (limiar) + MMR (contexto diverso).
  PASSO 6 - Geração: LLM Groq com prompt + FEW-SHOTS.

REGRAS DE COMPORTAMENTO (v4):
  - FILTRO DE DOMÍNIO: se a pergunta NÃO for sobre SAP/MES, o agente declina
    educadamente e ENCERRA (não oferece chamado). Ex.: "clima de hoje".
  - Se for do domínio SAP/MES e a base NÃO tiver a resposta, o agente oferece
    registrar um chamado (uma única vez — o app conduz o fluxo).
  - O LLM NUNCA oferece chamado por conta própria: quando não acha a resposta no
    contexto, ele responde apenas com o marcador [SEM_RESPOSTA]. Quem decide
    oferecer o chamado é o motor/aplicação (evita mensagens duplicadas).

Portabilidade: Colab e OCI. Sem GROQ_API_KEY, roda em "modo recuperação".
"""
from __future__ import annotations
import os
import re
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

# ---- Mensagens padronizadas ----
MSG_FORA_ESCOPO = (
    "Sou um assistente especializado em SAP e MES, portanto não consigo ajudar "
    "com esse assunto. Posso apoiar em dúvidas de SAP (MM, PP, QM, WM) ou nas "
    "integrações MES (Opcenter/PAS-X)."
)
MSG_OFERECE_CHAMADO = (
    "Não localizei essa informação na base de conhecimento. Deseja que eu registre "
    "um chamado para um especialista? Se sim, informe a ferramenta: SAP ou MES "
    "(ou responda 'não')."
)
SENTINELA_SEM_RESPOSTA = "[SEM_RESPOSTA]"

# ============ FILTRO DE DOMÍNIO (SAP / MES) ============
# Códigos e tcodes com fronteira de palavra (evita falsos positivos como "como" -> "co").
_PADRAO_CODIGOS = re.compile(
    r"\b(sap|mes|mm|pp|qm|wm|co|fi|sd|ecc|s/?4hana|s/?4|hana|fiori|abap|basis|"
    r"opcenter|pas-?x|pasx|idoc|"
    r"me\d{2}[a-z]?|co\d{2}[a-z]?|md\d{2}[a-z]?|mm\d{2}|qa\d{2}|lt\d{2}|"
    r"migo|miro|mrbr|mmbe|mb52|bd87|we0\d|smq\d|li20|xk05)\b",
    re.IGNORECASE,
)
# Palavras descritivas do domínio (substring é seguro por serem longas).
_PALAVRAS_DOMINIO = [
    "transação", "transacao", "tcode", "pedido de compra", "pedido", "compra",
    "requisição", "requisicao", "fornecedor", "estoque", "material", "mestre",
    "fatura", "nota fiscal", "ordem de produção", "ordem de producao", "mrp",
    "lista técnica", "lista tecnica", "backflush", "inspeção", "inspecao",
    "lote", "certificado", "qualidade", "depósito", "deposito", "transferência",
    "transferencia", "picking", "inventário", "inventario", "consignação",
    "consignacao", "subcontrat", "liberação", "liberacao", "estratégia",
    "estrategia", "autorização", "autorizacao", "liberar acesso", "liberar meu acesso",
    "movimento 101", "movimento 541", "registro info", "migração", "migracao",
]


def is_dominio_sap_mes(texto: str) -> bool:
    """Retorna True se a pergunta tem relação com o ambiente SAP/MES."""
    if _PADRAO_CODIGOS.search(texto or ""):
        return True
    t = (texto or "").lower()
    return any(p in t for p in _PALAVRAS_DOMINIO)


# ============ FEW-SHOTS (exemplos de orientação pergunta -> resposta) ============
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

Exemplo 9 (SAP, mas NÃO está na base — use o marcador):
Pergunta: Preciso liberar meu acesso à transação KSKK do SAP CO.
Resposta: [SEM_RESPOSTA]

Exemplo 10 (SAP, mas NÃO está na base — use o marcador):
Pergunta: Como configurar o esquema de cálculo do módulo SAP CO?
Resposta: [SEM_RESPOSTA]
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
        if self._vectorstore is None:
            raise RuntimeError("Índice não construído. Chame indexar() primeiro.")
        docs = self._vectorstore.similarity_search_with_score(pergunta, k=k)
        resultados = []
        for doc, dist in docs:
            similaridade = 1.0 / (1.0 + float(dist))
            resultados.append((doc.page_content, doc.metadata, similaridade))
        return resultados

    def recuperar_mmr(self, pergunta: str):
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

# COMO RESPONDER QUANDO A RESPOSTA ESTÁ NO CONTEXTO
- Comece pela solução; evite rodeios. Use passos numerados curtos (máximo ~6).
- Cite o TCODE sempre que aplicável (ME29N, MIGO, MIRO, MRBR, CO11N, MD01N, QA32, LT01, BD87).
- Não repita informação. Ao final, cite a fonte entre parênteses.

# REGRA CRÍTICA — QUANDO A RESPOSTA NÃO ESTÁ NO CONTEXTO
- NÃO invente e NÃO dê aula genérica sobre o tema.
- NÃO ofereça abrir chamado (isso é feito pelo sistema).
- Responda EXCLUSIVAMENTE com o marcador, sem nenhuma outra palavra: {SENTINELA_SEM_RESPOSTA}

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
           "fontes": [...], "precisa_chamado": bool, "fora_escopo": bool}
        """
        # 1) FILTRO DE DOMÍNIO — se não é SAP/MES, declina e encerra (sem chamado).
        if not is_dominio_sap_mes(pergunta):
            return {"tem_resposta": False, "resposta": MSG_FORA_ESCOPO,
                    "fontes": [], "precisa_chamado": False, "fora_escopo": True}

        # 2) Recupera e checa o limiar
        recuperados = self.recuperar(pergunta)
        melhor_score = recuperados[0][2] if recuperados else 0.0

        # Nada relevante na base -> oferece chamado (é do domínio SAP/MES)
        if melhor_score < LIMIAR_SIMILARIDADE:
            return {"tem_resposta": False, "resposta": MSG_OFERECE_CHAMADO,
                    "fontes": [], "precisa_chamado": True, "fora_escopo": False}

        # 3) Tem contexto -> gera com a LLM
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
            return {"tem_resposta": True, "resposta": resposta, "fontes": fontes,
                    "precisa_chamado": False, "fora_escopo": False}

        prompt = self._montar_prompt(contexto, pergunta)
        resposta = (llm.invoke(prompt).content or "").strip()

        # LLM não encontrou no contexto -> oferece chamado (domínio SAP/MES)
        if SENTINELA_SEM_RESPOSTA in resposta.upper() or resposta == "":
            return {"tem_resposta": False, "resposta": MSG_OFERECE_CHAMADO,
                    "fontes": [], "precisa_chamado": True, "fora_escopo": False}

        return {"tem_resposta": True, "resposta": resposta, "fontes": fontes,
                "precisa_chamado": False, "fora_escopo": False}


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..", "data", "documentos")
    engine = RAGEngine(base)
    n = engine.indexar()
    print(f"Indexados {n} chunks.\n")
    for pergunta in [
        "Como resolver o erro de estrategia de liberacao no pedido de compra?",  # sabe
        "Preciso liberar meu acesso a transacao KSKK do SAP CO",                 # SAP, nao na base -> chamado
        "Qual o clima de hoje?",                                                 # fora de escopo -> encerra
    ]:
        print("PERGUNTA:", pergunta)
        r = engine.responder(pergunta)
        print(f"  fora_escopo={r['fora_escopo']} | precisa_chamado={r['precisa_chamado']}")
        print("  Resposta:", r["resposta"][:160])
        print("-" * 70)
