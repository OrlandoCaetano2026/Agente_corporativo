# -*- coding: utf-8 -*-
"""
ticket_service.py
-----------------
Serviço de criação de chamados (tickets) do agente Orla_Tech Consultoria.

Comportamento:
- O agente só chama create_ticket() APÓS o usuário confirmar explicitamente.
- O número do chamado é sequencial e único: pega o maior ID já existente na base
  e incrementa (+1), garantindo que nunca colida com os chamados atuais.
- Persiste o novo chamado na planilha (Excel) e também pode ser exposto via API
  REST (api.py), o que facilita o deploy no OCI.

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

PRIORIDADE_SLA = {"Alta": 8, "Media": 16, "Média": 16, "Baixa": 24}
CATEGORIA_RESPONSAVEL = {
    "SAP MM": "Time MM", "SAP PP": "Time PP", "SAP QM": "Time QM",
    "SAP WM": "Time WM", "Integracao/MES": "Time Integracao",
    "Integração/MES": "Time Integracao", "Basis": "Time Basis",
}


@dataclass
class Ticket:
    modulo: str
    sistema: str
    categoria: str
    titulo: str
    descricao: str
    prioridade: str = "Media"
    id_chamado: Optional[str] = None
    data_abertura: str = field(default_factory=lambda: dt.date.today().isoformat())
    status: str = "Aberto"
    responsavel: Optional[str] = None
    sla_horas: Optional[int] = None
    ferramenta: str = "ServiceToday"
    origem: str = "Agente IA"

    def preencher_derivados(self):
        if self.responsavel is None:
            self.responsavel = CATEGORIA_RESPONSAVEL.get(self.categoria, "Time MM")
        if self.sla_horas is None:
            self.sla_horas = PRIORIDADE_SLA.get(self.prioridade, 16)
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
    Só executa se confirmado=True (o agente passa True somente após o 'sim' do usuário).
    """
    if not confirmado:
        return {
            "status": "aguardando_confirmacao",
            "mensagem": ("Não encontrei essa informação na base de conhecimento e "
                         "ela precisa de validação humana. Deseja que eu abra um "
                         "chamado no ServiceToday? (sim/não)"),
        }

    ticket.preencher_derivados()
    ticket.id_chamado = _proximo_id(xlsx_path)

    nova_linha = [
        ticket.id_chamado, ticket.data_abertura, ticket.modulo, ticket.sistema,
        ticket.categoria, ticket.titulo, ticket.descricao, ticket.prioridade,
        ticket.status, ticket.responsavel, ticket.sla_horas, ticket.ferramenta,
        ticket.origem,
    ]

    wb = load_workbook(xlsx_path)
    ws = wb[SHEET]
    ws.append(nova_linha)
    wb.save(xlsx_path)

    return {
        "status": "criado",
        "id_chamado": ticket.id_chamado,
        "mensagem": (f"Pronto! Abri o chamado {ticket.id_chamado} no ServiceToday "
                     f"(categoria {ticket.categoria}, prioridade {ticket.prioridade}, "
                     f"SLA {ticket.sla_horas}h). Use esse número para acompanhamento."),
        "ticket": asdict(ticket),
    }


if __name__ == "__main__":
    t = Ticket(modulo="MM", sistema="S/4HANA", categoria="SAP MM",
               titulo="Erro X nao documentado na base",
               descricao="Usuario relata erro nao encontrado na base de conhecimento.",
               prioridade="Alta")
    print("1) Sem confirmacao:", create_ticket(t, confirmado=False)["status"])
    print("2) Com confirmacao:", create_ticket(t, confirmado=True)["mensagem"])
