# ☁️ Guia de Deploy no OCI (Oracle Cloud) — sem Docker

Este guia mostra como publicar o **Agente de Suporte SAP da Orla_Tech** na nuvem
Oracle (OCI) usando **apenas Python** — sem necessidade de Docker, o que é ideal
para quem não pode instalar Docker no computador corporativo.

> ✅ O requisito do desafio (usar **pelo menos um serviço OCI**) é atendido com uma
> **VM Compute (Always Free)**. Opcionalmente, o **Object Storage** guarda os documentos.

---

## 🎯 Visão geral

```
[Seu navegador]  ──HTTP──►  [VM OCI Compute]  ──►  Streamlit (porta 8501)
                                    │
                                    └── Python + RAG + base de documentos
```

---

## Passo 1 — Criar conta e VM no OCI

1. Crie uma conta em **oracle.com/cloud/free** (tier *Always Free*).
2. No console OCI: **Menu → Compute → Instances → Create Instance**.
3. Configurações recomendadas (Always Free):
   - **Image:** Canonical Ubuntu 22.04
   - **Shape:** `VM.Standard.E2.1.Micro` (Always Free) ou `A1.Flex` (ARM, também free)
4. Em **Add SSH keys**, gere/baixe a chave SSH (guarde o arquivo `.key`).
5. Anote o **IP público** da instância após criada.

## Passo 2 — Liberar a porta 8501 (firewall do OCI)

1. Na VNIC da instância → **Subnet → Security List → Add Ingress Rules**.
2. Adicione a regra:
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** TCP
   - **Destination Port Range:** `8501`

## Passo 3 — Conectar na VM via SSH

```bash
ssh -i sua-chave.key ubuntu@SEU_IP_PUBLICO
```

## Passo 4 — Instalar Python e dependências

```bash
# Atualiza o sistema
sudo apt update && sudo apt install -y python3-pip python3-venv git

# Clona o repositório
git clone https://github.com/OrlandoCaetano2026/Agente_corporativo.git
cd Agente_corporativo

# Cria e ativa um ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instala as dependências
pip install -r requirements.txt
```

## Passo 5 — Configurar a chave da LLM

```bash
# Chave da Groq (ou outra LLM configurada)
export GROQ_API_KEY="sua-chave-aqui"
```

> 💡 Para tornar permanente, adicione a linha no final do arquivo `~/.bashrc`.

## Passo 6 — Abrir a porta no firewall do Ubuntu

```bash
sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT
```

## Passo 7 — Rodar o agente

```bash
# Deixa rodando mesmo após fechar o SSH (nohup)
nohup streamlit run app/main.py \
    --server.port=8501 --server.address=0.0.0.0 --server.headless=true &
```

## Passo 8 — Acessar

Abra no navegador:

```
http://SEU_IP_PUBLICO:8501
```

🎉 O agente estará rodando na nuvem Oracle!

---

## 📸 Registrar a execução (Passo 9 do desafio)

O desafio exige uma **imagem ou vídeo** do agente rodando na nuvem, dentro do README:

1. Acesse `http://SEU_IP_PUBLICO:8501` e faça uma pergunta ao agente.
2. Tire um **print** (incluindo a barra de endereço com o IP público visível) ou grave um **vídeo** curto.
3. Salve em `assets/` (ex.: `assets/demo_oci.png`).
4. O README já referencia essa imagem na seção "Deploy em nuvem".

---

## 🗄️ (Opcional) Usar OCI Object Storage

Para hospedar os documentos e a imagem do fluxo com URL pública:

1. **Menu → Storage → Buckets → Create Bucket** (ex.: `orla-tech-docs`).
2. Faça upload dos arquivos de `data/documentos/`.
3. Em cada objeto → **Create Pre-Authenticated Request** para gerar uma URL HTTP pública.
4. Use essa URL como a "imagem via HTTP" exigida no desafio.

---

## 🔧 Dicas de manutenção

- **Ver logs:** `cat nohup.out`
- **Parar o agente:** `pkill -f streamlit`
- **Atualizar o código:** `git pull` e reinicie o Streamlit
- **Rodar a API (em vez da UI):** `uvicorn src.api:app --host 0.0.0.0 --port 8000`
