# -*- coding: utf-8 -*-
"""
main.py — PASSO 7: Interface conversacional (Streamlit)
-------------------------------------------------------
Interface do Agente de Suporte SAP da Orla_Tech (v5).

Fluxos suportados:
  1) Pergunta INFORMATIVA ("o que é/faz X") -> responde; se não achar, só informa.
  2) Pergunta de PROBLEMA ("erro/não funciona") -> responde; se não achar, oferece chamado.
  3) Fora de SAP/MES -> declina educadamente e encerra (sem chamado).
  4) ABERTURA DIRETA ("quero abrir um chamado") -> pede a descrição, detecta
     ferramenta/módulo, pergunta a prioridade (P1-P4) e cria o chamado.

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
#   None | {"etapa": "descricao"|"ferramenta"|"prioridade", "descricao": str, ...}
if "chamado" not in st.session_state:
    st.session_state.chamado = None

for m in st.session_state.mensagens:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])


def responder(texto):
    st.markdown(texto)
    st.session_state.mensagens.append({"role": "assistant", "content": texto})


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


def iniciar_prioridade(descricao):
    """Detecta ferramenta/módulo e pede a prioridade."""
    info = analisar(descricao)
    st.session_state.chamado = {
        "etapa": "prioridade", "descricao": descricao,
        "ferramenta": info["ferramenta"], "modulo": info["modulo"],
        "categoria": info["categoria"],
    }
    responder(
        f"Entendido! Analisei a solicitação e identifiquei:\n"
        f"- **Ferramenta:** {info['ferramenta']}\n"
        f"- **Módulo:** {info['modulo']} ({info['categoria']})\n\n"
        f"Qual a **prioridade** do incidente?\n"
        f"- **P1** – Crítico (4h)\n- **P2** – Urgente (8h)\n"
        f"- **P3** – Médio (16h)\n- **P4** – Leve (24h)"
    )


if pergunta := st.chat_input("Digite sua dúvida ou 'quero abrir um chamado'..."):
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    c = st.session_state.chamado

    with st.chat_message("assistant"):
        # ===== FLUXO DE CHAMADO EM ANDAMENTO =====
        if c is not None:
            if _nao(pergunta):
                responder("Sem problemas, não abri nenhum chamado. Posso ajudar em algo mais? 😊")
                st.session_state.chamado = None

            # Etapa: aguardando a DESCRIÇÃO do chamado (abertura direta)
            elif c["etapa"] == "descricao":
                iniciar_prioridade(pergunta)

            # Etapa: escolher a FERRAMENTA (vindo de um problema não resolvido)
            elif c["etapa"] == "ferramenta":
                txt = pergunta.strip().lower()
                info = analisar(c["descricao"])
                if "mes" in txt:
                    ferramenta = "MES"
                elif "sap" in txt:
                    ferramenta = "SAP"
                else:
                    ferramenta = info["ferramenta"]
                st.session_state.chamado.update({
                    "etapa": "prioridade", "ferramenta": ferramenta,
                    "modulo": info["modulo"], "categoria": info["categoria"],
                })
                responder(
                    f"Ferramenta **{ferramenta}** · módulo **{info['modulo']}** "
                    f"({info['categoria']}).\n\nQual a **prioridade**?\n"
                    f"- **P1** – Crítico (4h)\n- **P2** – Urgente (8h)\n"
                    f"- **P3** – Médio (16h)\n- **P4** – Leve (24h)"
                )

            # Etapa: escolher a PRIORIDADE e CRIAR
            elif c["etapa"] == "prioridade":
                prio = parse_prioridade(pergunta)
                if prio is None:
                    responder("Não identifiquei a prioridade. Responda **P1**, **P2**, **P3** ou **P4** (ou 1-4).")
                else:
                    ticket = Ticket(
                        descricao=c["descricao"], modulo=c["modulo"],
                        ferramenta=c["ferramenta"], categoria=c["categoria"],
                        prioridade=prio,
                    )
                    r = create_ticket(ticket, confirmado=True)
                    responder("✅ " + r["mensagem"])
                    st.session_state.chamado = None

        # ===== SEM FLUXO ATIVO =====
        else:
            # O usuário quer ABRIR um chamado diretamente?
            if classificar_intencao(pergunta) == "abertura":
                st.session_state.chamado = {"etapa": "descricao"}
                responder("Claro! Descreva brevemente o **problema ou a solicitação** "
                          "que deseja registrar no chamado.")
            else:
                # Pergunta normal (RAG)
                with st.spinner("Consultando a base de conhecimento..."):
                    r = engine.responder(pergunta)
                responder(r["resposta"])

                if r.get("fontes"):
                    with st.expander("📚 Fontes consultadas"):
                        for f in r["fontes"]:
                            st.write(f"- **{f['fonte']}** ({f['tipo']}) · relevância {f['score']}")

                # Só inicia fluxo de chamado quando for PROBLEMA sem resposta
                if r.get("precisa_chamado"):
                    st.session_state.chamado = {"descricao": pergunta, "etapa": "ferramenta"}


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
    st.caption("Desenvolvido por Orlando Caetano")
    st.markdown("[LinkedIn](https://www.linkedin.com/in/orlando-caetano/)  |  [Repositorio](https://github.com/OrlandoCaetano2026/Agente_corporativo")
