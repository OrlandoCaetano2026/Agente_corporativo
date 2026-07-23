# -*- coding: utf-8 -*-
"""
ticket_service.py
-----------------
Serviço de criação de chamados (tickets) do agente Orla_Tech Consultoria.

Recursos:
- Seleção de FERRAMENTA de destino: SAP ou MES.
- DETECÇÃO AUTOMÁTICA do módulo (MM, PP, QM, WM ou MES) a partir do texto.
- Escala de PRIORIDADE P1-P4 (P1-Crítico, P2-Urgente, P3-Médio, P4-Leve) com SLA.
- Número de chamado sequencial e único (nunca colide com os existentes).
- O agente só cria o chamado APÓS a confirmação do usuário.

Formato do ID: INC00XXXXXX  (ex.: INC0010256)
"""
from __future__ import annotations
import os
import re
import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd
from openpyxl import load_workbook

DEFAULT_XLSX = os.getenv(
    "TICKETS_XLSX",
    os.path.join(os.path.dirname(__file__), "..", "data", "documentos",
                 "Chamados_Incidentes_Abertos.xlsx"),
)
SHEET = "Chamados_Abertos"
ID_PREFIX = "INC"
ID_WIDTH = 7

# ----- Escala de prioridade P1-P4 (com SLA em horas) -----
PRIORIDADE_SLA = {"P1": 4, "P2": 8, "P3": 16, "P4": 24}
PRIORIDADE_LABEL = {
    "P1": "P1 - Critico", "P2": "P2 - Urgente",
    "P3": "P3 - Medio", "P4": "P4 - Leve",
}

# ----- Responsáveis e categorias por módulo -----
MODULO_RESPONSAVEL = {
    "MM": "Time MM", "PP": "Time PP", "QM": "Time QM", "WM": "Time WM",
    "MES": "Time Integracao",
}
MODULO_CATEGORIA = {
    "MM": "SAP MM", "PP": "SAP PP", "QM": "SAP QM", "WM": "SAP WM",
    "MES": "Integracao/MES",
}

# ----- Palavras-chave para detecção automática de módulo -----
PALAVRAS_CHAVE = {
    "MM": ["pedido", "compra", "migo", "miro", "mrbr", "estoque", "fatura", "material",
           "fornecedor", "me21n", "me29n", "me59n", "requisicao", "requisição", "contrato",
           "consignacao", "consignação", "subcontrat", "mm17", "inventario", "inventário",
           "registro info", "mmbe", "mb52"],
    "PP": ["ordem de producao", "ordem de produção", "co11n", "co01", "mrp", "backflush",
           "lista tecnica", "lista técnica", "bom", "producao", "produção", "md01", "md04"],
    "QM": ["inspecao", "inspeção", "lote", "certificado", "qualidade", "qa32", "qa11",
           "decisao de uso", "decisão de uso"],
    "WM": ["deposito", "depósito", "transferencia", "transferência", "lt01", "lt12",
           "picking", "inventario wm", "reabastecimento", "li20"],
    "MES": ["opcenter", "pas-x", "pasx", "idoc", "integracao", "integração", "mes",
            "middleware", "status 51", "replica", "bd87", "smq1", "smq2"],
}


def detectar_modulo(texto: str) -> str:
    """Detecta o módulo (MM/PP/QM/WM/MES) a partir do texto do problema."""
    t = (texto or "").lower()
    pontuacao = {mod: 0 for mod in PALAVRAS_CHAVE}
    for mod, palavras in PALAVRAS_CHAVE.items():
        for p in palavras:
            if p in t:
                pontuacao[mod] += 1
    melhor = max(pontuacao, key=pontuacao.get)
    return melhor if pontuacao[melhor] > 0 else "MM"


def detectar_ferramenta(modulo: str) -> str:
    """MES -> ferramenta MES; demais módulos SAP -> ferramenta SAP."""
    return "MES" if modulo == "MES" else "SAP"


def analisar(descricao: str) -> dict:
    """
    Pré-analisa o problema SEM criar o chamado: sugere ferramenta, módulo,
    categoria e responsável. Útil para o agente confirmar antes de registrar.
    """
    modulo = detectar_modulo(descricao)
    return {
        "modulo": modulo,
        "ferramenta": detectar_ferramenta(modulo),
        "categoria": MODULO_CATEGORIA.get(modulo, "SAP MM"),
        "responsavel": MODULO_RESPONSAVEL.get(modulo, "Time MM"),
    }


