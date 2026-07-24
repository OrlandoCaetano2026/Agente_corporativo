# -*- coding: utf-8 -*-
"""
rag_engine.py — PASSOS 4, 5 e 6: Indexação vetorial, recuperação (RAG) e geração
--------------------------------------------------------------------------------
Núcleo do agente (versão revisada — v6):

  PASSO 4 - Indexação vetorial: embeddings (HuggingFace all-MiniLM-L6-v2) + FAISS.
  PASSO 5 - Recuperação: similaridade (limiar) + MMR (contexto diverso).
  PASSO 6 - Geração: LLM Groq com prompt refinado + 5 FEW-SHOTS.

NOVIDADES v6:
  - Fontes consultadas SEM duplicatas (dedupe por arquivo, mantém maior score).
  - CONTINUAÇÃO de conversa herda o domínio SAP/MES e a intenção de PROBLEMA
    (corrige "ainda não resolveu" caindo em fora de escopo / info sem chamado).
  - Detecção de abertura mais robusta (aceita 'incident' sem o 'e').
"""
from __future__ import annotations
import os
import re
from typing import List, Tuple, Optional

from document_loader import carregar_documentos, Chunk

# ============ REGRAS DO RAG (ajuste aqui) ============
LIMIAR_SIMILARIDADE = float(os.getenv("RAG_LIMIAR", "0.45"))
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
FETCH_K = int(os.getenv("RAG_FETCH_K", "12"))
MMR_LAMBDA = float(os.getenv("RAG_MMR_LAMBDA", "0.5"))
LLM_TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS = int(os.getenv("RAG_MAX_TOKENS", "700"))
# =====================================================

# ---- Mensagens padronizadas ----
MSG_FORA_ESCOPO = (
    "Sou um assistente especializado em SAP e MES, portanto não consigo ajudar "
    "com esse assunto. Posso apoiar em dúvidas de SAP (MM, PP, QM, WM) ou nas "
    "integrações MES (Opcenter/PAS-X)."
)
# Perguntas de PROBLEMA sem resposta na base -> encerra cordialmente (o app mostra botão)
MSG_PROBLEMA_SEM_RESPOSTA = (
    "Espero ter ajudado a esclarecer o ponto. 🙏\n\n"
    "Caso o problema **persista** ou precise de uma análise mais aprofundada, "
    "posso registrar um incidente para o time responsável avaliar."
)
# Perguntas INFORMATIVAS sem resposta na base -> apenas informa (SEM chamado)
MSG_INFO_SEM_RESPOSTA = (
    "Não tenho informações suficientes na base de conhecimento para responder essa "
    "pergunta com precisão. Sugiro consultar a documentação no portal da companhia."
)
SENTINELA_SEM_RESPOSTA = "[SEM_RESPOSTA]"

# ============ DETECÇÃO DE INTENÇÃO ============
# Ordem importa: abertura > informativa > problema > continuação.
_GATILHOS_ABERTURA = [
    "abrir chamado", "abrir um chamado", "abrir incidente", "abrir um incidente",
    "abrir incident", "abrir um incident", "abrir ticket", "abrir um ticket",
    "registrar chamado", "registrar um chamado", "registrar incidente",
    "criar chamado", "criar um chamado", "criar incidente", "criar incident",
    "quero um chamado", "preciso abrir um chamado",
    "quero abrir", "gostaria de abrir",
]
_GATILHOS_INFORMATIVA = [
    "o que e", "o que é", "o que faz", "o que significa", "para que serve",
    "para que sirve", "como funciona", "qual a funcao", "qual a função",
    "qual a finalidade", "defina", "definicao", "definição", "explique",
    "significa", "serve para", "pra que serve", "qual o objetivo",
]
_GATILHOS_PROBLEMA = [
    "erro", "nao funciona", "não funciona", "bloqueado", "bloqueada", "nao consigo",
    "não consigo", "falha", "travou", "travado", "nao aparece", "não aparece",
    "nao gera", "não gera", "nao carrega", "não carrega", "problema", "parou",
    "nao esta", "não está", "divergencia", "divergência", "nao replica", "não replica",
]
# Continuações de um problema anterior ("ainda não resolveu", "continua o erro"...).
# Só valem quando há contexto anterior — evita falso positivo em pergunta isolada.
_GATILHOS_CONTINUACAO = [
    "ainda", "continua", "continuo", "persiste", "persistiu",
    "nao resolveu", "não resolveu", "nao resolvi", "não resolvi",
    "nao deu certo", "não deu certo", "mesmo assim", "mesmo apos", "mesmo após",
    "sem sucesso", "sem resultado", "nao adiantou", "não adiantou",
    "segue igual", "permanece", "nao funcionou", "não funcionou",
    "nao consegui resolver", "não consegui resolver", "nao resolveram",
]


