# -*- coding: utf-8 -*-
"""
main.py — PASSO 7: Interface conversacional (Streamlit)
-------------------------------------------------------
Interface do Agente de Suporte SAP da Orla_Tech (v4).

Fluxo de abertura de chamado (guiado, sem loop):
  1. Pergunta normal -> RAG responde se houver base.
  2. Se a pergunta NÃO for de SAP/MES -> o agente declina e ENCERRA (não oferece chamado).
  3. Se for de SAP/MES e a base não tiver a resposta -> oferece chamado (uma única vez).
  4. Usuário escolhe a FERRAMENTA (SAP/MES) -> o módulo é detectado automaticamente.
  5. Usuário escolhe a PRIORIDADE (P1/P2/P3/P4) -> o chamado é criado.

Executar: streamlit run app/main.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import streamlit as st
from rag_engine import RAGEngine
from ticket_service import Ticket, create_ticket, analisar, PRIORIDADE_LABEL

DOCS = os.path.join(BASE_DIR, "data", "documentos")

st.set_page_config(page_title="Agente SAP · Orla_Tech", page_icon="🤖", layout="centered")


@st.cache_resource(show_spinner="Indexando a base de conhecimento...")
def carregar_engine():
    eng = RAGEngine(DOCS)
    eng.indexar()
    return eng


st.title("🤖 Agente de Suporte SAP — Orla_Tech")
st.caption("Especialista SAP · MM (foco), PP, QM, WM · ECC e S/4HANA · MES Opcenter e PAS-X")

engine = carregar_engine()

if "mensagens" not in st.session_state:
    st.session_state.mensagens = [
        {"role": "assistant",
         "content": "Olá! Sou o especialista de suporte SAP da Orla_Tech. Como posso ajudar você hoje?"}
    ]
# Estado do fluxo de chamado: None | {"descricao","etapa": "ferramenta"|"prioridade", ...}
if "chamado" not in st.session_state:
    st.session_state.chamado = None

for m in st.session_state.mensagens:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])


def responder_assistente(texto):
    st.markdown(texto)
    st.session_state.mensagens.append({"role": "assistant", "content": texto})


def _sim(t): return t.strip().lower() in {"sim", "s", "yes", "y", "pode", "quero", "confirmo", "ok"}
def _nao(t): return t.strip().lower() in {"nao", "não", "n", "no", "cancela", "cancelar"}

PRIOR_MAP = {
    "1": "P1", "p1": "P1", "critico": "P1", "crítico": "P1",
    "2": "P2", "p2": "P2", "urgente": "P2",
    "3": "P3", "p3": "P3", "medio": "P3", "médio": "P3",
    "4": "P4", "p4": "P4", "leve": "P4",
}

def parse_prioridade(texto):
    t = texto.strip().lower()
    for chave, val in PRIOR_MAP.items():
        if chave in t:
            return val
    return None


if pergunta := st.chat_input("Digite sua dúvida sobre SAP..."):
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    c = st.session_state.chamado

    with st.chat_message("assistant"):
        # ===== FLUXO DE CHAMADO EM ANDAMENTO =====
        if c is not None:
            # ETAPA 1 — escolher a ferramenta (ou cancelar)
            if c["etapa"] == "ferramenta":
                if _nao(pergunta):
                    responder_assistente("Sem problemas, não abri nenhum chamado. Posso ajudar em algo mais? 😊")
                    st.session_state.chamado = None
                else:
                    txt = pergunta.strip().lower()
                    info = analisar(c["descricao"])
                    if "mes" in txt:
                        ferramenta = "MES"
                    elif "sap" in txt:
                        ferramenta = "SAP"
                    else:
                        ferramenta = info["ferramenta"]  # sugestão automática
                    c["ferramenta"] = ferramenta
                    c["modulo"] = info["modulo"]
                    c["categoria"] = info["categoria"]
                    c["etapa"] = "prioridade"
                    responder_assistente(
                        f"Entendido! Ferramenta **{ferramenta}** · módulo detectado "
                        f"**{info['modulo']}** ({info['categoria']}).\n\n"
                        f"Qual a **prioridade** do incidente?\n"
                        f"- **P1** – Crítico (4h)\n- **P2** – Urgente (8h)\n"
                        f"- **P3** – Médio (16h)\n- **P4** – Leve (24h)"
                    )

            # ETAPA 2 — escolher a prioridade e CRIAR
            elif c["etapa"] == "prioridade":
                prio = parse_prioridade(pergunta)
                if prio is None:
                    responder_assistente(
                        "Não identifiquei a prioridade. Responda com **P1**, **P2**, **P3** ou **P4** "
                        "(ou 1, 2, 3, 4)."
                    )
                else:
                    ticket = Ticket(
                        descricao=c["descricao"], modulo=c["modulo"],
                        ferramenta=c["ferramenta"], categoria=c["categoria"],
                        prioridade=prio,
                    )
                    r = create_ticket(ticket, confirmado=True)
                    responder_assistente("✅ " + r["mensagem"])
                    st.session_state.chamado = None

        # ===== PERGUNTA NORMAL (RAG) =====
        else:
            with st.spinner("Consultando a base de conhecimento..."):
                r = engine.responder(pergunta)
            responder_assistente(r["resposta"])

            if r.get("fontes"):
                with st.expander("📚 Fontes consultadas"):
                    for f in r["fontes"]:
                        st.write(f"- **{f['fonte']}** ({f['tipo']}) · relevância {f['score']}")

            # Só inicia o fluxo de chamado quando o agente OFERECEU (domínio SAP/MES sem resposta)
            if r.get("precisa_chamado"):
                st.session_state.chamado = {"descricao": pergunta, "etapa": "ferramenta"}
            # fora_escopo=True -> não faz nada (encerra), não oferece chamado


with st.sidebar:
    st.header("ℹ️ Sobre")
    st.write("Agente RAG **especialista SAP** da Orla_Tech Consultoria.")
    st.write("Responde apenas temas de **SAP** (MM, PP, QM, WM) e **MES** (Opcenter/PAS-X). "
             "Fora disso, informa a limitação e encerra.")
    st.write("Quando não há resposta na base para um tema SAP/MES, oferece registrar "
             "um chamado no **ServiceToday**: escolha a **ferramenta** (SAP/MES), o "
             "**módulo** é detectado automaticamente e você define a **prioridade** (P1-P4).")
    st.divider()
    st.caption("SLA: P1-Crítico 4h · P2-Urgente 8h · P3-Médio 16h · P4-Leve 24h")
    if st.button("🔄 Reiniciar conversa"):
        st.session_state.mensagens = st.session_state.mensagens[:1]
        st.session_state.chamado = None
        st.rerun()