@dataclass
class Ticket:
    descricao: str
    modulo: Optional[str] = None
    ferramenta: Optional[str] = None
    sistema: str = "S/4HANA"
    prioridade: str = "P3"
    titulo: Optional[str] = None
    categoria: Optional[str] = None
    id_chamado: Optional[str] = None
    data_abertura: str = field(default_factory=lambda: dt.date.today().isoformat())
    status: str = "Aberto"
    responsavel: Optional[str] = None
    sla_horas: Optional[int] = None
    ferramenta_registro: str = "ServiceToday"
    origem: str = "Agente IA"

    def preencher_derivados(self):
        if self.modulo is None:
            self.modulo = detectar_modulo(self.descricao)
        if self.ferramenta is None:
            self.ferramenta = detectar_ferramenta(self.modulo)
        if self.categoria is None:
            self.categoria = MODULO_CATEGORIA.get(self.modulo, "SAP MM")
        if self.responsavel is None:
            self.responsavel = MODULO_RESPONSAVEL.get(self.modulo, "Time MM")
        if self.sla_horas is None:
            self.sla_horas = PRIORIDADE_SLA.get(self.prioridade, 16)
        if self.titulo is None:
            self.titulo = self.descricao[:60]
        return self


def _proximo_id(xlsx_path: str) -> str:
    """Lê a base e devolve o próximo ID sequencial único (nunca colide)."""
    if not os.path.exists(xlsx_path):
        return f"{ID_PREFIX}{1:0{ID_WIDTH}d}"
    df = pd.read_excel(xlsx_path, sheet_name=SHEET, dtype=str)
    nums = []
    for val in df["ID Chamado"].dropna():
        m = re.match(rf"{ID_PREFIX}(\d+)", str(val).strip())
        if m:
            nums.append(int(m.group(1)))
    proximo = (max(nums) + 1) if nums else 1
    return f"{ID_PREFIX}{proximo:0{ID_WIDTH}d}"


def create_ticket(ticket: Ticket, xlsx_path: str = DEFAULT_XLSX,
                  confirmado: bool = False) -> dict:
    """
    Cria o chamado e grava na base (planilha).
    Só executa se confirmado=True (o agente passa True após o 'sim' do usuário).
    """
    if not confirmado:
        return {
            "status": "aguardando_confirmacao",
            "mensagem": ("Deseja que eu registre um chamado? Se sim, para qual "
                         "ferramenta: SAP ou MES?"),
        }

    ticket.preencher_derivados()
    ticket.id_chamado = _proximo_id(xlsx_path)

    nova_linha = [
        ticket.id_chamado, ticket.data_abertura, ticket.modulo, ticket.sistema,
        ticket.categoria, ticket.titulo, ticket.descricao,
        PRIORIDADE_LABEL.get(ticket.prioridade, ticket.prioridade),
        ticket.status, ticket.responsavel, ticket.sla_horas,
        ticket.ferramenta_registro, ticket.origem,
    ]

    wb = load_workbook(xlsx_path)
    ws = wb[SHEET]
    ws.append(nova_linha)
    wb.save(xlsx_path)

    return {
        "status": "criado",
        "id_chamado": ticket.id_chamado,
        "mensagem": (f"Pronto! Registrei o chamado {ticket.id_chamado} no ServiceToday.\n"
                     f"- Ferramenta: {ticket.ferramenta}\n"
                     f"- Modulo/Categoria: {ticket.modulo} ({ticket.categoria})\n"
                     f"- Prioridade: {PRIORIDADE_LABEL.get(ticket.prioridade)}\n"
                     f"- SLA: {ticket.sla_horas}h\n"
                     f"- Responsavel: {ticket.responsavel}\n"
                     f"Use esse numero para acompanhamento."),
        "ticket": asdict(ticket),
    }


if __name__ == "__main__":
    desc = "Erro ao liberar pedido de compra na ME29N, estrategia nao encontrada."
    print("Análise:", analisar(desc))
    t = Ticket(descricao=desc, prioridade="P2")
    print(create_ticket(t, confirmado=True)["mensagem"])