def classificar_intencao(texto: str, contexto_anterior: str = "") -> str:
    """Retorna 'abertura' | 'informativa' | 'problema'.

    contexto_anterior: se houver uma pergunta anterior, frases de CONTINUAÇÃO
    ("ainda não resolveu") são tratadas como 'problema', para oferecer chamado.
    """
    t = (texto or "").lower()
    if any(g in t for g in _GATILHOS_ABERTURA):
        return "abertura"
    if any(g in t for g in _GATILHOS_INFORMATIVA):
        return "informativa"
    if any(g in t for g in _GATILHOS_PROBLEMA):
        return "problema"
    # Continuação de um problema já em andamento (precisa de contexto anterior)
    if contexto_anterior and any(g in t for g in _GATILHOS_CONTINUACAO):
        return "problema"
    # Sem gatilho claro: trata como informativa (mais conservador — não força chamado)
    return "informativa"


# ============ FILTRO DE DOMÍNIO (SAP / MES) ============
_PADRAO_CODIGOS = re.compile(
    r"\b(sap|mes|mm|pp|qm|wm|co|fi|sd|ecc|s/?4hana|s/?4|hana|fiori|abap|basis|"
    r"opcenter|pas-?x|pasx|idoc|erp|tcode|"
    r"me\d{2}[a-z]?|co\d{2}[a-z]?|md\d{2}[a-z]?|mm\d{2}|qa\d{2}|qe\d{2}|qp\d{2}|"
    r"qs\d{2}|qc\d{2}|qm\d{2}|lt\d{2}|ls\d{2}|lx\d{2}|lb\d{2}|cs\d{2}|ca\d{2}|"
    r"cr\d{2}|mb\d[a-z0-9]?|mi\d{2}|mk\d{2}|xk\d{2}|"
    r"migo|miro|mrbr|mmbe|mb52|bd87|we0\d|smq\d|li20|xk05)\b",
    re.IGNORECASE,
)
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
    "modulo", "módulo",
]


def is_dominio_sap_mes(texto: str) -> bool:
    """Retorna True se a pergunta tem relação com o ambiente SAP/MES."""
    if _PADRAO_CODIGOS.search(texto or ""):
        return True
    t = (texto or "").lower()
    return any(p in t for p in _PALAVRAS_DOMINIO)


