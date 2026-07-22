# -*- coding: utf-8 -*-
"""
rag_engine.py — PASSOS 4, 5 e 6: Indexação vetorial, recuperação (RAG) e geração
--------------------------------------------------------------------------------
Este módulo implementa o núcleo do agente:

  PASSO 4 - Indexação vetorial:
      Gera embeddings dos chunks (via LangChain + HuggingFace) e cria um índice
      FAISS em memória para busca por similaridade.

  PASSO 5 - Camada de recuperação (Retriever):
      Dada a pergunta do usuário, recupera os trechos mais relevantes da base.

  PASSO 6 - Geração e validação da resposta:
      Monta o contexto e chama a LLM. Se o contexto recuperado NÃO for suficiente
      (baixa similaridade), o agente NÃO inventa: informa que não sabe e sinaliza
      que é necessária ação humana -> abertura de chamado (ver ticket_service.py).

Observação de portabilidade:
  - Projetado para rodar no Google Colab e no OCI.
  - A LLM é plugável (GROQ por padrão, ex.: Llama 3.3 70B). Se não houver chave de
    API (GROQ_API_KEY), o motor funciona em "modo recuperação" (retorna os trechos
    encontrados) para permitir testes locais sem custo.
"""
from __future__ import annotations
import os
from typing import List, Tuple, Optional

from document_loader import carregar_documentos, Chunk

# Limiar de similaridade: abaixo disso, consideramos que a base NÃO tem resposta.
LIMIAR_SIMILARIDADE = float(os.getenv("RAG_LIMIAR", "0.35"))
TOP_K = int(os.getenv("RAG_TOP_K", "4"))


class RAGEngine:
    def __init__(self, pasta_documentos: str, modelo_embeddings: str = "sentence-transformers/all-MiniLM-L6-v2"):
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
        """Retorna [(texto, metadados, score_similaridade)] ordenado por relevância."""
        if self._vectorstore is None:
            raise RuntimeError("Índice não construído. Chame indexar() primeiro.")
        # FAISS retorna distância L2 (menor = mais similar). Convertendo em similaridade.
        docs = self._vectorstore.similarity_search_with_score(pergunta, k=k)
        resultados = []
        for doc, dist in docs:
            similaridade = 1.0 / (1.0 + float(dist))  # 0..1 (maior = melhor)
            resultados.append((doc.page_content, doc.metadata, similaridade))
        return resultados

    # ---------- PASSO 6: geração ----------
    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        # Usa a GROQ API (rápida e gratuita). Modelo configurável por variável de ambiente.
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        from langchain_groq import ChatGroq
        modelo = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._llm = ChatGroq(model=modelo, temperature=0.1)
        return self._llm

    def responder(self, pergunta: str) -> dict:
        """
        Retorna um dicionário:
          {
            "tem_resposta": bool,
            "resposta": str,
            "fontes": [ {fonte, tipo, score} ],
            "precisa_chamado": bool
          }
        """
        recuperados = self.recuperar(pergunta)
        melhor_score = recuperados[0][2] if recuperados else 0.0

        # Base NÃO tem embasamento suficiente -> não inventa, sinaliza ação humana.
        if melhor_score < LIMIAR_SIMILARIDADE:
            return {
                "tem_resposta": False,
                "resposta": (
                    "Não encontrei essa informação na base de conhecimento e ela "
                    "precisa de validação de um especialista humano. "
                    "Deseja que eu abra um chamado no ServiceToday? (sim/não)"
                ),
                "fontes": [],
                "precisa_chamado": True,
            }

        contexto = "\n\n".join(
            f"[Fonte: {m.get('fonte')} | tipo: {m.get('tipo')}]\n{t}"
            for t, m, s in recuperados
        )
        fontes = [{"fonte": m.get("fonte"), "tipo": m.get("tipo"), "score": round(s, 3)}
                  for _, m, s in recuperados]

        llm = self._get_llm()
        if llm is None:
            # Modo sem LLM (teste local): devolve os trechos recuperados.
            resposta = ("[Modo recuperação — sem LLM configurada]\n\n"
                        "Trechos mais relevantes encontrados na base:\n\n" + contexto[:1500])
            return {"tem_resposta": True, "resposta": resposta,
                    "fontes": fontes, "precisa_chamado": False}

        prompt = f"""Você é o assistente de suporte SAP da Orla_Tech Consultoria.
Responda à pergunta do colaborador APENAS com base no contexto abaixo.
Se o contexto não contiver a resposta, diga que não sabe e que é necessário abrir um chamado.
Seja objetivo, use passo a passo quando fizer sentido e cite a fonte.

CONTEXTO:
{contexto}

PERGUNTA: {pergunta}

RESPOSTA:"""
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
        "Qual a receita de bolo de chocolate?",  # fora do escopo -> deve pedir chamado
    ]:
        print("PERGUNTA:", pergunta)
        r = engine.responder(pergunta)
        print("Tem resposta:", r["tem_resposta"], "| Precisa chamado:", r["precisa_chamado"])
        print("Resposta:", r["resposta"][:300])
        print("-" * 70)
