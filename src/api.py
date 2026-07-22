# -*- coding: utf-8 -*-
"""
api.py
------
API REST (FastAPI) que expõe o serviço de chamados do agente Orla_Tech.
Esta é a camada que roda no OCI (ex.: OCI Compute, Container Instances ou OKE).

Endpoints:
  GET  /health           -> verificação de saúde (health check p/ o OCI)
  GET  /tickets          -> lista os chamados da base
  POST /tickets          -> cria um chamado (requer confirmado=true)
  GET  /tickets/next-id  -> mostra qual seria o próximo ID sequencial

Executar localmente:
  uvicorn src.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd

from ticket_service import Ticket, create_ticket, _proximo_id, DEFAULT_XLSX, SHEET

app = FastAPI(
    title="Orla_Tech - API de Chamados SAP",
    description="Serviço de criação de chamados do agente corporativo (ServiceToday).",
    version="1.0.0",
)


class TicketIn(BaseModel):
    modulo: str
    sistema: str
    categoria: str
    titulo: str
    descricao: str
    prioridade: str = "Media"
    confirmado: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "servico": "orla-tech-chamados"}


@app.get("/tickets/next-id")
def next_id():
    return {"proximo_id": _proximo_id(DEFAULT_XLSX)}


@app.get("/tickets")
def listar():
    try:
        df = pd.read_excel(DEFAULT_XLSX, sheet_name=SHEET, dtype=str).fillna("")
        return {"total": len(df), "chamados": df.to_dict(orient="records")}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Base de chamados não encontrada.")


@app.post("/tickets")
def criar(payload: TicketIn):
    t = Ticket(
        modulo=payload.modulo, sistema=payload.sistema, categoria=payload.categoria,
        titulo=payload.titulo, descricao=payload.descricao, prioridade=payload.prioridade,
    )
    return create_ticket(t, confirmado=payload.confirmado)