# ============ FEW-SHOTS (5 exemplos de orientação) ============
FEW_SHOTS = """# EXEMPLOS DE COMPORTAMENTO (siga este tom e formato)

Exemplo 1 (Informativa — conceito):
Pergunta: O que é o módulo MM?
Resposta: O MM (Materials Management) é o módulo do SAP para gestão de materiais:
compras, pedidos, entrada de mercadoria, estoques, faturas e mestre de materiais.
(Fonte: Catálogo de Transações SAP)

Exemplo 2 (Informativa — transação):
Pergunta: O que faz a transação MM01?
Resposta: A transação MM01 é utilizada para criar o mestre de material no SAP.
(Fonte: Catálogo de Transações SAP)

Exemplo 3 (Problema — MM):
Pergunta: A fatura foi bloqueada no MIRO por diferença de preço, o que faço?
Resposta:
1. Compare o preço do pedido com o da fatura e confira o registro info.
2. Se o preço do pedido estiver desatualizado, corrija e reprocesse.
3. Se a fatura estiver correta, libere manualmente em MRBR com justificativa.
(Fonte: Base de Conhecimento — SAP MM)

Exemplo 4 (Problema — MES):
Pergunta: A ordem não replica para o Opcenter, IDoc em status 51.
Resposta:
1. Abra o IDoc em WE02/WE19 e leia a mensagem de erro de aplicação.
2. Corrija o dado obrigatório ausente e valide a conexão da interface.
3. Reprocesse o IDoc em BD87.
(Fonte: Base de Conhecimento — Integração/MES)

Exemplo 5 (Não há conteúdo suficiente no contexto):
Pergunta: Qual o procedimento interno para configurar o esquema Z de preço?
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
- Para perguntas conceituais ("o que é", "o que faz"), responda de forma curta e clara.

# COMO RESPONDER QUANDO A RESPOSTA ESTÁ NO CONTEXTO
- Comece pela solução; evite rodeios. Use passos numerados curtos quando for um problema.
- Cite o TCODE sempre que aplicável (ME29N, MIGO, MIRO, MRBR, CO11N, MD01N, QA32, LT01).
- Não repita informação. Ao final, cite a fonte entre parênteses.

# REGRA CRÍTICA — QUANDO A RESPOSTA NÃO ESTÁ NO CONTEXTO
- NÃO invente e NÃO dê aula genérica.
- NÃO ofereça abrir chamado (isso é feito pelo sistema).
- Responda EXCLUSIVAMENTE com o marcador, sem mais nada: {SENTINELA_SEM_RESPOSTA}

{FEW_SHOTS}

# AGORA RESPONDA (use o contexto abaixo; siga o tom e o formato dos exemplos)

CONTEXTO:
{contexto}

PERGUNTA: {pergunta}

RESPOSTA:"""

    @staticmethod
    def _dedupe_fontes(fontes: List[dict]) -> List[dict]:
        """Remove fontes repetidas pelo nome do arquivo, mantendo o MAIOR score.

        O mesmo documento é quebrado em vários chunks; sem isso, um único
        arquivo (ex.: Chamados_Incidentes_Abertos.xlsx) apareceria várias vezes
        no box 'Fontes consultadas'. Aqui consolidamos por nome de arquivo.
        """
        melhor_por_fonte: dict = {}
        for f in fontes:
            nome = f.get("fonte")
            atual = melhor_por_fonte.get(nome)
            if atual is None or f.get("score", 0) > atual.get("score", 0):
                melhor_por_fonte[nome] = f
        return sorted(melhor_por_fonte.values(),
                      key=lambda x: x.get("score", 0), reverse=True)

    def responder(self, pergunta: str, contexto_anterior: str = "") -> dict:
        """
        Retorna:
          {"tem_resposta": bool, "resposta": str, "fontes": [...],
           "precisa_chamado": bool, "fora_escopo": bool, "intencao": str}

        contexto_anterior: última mensagem do usuário na conversa. Usado para que
        uma CONTINUAÇÃO ("ainda não resolveu") herde o domínio SAP/MES e a
        intenção de PROBLEMA da pergunta anterior.
        """
        intencao = classificar_intencao(pergunta, contexto_anterior)

        # 1) FILTRO DE DOMÍNIO — se não é SAP/MES, declina e encerra (sem chamado).
        #    Considera também o contexto anterior: se a conversa JÁ era SAP/MES,
        #    a continuação herda o domínio (corrige o bug de "fora de escopo").
        no_dominio = is_dominio_sap_mes(pergunta) or is_dominio_sap_mes(contexto_anterior)
        if not no_dominio:
            return {"tem_resposta": False, "resposta": MSG_FORA_ESCOPO, "fontes": [],
                    "precisa_chamado": False, "fora_escopo": True, "intencao": intencao}

        # 2) Recupera e checa o limiar.
        #    Se houver contexto anterior, enriquece a busca (a continuação sozinha
        #    — "ainda não resolveu" — tem pouca informação recuperável).
        consulta = (contexto_anterior + " " + pergunta).strip() if contexto_anterior else pergunta
        recuperados = self.recuperar(consulta)
        melhor_score = recuperados[0][2] if recuperados else 0.0

        if melhor_score < LIMIAR_SIMILARIDADE:
            # Sem base: o comportamento depende da INTENÇÃO
            if intencao == "problema":
                return {"tem_resposta": False, "resposta": MSG_PROBLEMA_SEM_RESPOSTA,
                        "fontes": [], "precisa_chamado": True, "fora_escopo": False,
                        "intencao": intencao}
            else:  # informativa
                return {"tem_resposta": False, "resposta": MSG_INFO_SEM_RESPOSTA,
                        "fontes": [], "precisa_chamado": False, "fora_escopo": False,
                        "intencao": intencao}

        # 3) Tem contexto -> gera com a LLM
        docs_mmr = self.recuperar_mmr(consulta)
        contexto = "\n\n".join(
            f"[Fonte: {d.metadata.get('fonte')} | tipo: {d.metadata.get('tipo')}]\n{d.page_content}"
            for d in docs_mmr
        )
        fontes = [{"fonte": m.get("fonte"), "tipo": m.get("tipo"), "score": round(s, 3)}
                  for _, m, s in recuperados]
        # Consolida fontes repetidas (mesmo arquivo em vários chunks)
        fontes = self._dedupe_fontes(fontes)

        llm = self._get_llm()
        if llm is None:
            resposta = ("[Modo recuperação — sem LLM configurada]\n\n"
                        "Trechos mais relevantes encontrados na base:\n\n" + contexto[:1500])
            return {"tem_resposta": True, "resposta": resposta, "fontes": fontes,
                    "precisa_chamado": False, "fora_escopo": False, "intencao": intencao}

        prompt = self._montar_prompt(contexto, pergunta)
        resposta = (llm.invoke(prompt).content or "").strip()

        # LLM não encontrou no contexto -> depende da intenção
        if SENTINELA_SEM_RESPOSTA in resposta.upper() or resposta == "":
            if intencao == "problema":
                return {"tem_resposta": False, "resposta": MSG_PROBLEMA_SEM_RESPOSTA,
                        "fontes": [], "precisa_chamado": True, "fora_escopo": False,
                        "intencao": intencao}
            else:
                return {"tem_resposta": False, "resposta": MSG_INFO_SEM_RESPOSTA,
                        "fontes": [], "precisa_chamado": False, "fora_escopo": False,
                        "intencao": intencao}

        return {"tem_resposta": True, "resposta": resposta, "fontes": fontes,
                "precisa_chamado": False, "fora_escopo": False, "intencao": intencao}


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..", "data", "documentos")
    engine = RAGEngine(base)
    n = engine.indexar()
    print(f"Indexados {n} chunks.\n")
    testes = [
        "O que é SAP?",
        "O que faz a transacao MM01?",
        "Erro ao liberar pedido de compra na ME29N",
        "Quero abrir um chamado",
        "Qual o clima de hoje?",
    ]
    for p in testes:
        r = engine.responder(p)
        print("P:", p)
        print(f"  intencao={r['intencao']} | fora_escopo={r['fora_escopo']} | precisa_chamado={r['precisa_chamado']}")
        print("  R:", r["resposta"][:120])
        print("-"*70)
