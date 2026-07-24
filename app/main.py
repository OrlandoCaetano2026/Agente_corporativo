# -*- coding: utf-8 -*-
"""
main.py — PASSO 7: Interface conversacional (Streamlit)
-------------------------------------------------------
Interface do Agente de Suporte SAP da Orla_Tech (v6).

Fluxos suportados:
  1) Pergunta INFORMATIVA ("o que é/faz X") -> responde; se não achar, só informa.
  2) Pergunta de PROBLEMA ("erro/não funciona") -> responde; se não resolver,
     encerra cordialmente e oferece o BOTÃO "Abrir incidente".
  3) Fora de SAP/MES -> declina educadamente e encerra (sem botão/chamado).
  4) ABERTURA DIRETA ("quero abrir um chamado") -> pede a descrição e segue
     para a escolha de prioridade por BOTÕES (P1-P4).

Novidades v6:
  - Continuação de conversa herda o domínio SAP/MES (corrige "fora de escopo").
  - Fontes consultadas sem duplicatas (dedupe no rag_engine).
  - Abertura de incidente por BOTÃO + prioridade em 4 BOTÕES (P1-P4).

Executar: streamlit run app/main.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import streamlit as st
from rag_engine import RAGEngine, classificar_intencao
from ticket_service import Ticket, create_ticket, analisar

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
         "content": "Olá! Sou o especialista de suporte SAP da Orla_Tech. Como posso ajudar?\n\n"
                    "Você pode tirar dúvidas (ex.: *\"O que faz a MM01?\"*) ou dizer "
                    "*\"quero abrir um chamado\"*."}
    ]
# Estado do fluxo de chamado:
#   None
#   | {"etapa": "descricao"}                         -> abertura direta (aguarda descrição)
#   | {"etapa": "oferta", "descricao": str}          -> problema sem solução (mostra botão)
#   | {"etapa": "prioridade", "descricao","ferramenta","modulo","categoria"}
if "chamado" not in st.session_state:
    st.session_state.chamado = None


def _ultima_pergunta_usuario():
    """Retorna a última mensagem do usuário (para dar contexto à continuação)."""
    for m in reversed(st.session_state.mensagens):
        if m["role"] == "user":
            return m["content"]
    return ""


for m in st.session_state.mensagens:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])


def registrar(texto):
    """Exibe e guarda a mensagem do assistente no histórico."""
    st.markdown(texto)
    st.session_state.mensagens.append({"role": "assistant", "content": texto})


PRIOR_LABEL = {
    "P1": "🔴 P1 · Crítico", "P2": "🟠 P2 · Alto",
    "P3": "🟡 P3 · Médio", "P4": "🟢 P4 · Leve",
}


def _preparar_prioridade(descricao):
    """Detecta ferramenta/módulo e coloca o fluxo na etapa de prioridade."""
    info = analisar(descricao)
    st.session_state.chamado = {
        "etapa": "prioridade", "descricao": descricao,
        "ferramenta": info["ferramenta"], "modulo": info["modulo"],
        "categoria": info["categoria"],
    }


# =========================================================
# ENTRADA DO USUÁRIO (chat)
# =========================================================
if pergunta := st.chat_input("Digite sua dúvida ou 'quero abrir um chamado'..."):
    contexto_anterior = _ultima_pergunta_usuario()  # antes de anexar a atual

    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        # Abertura direta em andamento: a mensagem é a descrição do chamado
        if st.session_state.chamado and st.session_state.chamado.get("etapa") == "descricao":
            _preparar_prioridade(pergunta)
            registrar("Perfeito! Já analisei a solicitação. "
                      "Selecione abaixo a **prioridade** do incidente. 👇")

        # Usuário pediu explicitamente para abrir um chamado
        elif classificar_intencao(pergunta) == "abertura":
            st.session_state.chamado = {"etapa": "descricao"}
            registrar("Claro! Descreva brevemente o **problema ou a solicitação** "
                      "que deseja registrar no chamado.")

        # Pergunta normal -> RAG (com contexto da conversa anterior)
        else:
            with st.spinner("Consultando a base de conhecimento..."):
                r = engine.responder(pergunta, contexto_anterior=contexto_anterior)
            registrar(r["resposta"])

            if r.get("fontes"):
                with st.expander("📚 Fontes consultadas"):
                    for f in r["fontes"]:
                        st.write(f"- **{f['fonte']}** ({f['tipo']}) · relevância {f['score']}")

            # Problema SAP/MES sem solução -> encerra cordialmente e oferece o botão
            if r.get("precisa_chamado"):
                descricao = (contexto_anterior + " " + pergunta).strip() if contexto_anterior else pergunta
                st.session_state.chamado = {"etapa": "oferta", "descricao": descricao}


# =========================================================
# ÁREA DE AÇÕES (botões) — renderizada sempre, sobrevive a reruns
# =========================================================
c = st.session_state.chamado

# --- Botão "Abrir incidente" (problema sem solução) ---
if c and c.get("etapa") == "oferta":
    col_a, col_b = st.columns([1, 2])
    with col_a:
        if st.button("🎫 Abrir incidente", type="primary", use_container_width=True):
            _preparar_prioridade(c["descricao"])
            st.rerun()
    with col_b:
        if st.button("Não, obrigado", use_container_width=True):
            st.session_state.chamado = None
            st.session_state.mensagens.append(
                {"role": "assistant",
                 "content": "Sem problemas! Fico à disposição para outras dúvidas. 😊"})
            st.rerun()

# --- Botões de PRIORIDADE (P1-P4) ---
elif c and c.get("etapa") == "prioridade":
    st.markdown(
        f"**Incidente identificado** · Ferramenta: **{c['ferramenta']}** · "
        f"Módulo: **{c['modulo']}** ({c['categoria']})"
    )
    st.caption("Selecione a prioridade (SLA): 🔴 P1 4h · 🟠 P2 8h · 🟡 P3 16h · 🟢 P4 24h")
    cols = st.columns(4)
    for i, prio in enumerate(["P1", "P2", "P3", "P4"]):
        with cols[i]:
            if st.button(PRIOR_LABEL[prio], key=f"prio_{prio}", use_container_width=True):
                ticket = Ticket(
                    descricao=c["descricao"], modulo=c["modulo"],
                    ferramenta=c["ferramenta"], categoria=c["categoria"],
                    prioridade=prio,
                )
                res = create_ticket(ticket, confirmado=True)
                st.session_state.mensagens.append(
                    {"role": "assistant", "content": "✅ " + res["mensagem"]})
                st.session_state.chamado = None
                st.rerun()
    if st.button("Cancelar", key="prio_cancel"):
        st.session_state.chamado = None
        st.session_state.mensagens.append(
            {"role": "assistant", "content": "Abertura de chamado cancelada. 😊"})
        st.rerun()


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("ℹ️ Sobre")
    st.write("Agente RAG **especialista SAP** da Orla_Tech Consultoria.")
    st.write("Responde dúvidas de **SAP** (MM, PP, QM, WM) e **MES** (Opcenter/PAS-X), "
             "incluindo conceitos e transações (tcodes).")
    st.write("Para **problemas sem solução na base** ou quando você pede, ele registra "
             "um chamado no **ServiceToday**: detecta a ferramenta e o módulo e você "
             "define a **prioridade** (P1-P4).")
    st.divider()
    st.caption("SLA: P1-Crítico 4h · P2-Urgente 8h · P3-Médio 16h · P4-Leve 24h")
    if st.button("🔄 Reiniciar conversa"):
        st.session_state.mensagens = st.session_state.mensagens[:1]
        st.session_state.chamado = None
        st.rerun()

    st.divider()
    st.markdown("<p style='font-size:15px;font-weight:700;margin:8px 0 8px'>Desenvolvido por Orlando Caetano</p>", unsafe_allow_html=True)
    st.markdown("<p style='margin:4px 0'><a href='https://www.linkedin.com/in/orlando-caetano/' target='_blank' style='text-decoration:none;color:inherit'><img src='https://img.icons8.com/color/48/linkedin.png' width='16' style='vertical-align:middle;margin-right:8px'>Orlando Caetano</a></p>", unsafe_allow_html=True)
    st.markdown("<p style='margin:4px 0'><a href='https://github.com/OrlandoCaetano2026/Agente_corporativo' target='_blank' style='text-decoration:none;color:inherit'><img src='https://cdn.simpleicons.org/github/FFFFFF' width='16' style='vertical-align:middle;margin-right:8px'>Repositorio do Projeto</a></p>", unsafe_allow_html=True)
