# -*- coding: utf-8 -*-
"""
main.py — PASSO 7: Interface conversacional (Streamlit)
-------------------------------------------------------
Interface web do Agente Corporativo de Suporte SAP da Orla_Tech.

Fluxo implementado (exatamente o do infográfico):
  1. Colaborador faz a pergunta.
  2. O agente consulta a base (RAG) e responde se houver embasamento.
  3. Se NÃO houver, informa educadamente que não sabe e PERGUNTA se deseja
     abrir um chamado.
  4. Se o usuário confirmar (sim), cria o chamado com número sequencial único
     e registra na base (via ticket_service).

Executar:
  streamlit run app/main.py
"""
import os
import sys

# garante que a pasta src esteja no path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import streamlit as st
from rag_engine import RAGEngine
from ticket_service import Ticket, create_ticket

DOCS = os.path.join(BASE_DIR, "data", "documentos")

st.set_page_config(page_title="Agente SAP · Orla_Tech", page_icon="🤖", layout="centered")


@st.cache_resource(show_spinner="Indexando a base de conhecimento...")
def carregar_engine():
    eng = RAGEngine(DOCS)
    eng.indexar()
    return eng


# ---------- Cabeçalho ----------
st.title("🤖 Agente de Suporte SAP — Orla_Tech")
st.caption("Base de conhecimento de MM (foco), PP, QM, WM · ECC e S/4HANA · MES Opcenter e PAS-X")

engine = carregar_engine()

# ---------- Estado da conversa ----------
if "mensagens" not in st.session_state:
    st.session_state.mensagens = [
        {"role": "assistant",
         "content": "Olá! Sou o assistente de suporte SAP da Orla_Tech. "
                    "Como posso ajudar você hoje?"}
    ]
if "pendente_chamado" not in st.session_state:
    st.session_state.pendente_chamado = None  # guarda a última pergunta sem resposta

# Renderiza histórico
for m in st.session_state.mensagens:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])


def _confirmou(texto: str) -> bool:
    return texto.strip().lower() in {"sim", "s", "yes", "y", "pode", "confirmo", "quero"}


def _negou(texto: str) -> bool:
    return texto.strip().lower() in {"nao", "não", "n", "no", "nao quero", "não quero"}


# ---------- Entrada do usuário ----------
if pergunta := st.chat_input("Digite sua dúvida sobre SAP..."):
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        # Caso 1: estamos aguardando confirmação para abrir chamado
        if st.session_state.pendente_chamado:
            if _confirmou(pergunta):
                dados = st.session_state.pendente_chamado
                ticket = Ticket(
                    modulo=dados.get("modulo", "MM"),
                    sistema=dados.get("sistema", "S/4HANA"),
                    categoria=dados.get("categoria", "SAP MM"),
                    titulo=dados["pergunta"][:60],
                    descricao=dados["pergunta"],
                    prioridade="Media",
                )
                r = create_ticket(ticket, confirmado=True)
                resposta = "✅ " + r["mensagem"]
                st.session_state.pendente_chamado = None
            elif _negou(pergunta):
                resposta = ("Sem problemas! Não abri nenhum chamado. "
                            "Se precisar de mais alguma coisa, é só perguntar. 😊")
                st.session_state.pendente_chamado = None
            else:
                resposta = "Só para confirmar: deseja que eu **abra o chamado**? Responda **sim** ou **não**."
            st.markdown(resposta)
            st.session_state.mensagens.append({"role": "assistant", "content": resposta})

        # Caso 2: pergunta normal -> consulta RAG
        else:
            with st.spinner("Consultando a base de conhecimento..."):
                r = engine.responder(pergunta)

            resposta = r["resposta"]

            if r["precisa_chamado"]:
                # guarda a pergunta para, se confirmado, virar chamado
                st.session_state.pendente_chamado = {"pergunta": pergunta,
                                                       "modulo": "MM", "sistema": "S/4HANA",
                                                       "categoria": "SAP MM"}
            st.markdown(resposta)

            if r["fontes"]:
                with st.expander("📚 Fontes consultadas"):
                    for f in r["fontes"]:
                        st.write(f"- **{f['fonte']}** ({f['tipo']}) · relevância {f['score']}")

            st.session_state.mensagens.append({"role": "assistant", "content": resposta})

# ---------- Rodapé ----------
with st.sidebar:
    st.header("ℹ️ Sobre")
    st.write("Agente RAG corporativo da **Orla_Tech Consultoria**.")
    st.write("Quando não encontra a resposta, ele pede confirmação e abre um "
             "chamado no **ServiceToday** com número sequencial único.")
    if st.button("🔄 Reiniciar conversa"):
        st.session_state.mensagens = st.session_state.mensagens[:1]
        st.session_state.pendente_chamado = None
        st.rerun()
